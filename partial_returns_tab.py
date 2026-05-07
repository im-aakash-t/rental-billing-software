# partial_returns_tab.py - REFINED VERSION (With Search & Print PDF + Machine Name Search)
import tkinter as tk
from tkinter import ttk, messagebox
import textwrap 
import sqlite3  
import os
import webbrowser
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from utils import safe_int, safe_float, log_error
from materials import get_material_by_code

# --- GLOBAL FONT SETTINGS ---
HEADER_FONT = ("Segoe UI", 12, "bold")
TABLE_FONT = ("Segoe UI", 11)

def get_pending_returns(db):
    """
    Returns pending returns using the new rental_items table.
    Includes phone2 for broader search capability.
    """
    try:
        conn = db.get_connection()
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        
        # 1. Fetch Active Rentals (Headers)
        c.execute("""
            SELECT r.id, r.bill_no, r.name, r.phone, r.phone2, r.address, r.date, 
                   ret.returned_items, ret.returned_quantities
            FROM rentals r
            LEFT JOIN returns ret ON ret.rental_id = r.id
            WHERE (r.cancelled IS NULL OR r.cancelled = 0)
            ORDER BY r.id DESC
        """)
        rentals = c.fetchall()
        results = []
        
        def clean_split(data):
            if not data: return []
            s = str(data).strip()
            return [p.strip() for p in s.replace('[','').replace(']','').split(',') if p.strip()]

        for r in rentals:
            row_dict = dict(r)
            rental_id = r['id']
            
            # 2. Fetch Items for this Rental
            c.execute("SELECT machine_name, quantity FROM rental_items WHERE rental_id=?", (rental_id,))
            items = c.fetchall()
            
            # 3. Parse Returned Data (if any)
            raw_ret_qtys = clean_split(row_dict.get("returned_quantities", ""))
            
            total_rented = 0
            total_returned = 0
            
            items_data = []
            
            for i, item in enumerate(items):
                name = item['machine_name']
                qty = item['quantity']
                
                ret_qty = 0
                if i < len(raw_ret_qtys):
                    ret_qty = safe_int(raw_ret_qtys[i])
                
                if qty <= 0: continue
                
                total_rented += qty
                total_returned += ret_qty
                
                items_data.append({
                    "name": name,
                    "taken": str(qty),
                    "returned": str(ret_qty) 
                })
            
            # Only show if not fully returned
            if total_returned < total_rented:
                row_dict["items_data"] = items_data
                results.append(row_dict)
                
        return results
        
    except Exception as e:
        log_error("get_pending_returns failed", e)
        return []

def create_partial_returns_tab(tab_control, db, update_return_fields_from_selection):
    """
    Adds a tab showing customers with pending returns using a Master-Detail View.
    """
    tab = ttk.Frame(tab_control)
    tab_control.add(tab, text="Pending Returns")

    tab.grid_columnconfigure(0, weight=1)
    tab.grid_rowconfigure(2, weight=1) # Adjusted for the new top frame

    # --- TOP SEARCH & PRINT FRAME ---
    top_frame = ttk.Frame(tab)
    top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
    
    ttk.Label(top_frame, text="🔍 Search:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 5))
    search_var = tk.StringVar()
    search_entry = ttk.Entry(top_frame, textvariable=search_var, width=40, font=("Segoe UI", 11))
    search_entry.pack(side="left")
    
    # Print Button logic
    def print_search_results():
        if not tree.get_children():
            messagebox.showinfo("No Data", "There are no pending returns to print.")
            return
            
        try:
            os.makedirs("reports", exist_ok=True)
            filepath = os.path.join("reports", f"Pending_Returns_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            
            # Create a Landscape A4 PDF document
            doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
            elements = []
            styles = getSampleStyleSheet()
            
            # Title
            title = Paragraph(f"<b>Pending Returns Report</b> - Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", styles['Title'])
            elements.append(title)
            elements.append(Paragraph("<br/><br/>", styles['Normal']))
            
            # Table Headers
            data = [["Bill No", "Customer Name", "Phone", "Address", "Date", "Pending Items"]]
            
            # Scrape the currently visible Treeview rows
            for parent_id in tree.get_children():
                values = tree.item(parent_id, "values")
                bill_no = values[0]
                name = values[1]
                phone = values[2]
                address = values[3].replace('\n', ' ')
                date = values[4]
                
                # Fetch pending items mapped to this customer
                items = []
                for child_id in tree.get_children(parent_id):
                    c_values = tree.item(child_id, "values")
                    items.append(f"{c_values[5]} (Qty: {c_values[6]})")
                items_str = ", ".join(items)
                
                # Use Paragraphs so long addresses and long item lists wrap neatly inside cells
                addr_p = Paragraph(address, styles["Normal"])
                items_p = Paragraph(items_str, styles["Normal"])
                
                data.append([bill_no, name, phone, addr_p, date, items_p])
                
            # Draw Table
            t = Table(data, colWidths=[60, 130, 90, 200, 70, 230])
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
            log_error("Print Pending Returns", e)

    ttk.Button(top_frame, text="🖨️ Print List", command=print_search_results).pack(side="right", padx=5)

    lbl = ttk.Label(tab, text="Customers with Pending Returns (Double-click to Process)", font=("Segoe UI", 12, "bold"))
    lbl.grid(row=1, column=0, pady=5, padx=10, sticky="w")
    
    # --- TREEVIEW SECTION ---
    tree_frame = ttk.Frame(tab)
    tree_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
    tree_frame.grid_columnconfigure(0, weight=1)
    tree_frame.grid_rowconfigure(0, weight=1)

    columns = ("Bill No", "Name", "Phone", "Address", "Date", "Item Name", "Taken")
    
    style = ttk.Style()
    style.configure("Pending.Treeview", font=("Segoe UI", 11), rowheight=40) 
    style.configure("Pending.Treeview.Heading", font=("Segoe UI", 11, "bold"), padding=(5, 5))
    
    tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
    tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
    
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", 
                        yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set,
                        style="Pending.Treeview", height=15)
    
    tree_scroll_y.config(command=tree.yview)
    tree_scroll_x.config(command=tree.xview)
    
    tree.grid(row=0, column=0, sticky="nsew")
    tree_scroll_y.grid(row=0, column=1, sticky="ns")
    tree_scroll_x.grid(row=1, column=0, sticky="ew")
    
    tree.heading("Bill No", text="Bill No")
    tree.heading("Name", text="Name")
    tree.heading("Phone", text="Phone")
    tree.heading("Address", text="Address")
    tree.heading("Date", text="Date")
    tree.heading("Item Name", text="Item Detail")
    tree.heading("Taken", text="Taken")
    
    tree.column("Bill No", width=100)
    tree.column("Name", width=150)
    tree.column("Phone", width=120)
    tree.column("Address", width=350)
    tree.column("Date", width=100)
    tree.column("Item Name", width=200)
    tree.column("Taken", width=100, anchor="center")

    tree.tag_configure("parent", font=("Segoe UI", 11, "bold"), background="#e6f3ff")
    tree.tag_configure("child", font=("Segoe UI", 11), background="white")

    def load_data(*args):
        try:
            keyword = search_var.get().strip().lower()
            tree.delete(*tree.get_children())
            records = get_pending_returns(db)
            
            for rec in records:
                # Add phone2 safely to search string
                phone2 = rec.get("phone2") or ""
                
                # ---> NEW: Extract all machine names for this customer <---
                item_names = " ".join([item["name"] for item in rec.get("items_data", [])])
                
                # ---> NEW: Added item_names to the search string <---
                search_string = f"{rec['bill_no']} {rec['name']} {rec['phone']} {phone2} {rec['address']} {item_names}".lower()
                
                # Apply filter!
                if keyword and keyword not in search_string:
                    continue
                
                addr = rec["address"] or ""
                wrapped_addr = "\n".join(textwrap.wrap(addr, width=45))
                
                parent_id = tree.insert("", "end", values=(
                    rec["bill_no"], rec["name"], rec["phone"], wrapped_addr,
                    rec["date"], "--- Items Below ---", ""
                ), tags=("parent",), open=True) 
                
                for item in rec["items_data"]:
                    tree.insert(parent_id, "end", values=(
                        "", "", "", "", "", 
                        item["name"], item["taken"]
                    ), tags=("child",))
                    
        except Exception as e:
            log_error("Loading pending returns table", e)
            
    # Trigger load_data automatically when user types in search bar
    search_var.trace_add("write", load_data)

    btn_frame = ttk.Frame(tab)
    btn_frame.grid(row=3, column=0, pady=10)
    ttk.Button(btn_frame, text="🔄 Refresh List", command=load_data).pack()

    load_data()

    def on_row_select_return(event):
        try:
            sel = tree.selection()
            if not sel: return
            
            item_id = sel[0]
            item_values = tree.item(item_id, 'values')
            
            bill_no = item_values[0]
            if not bill_no: # Child row
                parent_id = tree.parent(item_id)
                if parent_id:
                    bill_no = tree.item(parent_id, 'values')[0]
            
            if not bill_no: return
                
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT id FROM rentals WHERE bill_no = ?", (bill_no,))
            res = c.fetchone()
            
            if res:
                rental_id = res[0]
                tab_control.select(0) 
                update_return_fields_from_selection(db, rental_id)
                
        except Exception as e:
            log_error("Selecting pending return", e)

    tree.bind("<Double-1>", on_row_select_return)

    return {
        "frame": tab,
        "reload": load_data,
    }