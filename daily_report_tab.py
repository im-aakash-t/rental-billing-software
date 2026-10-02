# daily_report_tab.py - REFINED VERSION (Imports Master Calendar)
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import webbrowser
from datetime import datetime, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from utils import safe_float, safe_int, log_error

# --- FIX: Import the CustomDatePicker from the Analytics file instead of duplicating it ---
from analytics_dashboard import CustomDatePicker

def create_daily_report_tab(tab_control, db):
    tab = ttk.Frame(tab_control)
    tab_control.add(tab, text="📅 Day's Overview")

    top_frame = ttk.Frame(tab)
    top_frame.pack(fill="x", padx=10, pady=10)

    from_date_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
    to_date_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
    search_var = tk.StringVar() 
    
    def on_from_date_selected(new_date):
        from_date_var.set(new_date)
        load_daily_data()

    def on_to_date_selected(new_date):
        to_date_var.set(new_date)
        load_daily_data()

    ttk.Label(top_frame, text="From:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 5))
    from_btn = ttk.Button(top_frame, textvariable=from_date_var, width=12, command=lambda: CustomDatePicker(tab, from_date_var.get(), on_from_date_selected))
    from_btn.pack(side="left", padx=5)

    ttk.Label(top_frame, text="To:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(15, 5))
    to_btn = ttk.Button(top_frame, textvariable=to_date_var, width=12, command=lambda: CustomDatePicker(tab, to_date_var.get(), on_to_date_selected))
    to_btn.pack(side="left", padx=5)

    ttk.Label(top_frame, text="🔍 Search:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(25, 5))
    search_entry = ttk.Entry(top_frame, textvariable=search_var, width=25, font=("Segoe UI", 11))
    search_entry.pack(side="left", padx=5)
    
    search_var.trace_add("write", lambda *_: load_daily_data())

    def print_daily_report():
        if not tree.get_children():
            messagebox.showinfo("No Data", "There are no transactions in this date range to print.")
            return
            
        try:
            os.makedirs("reports", exist_ok=True)
            filepath = os.path.join("reports", f"Overview_Report_{from_date_var.get()}_to_{to_date_var.get()}_{datetime.now().strftime('%H%M%S')}.pdf")
            doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
            elements = []
            styles = getSampleStyleSheet()
            
            title = Paragraph(f"<b>Overview Report</b> - From: {from_date_var.get()} To: {to_date_var.get()}", styles['Title'])
            elements.append(title)
            
            summary_text = f"""
            <b>Rented Items:</b> {vars_cache['rented']} | <b>Returned Items:</b> {vars_cache['returned']}<br/>
            <b>Cash In:</b> Rs. {vars_cache['cash_in']:.2f} | <b>Cash Out:</b> Rs. {vars_cache['cash_out']:.2f}<br/>
            <b>UPI/GPay In:</b> Rs. {vars_cache['gpay_in']:.2f} | <b>UPI/GPay Out:</b> Rs. {vars_cache['gpay_out']:.2f}
            """
            elements.append(Paragraph(summary_text, styles['Normal']))
            elements.append(Paragraph("<br/><br/>", styles['Normal']))
            
            data = [["Date & Time", "Bill No", "Customer Name", "Transaction Type", "Details", "Amount", "Mode"]]
            
            for item_id in tree.get_children():
                values = tree.item(item_id, "values")
                data.append(list(values))
                
            t = Table(data, colWidths=[100, 60, 140, 110, 220, 80, 60])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2176ff")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 10),
                ('BOTTOMPADDING', (0,0), (-1,0), 8),
                ('TOPPADDING', (0,0), (-1,0), 8),
                ('BACKGROUND', (0,1), (-1,-1), colors.white),
                ('GRID', (0,0), (-1,-1), 1, colors.lightgrey),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            
            elements.append(t)
            doc.build(elements)
            webbrowser.open(filepath)
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to generate report: {e}")

    ttk.Button(top_frame, text="🖨️ Print Ledger", command=print_daily_report).pack(side="right", padx=5)

    cards_frame = ttk.Frame(tab)
    cards_frame.pack(fill="x", padx=10, pady=5)
    for i in range(6): cards_frame.columnconfigure(i, weight=1)

    labels = {}
    metrics = [
        ("rented", "📦 Rented Items", "#ff9800"),
        ("returned", "🔄 Returned Items", "#2196F3"),
        ("cash_in", "💵 Cash In (+)", "#4CAF50"),
        ("cash_out", "💸 Cash Out (-)", "#f44336"),
        ("gpay_in", "📱 GPay In (+)", "#4CAF50"),
        ("gpay_out", "💳 GPay Out (-)", "#f44336")
    ]
    
    for i, (key, title, color) in enumerate(metrics):
        card = ttk.Frame(cards_frame, style='Card.TFrame')
        card.grid(row=0, column=i, padx=5, sticky="nsew")
        ttk.Label(card, text=title, font=("Segoe UI", 9, "bold")).pack(pady=(5, 2))
        lbl = ttk.Label(card, text="0", font=("Segoe UI", 14, "bold"), foreground=color)
        lbl.pack(pady=(0, 5))
        labels[key] = lbl

    tree_frame = ttk.Frame(tab)
    tree_frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    columns = ("DateTime", "Bill No", "Customer Name", "Type", "Details", "Amount", "Mode")
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)
    
    tree.heading("DateTime", text="Date & Time")
    tree.heading("Bill No", text="Bill No")
    tree.heading("Customer Name", text="Customer Name")
    tree.heading("Type", text="Type")
    tree.heading("Details", text="Details")
    tree.heading("Amount", text="Amount (₹)")
    tree.heading("Mode", text="Mode")

    tree.column("DateTime", width=120, anchor="center")
    tree.column("Bill No", width=80, anchor="center")
    tree.column("Customer Name", width=150)
    tree.column("Type", width=120, anchor="center")
    tree.column("Details", width=250)
    tree.column("Amount", width=90, anchor="e")
    tree.column("Mode", width=80, anchor="center")

    tree.tag_configure("in", foreground="green")
    tree.tag_configure("out", foreground="red")
    tree.tag_configure("neutral", foreground="black")

    scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    vars_cache = {}

    def clean_split(d):
        if not d: return []
        s = str(d).replace('[','').replace(']','').replace("'",'').replace('"','')
        return [x.strip() for x in s.split(',') if x.strip()]

    def parse_datetime(dt_str, t_str="12:00 AM"):
        try: return datetime.strptime(f"{dt_str} {t_str}", "%d-%m-%y %I:%M %p")
        except: return datetime.min

    def load_daily_data():
        keyword = search_var.get().strip().lower()
        for item in tree.get_children(): tree.delete(item)
        cash_in = gpay_in = cash_out = gpay_out = 0.0
        rented_qty = returned_qty = 0
        records = []
        
        try:
            start_dt = datetime.strptime(from_date_var.get(), '%d-%m-%y')
            end_dt = datetime.strptime(to_date_var.get(), '%d-%m-%y') + timedelta(days=1, seconds=-1)
        except Exception as e:
            log_error("Date parsing error", e)
            return
            
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
                qtys = clean_split(r['returned_quantities'])
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
            
            for rec in records:
                amt_str = f"₹{rec['amount']:.2f}" if isinstance(rec['amount'], float) else rec['amount']
                tree.insert("", "end", values=(
                    rec['dt_disp'], rec['bill'], rec['name'], rec['type'], rec['desc'], amt_str, rec['mode']
                ), tags=(rec['tag'],))
                
            labels["rented"].config(text=str(rented_qty))
            labels["returned"].config(text=str(returned_qty))
            labels["cash_in"].config(text=f"₹{cash_in:,.2f}")
            labels["cash_out"].config(text=f"₹{cash_out:,.2f}")
            labels["gpay_in"].config(text=f"₹{gpay_in:,.2f}")
            labels["gpay_out"].config(text=f"₹{gpay_out:,.2f}")
            
            vars_cache.update({
                "rented": rented_qty, "returned": returned_qty,
                "cash_in": cash_in, "cash_out": cash_out,
                "gpay_in": gpay_in, "gpay_out": gpay_out
            })

        except Exception as e:
            log_error("Load Daily Report", e)

    load_daily_data()
    return {"frame": tab, "reload": load_daily_data}