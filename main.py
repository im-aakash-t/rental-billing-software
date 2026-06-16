# main.py - REFINED VERSION (With Customers CRM Tab)
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sys
import os
from customers_tab import create_customers_tab  # New CRM tab import
# Use shared imports for core functionality
from shared_imports import (
    DBManager, set_modern_theme, safe_float, callbacks
)

class RentalBillingApp:
    """Main application class with enhanced startup and error handling"""
    
    def __init__(self):
        self.root = None
        self.db = None
        self.tab_control = None
        self.tab_reload_funcs = [] 
        self.is_owner = False
        
    def initialize_database(self):
        """Initialize database with error handling"""
        try:
            self.db = DBManager()
            if self.db.conn is None:
                raise Exception("Failed to connect to database")
            
            is_valid, message = self.db.validate_database()
            if not is_valid:
                messagebox.showwarning("Database Issue", 
                                       f"Database validation issue: {message}\n\n"
                                       "The application will attempt to repair automatically.")
            return True
            
        except Exception as e:
            messagebox.showerror(
                "Database Error", 
                f"Failed to initialize database:\n{str(e)}\n\n"
                "Please ensure:\n"
                "• The application has write permissions\n"
                "• rentals.db is not open in another program\n"
                "• There's sufficient disk space"
            )
            return False
    
    def check_database_health(self):
        """Perform basic database health checks"""
        try:
            conn = self.db.get_connection()
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('rentals', 'returns')")
            tables = c.fetchall()
            
            if len(tables) < 2:
                messagebox.showwarning("Database Setup", "Some database tables are missing. The application will create them now.")
            
            db_size = self.db.get_database_size()
            if db_size > 100:
                messagebox.showwarning("Large Database", f"Database size is {db_size}MB. Consider backing up and archiving old data.")
                
        except Exception as e:
            print(f"[WARN] Database health check failed: {e}")
    
    def create_ui(self):
        """Create the main user interface"""
        # --- UI SCALING BUG FIX (Fixes the "Zoomed in" look on Windows) ---
        if os.name == 'nt':
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        try:
            self.root = tk.Tk()
            self.root.title("🏢 Rental Billing Software v2.0")
            
            # --- START MAXIMIZED FOR BEST VIEWING ---
            self.root.geometry("1280x720")
            self.root.minsize(1024, 650)
            try:
                self.root.state('zoomed') # Maximizes window safely
            except tk.TclError:
                pass
            
            # Set modern theme
            set_modern_theme(self.root)
            
            self.create_header()
            self.tab_control = ttk.Notebook(self.root)
            self.tab_control.pack(expand=1, fill="both", padx=10, pady=(5, 10))
            self.create_application_tabs()
            self.create_status_bar()
            
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.bind_shortcuts()
            
            return True
            
        except Exception as e:
            messagebox.showerror("UI Error", f"Failed to create user interface:\n{str(e)}")
            return False

    def create_header(self):
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        ttk.Label(header_frame, text="Dashboard", font=("Segoe UI", 12, "bold")).pack(side="left")
        refresh_btn = ttk.Button(header_frame, text="🔄 Refresh Data", command=self.manual_refresh)
        refresh_btn.pack(side="right")

    def manual_refresh(self):
        try:
            for reload_func in self.tab_reload_funcs:
                if callable(reload_func):
                    try: reload_func()
                    except Exception as e: print(f"[WARN] Tab reload failed: {e}")
            try: callbacks.reload_all_tabs()
            except: pass
            
            self.update_status_bar() 
            print("[INFO] Manual refresh triggered successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to refresh data: {e}")
            messagebox.showerror("Refresh Error", "An error occurred while refreshing data.")
    
    def create_status_bar(self):
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", side="bottom")
        
        self.db_status_var = tk.StringVar(value="🟢 Database: Connected")
        ttk.Label(status_frame, textvariable=self.db_status_var, font=("Segoe UI", 9)).pack(side="left", padx=10)
        
        self.record_count_var = tk.StringVar(value="Records: Loading...")
        ttk.Label(status_frame, textvariable=self.record_count_var, font=("Segoe UI", 9)).pack(side="left", padx=10)
        
        ttk.Label(status_frame, text="v2.0 | Rental Billing System", font=("Segoe UI", 9)).pack(side="right", padx=10)
        
        self.update_status_bar()
    
    def update_status_bar(self):
        try:
            if self.db and self.db.conn:
                c = self.db.conn.cursor()
                c.execute("SELECT COUNT(*) FROM rentals WHERE cancelled IS NULL OR cancelled = 0")
                active_records = c.fetchone()[0]
                
                c.execute("SELECT COUNT(*) FROM rentals WHERE cancelled = 1")
                cancelled_records = c.fetchone()[0]
                
                self.record_count_var.set(f"Active: {active_records} | Cancelled: {cancelled_records}")
                
        except Exception as e:
            self.record_count_var.set("Records: Error")
        
        self.root.after(10000, self.update_status_bar) 
    
    def create_application_tabs(self):
        try:
            from import_helper import create_tab, preload_tab_creators
            preload_tab_creators()
            
            t1 = create_tab('form', self.tab_control, self.db)
            update_return_fields = t1.get("update_return_fields_from_selection")

            t2 = create_tab('partial_returns', self.tab_control, self.db, update_return_fields_from_selection=update_return_fields)
            t3 = create_tab('pending', self.tab_control, self.db)
            
            from daily_report_tab import create_daily_report_tab
            t_daily = create_daily_report_tab(self.tab_control, self.db)
            
            t4 = create_tab('customer_report', self.tab_control, self.db)
            t5 = create_tab('analytics', self.tab_control, self.db)
            
            # --- NEW: Inject the Customers CRM Tab ---
            t_customers = create_customers_tab(self.tab_control, self.db)

            # Add all reload functions so the Refresh button updates everything
            self.tab_reload_funcs = [
                t1.get("reload"), t2.get("reload"), t3.get("reload"),
                t_daily.get("reload"), t4.get("reload"), t5.get("reload"),
                t_customers.get("reload")
            ]
            
            # --- NEW: Inject Materials Report Tab (Equipment Analytics) ONLY for owner view ---
            if self.is_owner:
                from materials_report_tab import create_materials_report_tab
                t_materials = create_materials_report_tab(self.tab_control, self.db)
                self.tab_reload_funcs.append(t_materials.get("reload"))
            
            # Centralize the callback registry to automatically refresh all tabs
            original_reload_all = callbacks.reload_all_tabs
            def global_reload_all_tabs():
                try:
                    if original_reload_all: original_reload_all()
                except Exception as e:
                    print(f"[WARN] Legacy reload failed: {e}")
                for reload_func in self.tab_reload_funcs:
                    if callable(reload_func):
                        try: reload_func()
                        except Exception as e: print(f"[WARN] Dynamic tab reload failed: {e}")
            
            callbacks.reload_all_tabs = global_reload_all_tabs
            
            self.tab_control.select(0)
            
        except Exception as e:
            messagebox.showerror("Tab Error", f"Failed to create application tabs:\n{str(e)}")
            raise
    
    def bind_shortcuts(self):
        self.root.bind('<Control-q>', lambda e: self.on_closing())
        self.root.bind('<Control-b>', lambda e: self.quick_backup())
        self.root.bind('<F5>', lambda e: self.manual_refresh()) 
    
    def quick_backup(self):
        try:
            from drive_backup import backup_files
            backup_files()
            messagebox.showinfo("Backup", "Google Drive backup initiated!")
        except Exception as e:
            messagebox.showerror("Backup Error", f"Backup failed: {e}")
    
    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit the application?"):
            try:
                # 1. Create a local physical backup
                if self.db: self.db.backup_database()
                
                # 2. Silently sync to Google Drive
                try:
                    from drive_backup import backup_files
                    backup_files(silent=True) # Runs silently in background as app closes!
                except Exception as e:
                    print(f"Cloud backup skipped: {e}")

                # 3. Shutdown safely
                if self.db: self.db.close()
                if self.root: self.root.destroy()
            except Exception as e:
                print(f"[ERROR] During shutdown: {e}")
                if self.root: self.root.destroy()
    
    def run(self):
        try:
            print("🚀 Starting Rental Billing Software v2.0...")
            
            # --- AUTHENTICATION ---
            auth_root = tk.Tk()
            auth_root.withdraw()
            while True:
                pwd = simpledialog.askstring("Authentication Required", "Enter Password:", show='*', parent=auth_root)
                if pwd == "AMA":
                    self.is_owner = False
                    break
                elif pwd == "AAKASHBENA":
                    self.is_owner = True
                    break
                elif pwd is None:
                    auth_root.destroy()
                    sys.exit(0)
                else:
                    messagebox.showerror("Access Denied", "Incorrect Password", parent=auth_root)
            auth_root.destroy()
            # ----------------------
            
            if not self.initialize_database(): sys.exit(1)
            try:
                from customers_tab import run_initial_regular_sync
                run_initial_regular_sync(self.db)
                print("👥 Background regular status sync initiated.")
            except Exception as e:
                print(f"[WARN] Failed to start initial regular customer sync: {e}")
            if not self.create_ui(): sys.exit(1)
            
            print("✅ Application started successfully")
            
            # --- NEW: Trigger silent backup on launch ---
            try:
                from drive_backup import backup_files
                backup_files(silent=True)
                print("☁️ Background Smart Sync triggered on startup.")
            except Exception as e:
                print(f"Startup sync skipped: {e}")
                
            self.root.mainloop()
            
        except KeyboardInterrupt:
            print("\n⚠️  Application interrupted by user")
        except Exception as e:
            messagebox.showerror("Fatal Error", f"Application failed to start:\n{str(e)}\n\nPlease check the error logs and try again.")
            sys.exit(1)

def main():
    app = RentalBillingApp()
    app.run()

if __name__ == "__main__":
    main()