# webapp/services.py - Business operations exposed to the web UI.
#
# Everything here either calls the existing logic modules directly, or is a
# line-for-line port of the data code that used to live inside the Tkinter tab
# builders (only the widget calls were replaced by returning plain data).
# All functions take the DBManager as the first argument and run on the single
# database worker thread (see webapp/worker.py).
import sqlite3
import textwrap
from collections import defaultdict
from datetime import datetime, timedelta

from utils import safe_float, safe_int, log_error, parse_date_key
from shared_imports import (
    DBManager, validate_form, save_form_data, update_form_data, get_record_by_id,
    has_return_entry, has_pending_returns, cancel_rental, generate_next_bill_no,
    calculate_master_balance, calculate_rental_days_unified,
    get_regular_customer_phones, get_customer_history,
)
from billing import generate_bill
from return_logic import (
    get_full_rental_details, save_return_data, get_total_past_dues,
    split_rental_bill, save_installment, get_installments,
    save_refund_history, get_refunds,
)
from form_logic import (
    load_table as logic_load_table, safe_get_record_by_id,
    calculate_balance_for_record, is_record_fully_returned,
)
from customers_tab import init_customers_db, sync_single_customer, run_initial_regular_sync
from partial_returns_tab import get_pending_returns
from analytics_dashboard import AnalyticsDashboard
import materials

MAX_MACHINES_PER_BILL = 5


class UserError(Exception):
    """An error that should be shown to the user as a dialog."""
    def __init__(self, title, message, kind="error"):
        super().__init__(message)
        self.title = title
        self.message = message
        self.kind = kind


def _s(value):
    """Mirror what a Tkinter StringVar shows for a DB value (None -> '')."""
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------
# Startup / app shell
# ---------------------------------------------------------------------------

def initialize_database():
    """Same steps as RentalBillingApp.initialize_database + tab setup in main.py."""
    try:
        db = DBManager()
        if db.conn is None:
            raise Exception("Failed to connect to database")
    except Exception as e:
        raise UserError(
            "Database Error",
            f"Failed to initialize database:\n{str(e)}\n\n"
            "Please ensure:\n"
            "• The application has write permissions\n"
            "• rentals.db is not open in another program\n"
            "• There's sufficient disk space")

    warning = None
    is_valid, message = db.validate_database()
    if not is_valid:
        warning = (f"Database validation issue: {message}\n\n"
                   "The application will attempt to repair automatically.")
    try:
        run_initial_regular_sync(db)
        print("👥 Background regular status sync initiated.")
    except Exception as e:
        print(f"[WARN] Failed to start initial regular customer sync: {e}")
    # create_customers_tab() used to do this when the UI was built
    init_customers_db(db)
    return db, warning


def status_counts(db):
    try:
        c = db.conn.cursor()
        c.execute("SELECT COUNT(*) FROM rentals WHERE cancelled IS NULL OR cancelled = 0")
        active_records = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM rentals WHERE cancelled = 1")
        cancelled_records = c.fetchone()[0]
        return {"text": f"Active: {active_records} | Cancelled: {cancelled_records}"}
    except Exception:
        return {"text": "Records: Error"}


def materials_list(db=None):
    # A list (not a dict) keeps the CSV order, which the name auto-fill relies on
    return [{"code": c, "name": m["name"], "price": m["price"]}
            for c, m in materials.materials_dict.items()]


# ---------------------------------------------------------------------------
# Outward Billing form
# ---------------------------------------------------------------------------

def next_bill_no(db):
    try:
        return generate_next_bill_no(db)
    except Exception:
        return "A00001"


class _Var:
    """Stand-in for a Tkinter StringVar so form_logic.load_table can be reused as-is."""
    def __init__(self, value=""):
        self._value = value

    def get(self):
        return self._value


class _Table:
    """Stand-in for the Treeview: collects the rows form_logic.load_table inserts."""
    def __init__(self):
        self.rows = []

    def get_children(self):
        return list(range(len(self.rows)))

    def delete(self, *items):
        self.rows.clear()

    def insert(self, parent, index, values=(), tags=(), **kwargs):
        self.rows.append({"values": [_s(v) for v in values], "tag": tags[0] if tags else ""})


def outward_table(db, search="", status="all", from_date="", to_date="", from_bill="", to_bill=""):
    table = _Table()
    logic_load_table(_Var(search), _Var(status), _Var(from_date), _Var(to_date),
                     _Var(from_bill), _Var(to_bill), table, db,
                     has_return_entry, has_pending_returns, limit=10000)
    # Drop the trailing ✓/✗ icon value: it had no column in the old table either
    return [{"values": r["values"][:8], "tag": r["tag"]} for r in table.rows]


def phone_info(db, phone, rental_id=None):
    """Port of update_balance_and_pending() from form_tab.py."""
    phone = (phone or "").strip()
    if not phone:
        return {"balance": "0.00", "past_due": "0.00", "pending": "No"}
    out = {}
    if rental_id:
        out["balance"] = f"{calculate_balance_for_record(rental_id, db):.2f}"
        out["past_due"] = f"{get_total_past_dues(db, phone, rental_id):.2f}"
    else:
        out["past_due"] = f"{get_total_past_dues(db, phone, None):.2f}"
    try:
        out["pending"] = "Yes" if has_pending_returns(phone, db) else "No"
    except Exception as e:
        log_error("Pending returns check", e)
    return out


def phone_suggestions(db, query, second=False):
    """Port of setup_phone_suggestions / setup_phone2_suggestions (the list part)."""
    query = (query or "").strip()
    if len(query) < 3:
        return []
    try:
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if second:
            c.execute("SELECT name, phone, phone2, address, is_regular FROM customers WHERE phone LIKE ? OR phone2 LIKE ? ORDER BY name ASC LIMIT 10", (f'%{query}%', f'%{query}%'))
        else:
            c.execute("SELECT name, phone, phone2, address, is_regular FROM customers WHERE phone LIKE ? ORDER BY name ASC LIMIT 10", (f'%{query}%',))
        out = []
        for r in [dict(row) for row in c.fetchall()]:
            if second:
                disp_phone = r.get("phone2", "") if query in str(r.get("phone2", "")) else r["phone"]
            else:
                disp_phone = r['phone']
            name_disp = r['name']
            if r.get('is_regular'):
                name_disp += " ⭐"
            label = f"{disp_phone} - {name_disp}"
            out.append({"label": label, "key": label.split(" - ")[0].strip(),
                        "phone": _s(disp_phone), "name": name_disp})
        return out
    except Exception:
        return []


def pick_customer(db, key, second=False):
    """Port of the suggestion on_select handlers: fill the form from a customer."""
    conn = db.get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if second:
        c.execute("SELECT * FROM customers WHERE phone = ? OR phone2 = ?", (key, key))
    else:
        c.execute("SELECT * FROM customers WHERE phone = ?", (key,))
    row = c.fetchone()
    if not row:
        return None
    rec = dict(row)
    dues_phone = rec["phone"] if second else key
    out = {
        "phone": _s(rec["phone"]), "name": _s(rec["name"]),
        "address": _s(rec.get("address", "")), "phone2": _s(rec.get("phone2", "")),
        "past_due": f"{get_total_past_dues(db, dues_phone, None):.2f}",
        "balance": "0.00",
    }
    try:
        out["pending"] = "Yes" if has_pending_returns(dues_phone, db) else "No"
    except Exception:
        pass
    return out


def select_record(db, bill_no):
    """Port of on_row_select_with_balance: load a bill into the form + return panel."""
    record = safe_get_record_by_id(bill_no, db)
    if not record:
        return None
    form = {k: _s(record.get(k)) for k in ["bill_no", "name", "phone", "phone2", "id_proof", "total",
                                         "advance", "date", "time", "vehicle", "payment_mode"]}
    form["cashier_name"] = _s(record.get("cashier_name"))
    form["address"] = _s(record.get("address"))
    form["record_id"] = _s(record["id"])

    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT machine_code, machine_name, quantity, total_price FROM rental_items WHERE rental_id = ?", (record["id"],))
    items = []
    for item in c.fetchall():
        if len(items) >= MAX_MACHINES_PER_BILL:
            break
        name = item[1] or ""
        is_spare = False
        if name.endswith(" (with spare)"):
            name = name[:-13]
            is_spare = True
        items.append({
            "code": item[0] or "", "name": name, "spare": is_spare,
            "qty": str(item[2]) if item[2] is not None else "",
            "rent": str(item[3]) if item[3] is not None else "",
        })

    out = {"form": form, "items": items}
    out.update(phone_info(db, record.get('phone', ''), record['id']))
    out["ret"] = return_load(db, record['id'])
    return out


def _form_data(payload):
    """Build the same dict submit_form() in form_logic.py builds from the Tk variables."""
    machines_list = []
    for row in payload.get("rows", []):
        name_val = str(row.get("name", "")).strip()
        if name_val and row.get("spare"):
            name_val += " (with spare)"
        machines_list.append(name_val)
    rows = payload.get("rows", [])
    f = payload.get("form", {})
    g = lambda k: str(f.get(k, "") or "")
    return {
        "bill_no": g("bill_no"), "mode": g("mode"),
        "name": g("name").strip(), "phone": g("phone").strip(),
        "phone2": g("phone2").strip(), "address": g("address").strip(),
        "id_proof": g("id_proof").strip(), "machines": machines_list,
        "rents": [str(r.get("rent", "")).strip() for r in rows],
        "quantities": [str(r.get("qty", "")).strip() for r in rows],
        "machine_codes": [str(r.get("code", "")).strip() for r in rows],
        "total": g("total").strip(),
        "advance": g("advance").strip(), "date": g("date").strip(),
        "time": g("time").strip(), "vehicle": g("vehicle").strip(),
        "payment_mode": g("payment_mode"), "cashier_name": g("cashier_name").strip(),
        "id": g("record_id"),
    }


def submit_form(db, payload):
    data = _form_data(payload)
    valid, msg = validate_form(data)
    if not valid:
        raise UserError("Validation Error", msg)
    try:
        if data["mode"] == "edit":
            update_form_data(data, db)
            success_msg = "Data updated successfully."
        else:
            save_form_data(data, db)
            success_msg = "Data saved successfully."
    except Exception as e:
        log_error("Form submission", e)
        raise UserError("Error", f"Failed to save: {e}")
    sync_single_customer(db, data)
    return {"message": success_msg}


def cancel_record(db, record_id):
    try:
        cancel_rental(record_id, db)
    except Exception as e:
        raise UserError("Error", str(e))
    return {"message": "Rental cancelled."}


def print_bill(db, bill_no, image_path="bill-layout.jpg"):
    """Port of form_logic.print_bill for the selected table row."""
    try:
        record = get_record_by_id(bill_no, db)
        if not record:
            return False
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT machine_name, quantity, total_price FROM rental_items WHERE rental_id=?", (record['id'],))
        items_rows = c.fetchall()
        clean_items = [r[0] for r in items_rows]
        clean_qtys = [r[1] for r in items_rows]
        clean_rents = [r[2] for r in items_rows]

        c.execute("SELECT deduction, damage FROM returns WHERE rental_id=?", (record['id'],))
        ret_row = c.fetchone()
        deduction = safe_float(ret_row[0]) if ret_row else 0.0
        damage = safe_float(ret_row[1]) if ret_row else 0.0

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
        raise UserError("Print Error", f"Failed: {e}")


# ---------------------------------------------------------------------------
# Return Processing panel (port of return_form.py)
# ---------------------------------------------------------------------------

def _history(installments, refunds, returns):
    def money_rows(rows):
        return [[_s(r['date_time']), f"{safe_float(r['amount']):.2f}",
                 _s(r.get('payment_mode', 'Cash')), _s(r.get('cashier_name', 'Unknown'))] for r in rows]
    return {
        "Paid": money_rows(installments),
        "Refund": money_rows(refunds),
        "Return": [[_s(r['date_time']), "-", "-", _s(r.get('cashier_name', 'Unknown'))] for r in returns],
    }


def return_load(db, rental_id):
    """Port of update_return_fields_from_selection (the data part)."""
    try:
        rental = dict(get_full_rental_details(db, rental_id))
        c0 = db.get_connection().cursor()
        c0.execute("SELECT bill_no FROM rentals WHERE id = ?", (rental_id,))
        bill_row = c0.fetchone()
        out = {
            "rental_id": _s(rental_id),
            "bill_no": _s(bill_row[0]) if bill_row else "",   # shown in the panel header only
            "name": _s(rental.get("name")),
            "phone": _s(rental.get("phone")),
            "rents": rental["rents"],
            "start_date": rental["date"], "start_time": rental["time"],
            "rented_quantities": rental["quantities"],
            "advance": f"{safe_float(rental.get('advance', 0.0)):.2f}",
            "fields": {},
        }
        installments = get_installments(db, int(rental_id))
        total_inst = 0.0
        for inst in installments:
            total_inst += safe_float(inst['amount'])
        refunds = get_refunds(db, int(rental_id))

        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM returns WHERE rental_id = ?", (rental_id,))
        prev_return_row = c.fetchone()

        current_returns = []
        if prev_return_row:
            prev_return = dict(prev_return_row)
            dt = f"{prev_return.get('return_date', '')} {prev_return.get('return_time', '')}".strip()
            cashier = prev_return.get('cashier_name', '') or 'Unknown'
            current_returns.append({'date_time': dt, 'cashier_name': cashier})
        out["history"] = _history(installments, refunds, current_returns)

        saved_returned_qtys = []
        fields = out["fields"]
        if prev_return_row:
            prev_return = dict(prev_return_row)
            if prev_return.get("returned_quantities"):
                s = str(prev_return["returned_quantities"]).replace('[','').replace(']','').replace("'",'').replace('"','')
                saved_returned_qtys = [safe_int(q) for q in s.split(",") if q.strip()]

            all_returned = True
            for sq, rq in zip(saved_returned_qtys + [0]*10, rental["quantities"] + [0]*10):
                if safe_int(sq) < safe_int(rq):
                    all_returned = False
                    break

            if all_returned:
                fields["date"] = _s(prev_return.get("return_date", ""))
                fields["time"] = _s(prev_return.get("return_time", ""))
            else:
                fields["date"] = datetime.now().strftime("%d-%m-%y")
                fields["time"] = datetime.now().strftime("%I:%M %p")

            fields["rental_days"] = str(prev_return.get("rental_days", 1))
            fields["due"] = f"{safe_float(prev_return.get('due_amount', 0)):.2f}"
            fields["damage"] = f"{safe_float(prev_return.get('damage', 0)):.2f}"
            fields["deduction"] = f"{safe_float(prev_return.get('deduction', 0)):.2f}"
            db_paid = safe_float(prev_return.get('amount_paid', 0))
            fields["amount_paid"] = f"{max(db_paid, total_inst):.2f}"
            fields["refund"] = f"{safe_float(prev_return.get('refund', 0)):.2f}"
            fields["payment_mode"] = _s(prev_return.get("payment_mode") or rental.get("payment_mode", "Cash"))
        else:
            fields["amount_paid"] = f"{total_inst:.2f}"
            fields["payment_mode"] = _s(rental.get("payment_mode", "Cash"))

        out["past_due"] = f"{get_total_past_dues(db, rental['phone'], int(rental_id)):.2f}"

        steppers = []
        for i, (machine, qty) in enumerate(zip(rental["machines"], rental["quantities"])):
            if safe_int(qty) <= 0: continue
            if len(steppers) >= 5: break
            default_val = saved_returned_qtys[i] if i < len(saved_returned_qtys) else 0
            steppers.append({"label": f"{machine} (Max: {qty})", "max": safe_int(qty), "value": str(default_val)})
        out["steppers"] = steppers
        return out
    except Exception as e:
        log_error("Update return fields", e)
        return None


def _save_return(db, rental_id, f, stepper_values, cashier_name):
    """Port of on_submit() from return_form.py."""
    full_details = get_full_rental_details(db, int(rental_id))
    final_returned_qtys = []
    final_returned_items = []
    spin_idx = 0
    for i, (machine, qty) in enumerate(zip(full_details["machines"], full_details["quantities"])):
        if safe_int(qty) > 0 and spin_idx < 5:
            final_returned_qtys.append(str(safe_int(stepper_values[spin_idx] if spin_idx < len(stepper_values) else 0)))
            spin_idx += 1
        else: final_returned_qtys.append("0")
        final_returned_items.append(str(full_details["machine_codes"][i]))

    save_return_data(
        db, rental_id=int(rental_id), return_date=f["date"], return_time=f["time"],
        rental_days=f["rental_days"], due_amount=f["due"],
        deduction=f["deduction"], damage=f["damage"],
        balance=f["balance"], amount_paid=f["amount_paid"],
        refund=f["refund"],
        returned_items=",".join(final_returned_items), returned_quantities=",".join(final_returned_qtys),
        payment_mode=f["payment_mode"],
        cashier_name=cashier_name or ""
    )


def return_submit(db, rental_id, fields, steppers, cashier_name):
    if not rental_id:
        return False
    try:
        _save_return(db, rental_id, fields, steppers, cashier_name)
    except Exception as e:
        raise UserError("Error", f"Failed to save: {e}")
    return {"message": "Return details saved."}


def _now_stamp():
    return datetime.now().strftime("%d-%m-%y %I:%M %p")


def return_add_payment(db, kind, rental_id, amount, cashier_name, payment_mode, fields, steppers):
    """Port of add_payment()/add_refund(): record the money, then silently save the return."""
    try:
        if kind == "refund":
            save_refund_history(db, int(rental_id), amount, cashier_name, payment_mode, _now_stamp())
        else:
            save_installment(db, int(rental_id), amount, payment_mode, cashier_name, _now_stamp())
    except Exception as e:
        raise UserError("Error", f"Invalid input: {e}")
    try:
        _save_return(db, rental_id, fields, steppers, cashier_name)
    except Exception:
        pass  # on_submit(silent=True) never reported errors
    return True


def return_split(db, rental_id, qty_to_return, fields, cashier_name):
    """Port of on_split_bill() -> proceed_split()."""
    try:
        new_bill_no = split_rental_bill(db, int(rental_id), qty_to_return)

        full_details = get_full_rental_details(db, int(rental_id))
        final_returned_qtys = [str(q) for q in qty_to_return if q > 0]
        final_returned_items = [str(code) for code in full_details["machine_codes"]]

        rental_days = safe_int(fields["rental_days"]) or 1
        daily_rent = sum(safe_float(r) for r in full_details["rents"])

        due, net_balance = calculate_master_balance(
            daily_rent=daily_rent,
            rental_days=rental_days,
            advance_paid=0.0,
            installments_paid=safe_float(fields["amount_paid"]),
            damage_charges=safe_float(fields["damage"]),
            discount_deduction=safe_float(fields["deduction"]),
            final_amount_paid=safe_float(fields["amount_paid"]),
            refund_given=safe_float(fields["refund"]),
            is_returned=True
        )

        save_return_data(
            db, rental_id=int(rental_id), return_date=fields["date"], return_time=fields["time"],
            rental_days=rental_days, due_amount=due,
            deduction=fields["deduction"], damage=fields["damage"],
            balance=net_balance, amount_paid=fields["amount_paid"],
            refund=fields["refund"],
            returned_items=",".join(final_returned_items),
            returned_quantities=",".join(final_returned_qtys),
            payment_mode=fields["payment_mode"],
            cashier_name=cashier_name
        )
        return {"message": f"Split Successful!\nNew pending bill created: {new_bill_no}"}
    except Exception as e:
        raise UserError("Split Failed", str(e))


def return_print(db, rental_id, image_path, fields):
    """Port of on_print_bill() from return_form.py."""
    if not rental_id:
        return False
    try:
        record = get_record_by_id(rental_id, db)
        if not record: return False
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT machine_name, quantity, total_price FROM rental_items WHERE rental_id=?", (rental_id,))
        items_rows = c.fetchall()

        clean_items = [r[0] for r in items_rows]
        clean_qtys = [r[1] for r in items_rows]
        clean_rents = [r[2] for r in items_rows]

        due_amt = safe_float(fields["due"])
        deduction_amt = safe_float(fields["deduction"])
        damage_amt = safe_float(fields["damage"])
        actual_billing_amount = due_amt - deduction_amt + damage_amt

        bill_no = record.get("bill_no") or record.get("id")
        generate_bill(
            bill_no=bill_no, date=record.get("date", ""), time=record.get("time", ""),
            address=record.get("address", ""), phone=record.get("phone", ""),
            items=clean_items, qty=clean_qtys, rent=clean_rents,
            total=actual_billing_amount,
            advance=record.get("advance", "0"),
            rental_days=fields["rental_days"],
            return_date=fields["date"], return_time=fields["time"],
            background_path=image_path, vehicle=record.get("vehicle", ""),
            name=record.get("name", ""),
            payment_mode=fields["payment_mode"],
            deduction=deduction_amt,
            damage=damage_amt
        )
        return True
    except Exception as e:
        raise UserError("Print Error", f"Failed: {e}")


# ---------------------------------------------------------------------------
# Pending Returns tab (port of partial_returns_tab.load_data)
# ---------------------------------------------------------------------------

def pending_returns_table(db, search="", sort="new_to_old"):
    out = []
    try:
        keyword = search.strip().lower()
        regular_phones = get_regular_customer_phones(db)
        records = get_pending_returns(db)
        is_new_to_old = (sort == "new_to_old")
        records.sort(
            key=lambda x: (parse_date_key(x.get("date", "")), safe_int(x.get("bill_no", 0))),
            reverse=is_new_to_old
        )
        for rec in records:
            phone2 = rec.get("phone2") or ""
            item_names = " ".join([item["name"] for item in rec.get("items_data", [])])
            search_string = f"{rec['bill_no']} {rec['name']} {rec['phone']} {phone2} {rec['address']} {item_names}".lower()
            if keyword and keyword not in search_string:
                continue
            addr = rec["address"] or ""
            wrapped_addr = "\n".join(textwrap.wrap(addr, width=45))
            cust_name = rec["name"]
            if rec["phone"] in regular_phones:
                cust_name += " ⭐"
            out.append({
                "bill_no": _s(rec["bill_no"]), "name": cust_name, "phone": _s(rec["phone"]),
                "address": wrapped_addr, "date": _s(rec["date"]),
                "items": [{"name": _s(i["name"]), "taken": i["taken"]} for i in rec["items_data"]],
            })
    except Exception as e:
        log_error("Loading pending returns table", e)
    return out


def rental_id_for_bill(db, bill_no):
    c = db.get_connection().cursor()
    c.execute("SELECT id FROM rentals WHERE bill_no = ?", (bill_no,))
    res = c.fetchone()
    return res[0] if res else None


# ---------------------------------------------------------------------------
# Pending / Refunds tab (port of pending_tab.load_pending_data)
# ---------------------------------------------------------------------------

def pending_payments_table(db, search="", filter="all", return_status="all", sort="new_to_old"):
    keyword = search.lower().strip()
    current_filter = filter
    current_return_status = return_status

    conn = db.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    all_data = []

    cursor.execute("""
        SELECT r.bill_no, r.name, r.phone, r.total as daily_rent, r.advance,
               ret.return_date as date, ret.rental_days, ret.due_amount,
               ret.amount_paid, ret.damage, ret.deduction, ret.refund,
               (SELECT SUM(amount) FROM installments WHERE rental_id = r.id) as inst_paid
        FROM returns ret
        JOIN rentals r ON r.id = ret.rental_id
        WHERE (r.cancelled IS NULL OR r.cancelled = 0)
    """)
    for row in cursor.fetchall():
        due, net_balance = calculate_master_balance(
            daily_rent=row['daily_rent'],
            rental_days=row['rental_days'],
            advance_paid=row['advance'],
            installments_paid=row['inst_paid'] or 0.0,
            damage_charges=row['damage'],
            discount_deduction=row['deduction'],
            final_amount_paid=row['amount_paid'],
            refund_given=row['refund'],
            is_returned=True,
            manual_due_override=row['due_amount']
        )
        if abs(net_balance) > 0.01:
            total_paid = max(safe_float(row['inst_paid']), safe_float(row['amount_paid']))
            all_data.append({
                "bill_no": row['bill_no'], "name": row['name'], "phone": row['phone'],
                "date": row['date'], "due_amount": due, "advance": safe_float(row['advance']),
                "amount_paid": total_paid, "balance": net_balance, "is_returned": True
            })

    cursor.execute("""
        SELECT r.id, r.bill_no, r.name, r.phone, r.date, r.time, r.total as daily_rent, r.advance,
               (SELECT SUM(amount) FROM installments WHERE rental_id = r.id) as inst_paid
        FROM rentals r
        WHERE (r.cancelled IS NULL OR r.cancelled = 0)
          AND r.id NOT IN (SELECT rental_id FROM returns)
    """)
    for row in cursor.fetchall():
        try: days = calculate_rental_days_unified(row['date'], row['time'])
        except: days = 1
        due, net_balance = calculate_master_balance(
            daily_rent=row['daily_rent'],
            rental_days=days,
            advance_paid=row['advance'],
            installments_paid=row['inst_paid'] or 0.0,
            is_returned=False
        )
        if abs(net_balance) > 0.01:
            all_data.append({
                "bill_no": row['bill_no'], "name": row['name'], "phone": row['phone'],
                "date": row['date'], "due_amount": due, "advance": safe_float(row['advance']),
                "amount_paid": safe_float(row['inst_paid']), "balance": net_balance, "is_returned": False
            })

    regular_phones = get_regular_customer_phones(db)
    is_new_to_old = (sort == "new_to_old")
    all_data.sort(
        key=lambda x: (parse_date_key(x.get("date", "")), safe_int(x.get("bill_no", 0))),
        reverse=is_new_to_old
    )

    out = []
    for row in all_data:
        if keyword and keyword not in row["name"].lower() and keyword not in row["phone"]:
            continue
        if current_filter == "collect" and row["balance"] < 0:
            continue
        if current_filter == "refund" and row["balance"] > 0:
            continue
        if current_return_status == "returned" and not row["is_returned"]:
            continue
        if current_return_status == "not_returned" and row["is_returned"]:
            continue
        cust_name = row["name"]
        if row["phone"] in regular_phones:
            cust_name += " ⭐"
        tag = "debt" if row["balance"] > 0 else "refund"
        out.append({"values": [
            _s(row["bill_no"]), cust_name, _s(row["phone"]), _s(row["date"]),
            f"{row['due_amount']:.2f}", f"{row['advance']:.2f}",
            f"{row['amount_paid']:.2f}", f"{row['balance']:.2f}"
        ], "tag": tag})
    return out


# ---------------------------------------------------------------------------
# Day's Overview tab (port of daily_report_tab.load_daily_data)
# ---------------------------------------------------------------------------

def _clean_split(d):
    if not d: return []
    s = str(d).replace('[','').replace(']','').replace("'",'').replace('"','')
    return [x.strip() for x in s.split(',') if x.strip()]


def daily_overview(db, from_date, to_date, search=""):
    def parse_datetime(dt_str, t_str="12:00 AM"):
        try: return datetime.strptime(f"{dt_str} {t_str}", "%d-%m-%y %I:%M %p")
        except: return datetime.min

    keyword = search.strip().lower()
    cash_in = gpay_in = cash_out = gpay_out = 0.0
    rented_qty = returned_qty = 0
    records = []

    try:
        start_dt = datetime.strptime(from_date, '%d-%m-%y')
        end_dt = datetime.strptime(to_date, '%d-%m-%y') + timedelta(days=1, seconds=-1)
    except Exception as e:
        log_error("Date parsing error", e)
        return {"ok": False, "rows": []}

    try:
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c2 = conn.cursor()

        c.execute("SELECT id, date, time, bill_no, name, advance, payment_mode FROM rentals WHERE (cancelled IS NULL OR cancelled = 0)")
        for r_obj in c.fetchall():
            r = dict(r_obj)
            if keyword and keyword not in str(r.get('bill_no', '')).lower() and keyword not in str(r.get('name', '')).lower():
                continue
            row_dt = parse_datetime(r['date'], r['time'])
            if not (start_dt <= row_dt <= end_dt): continue
            dt_display = f"{r['date']} {r['time']}"

            c2.execute("SELECT machine_name, quantity FROM rental_items WHERE rental_id=?", (r['id'],))
            items_str = []
            for item_obj in c2.fetchall():
                m_name = item_obj['machine_name']
                q = safe_int(item_obj['quantity'])
                if q > 0:
                    items_str.append(f"{m_name}({q})")
                    rented_qty += q
            if items_str:
                records.append({
                    "dt_sort": row_dt, "dt_disp": dt_display, "bill": r['bill_no'], "name": r['name'],
                    "type": "Rented Items", "desc": ", ".join(items_str),
                    "amount": "-", "mode": "-", "tag": "neutral"
                })

            adv = safe_float(r['advance'])
            if adv > 0:
                mode = r['payment_mode']
                records.append({
                    "dt_sort": row_dt, "dt_disp": dt_display, "bill": r['bill_no'], "name": r['name'],
                    "type": "Advance (In)", "desc": "Initial Advance Paid",
                    "amount": adv, "mode": mode, "tag": "in"
                })
                if mode.lower() in ['upi', 'gpay', 'phonepe', 'online']: gpay_in += adv
                else: cash_in += adv

        try:
            c.execute("SELECT ret.rental_id, ret.return_date, ret.return_time, r.bill_no, r.name, ret.amount_paid, ret.refund, ret.payment_mode, ret.returned_quantities FROM returns ret JOIN rentals r ON ret.rental_id = r.id")
        except sqlite3.OperationalError:
            c.execute("SELECT ret.rental_id, ret.return_date, ret.return_time, r.bill_no, r.name, ret.amount_paid, 0 as refund, ret.payment_mode, ret.returned_quantities FROM returns ret JOIN rentals r ON ret.rental_id = r.id")

        for r_obj in c.fetchall():
            r = dict(r_obj)
            if keyword and keyword not in str(r.get('bill_no', '')).lower() and keyword not in str(r.get('name', '')).lower():
                continue
            row_dt = parse_datetime(r['return_date'], r['return_time'])
            if not (start_dt <= row_dt <= end_dt): continue

            dt_display = f"{r['return_date']} {r['return_time']}"
            qtys = _clean_split(r['returned_quantities'])
            count = sum(safe_int(q) for q in qtys)
            if count > 0:
                returned_qty += count
                records.append({
                    "dt_sort": row_dt, "dt_disp": dt_display, "bill": r['bill_no'], "name": r['name'],
                    "type": "Returned Items", "desc": f"Total items returned: {count}",
                    "amount": "-", "mode": "-", "tag": "neutral"
                })

            total_paid_db = safe_float(r.get('amount_paid', 0))
            c2.execute("SELECT SUM(amount) FROM installments WHERE rental_id=?", (r['rental_id'],))
            inst_sum = safe_float(c2.fetchone()[0])
            actual_final_payment = max(0.0, total_paid_db - inst_sum)

            if actual_final_payment > 0:
                mode = r['payment_mode']
                records.append({
                    "dt_sort": row_dt, "dt_disp": dt_display, "bill": r['bill_no'], "name": r['name'],
                    "type": "Final Payment (In)", "desc": "Balance Paid on Return (Legacy)",
                    "amount": actual_final_payment, "mode": mode, "tag": "in"
                })
                if mode.lower() in ['upi', 'gpay', 'phonepe', 'online']: gpay_in += actual_final_payment
                else: cash_in += actual_final_payment

            refund_db = safe_float(r.get('refund', 0))
            c2.execute("SELECT SUM(amount) FROM refunds_history WHERE rental_id=?", (r['rental_id'],))
            ref_history_sum = safe_float(c2.fetchone()[0])
            actual_final_refund = max(0.0, refund_db - ref_history_sum)
            if actual_final_refund > 0:
                mode = r['payment_mode']
                records.append({
                    "dt_sort": row_dt, "dt_disp": dt_display, "bill": r['bill_no'], "name": r['name'],
                    "type": "Refund (Out)", "desc": "Refund Given to Customer (Legacy)",
                    "amount": actual_final_refund, "mode": mode, "tag": "out"
                })
                if mode.lower() in ['upi', 'gpay', 'phonepe', 'online']: gpay_out += actual_final_refund
                else: cash_out += actual_final_refund

        c.execute("SELECT rh.date_time, r.bill_no, r.name, rh.amount, rh.payment_mode FROM refunds_history rh JOIN rentals r ON rh.rental_id = r.id")
        for r_obj in c.fetchall():
            r = dict(r_obj)
            if keyword and keyword not in str(r.get('bill_no', '')).lower() and keyword not in str(r.get('name', '')).lower():
                continue
            dt_str = r['date_time']
            try:
                parts = dt_str.split(' ', 1)
                d_part = parts[0]
                t_part = parts[1] if len(parts) > 1 else "12:00 AM"
                row_dt = parse_datetime(d_part, t_part)
            except: continue
            if not (start_dt <= row_dt <= end_dt): continue

            amt = safe_float(r['amount'])
            mode = r['payment_mode']
            records.append({
                "dt_sort": row_dt, "dt_disp": dt_str, "bill": r['bill_no'], "name": r['name'],
                "type": "Refund (Out)", "desc": "Refund Given to Customer",
                "amount": amt, "mode": mode, "tag": "out"
            })
            if mode.lower() in ['upi', 'gpay', 'phonepe', 'online']: gpay_out += amt
            else: cash_out += amt

        c.execute("SELECT i.date_time, r.bill_no, r.name, i.amount, i.payment_mode FROM installments i JOIN rentals r ON i.rental_id = r.id")
        for r_obj in c.fetchall():
            r = dict(r_obj)
            if keyword and keyword not in str(r.get('bill_no', '')).lower() and keyword not in str(r.get('name', '')).lower():
                continue
            dt_str = r['date_time']
            try:
                parts = dt_str.split(' ', 1)
                d_part = parts[0]
                t_part = parts[1] if len(parts) > 1 else "12:00 AM"
                row_dt = parse_datetime(d_part, t_part)
            except: continue
            if not (start_dt <= row_dt <= end_dt): continue

            amt = safe_float(r['amount'])
            mode = r['payment_mode']
            records.append({
                "dt_sort": row_dt, "dt_disp": dt_str, "bill": r['bill_no'], "name": r['name'],
                "type": "Installment (In)", "desc": "Partial Payment Added",
                "amount": amt, "mode": mode, "tag": "in"
            })
            if mode.lower() in ['upi', 'gpay', 'phonepe', 'online']: gpay_in += amt
            else: cash_in += amt

        records.sort(key=lambda x: x['dt_sort'])

        rows = []
        for rec in records:
            amt_str = f"₹{rec['amount']:.2f}" if isinstance(rec['amount'], float) else rec['amount']
            rows.append({"values": [_s(rec['dt_disp']), _s(rec['bill']), _s(rec['name']), rec['type'],
                                    rec['desc'], amt_str, _s(rec['mode'])], "tag": rec['tag']})
        return {
            "ok": True, "rows": rows,
            "cards": {
                "rented": str(rented_qty), "returned": str(returned_qty),
                "cash_in": f"₹{cash_in:,.2f}", "cash_out": f"₹{cash_out:,.2f}",
                "gpay_in": f"₹{gpay_in:,.2f}", "gpay_out": f"₹{gpay_out:,.2f}",
            },
            "totals": {
                "rented": rented_qty, "returned": returned_qty,
                "cash_in": cash_in, "cash_out": cash_out,
                "gpay_in": gpay_in, "gpay_out": gpay_out,
            },
        }
    except Exception as e:
        log_error("Load Daily Report", e)
        return {"ok": False, "rows": []}


# ---------------------------------------------------------------------------
# Customer Report tab (port of customer_report_tab.load_data)
# ---------------------------------------------------------------------------

def customer_report(db, search=""):
    keyword = search.strip()
    if not keyword:
        return {"rows": [], "summary": "Enter a name or phone number to view report.", "summary_kind": "muted"}
    rows = []
    try:
        from materials import get_material_by_code
        regular_phones = get_regular_customer_phones(db)
        records = get_customer_history(db, keyword)
        total_billed = 0.0
        total_paid = 0.0
        total_refund = 0.0
        total_balance = 0.0

        def clean_split(d):
            s = str(d).replace('[','').replace(']','').replace("'",'').replace('"','')
            return [x.strip() for x in s.split(',') if x.strip()]

        for record in records:
            row = dict(record)
            if row.get("cancelled"): continue

            codes = clean_split(row.get("machine_codes", ""))
            qtys = clean_split(row.get("quantities", ""))
            raw_machines = clean_split(row.get("machines", ""))

            display_items = []
            max_len = max(len(codes), len(qtys))
            if any(codes):
                for i in range(max_len):
                    c = codes[i] if i < len(codes) else ""
                    q = qtys[i] if i < len(qtys) else "0"
                    if safe_int(q) > 0:
                        name = "Unknown"
                        if c:
                            mat = get_material_by_code(c)
                            if mat: name = mat['name']
                        display_items.append(f"{name}({q})")
            else:
                for m in raw_machines:
                    if len(m) > 1: display_items.append(m)

            machines_str = ", ".join(display_items)

            tot = safe_float(row.get('total', 0))
            adv = safe_float(row.get('advance', 0))
            paid = safe_float(row.get('amount_paid', 0))
            refund = safe_float(row.get('refund', 0))

            db_bal = row.get('balance')
            if db_bal is not None:
                bal = safe_float(db_bal)
            else:
                bal = tot - adv

            tag = ""
            if bal < 0: tag = "negative"
            elif bal > 0: tag = "positive"

            cust_name = row.get("name", "")
            if row.get("phone", "") in regular_phones:
                cust_name += " ⭐"

            rows.append({"values": [
                _s(row.get("bill_no", "")), _s(cust_name), _s(row.get("phone", "")), _s(row.get("date", "")),
                machines_str,
                f"₹{tot:.2f}", f"₹{adv:.2f}",
                _s(row.get("adv_mode", "")),
                _s(row.get("return_date", "") or "Open"),
                f"₹{paid:.2f}", f"₹{refund:.2f}",
                _s(row.get("paid_mode", "")),
                f"₹{bal:.2f}"
            ], "tag": tag})

            total_billed += tot
            total_paid += paid
            total_refund += refund
            total_balance += bal

        summary = (f"Summary — Total Billed: ₹{total_billed:.2f} | Total Paid: ₹{total_paid:.2f} | "
                   f"Total Refund: ₹{total_refund:.2f} | Net Balance: ₹{total_balance:.2f}")
        return {"rows": rows, "summary": summary, "summary_kind": "info",
                "totals": {"billed": total_billed, "paid": total_paid,
                           "refund": total_refund, "balance": total_balance}}
    except Exception as e:
        print(f"[ERROR] {e}")
        return {"rows": rows, "summary": f"Error: {e}", "summary_kind": "error"}


# ---------------------------------------------------------------------------
# Customers (CRM) tab (port of customers_tab.py)
# ---------------------------------------------------------------------------

def customers_table(db, search="", filter="All Customers"):
    out = []
    keyword = f"%{search.strip()}%"
    try:
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = "SELECT * FROM customers WHERE (name LIKE ? OR phone LIKE ?)"
        params = [keyword, keyword]
        if filter == "Regular Only":
            query += " AND is_regular = 1"
        elif filter == "Non-Regular Only":
            query += " AND is_regular = 0"
        query += " ORDER BY name ASC"
        c.execute(query, params)
        for r in c.fetchall():
            is_reg_text = "⭐ YES" if r['is_regular'] else "No"
            name_disp = r['name']
            if r['is_regular']:
                name_disp += " ⭐"
            out.append({
                "id": r['id'], "name": name_disp, "raw_name": _s(r['name']),
                "phone": _s(r['phone']), "phone2": _s(r['phone2']), "address": _s(r['address']),
                "regular": is_reg_text, "is_regular": bool(r['is_regular']),
            })
    except Exception as e:
        log_error("Load Customers", e)
    return out


def save_customer(db, customer_id, name, phone, phone2, address, is_regular):
    name = (name or "").strip()
    phone = (phone or "").strip()
    phone2 = (phone2 or "").strip()
    address = (address or "").strip()
    is_reg = 1 if is_regular else 0
    if not name or not phone:
        raise UserError("Validation Error", "Name and Primary Phone are required!", kind="warning")
    try:
        conn = db.get_connection()
        c = conn.cursor()
        if customer_id:
            c.execute("UPDATE customers SET name=?, phone2=?, address=?, is_regular=? WHERE id=?",
                      (name, phone2, address, is_reg, customer_id))
        else:
            c.execute("INSERT INTO customers (name, phone, phone2, address, is_regular) VALUES (?, ?, ?, ?, ?)",
                      (name, phone, phone2, address, is_reg))
        conn.commit()
    except sqlite3.IntegrityError:
        raise UserError("Duplicate", "A customer with this Primary Phone number already exists!")
    except Exception as e:
        raise UserError("Error", f"Failed to save: {e}")
    return True


# ---------------------------------------------------------------------------
# Analytics tab (reuses AnalyticsDashboard's data methods directly)
# ---------------------------------------------------------------------------

def analytics_kpis(db, pay_filter="All", profit_date=None):
    dashboard = AnalyticsDashboard(db)
    analytics = dashboard.get_pending_analytics()
    if pay_filter == "Returned":
        pay_amt = analytics['pending_payments_returned']
    elif pay_filter == "Not Returned":
        pay_amt = analytics['pending_payments_active']
    else:
        pay_amt = analytics['pending_payments']
    profit = dashboard.get_profit_on_date(profit_date or datetime.now().strftime('%d-%m-%y'))
    return {
        "pending_quantity": str(analytics['pending_quantity']),
        "pending_payments": f"₹{pay_amt:,.2f}",
        "refund_to_be_done": f"₹{analytics['refund_to_be_done']:,.2f}",
        "profit": f"₹{profit:,.2f}",
    }


def analytics_splits(db, from_date, to_date):
    stats = AnalyticsDashboard(db).get_transaction_splits(from_date, to_date)
    return {k: f"₹{stats[k]:,.2f}" for k in ("gpay_in", "gpay_out", "cash_in", "cash_out")}


def analytics_stock(db, search=""):
    kw = search.lower().strip()
    out = []
    for item in AnalyticsDashboard(db).get_stock_status():
        if kw and kw not in item['machine'].lower(): continue
        tag = 'out_of_stock' if item['available'] <= 0 else 'normal'
        out.append({"values": [_s(item['machine']), str(item['total']), str(item['rented']), str(item['available'])], "tag": tag})
    return out


def analytics_top_customers(db, from_date, to_date, limit="15"):
    lim = safe_int(limit, 15)
    if lim <= 0: lim = 15
    rows = []
    for i, customer in enumerate(AnalyticsDashboard(db).get_top_customers(from_date, to_date, lim), 1):
        rows.append([str(i), _s(customer[0]), _s(customer[1]), str(customer[2]), f"₹{safe_float(customer[3]):,.2f}"])
    return {"title": f"🏆 Top {lim} Customers", "limit": lim, "rows": rows}


def delete_old_data(db, start_str, end_str):
    """Port of do_delete() from analytics_dashboard.py (after the user confirmed)."""
    try:
        start_dt = datetime.strptime(start_str, '%d-%m-%y')
        end_dt = datetime.strptime(end_str, '%d-%m-%y') + timedelta(days=1, seconds=-1)
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, date, time FROM rentals")
        to_delete_ids = []
        def parse_dt(d, t="12:00 AM"):
            try: return datetime.strptime(f"{d} {t}", "%d-%m-%y %I:%M %p")
            except: return datetime.min
        for r in c.fetchall():
            if start_dt <= parse_dt(r[1], r[2]) <= end_dt: to_delete_ids.append(r[0])
        if not to_delete_ids:
            return {"deleted": 0, "message": "No records found in this date range."}
        placeholders = ','.join('?' for _ in to_delete_ids)
        for table in ['rental_items', 'returns', 'installments']:
            c.execute(f"DELETE FROM {table} WHERE rental_id IN ({placeholders})", to_delete_ids)
        c.execute(f"UPDATE rentals SET machines='', machine_codes='', quantities='', rents='', total=0, advance=0, cancelled=1 WHERE id IN ({placeholders})", to_delete_ids)
        conn.commit()
        return {"deleted": len(to_delete_ids), "message": f"Successfully deleted {len(to_delete_ids)} transaction records."}
    except Exception as e:
        log_error("Delete Data", e)
        raise UserError("Error", f"Failed to delete data: {e}")


# ---------------------------------------------------------------------------
# Equipment Analytics tab (owner only; port of materials_report_tab.load_data)
# ---------------------------------------------------------------------------

def equipment_analytics(db, from_date, to_date, search=""):
    def parse_datetime(dt_str, t_str=None):
        if not dt_str: return datetime.min
        if not t_str: t_str = "12:00 AM"
        dt_str = dt_str.strip()
        t_str = t_str.strip().upper()
        for fmt in ("%d-%m-%y %I:%M %p", "%d-%m-%Y %I:%M %p", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M %p"):
            try: return datetime.strptime(f"{dt_str} {t_str}", fmt)
            except ValueError: pass
        for fmt in ("%d-%m-%y", "%d-%m-%Y", "%Y-%m-%d"):
            try: return datetime.strptime(dt_str, fmt)
            except ValueError: pass
        return datetime.min

    empty = {"ok": True, "rows": [], "total_revenue": "₹0.00", "top_earner": "-", "top_freq": "-"}
    keyword = search.strip().lower()
    try:
        start_dt = datetime.strptime(from_date, '%d-%m-%y')
        end_dt = datetime.strptime(to_date, '%d-%m-%y') + timedelta(days=1, seconds=-1)
    except Exception as e:
        log_error("Date parsing error", e)
        return {"ok": False, "rows": []}

    try:
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT ret.rental_id as id,
                   r.date as taken_date, r.time as taken_time,
                   ret.return_date as ret_date, ret.return_time as ret_time
            FROM returns ret
            JOIN rentals r ON ret.rental_id = r.id
            WHERE (r.cancelled IS NULL OR r.cancelled = 0)
        """)
        valid_rental_ids = []
        for r in c.fetchall():
            taken_dt = parse_datetime(r['taken_date'], r['taken_time'])
            ret_dt = parse_datetime(r['ret_date'], r['ret_time'])
            if (start_dt <= taken_dt <= end_dt) and (start_dt <= ret_dt <= end_dt):
                if is_record_fully_returned(r['id'], db):
                    bal = calculate_balance_for_record(r['id'], db)
                    if abs(bal) < 0.01:
                        valid_rental_ids.append(r['id'])

        if not valid_rental_ids:
            return empty

        raw_records = []
        batch_size = 900
        for i in range(0, len(valid_rental_ids), batch_size):
            batch = valid_rental_ids[i:i+batch_size]
            placeholders = ','.join(['?'] * len(batch))
            c.execute(f"""
                SELECT ri.machine_name, ri.rental_id, ri.total_price, ret.rental_days
                FROM rental_items ri
                JOIN returns ret ON ri.rental_id = ret.rental_id
                WHERE ri.rental_id IN ({placeholders})
            """, batch)
            raw_records.extend(c.fetchall())

        aggregated = defaultdict(lambda: {"bills": set(), "rev": 0.0})
        for row in raw_records:
            name = row['machine_name']
            if name.endswith(" (with spare)"):
                name = name[:-13]
            days = safe_int(row['rental_days'])
            if days < 1:
                days = 1
            aggregated[name]["bills"].add(row['rental_id'])
            aggregated[name]["rev"] += safe_float(row['total_price']) * days

        records = []
        for name, data in aggregated.items():
            records.append({'machine_name': name, 'freq': len(data['bills']), 'rev': data['rev']})
        records.sort(key=lambda x: x['rev'], reverse=True)

        filtered_records = [rec for rec in records if not (keyword and keyword not in rec['machine_name'].lower())]

        overall_total_revenue = 0.0
        max_freq = 0
        max_rev = 0.0
        top_freq_name = "-"
        top_rev_name = "-"
        for rec in filtered_records:
            overall_total_revenue += safe_float(rec['rev'])
            if safe_float(rec['rev']) > max_rev:
                max_rev = safe_float(rec['rev'])

        rows = []
        for rec in filtered_records:
            m_name = rec['machine_name']
            freq = int(rec['freq'])
            rev = safe_float(rec['rev'])
            if freq > max_freq:
                max_freq = freq
                top_freq_name = m_name
            if rev == max_rev and max_rev > 0:
                top_rev_name = m_name
            contribution = (rev / overall_total_revenue * 100) if overall_total_revenue > 0 else 0
            bar_length = 15
            filled_blocks = int((rev / max_rev) * bar_length) if max_rev > 0 else 0
            bar_str = "█" * filled_blocks + "░" * (bar_length - filled_blocks)
            rows.append({"values": [m_name, f"{freq} Bills", f"{rev:.2f}", f"{contribution:.1f}%", bar_str],
                         "weight": (rev / max_rev) if max_rev > 0 else 0})

        return {
            "ok": True, "rows": rows,
            "total_revenue": f"₹{overall_total_revenue:,.2f}",
            "top_freq": f"{top_freq_name} ({max_freq} Bills)" if max_freq > 0 else "-",
            "top_earner": f"{top_rev_name} (₹{max_rev:,.2f})" if max_rev > 0 else "-",
        }
    except Exception as e:
        log_error("Load Equipment Analytics", e)
        return {"ok": False, "rows": []}
