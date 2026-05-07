# return_form.py - FIXED VERSION (Restored Paid Lock, Restored Missing Field Loads, Fixed Freeze)
from tkinter import Frame, ttk, StringVar, BooleanVar, messagebox
import tkinter as tk
from datetime import datetime
from return_logic import (
    get_full_rental_details, save_return_data,
    generate_return_pdf, should_freeze_return_fields,
    get_total_past_dues, split_rental_bill,
    save_installment, get_installments 
)
from billing import generate_bill, get_record_by_id
from materials import get_material_by_code
from utils import log_error, safe_float, safe_int, sync_lists
from shared_imports import calculate_master_balance 
import callbacks 

FORM_FONT = ("Segoe UI", 10)
HEADER_FONT = ("Segoe UI", 10, "bold")
BUTTON_FONT = ("Segoe UI", 10, "bold")

class CustomStepper(tk.Frame):
    def __init__(self, parent, textvariable):
        super().__init__(parent, bg="#f5f5f5")
        self.var = textvariable
        self.max_val = 0
        self.state_flag = "disabled"

        BORDER = "#d0d0d0"
        
        f1 = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        f1.pack(side="left", padx=(0, 1))
        self.btn_minus = tk.Button(f1, text="−", width=2, relief="flat", command=self.decrement, 
                                   font=("Segoe UI", 10, "bold"), bg="#ffffff", activebackground="#f0f0f0", cursor="hand2")
        self.btn_minus.pack(ipady=0)

        f2 = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        f2.pack(side="left")
        self.entry = tk.Entry(f2, textvariable=self.var, width=3, font=("Segoe UI", 10), 
                              justify="center", relief="flat", bg="#f4f4f4")
        self.entry.pack(ipady=1)

        f3 = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        f3.pack(side="left", padx=(1, 0))
        self.btn_plus = tk.Button(f3, text="+", width=2, relief="flat", command=self.increment, 
                                  font=("Segoe UI", 10, "bold"), bg="#ffffff", activebackground="#f0f0f0", cursor="hand2")
        self.btn_plus.pack(ipady=0)
        
        self.var.trace_add("write", self._validate)
        self._update_state()

    def increment(self):
        if self.state_flag == "disabled": return
        try: val = int(self.var.get() or 0)
        except ValueError: val = 0
        if val < self.max_val:
            self.var.set(str(val + 1))

    def decrement(self):
        if self.state_flag == "disabled": return
        try: val = int(self.var.get() or 0)
        except ValueError: val = 0
        if val > 0:
            self.var.set(str(val - 1))

    def _validate(self, *args):
        if self.state_flag == "disabled": return
        val_str = self.var.get()
        if not val_str: return
        try:
            val = int(val_str)
            if val > self.max_val: self.var.set(str(self.max_val)) 
            elif val < 0: self.var.set("0")
        except ValueError: pass 

    def _update_state(self):
        st = tk.NORMAL if self.state_flag == "normal" else tk.DISABLED
        bg_color = "#ffffff" if st == tk.NORMAL else "#e0e0e0"
        self.btn_minus.config(state=st, bg=bg_color)
        self.btn_plus.config(state=st, bg=bg_color)
        self.entry.config(state=st, disabledbackground="#e0e0e0")

    def config(self, **kwargs):
        if 'state' in kwargs:
            self.state_flag = kwargs['state']
            self._update_state()
        if 'to' in kwargs: self.max_val = int(kwargs['to'])


def create_return_form(parent, db):
    fields = {}
    frame = ttk.LabelFrame(parent, text="Return Processing", padding=5)
    frame.pack(fill="x", padx=5, pady=2)
    
    style = ttk.Style()
    style.configure("TLabelframe.Label", font=("Segoe UI", 11, "bold"), foreground="#2176ff")
    style.configure("Ret.TButton", font=BUTTON_FONT, padding=(6, 3))

    field_configs = {
        "rental_id": StringVar(), "date": StringVar(value=datetime.now().strftime("%d-%m-%y")),
        "time": StringVar(value=datetime.now().strftime("%I:%M %p")), "rental_days": StringVar(value="1"),
        "due": StringVar(value="0.00"), "deduction": StringVar(value="0.00"),
        "damage": StringVar(value="0.00"), "advance": StringVar(value="0.00"),
        "past_due": StringVar(value="0.00"), "refund": StringVar(value="0.00"), 
        "amount_paid": StringVar(value="0.00"), "balance": StringVar(value="0.00"),
        "payment_mode": StringVar(value="Cash")
    }
    fields.update(field_configs)

    rents = []
    rental_machine_codes = []
    rented_quantities_ref = [] 
    rental_start_date = None
    rental_start_time = None
    loading = True
    calculation_frozen = False
    current_phone = None
    balance_entry_widget = None

    main_left_frame = ttk.Frame(frame)
    main_left_frame.grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=2, rowspan=2)

    returned_qty_frame = ttk.LabelFrame(frame, text="Return Quantities", padding=2)
    returned_qty_frame.grid(row=0, column=1, sticky="nw", pady=2)

    payment_history_frame = ttk.LabelFrame(frame, text="Payment History", padding=2)
    payment_history_frame.grid(row=1, column=1, sticky="nsew", pady=2)

    machine_name_labels = []
    spinbox_vars = []
    spinboxes = []
    
    for i in range(5):
        lbl = ttk.Label(returned_qty_frame, text="", font=HEADER_FONT, width=25)
        lbl.grid(row=i, column=0, sticky="w", padx=10, pady=1)
        var = StringVar(value="0")
        sp = CustomStepper(returned_qty_frame, textvariable=var)
        sp.config(state="disabled")
        sp.grid(row=i, column=1, sticky="w", padx=10, pady=1)
        machine_name_labels.append(lbl)
        spinbox_vars.append(var)
        spinboxes.append(sp)

    history_tree = ttk.Treeview(payment_history_frame, columns=("Date", "Amount", "Mode", "Cashier"), show="headings", height=2)
    history_tree.heading("Date", text="Date & Time")
    history_tree.heading("Amount", text="Amount")
    history_tree.heading("Mode", text="Mode")
    history_tree.heading("Cashier", text="Cashier")
    history_tree.column("Date", width=140)
    history_tree.column("Amount", width=80, anchor="e")
    history_tree.column("Mode", width=70, anchor="center")
    history_tree.column("Cashier", width=100)
    history_scroll = ttk.Scrollbar(payment_history_frame, orient="vertical", command=history_tree.yview)
    history_tree.configure(yscrollcommand=history_scroll.set)
    history_tree.pack(side="left", fill="both", expand=True)
    history_scroll.pack(side="right", fill="y")

    def open_payment_popup(parent_widget):
        if not fields["rental_id"].get():
            messagebox.showwarning("Error", "Please select a rental record first.")
            return

        popup = tk.Toplevel(parent_widget)
        popup.title("Add Installment Payment")
        popup.geometry("380x280") 
        popup.resizable(False, False)
        popup.transient(parent_widget)
        popup.grab_set()

        popup.update_idletasks()
        x = parent_widget.winfo_rootx() + (parent_widget.winfo_width() // 2) - 190
        y = parent_widget.winfo_rooty() + (parent_widget.winfo_height() // 2) - 140
        popup.geometry(f"+{x}+{y}")

        ttk.Label(popup, text="Payment Amount (₹):", font=HEADER_FONT).pack(pady=(20, 5))
        amt_var = StringVar(value="") 
        ttk.Entry(popup, textvariable=amt_var, font=FORM_FONT, justify="center").pack(pady=5, ipady=4)
        ttk.Label(popup, text="Cashier Name:*", font=HEADER_FONT).pack(pady=(15, 5))
        cashier_var = StringVar()
        ttk.Entry(popup, textvariable=cashier_var, font=FORM_FONT, justify="center").pack(pady=5, ipady=4)

        def add_payment():
            try:
                amt_str = amt_var.get().strip()
                if not amt_str: return
                amt = safe_float(amt_str)
                if amt <= 0: return
                cashier_name = cashier_var.get().strip()
                if not cashier_name: return
                
                rental_id = fields["rental_id"].get()
                date_str = datetime.now().strftime("%d-%m-%y %I:%M %p")
                payment_mode = fields["payment_mode"].get()
                
                save_installment(db, int(rental_id), amt, payment_mode, cashier_name, date_str)
                history_tree.insert("", "end", values=(date_str, f"{amt:.2f}", payment_mode, cashier_name))
                
                current_paid = safe_float(fields["amount_paid"].get())
                fields["amount_paid"].set(f"{current_paid + amt:.2f}")
                
                conn = db.get_connection()
                if conn.cursor().execute("SELECT id FROM returns WHERE rental_id=?", (rental_id,)).fetchone():
                    on_submit(silent=True)
                else:
                    recalc_due() 
                    
                popup.destroy()
            except Exception as e: messagebox.showerror("Error", f"Invalid input: {e}")

        ttk.Button(popup, text="Add Payment", command=add_payment, style="Ret.TButton").pack(pady=20)

    field_layout = [
        ("Return Date:", "date", 0, 0), ("Return Time:", "time", 1, 0), ("Rental Days:", "rental_days", 2, 0),
        ("Damage:", "damage", 3, 0), ("Deduction:", "deduction", 4, 0), ("Payment Mode:", "payment_mode", 5, 0),
        ("Due Amount:", "due", 0, 2), ("Advance:", "advance", 1, 2), ("Past Due:", "past_due", 2, 2),
        ("Refund:", "refund", 3, 2), ("Paid Now:", "amount_paid", 4, 2), ("Net Balance:", "balance", 5, 2)
    ]
    PAD_Y = 2; PAD_X = 5
    widget_refs = {}

    for label, field_key, row, col in field_layout:
        ttk.Label(main_left_frame, text=label, font=HEADER_FONT).grid(row=row, column=col, sticky="e", padx=PAD_X, pady=PAD_Y)
        
        # RESTORED FIX: amount_paid is locked back to readonly to force popup usage
        state = "readonly" if field_key in ["rental_days", "due", "advance", "balance", "past_due", "amount_paid"] else "normal"

        if field_key == "payment_mode":
            payment_frame = ttk.Frame(main_left_frame)
            payment_frame.grid(row=row, column=col+1, sticky="w", padx=PAD_X)
            style.configure("Big.TRadiobutton", font=FORM_FONT)
            widget_refs['pm_radio1'] = ttk.Radiobutton(payment_frame, text="Cash", variable=fields["payment_mode"], value="Cash", style="Big.TRadiobutton")
            widget_refs['pm_radio1'].pack(side="left", padx=2)
            widget_refs['pm_radio2'] = ttk.Radiobutton(payment_frame, text="UPI", variable=fields["payment_mode"], value="UPI", style="Big.TRadiobutton")
            widget_refs['pm_radio2'].pack(side="left", padx=2)
        elif field_key == "amount_paid":
            amt_frame = ttk.Frame(main_left_frame)
            amt_frame.grid(row=row, column=col+1, sticky="w", padx=PAD_X, pady=PAD_Y)
            entry = ttk.Entry(amt_frame, textvariable=fields[field_key], width=8, state=state, font=FORM_FONT)
            entry.pack(side="left")
            widget_refs['add_payment_btn'] = ttk.Button(amt_frame, text="➕", width=3, command=lambda: open_payment_popup(frame))
            widget_refs['add_payment_btn'].pack(side="left", padx=(4,0))
            widget_refs[field_key] = entry
        else:
            entry = ttk.Entry(main_left_frame, textvariable=fields[field_key], width=12, state=state, font=FORM_FONT)
            entry.grid(row=row, column=col+1, sticky="w", padx=PAD_X, pady=PAD_Y)
            if field_key == "past_due": entry.configure(foreground="red")
            if field_key == "refund": entry.configure(foreground="purple")
            if field_key == "balance": 
                entry.configure(font=("Segoe UI", 11, "bold"))
                balance_entry_widget = entry
            if field_key in ["date", "time", "damage", "deduction", "refund"]:
                widget_refs[field_key] = entry

    edit_btn = ttk.Button(main_left_frame, text="✏️ Edit Return (Unfreeze)", command=lambda: set_return_form_state('normal'), style="Ret.TButton")
    edit_btn.grid(row=6, column=0, columnspan=4, sticky="w", padx=PAD_X, pady=5)
    edit_btn.grid_remove()

    button_frame = ttk.Frame(main_left_frame)
    button_frame.grid(row=7, column=0, columnspan=4, pady=(5, 0), sticky="w", padx=PAD_X) 
    
    submit_btn = ttk.Button(button_frame, text="Submit Return", style="Ret.TButton", command=lambda: on_submit())
    submit_btn.pack(side="left", padx=5)
    ttk.Button(button_frame, text="📄 Estimate", style="Ret.TButton", command=lambda: on_print_bill("Estimate-Bill.png")).pack(side="left", padx=5)
    ttk.Button(button_frame, text="🧾 Tax Invoice", style="Ret.TButton", command=lambda: on_print_bill("Tax-Invoice.png")).pack(side="left", padx=5)
    split_btn = ttk.Button(button_frame, text="Split & Close", style="Ret.TButton", command=lambda: on_split_bill())
    split_btn.pack(side="left", padx=5)

    def set_return_form_state(state):
        nonlocal calculation_frozen
        calculation_frozen = (state == 'disabled')
        # Amount paid is not in this list so the field stays readonly naturally, 
        # but we freeze the rest of the actual form entry boxes
        for k in ["date", "time", "damage", "deduction", "refund"]:
            if k in widget_refs: widget_refs[k].configure(state=state)
        
        widget_refs['pm_radio1'].configure(state=state)
        widget_refs['pm_radio2'].configure(state=state)
        if 'add_payment_btn' in widget_refs: widget_refs['add_payment_btn'].configure(state=state)
        
        for sp in spinboxes: sp.config(state=state)
        submit_btn.configure(state=state)
        split_btn.configure(state=state)
        
        if state == 'disabled': edit_btn.grid()
        else:
            edit_btn.grid_remove()
            if not loading: recalc_due()

    def clear_fields():
        set_return_form_state('normal')
        for k, v in fields.items():
            if k == "payment_mode": v.set("Cash")
            elif k == "rental_days": v.set("1")
            else: v.set("0.00" if k in ("due", "deduction", "damage", "advance", "amount_paid", "balance", "past_due", "refund") else "")
        fields["date"].set(datetime.now().strftime("%d-%m-%y"))
        fields["time"].set(datetime.now().strftime("%I:%M %p"))
        for i in range(5):
            machine_name_labels[i].config(text="")
            spinboxes[i].config(from_=0, to=0) 
            spinbox_vars[i].set("0")
        for item in history_tree.get_children(): history_tree.delete(item)
        if balance_entry_widget: balance_entry_widget.configure(foreground="black")

    def safe_parse_date_time(date_str, time_str):
        if not date_str or not time_str: return None
        try: return datetime.strptime(f"{date_str} {time_str}", "%d-%m-%y %I:%M %p")
        except: return None

    def calc_rental_days():
        start_dt = safe_parse_date_time(rental_start_date, rental_start_time)
        end_dt = safe_parse_date_time(fields["date"].get(), fields["time"].get())
        if start_dt and end_dt:
            if end_dt < start_dt: return 1
            delta = end_dt - start_dt
            days = max(delta.days, 0)
            hours = delta.seconds / 3600
            if days == 0 and hours <= 24: return 1
            if hours > 0: days += 1 
            return max(days, 1)
        return 1

    def recalc_due(*args):
        if loading or not rents or calculation_frozen: return
        try:
            rental_days = calc_rental_days()
            daily_rent = sum(safe_float(r) for r in rents)
            
            due_amount, _ = calculate_master_balance(
                daily_rent=daily_rent,
                rental_days=rental_days,
                advance_paid=fields["advance"].get(),
                is_returned=False 
            )
            
            fields["due"].set(f"{due_amount:.2f}")
            fields["rental_days"].set(str(rental_days))
            recalc_balance_only()
        except Exception: fields["due"].set("0.00")

    def recalc_balance_only(*args):
        try:
            daily_rent = sum(safe_float(r) for r in rents) if rents else 0.0
            rental_days = safe_int(fields["rental_days"].get()) or 1
            
            _, net = calculate_master_balance(
                daily_rent=daily_rent,
                rental_days=rental_days,
                advance_paid=fields["advance"].get(),
                installments_paid=0.0, 
                damage_charges=fields["damage"].get(),
                discount_deduction=fields["deduction"].get(),
                final_amount_paid=fields["amount_paid"].get(),
                refund_given=fields["refund"].get(),
                is_returned=True,
                manual_due_override=fields["due"].get() 
            )
            
            fields["balance"].set(f"{net:.2f}")
            
            if balance_entry_widget:
                if net != 0: balance_entry_widget.configure(foreground="red")
                else: balance_entry_widget.configure(foreground="green")
        except: fields["balance"].set("0.00")

    def on_date_time_change(*args):
        if calculation_frozen: return
        recalc_due()

    for child in main_left_frame.winfo_children():
        if isinstance(child, ttk.Entry):
            try:
                var_name = child.cget('textvariable')
                if var_name == str(fields["date"]) or var_name == str(fields["time"]):
                    child.bind("<KeyRelease>", on_date_time_change)
                    child.bind("<FocusOut>", on_date_time_change)
            except: pass

    fields["amount_paid"].trace_add("write", lambda *_: recalc_balance_only())
    fields["deduction"].trace_add("write", lambda *_: recalc_balance_only())
    fields["damage"].trace_add("write", lambda *_: recalc_balance_only())
    fields["refund"].trace_add("write", lambda *_: recalc_balance_only()) 

    def check_if_fully_returned():
        spin_idx = 0
        all_returned = True
        for qty in rented_quantities_ref:
            q = safe_int(qty)
            if q > 0:
                if spin_idx < 5:
                    if safe_int(spinbox_vars[spin_idx].get()) < q:
                        all_returned = False
                    spin_idx += 1
        return all_returned

    def on_split_bill():
        rental_id = fields["rental_id"].get()
        if not rental_id: return
        
        qty_to_return = []
        spin_idx = 0
        for qty in rented_quantities_ref:
            if safe_int(qty) > 0 and spin_idx < 5:
                qty_to_return.append(safe_int(spinbox_vars[spin_idx].get()))
                spin_idx += 1
            else:
                qty_to_return.append(0)
            
        if all(q == 0 for q in qty_to_return):
            messagebox.showwarning("Split Error", "You haven't marked any items as returned.")
            return
        if check_if_fully_returned():
            messagebox.showwarning("Split Error", "You are returning EVERYTHING. Just click Submit.")
            return
            
        if messagebox.askyesno("Confirm Split", "This will keep returned quantities in THIS bill, and move remaining items to a NEW bill.\nProceed?"):
            try:
                new_bill_no = split_rental_bill(db, int(rental_id), qty_to_return)
                messagebox.showinfo("Success", f"Split Successful!\nNew pending bill created: {new_bill_no}")
                update_return_fields_from_selection(db, int(rental_id))
                if callbacks.reload_all_tabs: callbacks.reload_all_tabs()
            except Exception as e:
                messagebox.showerror("Split Failed", str(e))

    def on_print_bill(image_path="bill-layout.jpg"):
        rental_id = fields["rental_id"].get()
        if not rental_id: return
        try:
            record = get_record_by_id(rental_id, db)
            if not record: return
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT machine_name, quantity, total_price FROM rental_items WHERE rental_id=?", (rental_id,))
            items_rows = c.fetchall()
            
            clean_items = [r[0] for r in items_rows]
            clean_qtys = [r[1] for r in items_rows]
            clean_rents = [r[2] for r in items_rows]

            bill_no = record.get("bill_no") or record.get("id")
            generate_bill(
                bill_no=bill_no, date=record.get("date", ""), time=record.get("time", ""),
                address=record.get("address", ""), phone=record.get("phone", ""),
                items=clean_items, qty=clean_qtys, rent=clean_rents, 
                total=fields["due"].get(), advance=record.get("advance", "0"),
                rental_days=fields["rental_days"].get(),
                return_date=fields["date"].get(), return_time=fields["time"].get(),
                background_path=image_path, vehicle=record.get("vehicle", ""),
                name=record.get("name", ""),
                payment_mode=fields["payment_mode"].get()
            )
        except Exception as e: messagebox.showerror("Print Error", f"Failed: {e}")

    def on_submit(silent=False):
        rental_id = fields["rental_id"].get()
        if not rental_id: return
        try:
            full_details = get_full_rental_details(db, int(rental_id))
            final_returned_qtys = []
            final_returned_items = []
            
            spin_idx = 0
            for i, (machine, qty) in enumerate(zip(full_details["machines"], full_details["quantities"])):
                if safe_int(qty) > 0 and spin_idx < 5:
                    final_returned_qtys.append(str(safe_int(spinbox_vars[spin_idx].get())))
                    spin_idx += 1
                else: final_returned_qtys.append("0")
                final_returned_items.append(str(full_details["machine_codes"][i]))

            save_return_data(
                db, rental_id=int(rental_id), return_date=fields["date"].get(), return_time=fields["time"].get(),
                rental_days=fields["rental_days"].get(), due_amount=fields["due"].get(),
                deduction=fields["deduction"].get(), damage=fields["damage"].get(),
                balance=fields["balance"].get(), amount_paid=fields["amount_paid"].get(),
                refund=fields["refund"].get(), 
                returned_items=",".join(final_returned_items), returned_quantities=",".join(final_returned_qtys),
                payment_mode=fields["payment_mode"].get()
            )
            
            if not silent: messagebox.showinfo("Success", "Return details saved.")
            if check_if_fully_returned() and abs(safe_float(fields["balance"].get())) < 0.01:
                set_return_form_state('disabled')
        except Exception as e:
            if not silent: messagebox.showerror("Error", f"Failed to save: {e}")

    def update_return_fields_from_selection(db, rental_id):
        nonlocal rents, rental_start_date, rental_start_time, rental_machine_codes, rented_quantities_ref, loading, calculation_frozen, current_phone
        loading = True
        clear_fields()
        try:
            rental = dict(get_full_rental_details(db, rental_id))
            rents = rental["rents"] 
            rental_start_date = rental["date"]
            rental_start_time = rental["time"]
            rented_quantities_ref = rental["quantities"]
            current_phone = rental["phone"]
            
            fields["rental_id"].set(rental_id)
            fields["advance"].set(f"{safe_float(rental.get('advance', 0.0)):.2f}")

            installments = get_installments(db, int(rental_id))
            total_inst = 0.0
            for inst in installments:
                total_inst += safe_float(inst['amount'])
                history_tree.insert("", "end", values=(
                    inst['date_time'], f"{safe_float(inst['amount']):.2f}", 
                    inst['payment_mode'], inst.get('cashier_name', 'Unknown')
                ))

            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM returns WHERE rental_id = ?", (rental_id,))
            prev_return_row = c.fetchone()
            
            saved_returned_qtys = []

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
                    fields["date"].set(prev_return.get("return_date", ""))
                    fields["time"].set(prev_return.get("return_time", ""))
                else:
                    fields["date"].set(datetime.now().strftime("%d-%m-%y"))
                    fields["time"].set(datetime.now().strftime("%I:%M %p"))
                
                fields["rental_days"].set(str(prev_return.get("rental_days", 1)))
                fields["due"].set(f"{safe_float(prev_return.get('due_amount', 0)):.2f}")
                
                # --- FIXED: LOAD THE MISSING FIELDS ---
                fields["damage"].set(f"{safe_float(prev_return.get('damage', 0)):.2f}")
                fields["deduction"].set(f"{safe_float(prev_return.get('deduction', 0)):.2f}")
                # --------------------------------------

                db_paid = safe_float(prev_return.get('amount_paid', 0))
                fields["amount_paid"].set(f"{max(db_paid, total_inst):.2f}")
                
                fields["refund"].set(f"{safe_float(prev_return.get('refund', 0)):.2f}")
                fields["payment_mode"].set(prev_return.get("payment_mode") or rental.get("payment_mode", "Cash"))
            else:
                fields["amount_paid"].set(f"{total_inst:.2f}")
                fields["payment_mode"].set(rental.get("payment_mode", "Cash"))
                recalc_due() 

            past_dues = get_total_past_dues(db, current_phone, int(rental_id))
            fields["past_due"].set(f"{past_dues:.2f}")

            spin_idx = 0
            for i, (machine, qty) in enumerate(zip(rental["machines"], rental["quantities"])):
                if safe_int(qty) <= 0: continue
                if spin_idx >= 5: break
                
                machine_name_labels[spin_idx].config(text=f"{machine} (Max: {qty})")
                
                default_val = saved_returned_qtys[i] if i < len(saved_returned_qtys) else 0
                
                spinboxes[spin_idx].config(to=safe_int(qty))
                spinbox_vars[spin_idx].set(str(default_val))
                spin_idx += 1

        except Exception as e: log_error("Update return fields", e)
        
        loading = False
        if not calculation_frozen: recalc_due()
        else: recalc_balance_only()

        # FIXED: Move freeze logic here AFTER everything calculates correctly
        try:
            if check_if_fully_returned() and abs(safe_float(fields["balance"].get())) < 0.01:
                set_return_form_state('disabled')
            else:
                set_return_form_state('normal')
        except: pass

    return {"frame": frame, "update_return_fields_from_selection": update_return_fields_from_selection}