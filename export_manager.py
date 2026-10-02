import csv
import json
import sqlite3
from datetime import datetime
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from utils import safe_float

class ExportManager:
    """Handles data export to various formats"""
    
    def __init__(self, db):
        self.db = db
        import sys
        if getattr(sys, 'frozen', False):
            self.exports_dir = os.path.join(os.path.dirname(sys.executable), "exports")
        else:
            self.exports_dir = "exports"
        os.makedirs(self.exports_dir, exist_ok=True)
    
    def export_rentals_to_csv(self, filename=None, date_range=None):
        """Export rentals data to CSV"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.exports_dir, f"rentals_export_{timestamp}.csv")
        
        conn = self.db.get_connection()
        c = conn.cursor()
        
        query = """
            SELECT 
                id, bill_no, name, phone, phone2, address, id_proof,
                machine_codes, machines, rents, quantities,
                total, advance, date, time, vehicle, payment_mode,
                cancelled
            FROM rentals
            WHERE 1=1
        """
        params = []
        
        if date_range:
            query += " AND date BETWEEN ? AND ?"
            params.extend([date_range[0], date_range[1]])
        
        query += " ORDER BY id DESC"
        
        c.execute(query, params)
        rentals = c.fetchall()
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow([
                'ID', 'Bill No', 'Name', 'Phone', 'Phone 2', 'Address', 'ID Proof',
                'Machine Codes', 'Machines', 'Rents', 'Quantities',
                'Total', 'Advance', 'Date', 'Time', 'Vehicle', 'Payment Mode',
                'Cancelled'
            ])
            
            # Write data
            writer.writerows(rentals)
        
        return filename, len(rentals)
    
    def export_returns_to_csv(self, filename=None):
        """Export returns data to CSV"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.exports_dir, f"returns_export_{timestamp}.csv")
        
        conn = self.db.get_connection()
        c = conn.cursor()
        
        query = """
            SELECT 
                r.id, rt.bill_no, rt.name, rt.phone,
                r.return_date, r.return_time, r.rental_days,
                r.due_amount, r.deduction, r.damage, r.balance,
                r.amount_paid, r.returned_items, r.returned_quantities,
                r.payment_mode
            FROM returns r
            JOIN rentals rt ON r.rental_id = rt.id
            ORDER BY r.id DESC
        """
        
        c.execute(query)
        returns_data = c.fetchall()
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow([
                'ID', 'Bill No', 'Name', 'Phone',
                'Return Date', 'Return Time', 'Rental Days',
                'Due Amount', 'Deduction', 'Damage', 'Balance',
                'Amount Paid', 'Returned Items', 'Returned Quantities',
                'Payment Mode'
            ])
            
            # Write data
            writer.writerows(returns_data)
        
        return filename, len(returns_data)
    
    def export_customer_report(self, customer_phone, filename=None):
        """Export customer report to CSV"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.exports_dir, f"customer_{customer_phone}_{timestamp}.csv")
        
        conn = self.db.get_connection()
        c = conn.cursor()
        
        query = """
            SELECT 
                r.id, r.bill_no, r.name, r.phone, r.date, r.machines, r.total,
                r.advance, r.payment_mode AS adv_mode,
                ret.return_date, ret.amount_paid, ret.payment_mode AS paid_mode,
                ret.balance
            FROM rentals r
            LEFT JOIN returns ret ON r.id = ret.rental_id
            WHERE r.phone = ? AND (r.cancelled IS NULL OR r.cancelled = 0)
            ORDER BY r.id DESC
        """
        
        c.execute(query, (customer_phone,))
        records = c.fetchall()
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow([
                'ID', 'Bill No', 'Name', 'Phone', 'Date', 'Machines', 'Total',
                'Advance', 'Advance Mode', 'Return Date', 'Amount Paid', 
                'Payment Mode', 'Balance'
            ])
            
            # Write data
            writer.writerows(records)
        
        return filename, len(records)
    
    def export_financial_summary(self, filename=None):
        """Export financial summary to CSV"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.exports_dir, f"financial_summary_{timestamp}.csv")
        
        conn = self.db.get_connection()
        c = conn.cursor()
        
        # Get financial metrics
        queries = {
            'total_revenue': "SELECT COALESCE(SUM(total), 0) FROM rentals WHERE (cancelled IS NULL OR cancelled = 0)",
            'total_advance': "SELECT COALESCE(SUM(advance), 0) FROM rentals WHERE (cancelled IS NULL OR cancelled = 0)",
            'total_returns': "SELECT COALESCE(SUM(amount_paid), 0) FROM returns",
            'pending_payments': "SELECT COALESCE(SUM(balance), 0) FROM returns WHERE balance > 0",
            'pending_rentals': """
                SELECT COALESCE(SUM(total - advance), 0)
                FROM rentals WHERE (cancelled IS NULL OR cancelled = 0)
                AND id NOT IN (SELECT rental_id FROM returns)
            """,
            'unique_customers': "SELECT COUNT(DISTINCT phone) FROM rentals WHERE (cancelled IS NULL OR cancelled = 0)",
            'total_rentals': "SELECT COUNT(*) FROM rentals WHERE (cancelled IS NULL OR cancelled = 0)"
        }
        
        results = {}
        for key, query in queries.items():
            c.execute(query)
            results[key] = c.fetchone()[0]
        
        # Calculate derived metrics
        pending_payments = safe_float(results['pending_payments'])
        pending_rentals = safe_float(results['pending_rentals'])
        
        summary_data = [
            ['Metric', 'Value'],
            ['Total Revenue', f'₹{safe_float(results["total_revenue"]):,.2f}'],
            ['Total Advance Collected', f'₹{safe_float(results["total_advance"]):,.2f}'],
            ['Total Returns Collected', f'₹{safe_float(results["total_returns"]):,.2f}'],
            ['Pending Payments', f'₹{pending_payments:,.2f}'],
            ['Pending Rental Dues', f'₹{pending_rentals:,.2f}'],
            ['Total Outstanding', f'₹{(pending_payments + pending_rentals):,.2f}'],
            ['Unique Customers', results['unique_customers']],
            ['Total Rentals', results['total_rentals']],
            ['Export Date', datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        ]
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(summary_data)
        
        return filename, len(summary_data) - 1  # Exclude header
    
    def create_export_dialog(self, parent):
        """Create export dialog window"""
        dialog = tk.Toplevel(parent)
        dialog.title("Export Data")
        dialog.geometry("500x400")
        dialog.transient(parent)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - dialog.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="📤 Export Data", 
                 font=("Segoe UI", 16, "bold")).pack(pady=(0, 20))
        
        # Export options
        options_frame = ttk.Frame(main_frame)
        options_frame.pack(fill=tk.X, pady=10)
        
        export_var = tk.StringVar(value="rentals")
        
        options = [
            ("📋 All Rentals Data", "rentals"),
            ("🔄 Returns Data", "returns"),
            ("📊 Financial Summary", "financial"),
            ("👥 Customer Report", "customer")
        ]
        
        for text, value in options:
            ttk.Radiobutton(options_frame, text=text, variable=export_var, 
                           value=value).pack(anchor="w", pady=5)
        
        # Customer phone input (for customer report)
        phone_frame = ttk.Frame(main_frame)
        phone_frame.pack(fill=tk.X, pady=10)
        
        phone_var = tk.StringVar()
        ttk.Label(phone_frame, text="Customer Phone:").pack(anchor="w")
        ttk.Entry(phone_frame, textvariable=phone_var, width=20).pack(anchor="w", pady=5)
        phone_frame.pack_forget()  # Hide initially
        
        def on_export_type_change(*args):
            if export_var.get() == "customer":
                phone_frame.pack(fill=tk.X, pady=10)
            else:
                phone_frame.pack_forget()
        
        export_var.trace_add("write", on_export_type_change)
        
        # Date range for rentals
        date_frame = ttk.Frame(main_frame)
        date_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(date_frame, text="Date Range (DD-MM-YY):").pack(anchor="w")
        date_inner_frame = ttk.Frame(date_frame)
        date_inner_frame.pack(fill=tk.X, pady=5)
        
        from_date_var = tk.StringVar()
        to_date_var = tk.StringVar(value=datetime.now().strftime("%d-%m-%y"))
        
        ttk.Label(date_inner_frame, text="From:").pack(side="left")
        ttk.Entry(date_inner_frame, textvariable=from_date_var, width=12).pack(side="left", padx=(5, 15))
        ttk.Label(date_inner_frame, text="To:").pack(side="left")
        ttk.Entry(date_inner_frame, textvariable=to_date_var, width=12).pack(side="left", padx=5)
        
        date_frame.pack_forget()  # Hide initially
        
        def on_rentals_type_change(*args):
            if export_var.get() == "rentals":
                date_frame.pack(fill=tk.X, pady=10)
            else:
                date_frame.pack_forget()
        
        export_var.trace_add("write", on_rentals_type_change)
        
        # Progress bar
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=10)
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X)
        
        status_var = tk.StringVar(value="Ready to export")
        ttk.Label(progress_frame, textvariable=status_var, font=("Segoe UI", 9)).pack(pady=5)
        
        def execute_export():
            export_type = export_var.get()
            progress_var.set(10)
            status_var.set("Starting export...")
            
            try:
                if export_type == "rentals":
                    date_range = None
                    if from_date_var.get() and to_date_var.get():
                        date_range = (from_date_var.get(), to_date_var.get())
                    
                    filename, count = self.export_rentals_to_csv(date_range=date_range)
                    messagebox.showinfo("Export Complete", 
                                      f"Exported {count} rentals to:\n{filename}")
                
                elif export_type == "returns":
                    filename, count = self.export_returns_to_csv()
                    messagebox.showinfo("Export Complete", 
                                      f"Exported {count} returns to:\n{filename}")
                
                elif export_type == "financial":
                    filename, count = self.export_financial_summary()
                    messagebox.showinfo("Export Complete", 
                                      f"Exported financial summary to:\n{filename}")
                
                elif export_type == "customer":
                    phone = phone_var.get().strip()
                    if not phone:
                        messagebox.showerror("Error", "Please enter customer phone number")
                        return
                    
                    filename, count = self.export_customer_report(phone)
                    messagebox.showinfo("Export Complete", 
                                      f"Exported {count} customer records to:\n{filename}")
                
                progress_var.set(100)
                status_var.set("Export completed successfully!")
                
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export data:\n{str(e)}")
                status_var.set("Export failed!")
                progress_var.set(0)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(button_frame, text="Export", command=execute_export,
                  style="Primary.TButton").pack(side="right", padx=(10, 0))
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right")
        
        return dialog