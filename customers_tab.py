# customers_tab.py - CUSTOMER DIRECTORY (CRM) - REFINED VERSION
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import webbrowser
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from utils import log_error

def init_customers_db(db):
    """Creates the customers table and auto-imports existing customers from rentals."""
    try:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS customers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        phone TEXT UNIQUE NOT NULL,
                        phone2 TEXT,
                        address TEXT,
                        is_regular INTEGER DEFAULT 0
                    )''')
        
        c.execute('''
            INSERT OR IGNORE INTO customers (name, phone, phone2, address)
            SELECT name, phone, phone2, address 
            FROM rentals 
            WHERE phone IS NOT NULL AND phone != ''
            GROUP BY phone
        ''')
        conn.commit()
    except Exception as e:
        log_error("Init Customers DB", e)

def create_customers_tab(tab_control, db):
    init_customers_db(db)

    tab = ttk.Frame(tab_control)
    tab_control.add(tab, text="👥 Customers")

    top_frame = ttk.Frame(tab)
    top_frame.pack(fill="x", padx=10, pady=10)

    search_var = tk.StringVar()
    filter_var = tk.StringVar(value="All Customers")

    ttk.Label(top_frame, text="🔍 Search:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 5))
    search_entry = ttk.Entry(top_frame, textvariable=search_var, width=25, font=("Segoe UI", 11))
    search_entry.pack(side="left", padx=5)

    ttk.Label(top_frame, text="Filter:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(15, 5))
    filter_combo = ttk.Combobox(top_frame, textvariable=filter_var, values=["All Customers", "Regular Only", "Non-Regular Only"], state="readonly", width=15, font=("Segoe UI", 10))
    filter_combo.pack(side="left", padx=5)

    btn_frame = ttk.Frame(top_frame)
    btn_frame.pack(side="right")

    def print_customers_list():
        if not tree.get_children():
            messagebox.showinfo("No Data", "No customers found to print.")
            return
        try:
            os.makedirs("reports", exist_ok=True)
            filepath = os.path.join("reports", f"Customer_List_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
            elements = []
            styles = getSampleStyleSheet()
            title = Paragraph(f"<b>Customer Directory</b> - Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title'])
            elements.append(title)
            elements.append(Paragraph("<br/><br/>", styles['Normal']))
            data = [["Name", "Phone 1", "Phone 2", "Address", "Regular?"]]
            for item_id in tree.get_children():
                values = tree.item(item_id, "values")
                addr_p = Paragraph(values[3], styles["Normal"]) 
                row_data = [values[0], values[1], values[2], addr_p, values[4]]
                data.append(row_data)
            t = Table(data, colWidths=[150, 100, 100, 350, 80])
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

    ttk.Button(btn_frame, text="➕ Add New Customer", command=lambda: open_customer_popup()).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="🖨️ Print List", command=print_customers_list).pack(side="left", padx=5)

    # --- TABLE (TREEVIEW) ---
    tree_frame = ttk.Frame(tab)
    tree_frame.pack(fill="both", expand=True, padx=10, pady=5)

    columns = ("Name", "Phone", "Phone 2", "Address", "Regular", "ID")
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

    tree.heading("Name", text="Customer Name")
    tree.heading("Phone", text="Primary Phone")
    tree.heading("Phone 2", text="Secondary Phone")
    tree.heading("Address", text="Address")
    tree.heading("Regular", text="Regular?")
    
    # --- UPDATED WIDTHS FOR BETTER SCANNABILITY ---
    tree.column("Name", width=140)
    tree.column("Phone", width=110, anchor="center")
    tree.column("Phone 2", width=110, anchor="center")
    tree.column("Address", width=800) # Maximized space for address
    tree.column("Regular", width=10, anchor="center") # Minimized space for star/status
    tree.column("ID", width=0, stretch=tk.NO)

    tree.tag_configure("is_regular", foreground="#006400", font=("Segoe UI", 11, "bold")) 
    tree.tag_configure("normal", foreground="black")

    scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll_y.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll_y.pack(side="right", fill="y")

    def load_customers(*args):
        for item in tree.get_children():
            tree.delete(item)
        keyword = f"%{search_var.get().strip()}%"
        filter_status = filter_var.get()
        try:
            conn = db.get_connection()
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            query = "SELECT * FROM customers WHERE (name LIKE ? OR phone LIKE ?)"
            params = [keyword, keyword]
            if filter_status == "Regular Only":
                query += " AND is_regular = 1"
            elif filter_status == "Non-Regular Only":
                query += " AND is_regular = 0"
            query += " ORDER BY name ASC"
            c.execute(query, params)
            for r in c.fetchall():
                is_reg_text = "⭐ YES" if r['is_regular'] else "No"
                tag = "is_regular" if r['is_regular'] else "normal"
                name_disp = r['name']
                if r['is_regular']:
                    name_disp += " ⭐"
                tree.insert("", "end", values=(
                    name_disp, r['phone'], r['phone2'], r['address'], is_reg_text, r['id']
                ), tags=(tag,))
        except Exception as e:
            log_error("Load Customers", e)

    def open_customer_popup(customer_id=None, current_data=None):
        popup = tk.Toplevel(tab)
        popup.title("Edit Customer" if customer_id else "Add New Customer")
        popup.geometry("450x460")
        popup.resizable(False, False)
        popup.transient(tab)
        popup.grab_set()

        popup.update_idletasks()
        x = tab.winfo_rootx() + (tab.winfo_width() // 2) - 225
        y = tab.winfo_rooty() + (tab.winfo_height() // 2) - 230
        popup.geometry(f"+{x}+{y}")

        main_pad = ttk.Frame(popup, padding=15)
        main_pad.pack(fill="both", expand=True)

        display_name = current_data[0] if current_data else ""
        if display_name.endswith(" ⭐"):
            display_name = display_name[:-2]
        name_var_pop = tk.StringVar(value=display_name)
        phone_var_pop = tk.StringVar(value=current_data[1] if current_data else "")
        phone2_var_pop = tk.StringVar(value=current_data[2] if current_data else "")
        is_regular_var = tk.BooleanVar(value=(current_data[4] == "⭐ YES") if current_data else False)

        fnt = ("Segoe UI", 10)

        ttk.Label(main_pad, text="Name:*", font=fnt).grid(row=0, column=0, sticky="e", pady=5, padx=5)
        ttk.Entry(main_pad, textvariable=name_var_pop, width=30, font=fnt).grid(row=0, column=1, pady=5)

        ttk.Label(main_pad, text="Primary Phone:*", font=fnt).grid(row=1, column=0, sticky="e", pady=5, padx=5)
        phone_entry = ttk.Entry(main_pad, textvariable=phone_var_pop, width=30, font=fnt)
        phone_entry.grid(row=1, column=1, pady=5)
        if customer_id: phone_entry.config(state="disabled")

        ttk.Label(main_pad, text="Secondary Phone:", font=fnt).grid(row=2, column=0, sticky="e", pady=5, padx=5)
        ttk.Entry(main_pad, textvariable=phone2_var_pop, width=30, font=fnt).grid(row=2, column=1, pady=5)

        ttk.Label(main_pad, text="Address:", font=fnt).grid(row=3, column=0, sticky="ne", pady=5, padx=5)
        address_text = tk.Text(main_pad, width=30, height=4, font=fnt, wrap="word")
        address_text.grid(row=3, column=1, pady=5)
        if current_data and current_data[3]:
            address_text.insert("1.0", current_data[3])

        ttk.Checkbutton(main_pad, text="⭐ Mark as Regular Customer", variable=is_regular_var, style="TCheckbutton").grid(row=4, column=1, sticky="w", pady=10)

        def save_customer():
            name = name_var_pop.get().strip()
            phone = phone_var_pop.get().strip()
            phone2 = phone2_var_pop.get().strip()
            address = address_text.get("1.0", tk.END).strip()
            is_reg = 1 if is_regular_var.get() else 0
            if not name or not phone:
                messagebox.showwarning("Validation Error", "Name and Primary Phone are required!")
                return
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
                load_customers()
                try:
                    import callbacks
                    if callbacks.reload_all_tabs: callbacks.reload_all_tabs()
                except:
                    pass
                popup.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror("Duplicate", "A customer with this Primary Phone number already exists!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")

        ttk.Button(main_pad, text="💾 Save Customer", command=save_customer).grid(row=5, column=0, columnspan=2, pady=15)

    def on_double_click(event):
        selected = tree.selection()
        if not selected: return
        item = tree.item(selected[0])
        values = item["values"]
        customer_id = values[5]
        open_customer_popup(customer_id, values)

    tree.bind("<Double-1>", on_double_click)
    ttk.Button(btn_frame, text="✏️ Edit Selected", command=lambda: on_double_click(None)).pack(side="left", padx=5)

    search_var.trace_add("write", load_customers)
    filter_combo.bind("<<ComboboxSelected>>", load_customers)

    load_customers()
    return {"frame": tab, "reload": load_customers}

def sync_single_customer(db, data):
    try:
        phone = data.get('phone', '').strip()
        if not phone: return 
        from shared_imports import sync_customer_from_last_bill
        sync_customer_from_last_bill(db, phone)
    except Exception as e:
        print(f"[WARN] Automatic CRM sync failed: {e}")

def run_initial_regular_sync(db):
    import threading
    from shared_imports import sync_customer_from_last_bill
    def sync():
        try:
            import sqlite3
            conn = sqlite3.connect(db.db_name)
            conn.row_factory = sqlite3.Row
            
            class ThreadLocalDB:
                def get_connection(self):
                    return conn
                    
            thread_db = ThreadLocalDB()
            
            c = conn.cursor()
            c.execute("SELECT phone FROM customers")
            phones = [row[0] for row in c.fetchall()]
            for phone in phones:
                sync_customer_from_last_bill(thread_db, phone)
            conn.close()
        except Exception as e:
            print(f"[WARN] Initial regular status sync failed: {e}")
    threading.Thread(target=sync, daemon=True).start()