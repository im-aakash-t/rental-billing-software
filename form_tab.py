# form_tab.py - REFINED VERSION (With Hardware Scanner Integration & Autocomplete)
import tkinter as tk
from tkinter import Frame, StringVar, ttk, messagebox
from datetime import datetime
import os
import webbrowser
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

import materials # Imported to access the materials dictionary for the dropdown

# Use shared imports
from shared_imports import (
    backup_files, get_material_by_code, generate_next_bill_no,
    has_return_entry, has_pending_returns, get_record_by_id, cancel_rental,
    BillingError, safe_float, safe_int, callbacks,
    calculate_rental_total, log_error
)

from form_logic import (
    clear_form_fields, submit_form, load_table as logic_load_table,
    on_row_select as logic_on_row_select, print_bill as logic_print_bill,
    setup_phone_suggestions, setup_phone2_suggestions, calculate_balance_for_record
)

from return_logic import get_total_past_dues
from return_form import create_return_form

from analytics_dashboard import CustomDatePicker

MAX_MACHINES_PER_BILL = 5
FORM_FONT = ("Segoe UI", 10)   
LABEL_FONT = ("Segoe UI", 10) 
HEADER_FONT = ("Segoe UI", 10, "bold")
TABLE_FONT = ("Segoe UI", 11)

class EnhancedTooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window: return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("Segoe UI", 9))
        label.pack(ipadx=2)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
        self.tip_window = None

def create_form_tab(tab_control, db):
    style = ttk.Style()
    
    style.configure("Form.TEntry", padding=(2, 2, 2, 2)) 
    style.configure("Form.TButton", font=("Segoe UI", 10, "bold"), padding=(6, 2))
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=(5, 5))
    style.configure("Treeview", font=TABLE_FONT, rowheight=26) 
    style.configure("TLabelframe.Label", font=("Segoe UI", 11, "bold"), foreground="#2176ff")
    style.configure("Big.TRadiobutton", font=("Segoe UI", 10))

    tab = Frame(tab_control, bg="#f5f5f5")
    tab_control.add(tab, text='📋 Outward Billing')

    main_paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
    main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    form_frame = Frame(main_paned, bg="#f5f5f5", padx=2, pady=2)
    table_frame = Frame(main_paned, bg="#f5f5f5", padx=2, pady=2)
    
    main_paned.add(form_frame, weight=1) 
    main_paned.add(table_frame, weight=1) 

    name_var = StringVar()
    phone_var = StringVar()
    phone2_var = StringVar()
    id_proof_var = StringVar()
    vehicle_var = StringVar()
    total_var = StringVar(value="0.00")
    advance_var = StringVar()
    date_var = StringVar(value=datetime.now().strftime('%d-%m-%y'))
    time_var = StringVar(value=datetime.now().strftime('%I:%M %p'))
    payment_mode_var = StringVar(value="Cash")
    cashier_name_var = StringVar()
    current_bill_no = StringVar(value=generate_next_bill_no(db))
    current_mode = StringVar(value="new")
    record_id_var = StringVar()
    search_var = StringVar()
    balance_var = StringVar(value="0.00")
    past_due_var = StringVar(value="0.00") 
    pending_returns_var = StringVar(value="No")
    customer_credit_var = StringVar(value="0.00")

    machine_code_vars = [StringVar() for _ in range(MAX_MACHINES_PER_BILL)]
    machine_name_vars = [StringVar() for _ in range(MAX_MACHINES_PER_BILL)]
    quantity_vars = [StringVar() for _ in range(MAX_MACHINES_PER_BILL)]
    rent_vars = [StringVar() for _ in range(MAX_MACHINES_PER_BILL)]

    details_frame = ttk.LabelFrame(form_frame, text="👤 Customer Details", padding=5)
    machines_frame = ttk.LabelFrame(form_frame, text="🔧 Machine Details", padding=5)
    summary_frame = ttk.LabelFrame(form_frame, text="💰 Summary", padding=5)
    
    details_frame.pack(fill="x", pady=(0, 4))
    machines_frame.pack(fill="x", pady=(0, 4))
    summary_frame.pack(fill="x", pady=(0, 4))

    PAD_Y = 2 
    PAD_X = 5

    ttk.Label(details_frame, text="Name:*", font=LABEL_FONT).grid(row=0, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    name_entry = ttk.Entry(details_frame, textvariable=name_var, width=45, font=FORM_FONT, style="Form.TEntry")
    name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=PAD_X, pady=PAD_Y)
    EnhancedTooltip(name_entry, "Enter customer full name")

    ttk.Label(details_frame, text="Phone:*", font=LABEL_FONT).grid(row=1, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    phone_entry = ttk.Entry(details_frame, textvariable=phone_var, width=45, font=FORM_FONT, style="Form.TEntry")
    phone_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=PAD_X, pady=PAD_Y)
    EnhancedTooltip(phone_entry, "Primary phone number (10 digits)")

    suggestion_box = tk.Listbox(details_frame, height=3, font=FORM_FONT, width=45)
    suggestion_box.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(0, 0))
    suggestion_box.grid_remove()

    ttk.Label(details_frame, text="Phone 2:", font=LABEL_FONT).grid(row=3, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    phone2_entry = ttk.Entry(details_frame, textvariable=phone2_var, width=45, font=FORM_FONT, style="Form.TEntry")
    phone2_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=PAD_X, pady=PAD_Y)

    suggestion_box2 = tk.Listbox(details_frame, height=3, font=FORM_FONT, width=45)
    suggestion_box2.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(0, 0))
    suggestion_box2.grid_remove()

    ttk.Label(details_frame, text="Address:", font=LABEL_FONT).grid(row=5, column=0, sticky="ne", padx=PAD_X, pady=PAD_Y)
    address_text = tk.Text(details_frame, height=2, font=FORM_FONT, width=45, wrap="word")
    address_text.grid(row=5, column=1, columnspan=2, sticky="ew", padx=PAD_X, pady=PAD_Y)

    # --- NEW SCANNER INTEGRATION SECTION ---
    ttk.Label(details_frame, text="ID Proof:", font=LABEL_FONT).grid(row=6, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    
    id_frame = ttk.Frame(details_frame)
    id_frame.grid(row=6, column=1, columnspan=2, sticky="ew", padx=PAD_X, pady=PAD_Y)
    
    id_proof_entry = ttk.Entry(id_frame, textvariable=id_proof_var, width=32, font=FORM_FONT, style="Form.TEntry")
    id_proof_entry.pack(side="left", fill="x", expand=True)
    
    def on_scan_click():
        bill = current_bill_no.get()
        name = name_var.get().strip()
        id_type = id_proof_var.get().strip()
        
        if not name or not id_type:
            messagebox.showwarning("Incomplete Data", "Please enter the Customer Name and ID Proof Type (e.g. 'Aadhar') before scanning!")
            return
            
        try:
            from scanner_helper import scan_and_save_id
            scan_status_lbl.config(text="⏳ Scanning...", foreground="orange")
            id_frame.update_idletasks() # Force UI update before scanner pauses app
            
            saved_path = scan_and_save_id(bill, name, id_type)
            
            if saved_path:
                scan_status_lbl.config(text="✅ Saved", foreground="green")
            else:
                scan_status_lbl.config(text="") # Cleared or Cancelled
        except ImportError:
            messagebox.showerror("Error", "scanner_helper.py missing! Cannot scan.")
            scan_status_lbl.config(text="")

    scan_btn = ttk.Button(id_frame, text="🖨️", width=8, command=on_scan_click)
    scan_btn.pack(side="left", padx=(5, 5))
    
    scan_status_lbl = ttk.Label(id_frame, text="", font=("Segoe UI", 9, "bold"), width=9)
    scan_status_lbl.pack(side="left")
    # ---------------------------------------

    details_frame.columnconfigure(1, weight=1)

    setup_phone_suggestions(phone_var, name_var, address_text, suggestion_box, db, phone2_var, balance_var, pending_returns_var, past_due_var)
    setup_phone2_suggestions(phone2_var, name_var, address_text, suggestion_box2, db, phone_var, balance_var, pending_returns_var, past_due_var)

    ttk.Label(machines_frame, text="Code", font=HEADER_FONT).grid(row=0, column=0, padx=PAD_X, pady=0)
    ttk.Label(machines_frame, text="Machine Name", font=HEADER_FONT).grid(row=0, column=1, padx=PAD_X, pady=0)
    ttk.Label(machines_frame, text="Qty", font=HEADER_FONT).grid(row=0, column=2, padx=PAD_X, pady=0)
    ttk.Label(machines_frame, text="Rent/Day", font=HEADER_FONT).grid(row=0, column=3, padx=PAD_X, pady=0)

    def update_total(*args):
        try:
            total = sum(safe_float(rent_vars[i].get() or 0) for i in range(MAX_MACHINES_PER_BILL))
            total_var.set(f"{total:.2f}")
        except Exception:
            total_var.set("0.00")

    machine_entries = []
    machine_comboboxes = [] # Track comboboxes for autocomplete
    
    for i in range(MAX_MACHINES_PER_BILL):
        code_entry = ttk.Entry(machines_frame, textvariable=machine_code_vars[i], width=8, font=FORM_FONT, style="Form.TEntry")
        code_entry.grid(row=i + 1, column=0, padx=PAD_X, pady=1)
        
        # --- NEW: Standard Entry (NO ARROW) ---
        m_name_entry = ttk.Entry(machines_frame, textvariable=machine_name_vars[i], width=50, font=FORM_FONT, style="Form.TEntry")
        m_name_entry.grid(row=i + 1, column=1, padx=PAD_X, pady=1)
        
        # --- NEW: Hidden floating listbox for suggestions ---
        suggestion_box = tk.Listbox(machines_frame, height=4, font=FORM_FONT)

        qty_entry = ttk.Entry(machines_frame, textvariable=quantity_vars[i], width=6, font=FORM_FONT, style="Form.TEntry")
        qty_entry.grid(row=i + 1, column=2, padx=PAD_X, pady=1)

        rent_entry = ttk.Entry(machines_frame, textvariable=rent_vars[i], width=10, font=FORM_FONT, style="Form.TEntry")
        rent_entry.grid(row=i + 1, column=3, padx=PAD_X, pady=1)

        machine_entries.extend([code_entry, m_name_entry, qty_entry, rent_entry])

        def make_handlers(idx, name_entry, sugg_box):
            is_updating = {"code": False, "name": False}

            def on_code_change(*args):
                if is_updating["code"]: return
                code = machine_code_vars[idx].get().strip().upper()
                
                mat = get_material_by_code(code) if code else None
                if mat:
                    is_updating["name"] = True
                    machine_name_vars[idx].set(mat["name"])
                    is_updating["name"] = False
                    
                    if not quantity_vars[idx].get():
                        quantity_vars[idx].set("1")
                        
                    try: qty = int(quantity_vars[idx].get())
                    except ValueError: qty = 1
                    rent_vars[idx].set(str(mat["price"] * qty))

            def on_qty_change(*args):
                code = machine_code_vars[idx].get().strip()
                mat = get_material_by_code(code) if code else None
                if mat:
                    try: qty = int(quantity_vars[idx].get())
                    except ValueError: qty = 0
                    rent_vars[idx].set(str(mat["price"] * qty))

            # --- NEW: Dedicated Auto-Fill Helper ---
            def check_and_fill_from_name(search_name):
                matched_code = None
                # Search the dictionary for an exact name match
                for c, m in materials.materials_dict.items():
                    if m['name'].lower() == search_name.lower():
                        matched_code = c
                        break
                
                if matched_code:
                    is_updating["code"] = True
                    machine_code_vars[idx].set(matched_code)
                    is_updating["code"] = False
                    
                    # Auto-set Qty to 1 if blank
                    if not quantity_vars[idx].get():
                        quantity_vars[idx].set("1")
                        
                    try: qty = int(quantity_vars[idx].get())
                    except ValueError: qty = 1
                    
                    # Update Rent
                    rent_vars[idx].set(str(materials.materials_dict[matched_code]["price"] * qty))

            def on_type(event):
                if is_updating["name"]: return
                
                # Safely ignore system keys without causing errors
                if hasattr(event, 'keysym') and event.keysym in ['Up', 'Down', 'Return', 'Escape', 'Tab']: return

                name = machine_name_vars[idx].get().strip()
                
                if name:
                    # Update the floating suggestion list
                    matches = [m['name'] for m in materials.materials_dict.values() if name.lower() in m['name'].lower()]
                    if matches:
                        sugg_box.delete(0, tk.END)
                        for m in matches:
                            sugg_box.insert(tk.END, m)
                        sugg_box.place(in_=name_entry, x=0, rely=1, relwidth=1)
                        sugg_box.lift()
                    else:
                        sugg_box.place_forget()
                else:
                    sugg_box.place_forget()

                # Try to auto-fill if what they typed exactly matches a machine
                check_and_fill_from_name(name)

            def on_select(event):
                if not sugg_box.curselection(): return
                selected = sugg_box.get(sugg_box.curselection())
                
                is_updating["name"] = True
                machine_name_vars[idx].set(selected)
                is_updating["name"] = False
                
                sugg_box.place_forget() # Hide the list
                name_entry.icursor(tk.END) # Move cursor to the end
                
                # Instantly auto-fill code, qty, and rent using the clicked name!
                check_and_fill_from_name(selected)

            def hide_box(event):
                # Tiny delay so the click registers before the box disappears
                sugg_box.after(150, sugg_box.place_forget)

            name_entry.bind('<KeyRelease>', on_type)
            name_entry.bind('<FocusOut>', hide_box)
            sugg_box.bind('<<ListboxSelect>>', on_select)

            return on_code_change, on_qty_change

        # Attach the logic to each row
        code_cb, qty_cb = make_handlers(i, m_name_entry, suggestion_box)
        machine_code_vars[i].trace_add("write", code_cb)
        quantity_vars[i].trace_add("write", qty_cb)
        rent_vars[i].trace_add("write", update_total)

    summary_left = tk.Frame(summary_frame, bg="#f5f5f5")
    summary_right = tk.Frame(summary_frame, bg="#f5f5f5")
    summary_left.pack(side="left", fill="both", expand=True, padx=5)
    summary_right.pack(side="right", fill="both", expand=True, padx=5)

    ttk.Label(summary_left, text="Date:", font=HEADER_FONT).grid(row=0, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    date_entry = ttk.Entry(summary_left, textvariable=date_var, width=18, font=FORM_FONT, style="Form.TEntry")
    date_entry.grid(row=0, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)

    ttk.Label(summary_left, text="Time:", font=HEADER_FONT).grid(row=1, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    time_entry = ttk.Entry(summary_left, textvariable=time_var, width=18, font=FORM_FONT, style="Form.TEntry")
    time_entry.grid(row=1, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)

    ttk.Label(summary_left, text="Pending Returns:", font=HEADER_FONT).grid(row=2, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    ttk.Entry(summary_left, textvariable=pending_returns_var, width=18, font=FORM_FONT, state="readonly", style="Form.TEntry").grid(row=2, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)

    ttk.Label(summary_left, text="Vehicle No.:", font=HEADER_FONT).grid(row=3, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    vehicle_entry = ttk.Entry(summary_left, textvariable=vehicle_var, width=18, font=FORM_FONT, style="Form.TEntry")
    vehicle_entry.grid(row=3, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)

    edit_btn = ttk.Button(summary_left, text="✏️ Edit Record", command=lambda: set_form_state('normal'), style="Form.TButton")
    edit_btn.grid(row=4, column=0, columnspan=2, sticky="ew", padx=PAD_X, pady=(10, 0))
    edit_btn.grid_remove()

    ttk.Label(summary_right, text="Daily Rent:", font=HEADER_FONT).grid(row=0, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    daily_rent_entry = ttk.Entry(summary_right, textvariable=total_var, width=18, font=FORM_FONT, style="Form.TEntry")
    daily_rent_entry.grid(row=0, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)

    ttk.Label(summary_right, text="Past Due:", font=HEADER_FONT).grid(row=1, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    pd_entry = ttk.Entry(summary_right, textvariable=past_due_var, width=18, font=FORM_FONT, state="readonly", style="Form.TEntry")
    pd_entry.grid(row=1, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)

    ttk.Label(summary_right, text="Balance Due:", font=HEADER_FONT).grid(row=2, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    bal_entry = ttk.Entry(summary_right, textvariable=balance_var, width=18, font=FORM_FONT, state="readonly", style="Form.TEntry")
    bal_entry.grid(row=2, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)

    ttk.Label(summary_right, text="Advance Paid:", font=HEADER_FONT).grid(row=3, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    advance_entry = ttk.Entry(summary_right, textvariable=advance_var, width=18, font=FORM_FONT, style="Form.TEntry")
    advance_entry.grid(row=3, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)
    
    pm_frame = ttk.Frame(summary_right)
    pm_frame.grid(row=4, column=1, sticky="w", padx=2, pady=PAD_Y)
    
    style.configure("Big.TRadiobutton", font=("Segoe UI", 10))
    pm_radio1 = ttk.Radiobutton(pm_frame, text="Cash", variable=payment_mode_var, value="Cash", style="Big.TRadiobutton")
    pm_radio1.pack(side="left", padx=2)
    pm_radio2 = ttk.Radiobutton(pm_frame, text="UPI", variable=payment_mode_var, value="UPI", style="Big.TRadiobutton")
    pm_radio2.pack(side="left", padx=2)
    
    ttk.Label(summary_right, text="Cashier Name:*", font=HEADER_FONT).grid(row=5, column=0, sticky="e", padx=PAD_X, pady=PAD_Y)
    cashier_entry = ttk.Entry(summary_right, textvariable=cashier_name_var, width=18, font=FORM_FONT, style="Form.TEntry")
    cashier_entry.grid(row=5, column=1, sticky="w", padx=PAD_X, pady=PAD_Y)

    def set_form_state(state):
        editable_widgets = [
            name_entry, phone_entry, phone2_entry, id_proof_entry,
            date_entry, time_entry, vehicle_entry,
            daily_rent_entry, advance_entry, cashier_entry
        ] + machine_entries
        
        for w in editable_widgets:
            w.configure(state=state)
            
        pm_radio1.configure(state=state)
        pm_radio2.configure(state=state)
        address_text.configure(state=state)
        
        scan_btn.configure(state='disabled' if state == 'disabled' else 'normal')
        
        if state == 'disabled':
            edit_btn.grid() 
        else:
            edit_btn.grid_remove() 

    def calculate_form_balance(*args):
        if current_mode.get() == "edit": return 
        try:
            tot = safe_float(total_var.get())
            adv = safe_float(advance_var.get())
            current_bill_bal = tot - adv
            balance_var.set(f"{current_bill_bal:.2f}") 
        except:
            balance_var.set("0.00")
            
    total_var.trace_add("write", calculate_form_balance)
    advance_var.trace_add("write", calculate_form_balance)

    def update_balance_and_pending(phone_number, specific_rental_id=None):
        phone_number = phone_number.strip()
        if not phone_number:
            balance_var.set("0.00")
            past_due_var.set("0.00")
            pending_returns_var.set("No")
            return
        
        latest_rental_id = None
        try:
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("""SELECT id FROM rentals WHERE phone = ? AND (cancelled IS NULL OR cancelled = 0) ORDER BY id DESC LIMIT 1""", (phone_number,))
            res = c.fetchone()
            if res: latest_rental_id = res[0]
        except: pass

        if specific_rental_id:
            current_bal = calculate_balance_for_record(specific_rental_id, db)
            past_dues = get_total_past_dues(db, phone_number, specific_rental_id)
            
            balance_var.set(f"{current_bal:.2f}")
            past_due_var.set(f"{past_dues:.2f}")
        else:
            past_dues = get_total_past_dues(db, phone_number, None)
            past_due_var.set(f"{past_dues:.2f}")
        
        pending = has_pending_returns(phone_number, db)
        pending_returns_var.set("Yes" if pending else "No")

    phone_var.trace_add("write", lambda *_: update_balance_and_pending(phone_var.get()))

    def_vars = {
            "name": name_var, "phone": phone_var, "phone2": phone2_var,
            "id_proof": id_proof_var, "vehicle": vehicle_var,
            "total": total_var, "advance": advance_var,
            "date": date_var, "time": time_var,
            "payment_mode": payment_mode_var,
            "cashier_name": cashier_name_var,
            "bill_no": current_bill_no, "mode": current_mode,
            "machine_codes": machine_code_vars, "machine_names": machine_name_vars,
            "quantities": quantity_vars, "rents": rent_vars,
            "record_id": record_id_var,
            "db": db,
            "balance_var": balance_var,
            "past_due_var": past_due_var
        }

    def wrapped_clear_form():
        # --- FIX: We MUST unlock the form BEFORE trying to clear the text boxes! ---
        set_form_state('normal') 
        clear_form_fields(def_vars, address_text)
        scan_status_lbl.config(text="")

    btn_frame = ttk.Frame(form_frame) 
    btn_frame.pack(side="bottom", fill="x", pady=5) 

    btn_inner = ttk.Frame(btn_frame)
    btn_inner.pack(anchor="center")

    def cancel_current_rental():
        if not record_id_var.get():
            messagebox.showwarning("No Selection", "Please select a rental to cancel.")
            return
        if messagebox.askyesno("Confirm Cancellation", "Cancel this rental? Undo is not possible."):
            try:
                cancel_rental(record_id_var.get(), db)
                messagebox.showinfo("Success", "Rental cancelled.")
                wrapped_clear_form()
                try:
                    if callbacks.reload_all_tabs: callbacks.reload_all_tabs()
                    else: load_table()
                except:
                    load_table()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    ttk.Button(btn_inner, text="💾 Submit", style="Form.TButton", 
               command=lambda: submit_form(def_vars, address_text, db, wrapped_clear_form, load_table), 
               width=9).pack(side="left", padx=2)
        
    ttk.Button(btn_inner, text="Clear", style="Form.TButton", command=wrapped_clear_form, 
               width=8).pack(side="left", padx=2)
        
    ttk.Button(btn_inner, text="📄 Estimate", style="Form.TButton", 
                command=lambda: logic_print_bill(table, db, def_vars, image_path="Estimate-Bill.png"), 
                width=10).pack(side="left", padx=2)

    ttk.Button(btn_inner, text="🧾 Tax Inv.", style="Form.TButton", 
                command=lambda: logic_print_bill(table, db, def_vars, image_path="Tax-Invoice.png"), 
                width=10).pack(side="left", padx=2)

    ttk.Button(btn_inner, text="Backup", style="Form.TButton", command=backup_files, 
               width=9).pack(side="left", padx=2)

    ttk.Button(btn_inner, text="Cancel", style="Form.TButton", command=cancel_current_rental, 
               width=9).pack(side="left", padx=2)

    search_frame = ttk.Frame(table_frame)
    search_frame.pack(fill="x", pady=(0, 2))
    
    ttk.Label(search_frame, text="🔍 Search:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 5))
    search_entry = ttk.Entry(search_frame, textvariable=search_var, width=20, font=("Segoe UI", 10))
    search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

    def print_outward_list():
        if not table.get_children():
            messagebox.showinfo("No Data", "There is no data to print.")
            return
            
        try:
            os.makedirs("reports", exist_ok=True)
            filepath = os.path.join("reports", f"Outward_List_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            
            doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
            elements = []
            styles = getSampleStyleSheet()
            
            title = Paragraph(f"<b>Outward Billing List</b> - Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title'])
            elements.append(title)
            elements.append(Paragraph("<br/><br/>", styles['Normal']))
            
            data = [["Bill No", "Name", "Phone", "Address", "Date", "Balance", "Pending Items"]]
            
            for item_id in table.get_children():
                values = table.item(item_id, "values")
                addr_p = Paragraph(values[4], styles["Normal"]) 
                row_data = [values[0], values[1], values[2], addr_p, values[5], values[6], values[7]]
                data.append(row_data)
                
            t = Table(data, colWidths=[70, 140, 100, 250, 80, 80, 80])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2176ff")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 11),
                ('BOTTOMPADDING', (0,0), (-1,0), 10),
                ('TOPPADDING', (0,0), (-1,0), 10),
                ('BACKGROUND', (0,1), (-1,-1), colors.white),
                ('GRID', (0,0), (-1,-1), 1, colors.lightgrey),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            
            elements.append(t)
            doc.build(elements)
            webbrowser.open(filepath)
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to generate report: {e}")

    ttk.Button(search_frame, text="🖨️ Print List", command=print_outward_list).pack(side="right", padx=5)

    filter_frame = ttk.Frame(table_frame)
    filter_frame.pack(fill="x", pady=2)
    
    row1 = ttk.Frame(filter_frame)
    row1.pack(fill="x", pady=2)
    
    filter_var = tk.StringVar(value="all")
    ttk.Label(row1, text="Status Filter:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 5))
    ttk.Radiobutton(row1, text="All", variable=filter_var, value="all").pack(side="left", padx=(0, 5))
    ttk.Radiobutton(row1, text="Pending Returns", variable=filter_var, value="pending").pack(side="left", padx=(0, 5))
    ttk.Radiobutton(row1, text="Balance Due", variable=filter_var, value="balance").pack(side="left", padx=(0, 5))
    
    row2 = ttk.Frame(filter_frame)
    row2.pack(fill="x", pady=2)
    
    from_date_var = tk.StringVar()
    to_date_var = tk.StringVar()
    from_bill_var = tk.StringVar()
    to_bill_var = tk.StringVar()
    
    ttk.Label(row2, text="Date From:", font=("Segoe UI", 9)).pack(side="left")
    ttk.Button(row2, textvariable=from_date_var, width=10, command=lambda: CustomDatePicker(table_frame, from_date_var.get(), from_date_var.set)).pack(side="left", padx=(0, 5))
    
    ttk.Label(row2, text="To:", font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))
    ttk.Button(row2, textvariable=to_date_var, width=10, command=lambda: CustomDatePicker(table_frame, to_date_var.get(), to_date_var.set)).pack(side="left", padx=(0, 10))
    
    ttk.Label(row2, text="Bill No From:", font=("Segoe UI", 9)).pack(side="left")
    ttk.Entry(row2, textvariable=from_bill_var, width=8, font=("Segoe UI", 9)).pack(side="left", padx=(0, 5))
    
    ttk.Label(row2, text="To:", font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))
    ttk.Entry(row2, textvariable=to_bill_var, width=8, font=("Segoe UI", 9)).pack(side="left", padx=(0, 15))
    
    def clear_all_filters():
        from_date_var.set("")
        to_date_var.set("")
        from_bill_var.set("")
        to_bill_var.set("")
        filter_var.set("all")
        search_var.set("")
        
    ttk.Button(row2, text="✖ Clear Filters", command=clear_all_filters).pack(side="left")

    table_area = Frame(table_frame)
    table_area.pack(fill="both", expand=True)
    
    table_area.grid_rowconfigure(0, weight=1)
    table_area.grid_columnconfigure(0, weight=1)

    cols = ("Bill No", "Name", "Phone", "Phone 2", "Address", "Date", "Balance", "Pending")
    
    table = ttk.Treeview(table_area, columns=cols, show="headings", height=8)
    
    table_scroll_y = ttk.Scrollbar(table_area, orient="vertical", command=table.yview)
    table_scroll_x = ttk.Scrollbar(table_area, orient="horizontal", command=table.xview)
    
    table.configure(yscrollcommand=table_scroll_y.set, xscrollcommand=table_scroll_x.set)
    
    table.grid(row=0, column=0, sticky="nsew")
    table_scroll_y.grid(row=0, column=1, sticky="ns")
    table_scroll_x.grid(row=1, column=0, sticky="ew")
    
    col_widths = {
        "Bill No": 80, "Name": 130, "Phone": 100, "Phone 2": 100, 
        "Address": 200, "Date": 90, "Balance": 100, "Pending": 80
    }
    
    for col in cols:
        table.heading(col, text=col)
        table.column(col, width=col_widths.get(col, 100), anchor="center" if col != "Address" and col != "Name" else "w")

    table.tag_configure("returned", foreground="green", font=("Segoe UI", 11, "bold"))
    table.tag_configure("not_returned", foreground="red", font=TABLE_FONT)

    return_area = Frame(table_frame, bg="#f5f5f5")
    return_area.pack(fill="x", pady=5) 
    return_form_widget = create_return_form(return_area, db)
    update_return_fields_from_selection = return_form_widget["update_return_fields_from_selection"]

    def load_table(limit=10000):
        try:
            logic_load_table(
                search_var, filter_var, from_date_var, to_date_var, 
                from_bill_var, to_bill_var, table, db, 
                has_return_entry, has_pending_returns, limit=limit
            )
        except Exception as e: messagebox.showerror("Error", str(e))

    search_var.trace_add("write", lambda *_: load_table())
    filter_var.trace_add("write", lambda *_: load_table())
    from_date_var.trace_add("write", lambda *_: load_table())
    to_date_var.trace_add("write", lambda *_: load_table())
    from_bill_var.trace_add("write", lambda *_: load_table())
    to_bill_var.trace_add("write", lambda *_: load_table())

    def on_row_select_with_balance(event):
        logic_on_row_select(event, table, db, def_vars, address_text)
        selected = table.selection()
        if selected:
            values = table.item(selected[0], "values")
            record = get_record_by_id(values[0], db)
            if record:
                update_return_fields_from_selection(db, record['id'])
                update_balance_and_pending(record.get('phone', ''), record['id'])
                set_form_state('disabled') 

    table.bind("<<TreeviewSelect>>", on_row_select_with_balance)

    def on_key_press(event):
        if event.state & 0x4:
            if event.keysym == 'n': wrapped_clear_form()
            elif event.keysym == 's': submit_form(def_vars, address_text, db, wrapped_clear_form, load_table)
            elif event.keysym == 'p': logic_print_bill(table, db, def_vars)

    tab.bind_all("<Control-n>", on_key_press)
    tab.bind_all("<Control-s>", on_key_press)
    tab.bind_all("<Control-p>", on_key_press)

    load_table()

    return {
        "frame": tab,
        "reload": load_table,
        "update_return_fields_from_selection": update_return_fields_from_selection
    }