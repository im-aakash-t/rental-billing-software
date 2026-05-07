# pending_tab.py - REFINED VERSION (With Refund Filter)
import tkinter as tk
from tkinter import ttk, messagebox
import callbacks
import os
import sqlite3
import webbrowser
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from utils import safe_float, log_error

def create_pending_tab(tab_control, db):
    tab = ttk.Frame(tab_control)
    tab_control.add(tab, text="Pending / Refunds")

    # --- TOP CONTROL FRAME ---
    top_frame = ttk.Frame(tab)
    top_frame.pack(fill="x", padx=10, pady=10)
    
    # Search Box
    search_var = tk.StringVar()
    ttk.Label(top_frame, text="🔍 Search:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 5))
    search_entry = ttk.Entry(top_frame, textvariable=search_var, width=25, font=("Segoe UI", 10))
    search_entry.pack(side="left", padx=(0, 20))

    # --- THE NEW FILTER SYSTEM ---
    filter_var = tk.StringVar(value="all")
    ttk.Label(top_frame, text="Filter:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 5))
    
    style = ttk.Style()
    style.configure("Filter.TRadiobutton", font=("Segoe UI", 10))
    
    ttk.Radiobutton(top_frame, text="All", variable=filter_var, value="all", style="Filter.TRadiobutton").pack(side="left", padx=5)
    ttk.Radiobutton(top_frame, text="🔴 To Collect (Debt)", variable=filter_var, value="collect", style="Filter.TRadiobutton").pack(side="left", padx=5)
    ttk.Radiobutton(top_frame, text="🟢 To Refund", variable=filter_var, value="refund", style="Filter.TRadiobutton").pack(side="left", padx=5)
    
    return_status_var = tk.StringVar(value="all")
    ttk.Label(top_frame, text=" |  Status:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(10, 5))
    ttk.Radiobutton(top_frame, text="All", variable=return_status_var, value="all", style="Filter.TRadiobutton").pack(side="left", padx=5)
    ttk.Radiobutton(top_frame, text="Returned", variable=return_status_var, value="returned", style="Filter.TRadiobutton").pack(side="left", padx=5)
    ttk.Radiobutton(top_frame, text="Not Returned", variable=return_status_var, value="not_returned", style="Filter.TRadiobutton").pack(side="left", padx=5)

    def print_pending_list():
        if not tree.get_children():
            messagebox.showinfo("No Data", "There is no data to print.")
            return
        try:
            os.makedirs("reports", exist_ok=True)
            
            # Change report title based on filter
            f_type = filter_var.get()
            if f_type == "collect": title_text = "Pending Collections (Debt) Report"
            elif f_type == "refund": title_text = "Pending Refunds Report"
            else: title_text = "All Pending Payments & Refunds Report"
            
            filepath = os.path.join("reports", f"Pending_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
            elements = []
            styles = getSampleStyleSheet()
            
            title = Paragraph(f"<b>{title_text}</b> - {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title'])
            elements.append(title)
            elements.append(Paragraph("<br/><br/>", styles['Normal']))
            data = [["Bill No", "Name", "Phone", "Date", "Due", "Advance", "Paid", "Balance"]]
            
            for item_id in tree.get_children():
                values = tree.item(item_id, "values")
                data.append(list(values))
                
            t = Table(data, colWidths=[70, 150, 100, 80, 80, 80, 80, 100])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2176ff")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
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

    ttk.Button(top_frame, text="🖨️ Print List", command=print_pending_list).pack(side="right", padx=5)

    # --- TABLE SETUP ---
    columns = ("Bill No", "Name", "Phone", "Date", "Due", "Advance", "Paid", "Balance")
    tree = ttk.Treeview(tab, columns=columns, show="headings", height=20)

    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="center", width=100)
        
    tree.pack(fill="both", expand=True, padx=10, pady=5)
    
    tree.tag_configure("debt", foreground="red")
    tree.tag_configure("refund", foreground="green", font=("Segoe UI", 10, "bold"))

    def load_pending_data(*_):
        # Master Engine Imported safely locally to avoid circular bugs
        from shared_imports import calculate_master_balance, calculate_rental_days_unified

        keyword = search_var.get().lower().strip()
        current_filter = filter_var.get()
        current_return_status = return_status_var.get()
        
        tree.delete(*tree.get_children())
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        all_data = []

        # 1. Closed Rentals (Returns) -> Calculate true live balance
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

        # 2. Active Rentals -> Calculate true live balance
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

        # Sort globally
        all_data.sort(key=lambda x: x["balance"], reverse=True)
        
        for row in all_data:
            # Apply Search Filter
            if keyword and keyword not in row["name"].lower() and keyword not in row["phone"]:
                continue
            
            # Apply Category Filter (Debt vs Refund)
            if current_filter == "collect" and row["balance"] < 0:
                continue
            if current_filter == "refund" and row["balance"] > 0:
                continue
                
            # Apply Return Status Filter
            if current_return_status == "returned" and not row["is_returned"]:
                continue
            if current_return_status == "not_returned" and row["is_returned"]:
                continue
            
            tag = "debt" if row["balance"] > 0 else "refund"
            tree.insert("", "end", values=(
                row["bill_no"], row["name"], row["phone"], row["date"],
                f"{row['due_amount']:.2f}", f"{row['advance']:.2f}",
                f"{row['amount_paid']:.2f}", f"{row['balance']:.2f}"
            ), tags=(tag,))

    # Bind variables to trigger table reload on change
    search_var.trace_add("write", load_pending_data)
    filter_var.trace_add("write", load_pending_data)
    return_status_var.trace_add("write", load_pending_data)
    
    load_pending_data()
    callbacks.pending_reload_table = load_pending_data

    return {"frame": tab, "reload": load_pending_data}