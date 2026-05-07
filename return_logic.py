# return_logic.py - REFINED VERSION (Fixed Past Due Cross-Collateralization & Blank Saving)
import os
import sqlite3
import logging
import webbrowser
from math import ceil
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from bill_number import generate_next_bill_no
from utils import calculate_rental_days_unified, log_error, safe_float, safe_int, sync_lists
from materials import get_material_by_code

logger = logging.getLogger(__name__)

def get_full_rental_details(db, rental_id):
    conn = db.get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM rentals WHERE id = ?", (rental_id,))
        row_obj = c.fetchone()
        if not row_obj: return None
        
        row = dict(row_obj)
        saved_total = safe_float(row.get("total", 0))
        
        c.execute("""
            SELECT machine_code, machine_name, quantity, total_price 
            FROM rental_items 
            WHERE rental_id = ? 
            ORDER BY id ASC
        """, (rental_id,))
        items = c.fetchall()
        
        clean_machines, clean_codes, clean_quantities, clean_rents = [], [], [], []
        calculated_standard_total = 0.0
        
        for item in items:
            code, name, qty, line_total = item
            clean_codes.append(code if code else "")
            clean_machines.append(name)
            clean_quantities.append(qty)
            calculated_standard_total += line_total
            clean_rents.append(line_total)

        factor = 1.0
        if calculated_standard_total > 0 and saved_total > 0:
            if abs(calculated_standard_total - saved_total) > 1.0:
                factor = saved_total / calculated_standard_total

        final_rents = [r * factor for r in clean_rents]

        return {
            "id": row["id"], "name": row["name"], "phone": row["phone"],
            "phone2": row.get("phone2", ""), "address": row.get("address", ""),
            "id_proof": row.get("id_proof", ""), "date": row["date"], "time": row["time"],
            "vehicle": row.get("vehicle", ""), "advance": safe_float(row.get("advance", 0)),
            "machines": clean_machines, "machine_codes": clean_codes,
            "quantities": clean_quantities, "rents": final_rents,
            "payment_mode": row.get("payment_mode", "Cash"), "total": saved_total,
        }
    except Exception as e:
        log_error(f"get_full_rental_details ID {rental_id}", e)
        return None

def split_rental_bill(db, rental_id, quantities_to_return):
    conn = db.get_connection()
    conn.execute("BEGIN TRANSACTION")
    try:
        c = conn.cursor()
        data = get_full_rental_details(db, rental_id)
        if not data: raise ValueError("Original rental not found")

        c.execute("SELECT id, quantity, unit_price FROM rental_items WHERE rental_id=? ORDER BY id ASC", (rental_id,))
        db_items = c.fetchall()
        
        total_items = len(data['machines'])
        if len(quantities_to_return) < total_items:
             quantities_to_return += [0] * (total_items - len(quantities_to_return))
        
        move_items = []
        total_rent_value_moving = 0.0
        total_rent_value_original = data['total']
        
        for i in range(total_items):
            original_qty = data['quantities'][i]
            returning_qty = quantities_to_return[i]
            remaining_qty = max(0, original_qty - returning_qty)
            
            effective_unit_price = data['rents'][i] / original_qty if original_qty > 0 else 0
            
            if remaining_qty > 0:
                line_total = effective_unit_price * remaining_qty
                move_items.append({
                    "code": data['machine_codes'][i], "name": data['machines'][i],
                    "qty": remaining_qty, "unit": effective_unit_price, "total": line_total
                })
                total_rent_value_moving += line_total
            
            if i < len(db_items):
                db_item_id = db_items[i][0]
                if returning_qty > 0:
                    new_line_total = db_items[i][2] * returning_qty
                    c.execute("UPDATE rental_items SET quantity=?, total_price=? WHERE id=?", 
                              (returning_qty, new_line_total, db_item_id))
                else:
                    c.execute("DELETE FROM rental_items WHERE id=?", (db_item_id,))

        ratio = total_rent_value_moving / total_rent_value_original if total_rent_value_original > 0 else 0
        advance_to_move = safe_float(data['advance']) * ratio
        advance_to_keep = safe_float(data['advance']) - advance_to_move
        
        total_keep = total_rent_value_original - total_rent_value_moving
        new_bill_no = generate_next_bill_no(db)
        
        c.execute("""
            INSERT INTO rentals (
                bill_no, name, phone, phone2, address, id_proof,
                total, advance, date, time, vehicle, payment_mode,
                machine_codes, machines, rents, quantities 
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '')
        """, (
            new_bill_no, data['name'], data['phone'], data.get('phone2', ''), 
            data.get('address', ''), data.get('id_proof', ''),
            total_rent_value_moving, advance_to_move,
            data['date'], data['time'], data['vehicle'], data['payment_mode']
        ))
        
        new_rental_id = c.lastrowid
        
        for item in move_items:
            c.execute("""
                INSERT INTO rental_items (rental_id, machine_code, machine_name, quantity, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (new_rental_id, item['code'], item['name'], item['qty'], item['unit'], item['total']))
            
        c.execute("UPDATE rentals SET total=?, advance=? WHERE id=?", (total_keep, advance_to_keep, rental_id))
        c.execute("DELETE FROM returns WHERE rental_id=?", (rental_id,))
        
        conn.commit()
        return new_bill_no
    except Exception as e:
        conn.rollback()
        raise e

def get_total_past_dues(db, phone, current_rental_id):
    if not phone: return 0.0
    try:
        conn = db.get_connection()
        c = conn.cursor()
        
        query_closed = """
            SELECT COALESCE(SUM(ret.balance), 0)
            FROM returns ret
            JOIN rentals r ON ret.rental_id = r.id
            WHERE r.phone = ? AND (r.cancelled IS NULL OR r.cancelled = 0)
        """
        params_closed = [phone]
        if current_rental_id:
             query_closed += " AND r.id != ?"
             params_closed.append(current_rental_id)
        
        c.execute(query_closed, params_closed)
        closed_debt = safe_float(c.fetchone()[0])
        
        return closed_debt
    except Exception as e:
        return 0.0

def get_customer_history(db, keyword):
    try:
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        like_kw = f"%{keyword}%"
        c.execute("""
            SELECT r.bill_no, r.id, r.name, r.phone, r.date, r.total,
                   r.advance, r.payment_mode AS adv_mode,
                   ret.return_date, ret.amount_paid, ret.refund, ret.payment_mode AS paid_mode,
                   r.cancelled, ret.balance
            FROM rentals r
            LEFT JOIN returns ret ON r.id = ret.rental_id
            WHERE r.name LIKE ? OR r.phone LIKE ?
            ORDER BY r.id DESC
        """, (like_kw, like_kw))
        return c.fetchall()
    except Exception as e: return []

def calculate_rental_days(start_date, start_time, return_date, return_time):
    return calculate_rental_days_unified(start_date, start_time, return_date, return_time)

def save_return_data(db, rental_id, return_date, return_time, rental_days, due_amount, deduction, damage, balance, amount_paid, returned_items, returned_quantities, payment_mode, refund=0):
    try:
        # CRITICAL FIX: Cast ALL inputs to floats so SQLite never silently rejects empty blank boxes
        due_amount = safe_float(due_amount)
        deduction = safe_float(deduction)
        damage = safe_float(damage)
        balance = safe_float(balance)
        amount_paid = safe_float(amount_paid)
        refund = safe_float(refund)
        rental_days = safe_int(rental_days)

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM returns WHERE rental_id = ?", (rental_id,))
        if c.fetchone():
            c.execute("""
                UPDATE returns SET
                    return_date=?, return_time=?, rental_days=?, due_amount=?,
                    deduction=?, damage=?, balance=?, amount_paid=?, refund=?,
                    returned_items=?, returned_quantities=?, payment_mode=?
                WHERE rental_id=?
            """, (return_date, return_time, rental_days, due_amount, deduction, damage, balance, amount_paid, refund, returned_items, returned_quantities, payment_mode, rental_id))
        else:
            c.execute("""
                INSERT INTO returns (
                    rental_id, return_date, return_time, rental_days,
                    due_amount, deduction, damage, balance, amount_paid, refund,
                    returned_items, returned_quantities, payment_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rental_id, return_date, return_time, rental_days, due_amount, deduction, damage, balance, amount_paid, refund, returned_items, returned_quantities, payment_mode))
        conn.commit()
    except Exception as e: raise

def should_freeze_return_fields(rented_quantities, returned_quantities, balance, epsilon=0.01):
    try:
        rented = list(rented_quantities) if rented_quantities else []
        returned = list(returned_quantities) if returned_quantities else []
        rented += [0] * (max(len(rented), len(returned)) - len(rented))
        returned += [0] * (max(len(rented), len(returned)) - len(returned))
        return all(r == q for r, q in zip(returned, rented)) and abs(safe_float(balance)) < epsilon
    except: return False

def generate_return_pdf(*args, **kwargs): pass 

def save_installment(db, rental_id, amount, payment_mode, cashier_name, date_time):
    try:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO installments (rental_id, amount, payment_mode, cashier_name, date_time)
            VALUES (?, ?, ?, ?, ?)
        """, (rental_id, amount, payment_mode, cashier_name, date_time))
        conn.commit()
        return True
    except Exception as e: raise e

def get_installments(db, rental_id):
    try:
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM installments WHERE rental_id = ? ORDER BY id ASC", (rental_id,))
        return [dict(row) for row in c.fetchall()]
    except Exception as e: return []