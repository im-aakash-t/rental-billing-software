# materials_report_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import os
import csv
import webbrowser
from datetime import datetime, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from utils import safe_float, safe_int, log_error

from analytics_dashboard import CustomDatePicker

def create_materials_report_tab(tab_control, db):
    tab = ttk.Frame(tab_control)
    tab_control.add(tab, text="📦 Equipment Analytics")

    # --- TOP CONTROL FRAME ---
    top_frame = ttk.Frame(tab)
    top_frame.pack(fill="x", padx=10, pady=10)

    from_date_var = tk.StringVar(value=(datetime.now() - timedelta(days=60)).strftime('%d-%m-%y'))
    to_date_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
    search_var = tk.StringVar() 
    
    def on_from_date_selected(new_date):
        from_date_var.set(new_date)
        load_data()

    def on_to_date_selected(new_date):
        to_date_var.set(new_date)
        load_data()

    ttk.Label(top_frame, text="From:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 5))
    from_btn = ttk.Button(top_frame, textvariable=from_date_var, width=12, command=lambda: CustomDatePicker(tab, from_date_var.get(), on_from_date_selected))
    from_btn.pack(side="left", padx=5)

    ttk.Label(top_frame, text="To:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(15, 5))
    to_btn = ttk.Button(top_frame, textvariable=to_date_var, width=12, command=lambda: CustomDatePicker(tab, to_date_var.get(), on_to_date_selected))
    to_btn.pack(side="left", padx=5)

    ttk.Label(top_frame, text="🔍 Search:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(25, 5))
    search_entry = ttk.Entry(top_frame, textvariable=search_var, width=25, font=("Segoe UI", 11))
    search_entry.pack(side="left", padx=5)
    
    search_var.trace_add("write", lambda *_: load_data())

    def export_csv():
        if not tree.get_children():
            messagebox.showinfo("No Data", "There are no records to export.")
            return
            
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Save as Excel/CSV"
        )
        if not filepath:
            return
            
        try:
            with open(filepath, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(["Equipment Type", "Rental Frequency (Bills)", "Total Revenue (Rs.)", "Contribution (%)"])
                for item_id in tree.get_children():
                    values = tree.item(item_id, "values")
                    # Exclude the visual bar from the CSV export
                    writer.writerow(values[:4])
            messagebox.showinfo("Success", f"Data exported successfully to\n{os.path.basename(filepath)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export data: {e}")

    def print_report():
        if not tree.get_children():
            messagebox.showinfo("No Data", "There are no records to print.")
            return
            
        try:
            os.makedirs("reports", exist_ok=True)
            filepath = os.path.join("reports", f"Equipment_Analytics_{from_date_var.get()}_to_{to_date_var.get()}_{datetime.now().strftime('%H%M%S')}.pdf")
            doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
            elements = []
            styles = getSampleStyleSheet()
            
            title = Paragraph(f"<b>Equipment Analytics Report</b> - From: {from_date_var.get()} To: {to_date_var.get()}", styles['Title'])
            elements.append(title)
            
            summary_text = f"<b>Total Revenue:</b> {tot_rev_var.get()} &nbsp;&nbsp; | &nbsp;&nbsp; <b>Top Earner:</b> {top_earner_var.get()} &nbsp;&nbsp; | &nbsp;&nbsp; <b>Most Frequent:</b> {top_freq_var.get()}"
            elements.append(Paragraph(summary_text, styles['Normal']))
            elements.append(Paragraph("<br/><br/>", styles['Normal']))
            
            data = [["Equipment Type", "Rental Frequency (Bills)", "Total Revenue (Rs.)", "Contribution (%)"]]
            
            for item_id in tree.get_children():
                values = tree.item(item_id, "values")
                data.append(list(values[:4])) # Exclude visual bar
                
            t = Table(data, colWidths=[250, 150, 150, 150])
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

    # Buttons Container
    btn_frame = ttk.Frame(top_frame)
    btn_frame.pack(side="right")
    
    ttk.Button(btn_frame, text="📊 Export CSV", command=export_csv).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="🖨️ Print Report", command=print_report).pack(side="left", padx=5)

    # --- SUMMARY CARDS FRAME ---
    summary_frame = ttk.Frame(tab)
    summary_frame.pack(fill="x", padx=10, pady=(0, 10))

    tot_rev_var = tk.StringVar(value="₹0.00")
    top_freq_var = tk.StringVar(value="-")
    top_earner_var = tk.StringVar(value="-")

    def create_summary_card(parent, title, text_var, color):
        card = ttk.LabelFrame(parent, text=title)
        card.pack(side="left", fill="x", expand=True, padx=5)
        lbl = ttk.Label(card, textvariable=text_var, font=("Segoe UI", 12, "bold"), foreground=color)
        lbl.pack(pady=8, padx=10)

    create_summary_card(summary_frame, "💰 Total Revenue", tot_rev_var, "#007F5F")
    create_summary_card(summary_frame, "🔥 Top Earning Equipment", top_earner_var, "#2176ff")
    create_summary_card(summary_frame, "📈 Most Frequent on Bills", top_freq_var, "#D90429")

    # --- TREEVIEW FRAME ---
    tree_frame = ttk.Frame(tab)
    tree_frame.pack(fill="both", expand=True, padx=10, pady=5)
    
    columns = ("Equipment Type", "Rental Frequency", "Total Revenue", "Contribution (%)", "Visual Trend")
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)
    
    tree.heading("Equipment Type", text="Equipment Type")
    tree.heading("Rental Frequency", text="Frequency (No. of Bills)")
    tree.heading("Total Revenue", text="Total Revenue (₹)")
    tree.heading("Contribution (%)", text="Contribution (%)")
    tree.heading("Visual Trend", text="Visual Revenue Weight")

    tree.column("Equipment Type", width=250, anchor="w")
    tree.column("Rental Frequency", width=150, anchor="center")
    tree.column("Total Revenue", width=120, anchor="e")
    tree.column("Contribution (%)", width=120, anchor="center")
    tree.column("Visual Trend", width=150, anchor="w")

    scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    def parse_datetime(dt_str, t_str=None):
        if not dt_str: return datetime.min
        if not t_str: t_str = "12:00 AM"
        dt_str = dt_str.strip()
        t_str = t_str.strip().upper()
        # Try full datetime formats
        for fmt in ("%d-%m-%y %I:%M %p", "%d-%m-%Y %I:%M %p", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M %p"):
            try: return datetime.strptime(f"{dt_str} {t_str}", fmt)
            except ValueError: pass
        # Try date-only formats
        for fmt in ("%d-%m-%y", "%d-%m-%Y", "%Y-%m-%d"):
            try: return datetime.strptime(dt_str, fmt)
            except ValueError: pass
        return datetime.min

    def load_data():
        keyword = search_var.get().strip().lower()
        for item in tree.get_children(): tree.delete(item)
        
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
            
            # Imports to filter completed bills
            from form_logic import calculate_balance_for_record, is_record_fully_returned

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
                
                # Check that BOTH taken date and return date fall within the filter range
                if (start_dt <= taken_dt <= end_dt) and (start_dt <= ret_dt <= end_dt):
                    # Filter only completed bills: net balance is 0 and all items returned
                    if is_record_fully_returned(r['id'], db):
                        bal = calculate_balance_for_record(r['id'], db)
                        if abs(bal) < 0.01:
                            valid_rental_ids.append(r['id'])
                    
            if not valid_rental_ids:
                tot_rev_var.set("₹0.00")
                top_freq_var.set("-")
                top_earner_var.set("-")
                return
                
            # Batch query to prevent SQLite limit of 999 variables
            # JOIN returns to get the exact rental_days for correct revenue computation
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

            # Aggregate in Python using actual duration billing (total_price * rental_days)
            from collections import defaultdict
            aggregated = defaultdict(lambda: {"bills": set(), "rev": 0.0})
            for row in raw_records:
                name = row['machine_name']
                days = safe_int(row['rental_days'])
                if days < 1:
                    days = 1
                aggregated[name]["bills"].add(row['rental_id'])
                aggregated[name]["rev"] += safe_float(row['total_price']) * days

            # Convert to a sorted list of dicts
            records = []
            for name, data in aggregated.items():
                records.append({
                    'machine_name': name,
                    'freq': len(data['bills']),
                    'rev': data['rev']
                })
            records.sort(key=lambda x: x['rev'], reverse=True)
            
            # Filter by keyword first so that summary cards and totals match search filters
            filtered_records = []
            for rec in records:
                m_name = rec['machine_name']
                if keyword and keyword not in m_name.lower():
                    continue
                filtered_records.append(rec)
            
            overall_total_revenue = 0.0
            max_freq = 0
            max_rev = 0.0
            top_freq_name = "-"
            top_rev_name = "-"
            
            # Pass 1: Calculate totals and max values for visual bars
            for rec in filtered_records:
                overall_total_revenue += safe_float(rec['rev'])
                if safe_float(rec['rev']) > max_rev:
                    max_rev = safe_float(rec['rev'])
            
            # Pass 2: Populate treeview and identify top earner/freq
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
                
                # Visual Bar calculation (15 blocks max)
                bar_length = 15
                filled_blocks = int((rev / max_rev) * bar_length) if max_rev > 0 else 0
                bar_str = "█" * filled_blocks + "░" * (bar_length - filled_blocks)
                    
                tree.insert("", "end", values=(
                    m_name,
                    f"{freq} Bills",
                    f"{rev:.2f}",
                    f"{contribution:.1f}%",
                    bar_str
                ))
            
            tot_rev_var.set(f"₹{overall_total_revenue:,.2f}")
            top_freq_var.set(f"{top_freq_name} ({max_freq} Bills)" if max_freq > 0 else "-")
            top_earner_var.set(f"{top_rev_name} (₹{max_rev:,.2f})" if max_rev > 0 else "-")

        except Exception as e:
            log_error("Load Equipment Analytics", e)

    load_data()
    return {"frame": tab, "reload": load_data}