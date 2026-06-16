# form_logic.py - REFINED VERSION (With Master Math Engine)
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
from customers_tab import sync_single_customer

# Use shared imports exclusively
from shared_imports import (
    calculate_rental_days_unified, safe_float, safe_int, log_error, callbacks,
    validate_form, save_form_data, update_form_data, load_all_records, get_record_by_id, 
    has_return_entry, has_pending_returns, generate_next_bill_no, get_material_by_code,
    calculate_master_balance # <-- Master Engine
)

from return_logic import get_total_past_dues

MAX_MACHINES_PER_BILL = 5

def clear_form_fields(vars_dict, address_text):
    try:
        for key in ["name", "phone", "phone2", "id_proof", "vehicle"]:
            vars_dict[key].set("")
        
        vars_dict["total"].set("0.00")
        vars_dict["advance"].set("")
        vars_dict["date"].set(datetime.now().strftime('%d-%m-%y'))
        vars_dict["time"].set(datetime.now().strftime('%I:%M %p'))
        vars_dict["payment_mode"].set("Cash")
        vars_dict["cashier_name"].set("") 
        
        if "balance_var" in vars_dict: vars_dict["balance_var"].set("0.00")
        if "past_due_var" in vars_dict: vars_dict["past_due_var"].set("0.00")
        
        try: vars_dict["bill_no"].set(generate_next_bill_no(vars_dict["db"]))
        except: vars_dict["bill_no"].set("A00001")
            
        vars_dict["mode"].set("new")
        vars_dict["record_id"].set("")
        
        address_text.delete("1.0", tk.END)
        
        for i in range(MAX_MACHINES_PER_BILL):
            vars_dict["machine_codes"][i].set("")
            vars_dict["machine_names"][i].set("")
            vars_dict["quantities"][i].set("")
            vars_dict["rents"][i].set("")
            
    except Exception as e: log_error("Form clearing", e)

def submit_form(vars_dict, address_text, db, clear_form_cb, load_table_cb):
    try:
        data = {
            "bill_no": vars_dict["bill_no"].get(), "mode": vars_dict["mode"].get(),
            "name": vars_dict["name"].get().strip(), "phone": vars_dict["phone"].get().strip(),
            "phone2": vars_dict["phone2"].get().strip(), "address": address_text.get("1.0", tk.END).strip(),
            "id_proof": vars_dict["id_proof"].get().strip(), "machines": [v.get().strip() for v in vars_dict["machine_names"]],
            "rents": [v.get().strip() for v in vars_dict["rents"]], "quantities": [v.get().strip() for v in vars_dict["quantities"]],
            "machine_codes": [v.get().strip() for v in vars_dict["machine_codes"]], "total": vars_dict["total"].get().strip(),
            "advance": vars_dict["advance"].get().strip(), "date": vars_dict["date"].get().strip(),
            "time": vars_dict["time"].get().strip(), "vehicle": vars_dict["vehicle"].get().strip(),
            "payment_mode": vars_dict["payment_mode"].get(), "cashier_name": vars_dict["cashier_name"].get().strip(), 
            "id": vars_dict["record_id"].get()
        }
        
        valid, msg = validate_form(data)
        if not valid:
            messagebox.showerror("Validation Error", msg)
            return False
        
        if data["mode"] == "edit":
            update_form_data(data, db)
            success_msg = "Data updated successfully."
        else:
            save_form_data(data, db)
            success_msg = "Data saved successfully."
        
        messagebox.showinfo("Success", success_msg)
        clear_form_cb()
        load_table_cb()
        callbacks.reload_all_tabs()
        sync_single_customer(db, data)
        return True
    except Exception as e:
        log_error("Form submission", e)
        return False

def calculate_balance_for_record(record_id, db):
    try:
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT date, time, advance, total FROM rentals WHERE id = ?", (record_id,))
        rental_row = c.fetchone()
        if not rental_row: return 0.0
        
        c.execute("SELECT SUM(amount) FROM installments WHERE rental_id = ?", (record_id,))
        inst_sum = c.fetchone()[0]
        total_inst = safe_float(inst_sum)
        
        c.execute("SELECT * FROM returns WHERE rental_id = ?", (record_id,))
        return_row = c.fetchone()
        
        if return_row:
            try: refund_val = safe_float(return_row['refund'])
            except: refund_val = 0.0
            
            # --- FIX: Passes return_row['due_amount'] as override so table matches forms ---
            _, net_balance = calculate_master_balance(
                daily_rent=rental_row['total'],
                rental_days=return_row['rental_days'],
                advance_paid=rental_row['advance'],
                installments_paid=total_inst,
                damage_charges=return_row['damage'],
                discount_deduction=return_row['deduction'],
                final_amount_paid=return_row['amount_paid'],
                refund_given=refund_val,
                is_returned=True,
                manual_due_override=return_row['due_amount'] 
            )
            return net_balance
        else:
            try: live_days = calculate_rental_days_unified(rental_row['date'], rental_row['time'])
            except: live_days = 1
                
            _, net_balance = calculate_master_balance(
                daily_rent=rental_row['total'],
                rental_days=live_days,
                advance_paid=rental_row['advance'],
                installments_paid=total_inst,
                is_returned=False
            )
            return net_balance
    except Exception as e:
        log_error(f"Balance calculation for {record_id}", e)
        return 0.0

def is_record_fully_returned(record_id, db):
    try:
        c = db.get_connection().cursor()
        c.execute("SELECT SUM(quantity) FROM rental_items WHERE rental_id=?", (record_id,))
        rented_total = safe_int(c.fetchone()[0])
        
        if rented_total == 0:
            c.execute("SELECT quantities FROM rentals WHERE id=?", (record_id,))
            r_row = c.fetchone()
            if r_row and r_row[0]:
                rented_total = sum(safe_int(x) for x in str(r_row[0]).replace('[','').replace(']','').replace("'",'').replace('"','').split(',') if x.strip())
                
        if rented_total == 0: return True 
            
        c.execute("SELECT returned_quantities FROM returns WHERE rental_id=?", (record_id,))
        ret_row = c.fetchone()
        if not ret_row or not ret_row[0]: return False 
            
        returned_total = sum(safe_int(x) for x in str(ret_row[0]).replace('[','').replace(']','').replace("'",'').replace('"','').split(',') if x.strip())
        return returned_total >= rented_total
    except Exception as e: return False

def load_table(search_var, filter_var, from_date_var, to_date_var, from_bill_var, to_bill_var, table, db, has_return_fn, has_pending_fn=None, limit=100):
    try:
        table.delete(*table.get_children())
        
        keyword = search_var.get().strip().lower()
        f_type = filter_var.get()
        f_date = from_date_var.get().strip()
        t_date = to_date_var.get().strip()
        f_bill = from_bill_var.get().strip().upper()
        t_bill = to_bill_var.get().strip().upper()
        
        try:
            dt_start = datetime.strptime(f_date, "%d-%m-%y") if f_date else datetime.min
            dt_end = datetime.strptime(t_date, "%d-%m-%y") if t_date else datetime.max
        except:
            dt_start, dt_end = datetime.min, datetime.max

        records = load_all_records(db, limit=limit * 5) 
        view_count = 0
        
        # Get regular customer phones set
        from shared_imports import get_regular_customer_phones
        regular_phones = get_regular_customer_phones(db)
        
        for rec in sorted(records, key=lambda r: r["id"], reverse=True):
            address_str = str(rec.get("address", "")).lower()
            bill_str = str(rec.get("bill_no", "")).lower()
            phone2_str = str(rec.get("phone2", "")).lower()
            
            if keyword and keyword not in rec["name"].lower() and keyword not in str(rec["phone"]) and keyword not in phone2_str and keyword not in address_str and keyword not in bill_str: 
                continue
                
            try:
                rec_dt = datetime.strptime(rec["date"], "%d-%m-%y")
                if not (dt_start <= rec_dt <= dt_end): continue
            except: pass
            
            rec_bill = str(rec["bill_no"]).upper()
            if f_bill and rec_bill < f_bill: continue
            if t_bill and rec_bill > t_bill: continue
            
            live_balance = calculate_balance_for_record(rec["id"], db)
            fully_returned = is_record_fully_returned(rec["id"], db)
            pending = "No" if fully_returned else "Yes"
            
            if f_type == "pending" and pending == "No": continue
            if f_type == "balance" and abs(live_balance) < 0.01: continue
            
            tag = "returned" if live_balance <= 0 and fully_returned else "not_returned"
            icon = "✓" if tag == "returned" else "✗"
            
            cust_name = rec["name"]
            if rec["phone"] in regular_phones:
                cust_name += " ⭐"

            table.insert("", "end", values=(
                rec["bill_no"], cust_name, rec["phone"], rec.get("phone2", ""),
                rec.get("address", ""), rec["date"], f"{live_balance:.2f}", pending, icon
            ), tags=(tag,))
            
            view_count += 1
            if view_count >= limit: break
    except Exception as e: log_error("Table loading", e)

def safe_get_record_by_id(identifier, db):
    if not identifier: return None
    try:
        if isinstance(identifier, (list, tuple)): identifier = identifier[0]
        return get_record_by_id(identifier, db)
    except Exception: return None

def on_row_select(event, table, db, field_vars, address_text):
    try:
        sel = table.selection()
        if not sel: return
        values = table.item(sel, "values")
        if not values: return
        bill_no = values[0]
        record = safe_get_record_by_id(bill_no, db)
        if record: populate_form_from_record(record, field_vars, address_text)
    except Exception as e: log_error("Row selection", e)

def populate_form_from_record(record, field_vars, address_text):
    try:
        for key in ["bill_no", "name", "phone", "phone2", "id_proof", "total", 
                    "advance", "date", "time", "vehicle", "payment_mode"]:
            val = record.get(key)
            if val is None: val = ""
            field_vars[key].set(val)
        
        cashier_val = record.get("cashier_name")
        if cashier_val is None: cashier_val = ""
        field_vars["cashier_name"].set(cashier_val)
        field_vars["mode"].set("edit")
        field_vars["record_id"].set(record["id"])
        
        addr_val = record.get("address")
        if addr_val is None: addr_val = ""
        
        old_state = address_text.cget("state")
        address_text.configure(state=tk.NORMAL)
        address_text.delete("1.0", "end")
        address_text.insert("1.0", addr_val)
        address_text.configure(state=old_state)
        
        db = field_vars["db"]
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT machine_code, machine_name, quantity, total_price FROM rental_items WHERE rental_id = ?", (record["id"],))
        items = c.fetchall()
        
        display_idx = 0
        for item in items:
            if display_idx >= MAX_MACHINES_PER_BILL: break
            field_vars["machine_codes"][display_idx].set(item[0] or "")
            field_vars["machine_names"][display_idx].set(item[1] or "")
            field_vars["quantities"][display_idx].set(str(item[2]) if item[2] is not None else "")
            field_vars["rents"][display_idx].set(str(item[3]) if item[3] is not None else "")
            display_idx += 1
            
        for i in range(display_idx, MAX_MACHINES_PER_BILL):
            field_vars["machine_codes"][i].set("")
            field_vars["machine_names"][i].set("")
            field_vars["quantities"][i].set("")
            field_vars["rents"][i].set("")
    except Exception as e: log_error("Form population", e)
    
def print_bill(table, db, current_vars=None, image_path="bill-layout.jpg"):
    try:
        sel = table.selection()
        if not sel: 
            messagebox.showwarning("Error", "No record selected")
            return False
            
        values = table.item(sel, "values")
        record = get_record_by_id(values[0], db)
        if not record: return False
        
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT machine_name, quantity, total_price FROM rental_items WHERE rental_id=?", (record['id'],))
        items_rows = c.fetchall()
        
        clean_items = [r[0] for r in items_rows]
        clean_qtys = [r[1] for r in items_rows]
        clean_rents = [r[2] for r in items_rows]

        # Query deduction and damage if exists in returns table
        c.execute("SELECT deduction, damage FROM returns WHERE rental_id=?", (record['id'],))
        ret_row = c.fetchone()
        deduction = safe_float(ret_row[0]) if ret_row else 0.0
        damage = safe_float(ret_row[1]) if ret_row else 0.0

        from billing import generate_bill
        generate_bill(
            bill_no=record.get("bill_no"), date=record.get("date"), time=record.get("time"),
            address=record.get("address"), phone=record.get("phone"),
            items=clean_items, qty=clean_qtys, rent=clean_rents,
            total=safe_float(record.get("total", "0")), 
            advance=safe_float(record.get("advance", "0")), 
            rental_days=1, background_path=image_path, vehicle=record.get("vehicle", ""),
            name=record.get("name", ""),
            payment_mode=record.get("payment_mode", "Cash"),
            deduction=deduction,
            damage=damage
        )
        return True
    except Exception as e:
        messagebox.showerror("Print Error", f"Failed: {e}")
        return False

def setup_phone_suggestions(phone_var, name_var, address_text, suggestion_box, db, 
                            phone2_var=None, balance_var=None, pending_var=None, past_due_var=None):
    def show_suggestions(*_):
        query = phone_var.get().strip()
        if len(query) < 3: 
            suggestion_box.grid_remove()
            return
        try:
            conn = db.get_connection()
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT name, phone, phone2, address, is_regular FROM customers WHERE phone LIKE ? ORDER BY name ASC LIMIT 10", (f'%{query}%',))
            matches = [dict(row) for row in c.fetchall()]
            suggestion_box.delete(0, tk.END)
            for r in matches:
                name_disp = r['name']
                if r.get('is_regular'):
                    name_disp += " ⭐"
                suggestion_box.insert(tk.END, f"{r['phone']} - {name_disp}")
            if matches: suggestion_box.grid()
            else: suggestion_box.grid_remove()
        except Exception as e: suggestion_box.grid_remove()

    def on_select(event):
        try:
            sel = suggestion_box.curselection()
            if not sel: return
            phone = suggestion_box.get(sel[0]).split(" - ")[0].strip()
            
            conn = db.get_connection()
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM customers WHERE phone = ?", (phone,))
            row = c.fetchone()
            if not row: return
            rec = dict(row)
            
            phone_var.set(rec["phone"])
            name_var.set(rec["name"])
            address_text.delete("1.0", tk.END)
            address_text.insert("1.0", rec.get("address", ""))
            if phone2_var: phone2_var.set(rec.get("phone2", ""))
            
            if past_due_var:
                from return_logic import get_total_past_dues
                past_dues = get_total_past_dues(db, phone, None) 
                past_due_var.set(f"{past_dues:.2f}")
            if balance_var: balance_var.set("0.00")
            if pending_var:
                from shared_imports import has_pending_returns
                pending = has_pending_returns(phone, db)
                pending_var.set("Yes" if pending else "No")
                
            suggestion_box.grid_remove()
        except Exception as e: pass

    phone_var.trace_add("write", show_suggestions)
    suggestion_box.bind("<<ListboxSelect>>", on_select)
    suggestion_box.bind("<FocusOut>", lambda e: suggestion_box.grid_remove() if suggestion_box.focus_get() != suggestion_box else None)

def setup_phone2_suggestions(phone2_var, name_var, address_text, suggestion_box, db, 
                             phone_var=None, balance_var=None, pending_var=None, past_due_var=None):
    def show_suggestions(*_):
        query = phone2_var.get().strip()
        if len(query) < 3: 
            suggestion_box.grid_remove()
            return
        try:
            conn = db.get_connection()
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT name, phone, phone2, address, is_regular FROM customers WHERE phone LIKE ? OR phone2 LIKE ? ORDER BY name ASC LIMIT 10", (f'%{query}%', f'%{query}%'))
            matches = [dict(row) for row in c.fetchall()]
            suggestion_box.delete(0, tk.END)
            for r in matches: 
                disp_phone = r.get("phone2", "") if query in str(r.get("phone2", "")) else r["phone"]
                name_disp = r['name']
                if r.get('is_regular'):
                    name_disp += " ⭐"
                suggestion_box.insert(tk.END, f"{disp_phone} - {name_disp}")
            if matches: suggestion_box.grid()
            else: suggestion_box.grid_remove()
        except: suggestion_box.grid_remove()

    def on_select(event):
        try:
            sel = suggestion_box.curselection()
            if not sel: return
            selected_phone = suggestion_box.get(sel[0]).split(" - ")[0].strip()
            
            conn = db.get_connection()
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM customers WHERE phone = ? OR phone2 = ?", (selected_phone, selected_phone))
            row = c.fetchone()
            if not row: return
            rec = dict(row)
            
            if phone_var: phone_var.set(rec["phone"])
            phone2_var.set(rec.get("phone2", ""))
            name_var.set(rec["name"])
            address_text.delete("1.0", tk.END)
            address_text.insert("1.0", rec.get("address", ""))
            
            if past_due_var:
                from return_logic import get_total_past_dues
                past_dues = get_total_past_dues(db, rec["phone"], None) 
                past_due_var.set(f"{past_dues:.2f}")
            if balance_var: balance_var.set("0.00")
            if pending_var:
                from shared_imports import has_pending_returns
                pending = has_pending_returns(rec["phone"], db)
                pending_var.set("Yes" if pending else "No")
                
            suggestion_box.grid_remove()
        except Exception as e: pass

    phone2_var.trace_add("write", show_suggestions)
    suggestion_box.bind("<<ListboxSelect>>", on_select)
    suggestion_box.bind("<FocusOut>", lambda e: suggestion_box.grid_remove() if suggestion_box.focus_get() != suggestion_box else None)