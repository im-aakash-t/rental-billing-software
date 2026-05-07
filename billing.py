# billing.py - FULLY REFINED VERSION (With Name in Address)
import os
import sqlite3
import webbrowser
import textwrap
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from bill_number import generate_next_bill_no
from utils import safe_float, safe_int, sync_lists, validate_phone, validate_date, validate_time, sanitize_sql_input
from materials import get_material_by_code

REPORTS_DIR = "reports"

class BillingError(Exception):
    """Custom exception for billing operations"""
    pass

def calculate_due_amount(rents, rental_days, quantities=None, returned_quantities=None, amount_paid=0.0):
    """Calculate due amount with comprehensive validation."""
    try:
        if isinstance(rents, str):
            rents = [safe_float(x) for x in rents.split(',') if x]
        if quantities is None:
            quantities = [1] * len(rents)
        elif isinstance(quantities, str):
            quantities = [safe_int(x) for x in quantities.split(',') if x]
            
        if returned_quantities is None or returned_quantities == []:
            total = 0
            for r, q in zip(rents, quantities):
                total += safe_float(r) * safe_int(q) * safe_int(rental_days, 1)
            return total

        if isinstance(returned_quantities, str):
            returned_quantities = [safe_int(x) for x in returned_quantities.split(',') if x]

        rents, quantities, returned_quantities = sync_lists(rents, quantities, returned_quantities, pad_value=0)

        effective_quantities = [max(q - rq, 0) for q, rq in zip(quantities, returned_quantities)]

        if all(q == 0 for q in effective_quantities):
            return 0

        total = 0
        for r, q in zip(rents, effective_quantities):
            total += safe_float(r) * safe_int(q) * safe_int(rental_days, 1)

        return total
    except Exception as e:
        raise BillingError(f"Due amount calculation failed: {e}")

def validate_form(data):
    """Enhanced form validation with detailed error messages."""
    errors = []
    
    if not data.get('name', '').strip():
        errors.append("Customer name is required")
    elif len(data['name'].strip()) < 2:
        errors.append("Customer name must be at least 2 characters")
    
    phone = data.get('phone', '').strip()
    is_valid_phone, phone_error = validate_phone(phone)
    if not is_valid_phone:
        errors.append(phone_error)
    
    machines = [m.strip() for m in data['machines'] if m.strip()]
    if not any(machines):
        errors.append("At least one machine is required")
    
    try:
        total = safe_float(data['total'])
        advance = safe_float(data['advance'])
        
        if total < 0:
            errors.append("Total amount cannot be negative")
        if advance < 0:
            errors.append("Advance amount cannot be negative")
            
    except ValueError:
        errors.append("Total and Advance must be valid numbers")
    
    date = data.get('date', '').strip()
    is_valid_date, date_error = validate_date(date)
    if not is_valid_date:
        errors.append(date_error)
    
    time = data.get('time', '').strip()
    is_valid_time, time_error = validate_time(time)
    if not is_valid_time:
        errors.append(time_error)
    
    if errors:
        return False, " | ".join(errors)
    return True, "Valid"

def save_form_data(data, db):
    """Save form data using the new rental_items table."""
    conn = db.get_connection()
    conn.execute("BEGIN TRANSACTION")
    try:
        c = conn.cursor()
        bill_no = generate_next_bill_no(db)
        sanitized = {k: sanitize_sql_input(v) for k, v in data.items()}
        
        c.execute("""
            INSERT INTO rentals (
                bill_no, name, phone, phone2, address, id_proof,
                total, advance, date, time, vehicle, payment_mode, cashier_name,
                machine_codes, machines, rents, quantities 
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '')
        """, (
            bill_no,
            sanitized.get("name", ""),
            sanitized.get("phone", ""),
            sanitized.get("phone2", ""),
            sanitized.get("address", ""),
            sanitized.get("id_proof", ""),
            sanitized.get("total", "0"),
            sanitized.get("advance", "0"),
            sanitized.get("date", ""),
            sanitized.get("time", ""),
            sanitized.get("vehicle", ""),
            sanitized.get("payment_mode", "Cash"),
            sanitized.get("cashier_name", "") 
        ))
        
        rental_id = c.lastrowid
        
        codes = data.get('machine_codes', [])
        names = data.get('machines', [])
        rents = data.get('rents', [])
        qtys = data.get('quantities', [])
        
        for i in range(len(names)):
            qty = safe_int(qtys[i] if i < len(qtys) else 0)
            if qty <= 0: continue
            
            code = codes[i] if i < len(codes) else ""
            name = names[i] if i < len(names) else "Unknown"
            
            total_line_price = safe_float(rents[i] if i < len(rents) else 0)
            unit_price = total_line_price / qty if qty > 0 else 0
            
            c.execute("""
                INSERT INTO rental_items (rental_id, machine_code, machine_name, quantity, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (rental_id, code, name, qty, unit_price, total_line_price))

        conn.commit()
        return bill_no
    except Exception as e:
        conn.rollback()
        raise BillingError(f"Failed to save form data: {e}")

def update_form_data(data, db):
    """Update form data by replacing items in rental_items."""
    conn = db.get_connection()
    conn.execute("BEGIN TRANSACTION")
    try:
        c = conn.cursor()
        sanitized = {k: sanitize_sql_input(v) for k, v in data.items()}
        rental_id = data['id']
        
        c.execute("""
            UPDATE rentals SET 
                name=?, phone=?, phone2=?, address=?, id_proof=?, 
                total=?, advance=?, date=?, time=?, vehicle=?, payment_mode=?, cashier_name=?
            WHERE id=?
        """, (
            sanitized.get('name', ''), 
            sanitized.get('phone', ''), 
            sanitized.get('phone2', ""), 
            sanitized.get('address', ""), 
            sanitized.get('id_proof', ""),
            sanitized.get('total', '0'), 
            sanitized.get('advance', '0'), 
            sanitized.get('date', ''), 
            sanitized.get('time', ''),
            sanitized.get('vehicle', ""), 
            sanitized.get('payment_mode', "Cash"), 
            sanitized.get("cashier_name", ""), 
            rental_id
        ))
        
        c.execute("DELETE FROM rental_items WHERE rental_id=?", (rental_id,))
        
        codes = data.get('machine_codes', [])
        names = data.get('machines', [])
        rents = data.get('rents', [])
        qtys = data.get('quantities', [])
        
        for i in range(len(names)):
            qty = safe_int(qtys[i] if i < len(qtys) else 0)
            if qty <= 0: continue
            
            code = codes[i] if i < len(codes) else ""
            name = names[i] if i < len(names) else "Unknown"
            total_line_price = safe_float(rents[i] if i < len(rents) else 0)
            unit_price = total_line_price / qty if qty > 0 else 0
            
            c.execute("""
                INSERT INTO rental_items (rental_id, machine_code, machine_name, quantity, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (rental_id, code, name, qty, unit_price, total_line_price))

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise BillingError(f"Failed to update form data: {e}")

def load_all_records(db, limit=1000):
    """Load records (Headers only)."""
    conn = db.get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT * FROM rentals 
            WHERE cancelled IS NULL OR cancelled = 0 
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        raise BillingError(f"Failed to load records: {e}")

def get_record_by_id(identifier, db):
    """Get record header by ID or Bill No."""
    conn = db.get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM rentals WHERE bill_no = ?", (identifier,))
        row = c.fetchone()
        if not row:
            try:
                rental_id = safe_int(identifier)
                c.execute("SELECT * FROM rentals WHERE id = ?", (rental_id,))
                row = c.fetchone()
            except ValueError: return None
        return dict(row) if row else None
    except Exception as e:
        raise BillingError(f"Failed to get record: {e}")

def generate_bill(bill_no, date, time, address, phone, items, qty, rent, total, advance, 
                  rental_days=1, background_path="bill-layout.jpg", output_pdf=None,
                  return_date=None, return_time=None, vehicle="", name="", payment_mode=""):
    """Generate bill PDF with perfectly aligned coordinates."""
    try:
        if output_pdf is None:
            output_pdf = os.path.join(REPORTS_DIR, f"{bill_no}.pdf")
        os.makedirs(REPORTS_DIR, exist_ok=True)

        c = canvas.Canvas(output_pdf, pagesize=A4)
        width, height = A4

        if not os.path.exists(background_path):
            raise BillingError(f"Background image not found: {background_path}")

        c.drawImage(background_path, 0, 0, width=width, height=height)
        c.setFont("Helvetica", 12)

        # --- HEADER ALIGNMENT ---
        c.drawString(110, height - 215, str(bill_no))
        c.drawString(450, height - 215, str(date))
        c.drawString(450, height - 248, str(time))

        # --- NEW: NAME & ADDRESS ALIGNMENT ---
        address_lines = []
        if name:
            address_lines.append(str(name)) # Name becomes Line 1
            
        for para in str(address).split('\n'):
            address_lines.extend(textwrap.wrap(para, width=55))

        start_y = height - 280
        line_height = 27
        for i, line in enumerate(address_lines):
            if i > 4: break # Increased to 4 to allow room for the Name + Address
            c.drawString(110, start_y - i*line_height, line.strip())

        # --- PHONE & VEHICLE ALIGNMENT ---
        c.drawString(130, height - 384, str(phone))
        if vehicle:
            c.drawString(400, height - 384, f"{vehicle}") 

        # --- ITEMS TABLE ALIGNMENT ---
        y = height - 460 # Start height for the first item
        
        target_len = max(len(items), len(qty), len(rent))
        items += [""] * (target_len - len(items))
        qty += [0] * (target_len - len(qty))
        rent += [0.0] * (target_len - len(rent))
        
        for i in range(len(items)):
            item_name = str(items[i]).strip()
            if len(item_name) <= 1 and qty[i] <= 0:
                continue
            if not item_name: continue

            # Truncate long names to prevent overlap
            display_name = (item_name[:28] + '..') if len(item_name) > 30 else item_name

            c.drawString(75, y, str(i + 1))                                # S.No
            c.drawString(110, y, display_name)                             # Item Name
            c.drawString(300, y, str(qty[i]))                              # Quantity
            c.drawString(360, y, str(int(safe_float(rent[i]))))            # Rent/Amount
            y -= 25 # Spacing between rows

        # --- TOTALS ALIGNMENT ---
        c.drawString(410, y - 20, f"Rs.{int(safe_float(total))}")   # Total
        c.drawString(480, y - 20, f"Rs.{int(safe_float(advance))}") # Advance
        
        if payment_mode:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(480, y - 5, f"{str(payment_mode).upper()}:")
            c.setFont("Helvetica", 12)

        # --- RETURN DATES ALIGNMENT ---
        if return_date and return_time:
            c.setFont("Helvetica", 10)
            c.drawString(180, 85, f"{return_date}")
            c.drawString(130, 65, f"{return_time}")

        c.save()
        try:
            webbrowser.open_new(os.path.abspath(output_pdf))
        except Exception as e:
            print(f"[INFO] Could not open PDF automatically: {e}")
        return output_pdf
    except Exception as e:
        raise BillingError(f"Failed to generate bill PDF: {e}")

def print_bill_from_record(record, db_conn=None):
    """
    Print bill from record, fetching items accurately from rental_items.
    Requires a database connection (db_conn) to fetch items.
    """
    try:
        bill_no = record.get("bill_no") or record.get("id")
        name = record.get("name", "") # <--- GET NAME
        date = record.get("date", "")
        time = record.get("time", "")
        address = record.get("address", "")
        phone = record.get("phone", "")
        vehicle = record.get("vehicle", "")
        
        clean_items = []
        clean_qtys = []
        clean_rents = []
        
        # 1. Try to fetch from rental_items (The Correct Way)
        if db_conn:
            try:
                c = db_conn.cursor()
                c.execute("""
                    SELECT machine_name, quantity, total_price 
                    FROM rental_items 
                    WHERE rental_id = ?
                """, (record['id'],))
                rows = c.fetchall()
                for row in rows:
                    clean_items.append(row[0])
                    clean_qtys.append(row[1])
                    clean_rents.append(row[2])
            except Exception as e:
                print(f"[WARN] Failed to fetch rental_items: {e}")

        # 2. Fallback: If DB fetch failed or returned nothing (Legacy Record), use CSV
        if not clean_items and record.get("machines"):
            def clean_split(d):
                if not d: return []
                s = str(d).replace('[','').replace(']','').replace("'",'').replace('"','')
                return [x.strip() for x in s.split(',') if x.strip()]
            
            clean_items = clean_split(record.get("machines", ""))
            clean_qtys = [safe_int(q) for q in clean_split(record.get("quantities", "0"))]
            clean_rents = [0.0] * len(clean_items) 

        total = safe_float(record.get("total", "0"))
        advance = record.get("advance", "0")
        payment_mode = record.get("payment_mode", "Cash")

        generate_bill(
            bill_no, date, time, address, phone, 
            items=clean_items, 
            qty=clean_qtys, 
            rent=clean_rents, 
            total=total, 
            advance=advance,
            vehicle=vehicle,
            name=name, # <--- PASS NAME
            payment_mode=payment_mode
        )

    except Exception as e:
        raise BillingError(f"Failed to print bill from record: {e}")

def fetch_and_print_bill(db_path, rental_id):
    """Fetch and print bill connecting directly."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT * FROM rentals WHERE id = ?", (rental_id,))
        row = c.fetchone()
        
        if row:
            print_bill_from_record(dict(row), db_conn=conn)
        else:
            print(f"[ERROR] Rental ID {rental_id} not found.")
            
        conn.close()
    except Exception as e:
        print(f"[ERROR] Failed to fetch and print bill: {e}")

def get_customer_credit(phone, db):
    conn = db.get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT COALESCE(SUM(balance), 0) FROM returns
            WHERE rental_id IN (
                SELECT id FROM rentals WHERE phone = ?
            )
        """, (phone,))
        credit = c.fetchone()[0]
        return safe_float(credit)
    except Exception as e:
        raise BillingError(f"get_customer_credit failed: {e}")

def has_return_entry(rental_id, db):
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance, returned_items, returned_quantities FROM returns WHERE rental_id = ?", (rental_id,))
        row = cursor.fetchone()
        if not row: return False
        if safe_float(row[0]) > 0: return False
        return True
    except Exception as e:
        raise BillingError(f"has_return_entry failed: {e}")

def has_pending_returns(phone, db):
    conn = db.get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT COUNT(*) FROM rentals r
            WHERE r.phone = ?
              AND (r.cancelled IS NULL OR r.cancelled = 0)
              AND r.id NOT IN (SELECT rental_id FROM returns)
        """, (phone,))
        count = c.fetchone()[0]
        return count > 0
    except Exception as e:
        raise BillingError(f"has_pending_returns failed: {e}")

def cancel_rental(rental_id, db):
    conn = db.get_connection()
    conn.execute("BEGIN TRANSACTION")
    try:
        c = conn.cursor()
        c.execute("UPDATE rentals SET cancelled = 1 WHERE id = ?", (rental_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise BillingError(f"Failed to cancel rental: {e}")