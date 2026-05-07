# analytics_dashboard.py - REFINED VERSION (Dynamic Real-Time Refresh)
import tkinter as tk
from tkinter import ttk, messagebox
import csv
import calendar
import os
import sqlite3
import webbrowser
from datetime import datetime, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from utils import safe_float, safe_int, log_error

# --- MASTER CALENDAR COMPONENT ---
class CustomDatePicker(tk.Toplevel):
    def __init__(self, parent, current_date_str, callback):
        super().__init__(parent)
        self.callback = callback
        try: self.current_date = datetime.strptime(current_date_str, '%d-%m-%y')
        except: self.current_date = datetime.now()
        self.year = self.current_date.year
        self.month = self.current_date.month
        self.title("Select Date")
        
        x = parent.winfo_pointerx()
        y = parent.winfo_pointery() + 15
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()
        
        if x + 420 > screen_width: x = screen_width - 430
        if y + 340 > screen_height: y = screen_height - 350
        
        self.geometry(f"420x340+{x}+{y}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.setup_ui()
        
    def setup_ui(self):
        self.configure(padx=10, pady=10)
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(header, text="◀", width=3, command=self.prev_month).pack(side=tk.LEFT)
        self.lbl_month_year = ttk.Label(header, font=("Segoe UI", 10, "bold"), anchor="center")
        self.lbl_month_year.pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(header, text="▶", width=3, command=self.next_month).pack(side=tk.RIGHT)
        
        self.days_frame = ttk.Frame(self)
        self.days_frame.pack(fill=tk.BOTH, expand=True)
        self.update_calendar()
        
    def update_calendar(self):
        for widget in self.days_frame.winfo_children(): widget.destroy()
        month_name = calendar.month_name[self.month]
        self.lbl_month_year.config(text=f"{month_name} {self.year}")
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for i in range(7): self.days_frame.columnconfigure(i, weight=1)
        for i, d in enumerate(days): ttk.Label(self.days_frame, text=d, font=("Segoe UI", 8, "bold"), anchor="center").grid(row=0, column=i, padx=2, pady=5)
            
        cal = calendar.monthcalendar(self.year, self.month)
        for row_idx, week in enumerate(cal):
            for col_idx, day in enumerate(week):
                if day != 0:
                    btn = ttk.Button(self.days_frame, text=str(day), width=3, command=lambda d=day: self.select_date(d))
                    btn.grid(row=row_idx+1, column=col_idx, padx=1, pady=1, sticky="ew")
                    if day == datetime.now().day and self.month == datetime.now().month and self.year == datetime.now().year:
                        btn.state(['pressed'])

    def prev_month(self):
        self.month -= 1
        if self.month == 0: self.month = 12; self.year -= 1
        self.update_calendar()
        
    def next_month(self):
        self.month += 1
        if self.month == 13: self.month = 1; self.year += 1
        self.update_calendar()
        
    def select_date(self, day):
        self.callback(datetime(self.year, self.month, day).strftime('%d-%m-%y'))
        self.destroy()

class AnalyticsDashboard:
    def __init__(self, db):
        self.db = db
        
    def get_pending_analytics(self):
        from shared_imports import calculate_master_balance, calculate_rental_days_unified

        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("""
            SELECT COALESCE(SUM(ri.quantity), 0)
            FROM rental_items ri
            JOIN rentals r ON ri.rental_id = r.id
            WHERE (r.cancelled IS NULL OR r.cancelled = 0)
            AND r.id NOT IN (SELECT rental_id FROM returns)
        """)
        pending_quantity = safe_int(c.fetchone()[0])
        
        c.execute("""
            SELECT r.total as daily_rent, r.advance,
                   ret.rental_days, ret.due_amount,
                   ret.amount_paid, ret.damage, ret.deduction, ret.refund,
                   (SELECT SUM(amount) FROM installments WHERE rental_id = r.id) as inst_paid
            FROM returns ret
            JOIN rentals r ON r.id = ret.rental_id
            WHERE (r.cancelled IS NULL OR r.cancelled = 0)
        """)
        unpaid_returns = 0.0
        refund_returns = 0.0
        for row in c.fetchall():
            _, net_bal = calculate_master_balance(
                daily_rent=row['daily_rent'], rental_days=row['rental_days'],
                advance_paid=row['advance'], installments_paid=row['inst_paid'] or 0.0,
                damage_charges=row['damage'], discount_deduction=row['deduction'],
                final_amount_paid=row['amount_paid'], refund_given=row['refund'],
                is_returned=True, manual_due_override=row['due_amount']
            )
            if net_bal > 0: unpaid_returns += net_bal
            elif net_bal < 0: refund_returns += abs(net_bal)

        c.execute("""
            SELECT r.date, r.time, r.total as daily_rent, r.advance,
                   (SELECT SUM(amount) FROM installments WHERE rental_id = r.id) as inst_paid
            FROM rentals r
            WHERE (r.cancelled IS NULL OR r.cancelled = 0)
              AND r.id NOT IN (SELECT rental_id FROM returns)
        """)
        unpaid_active = 0.0
        refund_active = 0.0
        for row in c.fetchall():
            try: days = calculate_rental_days_unified(row['date'], row['time'])
            except: days = 1
            _, net_bal = calculate_master_balance(
                daily_rent=row['daily_rent'], rental_days=days,
                advance_paid=row['advance'], installments_paid=row['inst_paid'] or 0.0,
                is_returned=False
            )
            if net_bal > 0: unpaid_active += net_bal
            elif net_bal < 0: refund_active += abs(net_bal)
                
        return {
            'pending_quantity': pending_quantity,
            'pending_payments': unpaid_returns + unpaid_active,
            'pending_payments_returned': unpaid_returns,
            'pending_payments_active': unpaid_active,
            'refund_to_be_done': refund_returns + refund_active
        }

    def get_profit_on_date(self, target_date):
        conn = self.db.get_connection()
        c = conn.cursor()
        
        c.execute("SELECT COALESCE(SUM(advance), 0) FROM rentals WHERE date = ? AND (cancelled IS NULL OR cancelled = 0)", (target_date,))
        advances = safe_float(c.fetchone()[0])
        
        c.execute("""
            SELECT SUM(ret.amount_paid - COALESCE((SELECT SUM(amount) FROM installments WHERE rental_id = ret.rental_id), 0))
            FROM returns ret WHERE ret.return_date = ?
        """, (target_date,))
        returns_paid = max(0.0, safe_float(c.fetchone()[0] or 0))
        
        c.execute("SELECT COALESCE(SUM(amount), 0) FROM installments WHERE date_time LIKE ?", (f"{target_date} %",))
        installments_today = safe_float(c.fetchone()[0])
        
        try:
            c.execute("SELECT COALESCE(SUM(refund), 0) FROM returns WHERE return_date = ?", (target_date,))
            refunds = safe_float(c.fetchone()[0])
        except:
            c.execute("SELECT COALESCE(SUM(ABS(balance)), 0) FROM returns WHERE return_date = ? AND balance < 0", (target_date,))
            refunds = safe_float(c.fetchone()[0])
        
        return (advances + returns_paid + installments_today) - refunds

    def get_transaction_splits(self, start_str, end_str):
        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        gpay_in = gpay_out = cash_in = cash_out = 0.0
        
        try:
            start_dt = datetime.strptime(start_str, '%d-%m-%y')
            end_dt = datetime.strptime(end_str, '%d-%m-%y') + timedelta(days=1, seconds=-1)
        except:
            start_dt = datetime.min; end_dt = datetime.max

        def parse_dt(d, t="12:00 AM"):
            try: return datetime.strptime(f"{d} {t}", "%d-%m-%y %I:%M %p")
            except: return datetime.min

        c.execute("SELECT date, time, advance, payment_mode FROM rentals WHERE (cancelled IS NULL OR cancelled = 0)")
        for r in c.fetchall():
            if start_dt <= parse_dt(r['date'], r['time']) <= end_dt:
                amt = safe_float(r["advance"])
                mode = str(r["payment_mode"]).lower()
                if amt > 0:
                    if mode in ['gpay', 'upi', 'phonepe', 'online']: gpay_in += amt
                    else: cash_in += amt

        try: c.execute("SELECT rental_id, return_date, return_time, amount_paid, refund, payment_mode FROM returns")
        except: c.execute("SELECT rental_id, return_date, return_time, amount_paid, 0 as refund, payment_mode FROM returns")
        
        c2 = conn.cursor()
        for r in c.fetchall():
            if start_dt <= parse_dt(r['return_date'], r['return_time']) <= end_dt:
                total_paid_db = safe_float(r["amount_paid"])
                c2.execute("SELECT SUM(amount) FROM installments WHERE rental_id=?", (r['rental_id'],))
                inst_sum = safe_float(c2.fetchone()[0])
                actual_final_payment = max(0.0, total_paid_db - inst_sum)
                
                mode = str(r["payment_mode"]).lower()
                refund_amt = safe_float(r["refund"]) if "refund" in r.keys() else 0.0
                is_gpay = mode in ['gpay', 'upi', 'phonepe', 'online']
                
                if actual_final_payment > 0:
                    if is_gpay: gpay_in += actual_final_payment
                    else: cash_in += actual_final_payment
                if refund_amt > 0:
                    if is_gpay: gpay_out += refund_amt
                    else: cash_out += refund_amt

        c.execute("SELECT date_time, amount, payment_mode FROM installments")
        for r in c.fetchall():
            dt_str = r['date_time']
            parts = dt_str.split(' ', 1)
            rdt = parse_dt(parts[0], parts[1] if len(parts) > 1 else "12:00 AM")
            if start_dt <= rdt <= end_dt:
                amt = safe_float(r['amount'])
                if str(r['payment_mode']).lower() in ['gpay', 'upi', 'phonepe', 'online']: gpay_in += amt
                else: cash_in += amt
                
        return {'gpay_in': gpay_in, 'gpay_out': gpay_out, 'cash_in': cash_in, 'cash_out': cash_out}

    def get_stock_status(self):
        conn = self.db.get_connection()
        c = conn.cursor()
        inventory = {}
        try:
            with open('materials.csv', mode='r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    name = row.get('name', '').strip()
                    if name: inventory[name] = safe_int(row.get('quantity', 0))
        except: pass
            
        c.execute("""
            SELECT ri.machine_name, SUM(ri.quantity)
            FROM rental_items ri
            JOIN rentals r ON ri.rental_id = r.id
            WHERE (r.cancelled IS NULL OR r.cancelled = 0)
            AND r.id NOT IN (SELECT rental_id FROM returns)
            GROUP BY ri.machine_name
        """)
        rented_out = {row[0]: safe_int(row[1]) for row in c.fetchall()}
        
        stock_data = []
        for machine in sorted(set(list(inventory.keys()) + list(rented_out.keys()))):
            total_qty = inventory.get(machine, 0)
            rented_qty = rented_out.get(machine, 0)
            stock_data.append({'machine': machine, 'total': total_qty, 'rented': rented_qty, 'available': max(0, total_qty - rented_qty)})
        return stock_data

    def get_top_customers(self, start_str, end_str, limit=10):
        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        try:
            start_dt = datetime.strptime(start_str, '%d-%m-%y')
            end_dt = datetime.strptime(end_str, '%d-%m-%y') + timedelta(days=1, seconds=-1)
        except:
            start_dt = datetime.min; end_dt = datetime.max

        def parse_dt(d, t="12:00 AM"):
            try: return datetime.strptime(f"{d} {t}", "%d-%m-%y %I:%M %p")
            except: return datetime.min

        customer_stats = {} 
        
        # Safe check to see if the refund column exists in the returns table
        has_refund = False
        try:
            c.execute("SELECT refund FROM returns LIMIT 1")
            has_refund = True
        except:
            pass
            
        # Dynamically build the query based on column availability
        if has_refund:
            query = """
                SELECT r.id, r.date, r.time, r.name, r.phone, r.advance,
                       (SELECT SUM(amount) FROM installments WHERE rental_id = r.id) as inst_paid,
                       ret.amount_paid as ret_paid,
                       ret.refund as ret_refund
                FROM rentals r
                LEFT JOIN returns ret ON r.id = ret.rental_id
                WHERE (r.cancelled IS NULL OR r.cancelled = 0)
            """
        else:
            query = """
                SELECT r.id, r.date, r.time, r.name, r.phone, r.advance,
                       (SELECT SUM(amount) FROM installments WHERE rental_id = r.id) as inst_paid,
                       ret.amount_paid as ret_paid,
                       0 as ret_refund
                FROM rentals r
                LEFT JOIN returns ret ON r.id = ret.rental_id
                WHERE (r.cancelled IS NULL OR r.cancelled = 0)
            """
            
        c.execute(query)
        
        for r in c.fetchall():
            if start_dt <= parse_dt(r['date'], r['time']) <= end_dt:
                phone = r['phone']
                if phone not in customer_stats: 
                    customer_stats[phone] = {'name': r['name'], 'count': 0, 'spent': 0.0}
                
                customer_stats[phone]['count'] += 1
                
                advance = safe_float(r['advance'])
                inst_paid = safe_float(r['inst_paid'])
                
                if r['ret_paid'] is not None:
                    # Rental has been returned
                    ret_paid = safe_float(r['ret_paid'])
                    ret_refund = safe_float(r['ret_refund'])
                    
                    # 'amount_paid' in DB might include installments, subtract to avoid double-counting
                    actual_final_payment = max(0.0, ret_paid - inst_paid)
                    
                    # Total revenue for this returned rental
                    total_spent = advance + inst_paid + actual_final_payment - ret_refund
                else:
                    # Active rental, just advance and installments count towards spending
                    total_spent = advance + inst_paid
                    
                customer_stats[phone]['spent'] += max(0.0, total_spent)

        # Sort by total spent, highest first
        return sorted([(stats['name'], p, stats['count'], stats['spent']) for p, stats in customer_stats.items()], key=lambda x: x[3], reverse=True)[:limit]

    def create_kpi_cards(self, parent):
        kpi_frame = ttk.Frame(parent)
        kpi_frame.pack(fill=tk.X, padx=10, pady=10)
        for i in range(4): kpi_frame.columnconfigure(i, weight=1)

        card1 = ttk.Frame(kpi_frame, style='Card.TFrame')
        card1.grid(row=0, column=0, padx=5, sticky="nsew")
        ttk.Label(card1, text="📦 Pending Quantity", font=("Segoe UI", 10, "bold"), foreground="#ff9800").pack(pady=(10, 5))
        self.lbl_pending_qty = ttk.Label(card1, text="0", font=("Segoe UI", 16, "bold"))
        self.lbl_pending_qty.pack(pady=(0, 10))

        card2 = ttk.Frame(kpi_frame, style='Card.TFrame')
        card2.grid(row=0, column=1, padx=5, sticky="nsew")
        
        card2_header = ttk.Frame(card2)
        card2_header.pack(fill=tk.X, padx=5, pady=(5, 0))
        ttk.Label(card2_header, text="💰 Pending Payments", font=("Segoe UI", 10, "bold"), foreground="#f44336").pack(side=tk.LEFT)
        
        self.pending_pay_filter = ttk.Combobox(card2_header, values=["All", "Returned", "Not Returned"], state="readonly", width=11, font=("Segoe UI", 8))
        self.pending_pay_filter.set("All")
        self.pending_pay_filter.pack(side=tk.RIGHT)
        
        self.lbl_pending_pay = ttk.Label(card2, text="₹0.00", font=("Segoe UI", 16, "bold"))
        self.lbl_pending_pay.pack(pady=(5, 10))
        
        self.pending_pay_filter.bind("<<ComboboxSelected>>", lambda e: update_kpis())

        card3 = ttk.Frame(kpi_frame, style='Card.TFrame')
        card3.grid(row=0, column=2, padx=5, sticky="nsew")
        ttk.Label(card3, text="💸 Refund to be Done", font=("Segoe UI", 10, "bold"), foreground="#9c27b0").pack(pady=(10, 5))
        self.lbl_pending_refund = ttk.Label(card3, text="₹0.00", font=("Segoe UI", 16, "bold"))
        self.lbl_pending_refund.pack(pady=(0, 10))

        card4 = ttk.Frame(kpi_frame, style='Card.TFrame')
        card4.grid(row=0, column=3, padx=5, sticky="nsew")
        header_frame = ttk.Frame(card4)
        header_frame.pack(pady=(5, 0))
        ttk.Label(header_frame, text="📈 Profit on Date ", font=("Segoe UI", 10, "bold"), foreground="#4CAF50").pack(side="left")
        
        self.date_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
        self.lbl_profit = ttk.Label(card4, text="₹0.00", font=("Segoe UI", 16, "bold"))
        
        def on_date_selected(new_date):
            self.date_var.set(f"📅 {new_date}")
            self.update_kpis()
            
        ttk.Button(header_frame, textvariable=self.date_var, width=12, command=lambda: CustomDatePicker(parent, self.date_var.get().replace("📅 ", ""), on_date_selected)).pack(side="left", padx=5)
        self.lbl_profit.pack(pady=(10, 10))

        def update_kpis():
            analytics = self.get_pending_analytics()
            self.lbl_pending_qty.config(text=str(analytics['pending_quantity']))
            
            pay_filter = self.pending_pay_filter.get()
            if pay_filter == "Returned":
                pay_amt = analytics['pending_payments_returned']
            elif pay_filter == "Not Returned":
                pay_amt = analytics['pending_payments_active']
            else:
                pay_amt = analytics['pending_payments']
                
            self.lbl_pending_pay.config(text=f"₹{pay_amt:,.2f}")
            self.lbl_pending_refund.config(text=f"₹{analytics['refund_to_be_done']:,.2f}")
            
            clean_date = self.date_var.get().replace("📅 ", "")
            profit = self.get_profit_on_date(clean_date)
            self.lbl_profit.config(text=f"₹{profit:,.2f}")
            
        self.update_kpis = update_kpis
        self.update_kpis()
        return kpi_frame

    def create_transaction_splits(self, parent):
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        daily_frame = ttk.LabelFrame(main_frame, text="Transaction Splits", padding=10)
        daily_frame.pack(fill=tk.X, pady=10)
        daily_header = ttk.Frame(daily_frame)
        daily_header.pack(fill=tk.X, pady=(0, 10))
        
        from_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
        to_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))

        ttk.Label(daily_header, text="From: ", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Button(daily_header, textvariable=from_var, width=12, command=lambda: CustomDatePicker(parent, from_var.get(), lambda d: [from_var.set(d), update_splits()])).pack(side="left", padx=5)
        ttk.Label(daily_header, text="To: ", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)
        ttk.Button(daily_header, textvariable=to_var, width=12, command=lambda: CustomDatePicker(parent, to_var.get(), lambda d: [to_var.set(d), update_splits()])).pack(side="left", padx=5)

        cards_frame = ttk.Frame(daily_frame)
        cards_frame.pack(fill=tk.X, pady=10)
        for i in range(4): cards_frame.columnconfigure(i, weight=1)

        daily_labels = {}
        items = [("gpay_in", "🟢 Received GPay", "#4CAF50"), ("gpay_out", "🔴 Refunded GPay", "#f44336"),
                 ("cash_in", "🟢 Received Cash", "#4CAF50"), ("cash_out", "🔴 Refunded Cash", "#f44336")]
        
        for i, (key, label, color) in enumerate(items):
            card = ttk.Frame(cards_frame, style='Card.TFrame')
            card.grid(row=0, column=i, padx=5, sticky="nsew")
            ttk.Label(card, text=label, font=("Segoe UI", 9, "bold")).pack(pady=(5, 2))
            val_label = ttk.Label(card, text="₹0.00", font=("Segoe UI", 12, "bold"), foreground=color)
            val_label.pack(pady=(0, 5))
            daily_labels[key] = val_label
            
        def update_splits():
            stats = self.get_transaction_splits(from_var.get(), to_var.get())
            for k in daily_labels: daily_labels[k].config(text=f"₹{stats[k]:,.2f}")

        self.update_splits = update_splits
        self.update_splits()

        del_frame = ttk.LabelFrame(main_frame, text="🗑️ Delete Old Data (Keeps Customers)", padding=10)
        del_frame.pack(fill=tk.X, pady=20)
        ttk.Label(del_frame, text="WARNING: This will permanently wipe financial and item records for the selected date range.\nCustomer info (Name, Phone, Address) will be retained for auto-complete.", foreground="red").pack(pady=(0,10))
        del_controls = ttk.Frame(del_frame)
        del_controls.pack()
        del_from = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
        del_to = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
        
        ttk.Label(del_controls, text="From:").pack(side="left", padx=5)
        ttk.Button(del_controls, textvariable=del_from, command=lambda: CustomDatePicker(parent, del_from.get(), del_from.set)).pack(side="left", padx=5)
        ttk.Label(del_controls, text="To:").pack(side="left", padx=5)
        ttk.Button(del_controls, textvariable=del_to, command=lambda: CustomDatePicker(parent, del_to.get(), del_to.set)).pack(side="left", padx=5)
        
        def do_delete():
            start_str, end_str = del_from.get(), del_to.get()
            if not messagebox.askyesno("Confirm Deletion", f"Are you absolutely sure you want to delete transactions from {start_str} to {end_str}?\n\nThis cannot be undone!"): return
            try:
                start_dt = datetime.strptime(start_str, '%d-%m-%y')
                end_dt = datetime.strptime(end_str, '%d-%m-%y') + timedelta(days=1, seconds=-1)
                conn = self.db.get_connection()
                c = conn.cursor()
                c.execute("SELECT id, date, time FROM rentals")
                to_delete_ids = []
                def parse_dt(d, t="12:00 AM"):
                    try: return datetime.strptime(f"{d} {t}", "%d-%m-%y %I:%M %p")
                    except: return datetime.min
                for r in c.fetchall():
                    if start_dt <= parse_dt(r[1], r[2]) <= end_dt: to_delete_ids.append(r[0])
                if not to_delete_ids:
                    messagebox.showinfo("Result", "No records found in this date range.")
                    return
                placeholders = ','.join('?' for _ in to_delete_ids)
                for table in ['rental_items', 'returns', 'installments']:
                    c.execute(f"DELETE FROM {table} WHERE rental_id IN ({placeholders})", to_delete_ids)
                c.execute(f"UPDATE rentals SET machines='', machine_codes='', quantities='', rents='', total=0, advance=0, cancelled=1 WHERE id IN ({placeholders})", to_delete_ids)
                conn.commit()
                messagebox.showinfo("Success", f"Successfully deleted {len(to_delete_ids)} transaction records.")
                import callbacks
                if hasattr(callbacks, 'reload_all_tabs'): callbacks.reload_all_tabs()
            except Exception as e:
                log_error("Delete Data", e)
                messagebox.showerror("Error", f"Failed to delete data: {e}")

        ttk.Button(del_controls, text="Delete Records", command=do_delete).pack(side="left", padx=20)

    def create_top_customers_widget(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        ctrl_frame = ttk.Frame(frame)
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))

        from_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
        to_var = tk.StringVar(value=datetime.now().strftime('%d-%m-%y'))
        limit_var = tk.StringVar(value="15")

        ttk.Label(ctrl_frame, text="From: ", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Button(ctrl_frame, textvariable=from_var, width=12, command=lambda: CustomDatePicker(parent, from_var.get(), lambda d: [from_var.set(d), load_top_customers()])).pack(side="left", padx=5)
        ttk.Label(ctrl_frame, text="To: ", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, textvariable=to_var, width=12, command=lambda: CustomDatePicker(parent, to_var.get(), lambda d: [to_var.set(d), load_top_customers()])).pack(side="left", padx=5)
        ttk.Label(ctrl_frame, text="Top N: ", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(15, 5))
        limit_entry = ttk.Entry(ctrl_frame, textvariable=limit_var, width=6, font=("Segoe UI", 10))
        limit_entry.pack(side="left")
        ttk.Button(ctrl_frame, text="🔄 Update", command=lambda: load_top_customers()).pack(side="left", padx=10)

        title_lbl = ttk.Label(frame, text="🏆 Top Customers", font=("Segoe UI", 12, "bold"))
        title_lbl.pack(anchor="w", pady=(0, 10))
        
        columns = ("Rank", "Name", "Phone", "Rentals", "Total Spent")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            tree.heading(col, text=col)
            if col == "Rank": tree.column(col, width=60, anchor="center")
            elif col in ["Name", "Phone"]: tree.column(col, width=150)
            else: tree.column(col, width=100, anchor="center")
            
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill="y")

        def load_top_customers(*args):
            tree.delete(*tree.get_children())
            lim = safe_int(limit_var.get(), 15)
            if lim <= 0: lim = 15
            title_lbl.config(text=f"🏆 Top {lim} Customers")
            for i, customer in enumerate(self.get_top_customers(from_var.get(), to_var.get(), lim), 1):
                tree.insert("", "end", values=(i, customer[0], customer[1], customer[2], f"₹{safe_float(customer[3]):,.2f}"))

        self.load_top_customers = load_top_customers
        limit_entry.bind("<Return>", self.load_top_customers)
        self.load_top_customers()

    def create_stock_status_widget(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        header_frame = ttk.Frame(frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="📦 Live Stock Status", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Label(header_frame, text="(Cross-referenced with active rentals)", font=("Segoe UI", 9)).pack(side="left", padx=10)

        search_var = tk.StringVar()
        ttk.Label(header_frame, text="🔍 Search:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(20, 5))
        ttk.Entry(header_frame, textvariable=search_var, width=20).pack(side="left")

        columns = ("Machine Name", "Total Stock", "Currently Rented", "Available Now")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=20)
        
        def print_stock_report():
            if not tree.get_children(): return
            try:
                os.makedirs("reports", exist_ok=True)
                filepath = os.path.join("reports", f"Stock_Status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
                doc = SimpleDocTemplate(filepath, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
                elements = []
                elements.append(Paragraph(f"<b>Live Stock Status Report</b> - {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", getSampleStyleSheet()['Title']))
                elements.append(Paragraph("<br/><br/>", getSampleStyleSheet()['Normal']))
                data = [["Machine Name", "Total Stock", "Currently Rented", "Available Now"]]
                for item_id in tree.get_children(): data.append(list(tree.item(item_id, "values")))
                t = Table(data, colWidths=[200, 100, 100, 100])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2176ff")), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('BOTTOMPADDING', (0,0), (-1,0), 10),
                    ('TOPPADDING', (0,0), (-1,0), 10), ('BACKGROUND', (0,1), (-1,-1), colors.white), ('GRID', (0,0), (-1,-1), 1, colors.lightgrey),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
                ]))
                elements.append(t)
                doc.build(elements)
                webbrowser.open(filepath)
            except Exception as e: messagebox.showerror("Print Error", f"Failed: {e}")

        ttk.Button(header_frame, text="🖨️ Print Stock", command=print_stock_report).pack(side="right", padx=10)

        for col in columns:
            tree.heading(col, text=col)
            if col == "Machine Name": tree.column(col, width=300)
            else: tree.column(col, width=120, anchor="center")
            
        tree.tag_configure('out_of_stock', foreground='red')
        
        def load_stock(*args):
            tree.delete(*tree.get_children())
            
            # ---> FIX: FETCH FRESH DATA EVERY TIME THE TABLE RELOADS <---
            fresh_stock_data = self.get_stock_status()
            
            kw = search_var.get().lower().strip()
            for item in fresh_stock_data:
                if kw and kw not in item['machine'].lower(): continue
                tag = 'out_of_stock' if item['available'] <= 0 else 'normal'
                tree.insert("", "end", values=(item['machine'], item['total'], item['rented'], item['available']), tags=(tag,))
                
        self.load_stock = load_stock
        search_var.trace_add("write", self.load_stock)
        self.load_stock()
            
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill="y")


def create_analytics_tab(tab_control, db):
    tab = ttk.Frame(tab_control)
    tab_control.add(tab, text="📊 Analytics")
    dashboard = AnalyticsDashboard(db)
    analytics_notebook = ttk.Notebook(tab)
    analytics_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    overview_tab = ttk.Frame(analytics_notebook)
    analytics_notebook.add(overview_tab, text="Overview")
    dashboard.create_kpi_cards(overview_tab)
    dashboard.create_transaction_splits(overview_tab)
    
    stock_tab = ttk.Frame(analytics_notebook)
    analytics_notebook.add(stock_tab, text="Stock Status")
    dashboard.create_stock_status_widget(stock_tab)

    customers_tab = ttk.Frame(analytics_notebook)
    analytics_notebook.add(customers_tab, text="Top Customers")
    dashboard.create_top_customers_widget(customers_tab)
    
    tab.cleanup = lambda: None
    tab.dashboard = dashboard
    
    # ---> FIX: EXPOSE RELOAD HOOK SO "REFRESH DATA" BUTTON WORKS <---
    def reload_all_analytics():
        try:
            if hasattr(dashboard, 'update_kpis'): dashboard.update_kpis()
            if hasattr(dashboard, 'update_splits'): dashboard.update_splits()
            if hasattr(dashboard, 'load_stock'): dashboard.load_stock()
            if hasattr(dashboard, 'load_top_customers'): dashboard.load_top_customers()
        except Exception as e:
            print(f"[ERROR] Analytics reload failed: {e}")

    return {"frame": tab, "reload": reload_all_analytics, "cleanup": tab.cleanup}