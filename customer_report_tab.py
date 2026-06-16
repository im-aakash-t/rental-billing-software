# customer_report_tab.py - REFINED VERSION (With Bill No)
import tkinter as tk
from tkinter import ttk, messagebox
import callbacks
import os
import webbrowser
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from utils import safe_float, safe_int, log_error
from materials import get_material_by_code

def create_customer_report_tab(tab_control, db):
    tab = ttk.Frame(tab_control)
    tab_control.add(tab, text="Customer Report")

    tab.grid_columnconfigure(0, weight=1)
    tab.grid_rowconfigure(2, weight=1) 

    search_frame = ttk.Frame(tab)
    search_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
    
    search_var = tk.StringVar()
    ttk.Label(search_frame, text="🔍 Search (Name or Phone):", font=("Segoe UI", 11, "bold")).pack(side="left", padx=5)
    search_entry = ttk.Entry(search_frame, textvariable=search_var, width=30, font=("Segoe UI", 11))
    search_entry.pack(side="left", padx=5)
    
    ttk.Button(search_frame, text="🔄 Refresh", command=lambda: load_data()).pack(side="left", padx=10)

    def print_customer_report():
        if not tree.get_children():
            messagebox.showinfo("No Data", "There is no data to print.")
            return
            
        try:
            os.makedirs("reports", exist_ok=True)
            filepath = os.path.join("reports", f"Customer_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            
            doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
            elements = []
            styles = getSampleStyleSheet()
            
            title = Paragraph(f"<b>Customer Report</b> - Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title'])
            elements.append(title)
            elements.append(Paragraph("<br/><br/>", styles['Normal']))
            
            data = [["Bill No", "Name", "Phone", "Date", "Machines", "Total", "Adv", "Return Dt", "Paid", "Refund", "Balance"]]
            
            for item_id in tree.get_children():
                values = tree.item(item_id, "values")
                machines_p = Paragraph(values[4], styles["Normal"])
                row_data = [
                    values[0], values[1], values[2], values[3], machines_p, 
                    values[5], values[6], values[8], values[9], values[10], values[12]
                ]
                data.append(row_data)
                
            t = Table(data, colWidths=[70, 90, 80, 60, 160, 50, 50, 70, 50, 50, 60])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2176ff")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
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
            log_error("Print Customer Report", e)

    ttk.Button(search_frame, text="🖨️ Print List", command=print_customer_report).pack(side="right", padx=5)

    summary_lbl = ttk.Label(tab, text="", font=("Segoe UI", 11, "bold"))
    summary_lbl.grid(row=1, column=0, sticky="w", padx=10, pady=5)

    tree_frame = ttk.Frame(tab)
    tree_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
    
    tree_frame.grid_columnconfigure(0, weight=1)
    tree_frame.grid_rowconfigure(0, weight=1)

    columns = ("Bill No", "Name", "Phone", "Date", "Machines", "Total",
               "Advance", "Adv Mode", "Return Date", "Paid", "Refund", "Paid Mode", "Balance")
    
    tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
    tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
    
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", 
                        yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set,
                        height=15)
    
    tree_scroll_y.config(command=tree.yview)
    tree_scroll_x.config(command=tree.xview)
    
    tree.grid(row=0, column=0, sticky="nsew")
    tree_scroll_y.grid(row=0, column=1, sticky="ns")
    tree_scroll_x.grid(row=1, column=0, sticky="ew")
    
    tree.heading("Bill No", text="Bill No")
    tree.column("Bill No", width=80, anchor="center")
    tree.heading("Name", text="Name")
    tree.column("Name", width=120, anchor="w")
    tree.heading("Phone", text="Phone")
    tree.column("Phone", width=100, anchor="center")
    tree.heading("Date", text="Date")
    tree.column("Date", width=90, anchor="center")
    tree.heading("Machines", text="Machines")
    tree.column("Machines", width=250, anchor="w") 
    
    for col in ["Total", "Advance", "Paid", "Refund", "Balance"]:
        tree.heading(col, text=col)
        tree.column(col, width=80, anchor="e")
        
    for col in ["Adv Mode", "Paid Mode", "Return Date"]:
        tree.heading(col, text=col)
        tree.column(col, width=80, anchor="center")
        
    tree.tag_configure("negative", foreground="green") 
    tree.tag_configure("positive", foreground="red")   

    def load_data(*_):
        tree.delete(*tree.get_children())
        keyword = search_var.get().strip()
        
        if not keyword:
            summary_lbl.config(text="Enter a name or phone number to view report.")
            return
        
        try:
            from shared_imports import get_regular_customer_phones, get_customer_history
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

                tree.insert("", "end", values=(
                    row.get("bill_no", ""), # Use bill_no here
                    cust_name, 
                    row.get("phone", ""), 
                    row.get("date", ""),
                    machines_str,
                    f"₹{tot:.2f}",
                    f"₹{adv:.2f}",
                    row.get("adv_mode", ""), 
                    row.get("return_date", "") or "Open",
                    f"₹{paid:.2f}",
                    f"₹{refund:.2f}",
                    row.get("paid_mode", ""),
                    f"₹{bal:.2f}"
                ), tags=(tag,))
                
                total_billed += tot
                total_paid += paid
                total_refund += refund
                total_balance += bal
                    
            summary_lbl.config(
                text=f"Summary — Total Billed: ₹{total_billed:.2f} | Total Paid: ₹{total_paid:.2f} | Total Refund: ₹{total_refund:.2f} | Net Balance: ₹{total_balance:.2f}",
                foreground="#2176ff"
            )
            
        except Exception as e:
            summary_lbl.config(text=f"Error: {e}", foreground="red")
            print(f"[ERROR] {e}")

    search_var.trace_add("write", load_data)
    callbacks.customer_report_reload_table = load_data

    return {
        "frame": tab,
        "reload": load_data
    }