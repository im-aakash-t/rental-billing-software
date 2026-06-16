# db_manager.py - REFINED VERSION (With Refund Column)
import sqlite3
import os
from datetime import datetime

class DBManager:
    """Enhanced DB manager with proper constraints, indexes, and error handling."""
    def __init__(self, db_name="rentals.db"):
        self.db_name = db_name
        try:
            self.conn = sqlite3.connect(db_name)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA busy_timeout = 30000") 
            self.create_tables()
            self.create_indexes()
            self.create_triggers()
        except Exception as e:
            print(f"[ERROR] DB connection failed: {e}")
            self.conn = None

    def create_tables(self):
        try:
            c = self.conn.cursor()
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS rentals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bill_no TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL CHECK(length(name) >= 2),
                    phone TEXT NOT NULL CHECK(length(phone) >= 10),
                    phone2 TEXT,
                    address TEXT,
                    id_proof TEXT,
                    machine_codes TEXT, 
                    machines TEXT,      
                    rents TEXT,         
                    quantities TEXT,    
                    total REAL NOT NULL CHECK(total >= 0),
                    advance REAL NOT NULL CHECK(advance >= 0),
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    vehicle TEXT,
                    payment_mode TEXT DEFAULT 'Cash',
                    adv_mode TEXT DEFAULT 'Cash', 
                    cashier_name TEXT,  
                    cancelled INTEGER DEFAULT 0 CHECK(cancelled IN (0,1)),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS rental_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rental_id INTEGER NOT NULL,
                    machine_code TEXT,
                    machine_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    unit_price REAL NOT NULL CHECK(unit_price >= 0),
                    total_price REAL NOT NULL CHECK(total_price >= 0),
                    FOREIGN KEY(rental_id) REFERENCES rentals(id) ON DELETE CASCADE
                )
            """)
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS returns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rental_id INTEGER NOT NULL,
                    return_date TEXT NOT NULL,
                    return_time TEXT NOT NULL,
                    rental_days INTEGER NOT NULL CHECK(rental_days >= 1),
                    due_amount REAL NOT NULL CHECK(due_amount >= 0),
                    deduction REAL DEFAULT 0 CHECK(deduction >= 0),
                    damage REAL DEFAULT 0 CHECK(damage >= 0),
                    balance REAL NOT NULL,
                    amount_paid REAL DEFAULT 0 CHECK(amount_paid >= 0),
                    refund REAL DEFAULT 0 CHECK(refund >= 0),
                    returned_items TEXT NOT NULL,
                    returned_quantities TEXT NOT NULL,
                    payment_mode TEXT DEFAULT 'Cash',
                    paid_mode TEXT DEFAULT 'Cash',
                    cashier_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(rental_id) REFERENCES rentals(id) ON DELETE CASCADE
                )
            """)
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    record_id INTEGER NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('INSERT', 'UPDATE', 'DELETE')),
                    old_values TEXT,
                    new_values TEXT,
                    changed_by TEXT DEFAULT 'system',
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS installments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rental_id INTEGER NOT NULL,
                    amount REAL NOT NULL CHECK(amount > 0),
                    payment_mode TEXT DEFAULT 'Cash',
                    cashier_name TEXT,
                    date_time TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(rental_id) REFERENCES rentals(id) ON DELETE CASCADE
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS refunds_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rental_id INTEGER NOT NULL,
                    amount REAL NOT NULL CHECK(amount > 0),
                    cashier_name TEXT,
                    payment_mode TEXT DEFAULT 'Cash',
                    date_time TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(rental_id) REFERENCES rentals(id) ON DELETE CASCADE
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    phone2 TEXT,
                    address TEXT,
                    is_regular INTEGER DEFAULT 0
                )
            """)
            # --- MIGRATIONS ---
            try:
                c.execute("ALTER TABLE rentals ADD COLUMN cashier_name TEXT")
            except sqlite3.OperationalError: pass 
            
            try:
                c.execute("ALTER TABLE returns ADD COLUMN refund REAL DEFAULT 0")
                print("[INFO] Added 'refund' column to existing returns table.")
            except sqlite3.OperationalError: pass 

            try:
                c.execute("ALTER TABLE returns ADD COLUMN cashier_name TEXT")
                print("[INFO] Added 'cashier_name' column to existing returns table.")
            except sqlite3.OperationalError: pass
            
            try:
                c.execute("ALTER TABLE refunds_history ADD COLUMN payment_mode TEXT DEFAULT 'Cash'")
                print("[INFO] Added 'payment_mode' column to existing refunds_history table.")
            except sqlite3.OperationalError: pass 
            
            self.conn.commit()
            
        except Exception as e:
            print(f"[ERROR] Failed to create tables: {e}")
            raise

    def create_indexes(self):
        try:
            c = self.conn.cursor()
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_rentals_phone ON rentals(phone)",
                "CREATE INDEX IF NOT EXISTS idx_rentals_bill_no ON rentals(bill_no)",
                "CREATE INDEX IF NOT EXISTS idx_rentals_date ON rentals(date)",
                "CREATE INDEX IF NOT EXISTS idx_rentals_cancelled ON rentals(cancelled)",
                "CREATE INDEX IF NOT EXISTS idx_rentals_name ON rentals(name)",
                "CREATE INDEX IF NOT EXISTS idx_returns_rental_id ON returns(rental_id)",
                "CREATE INDEX IF NOT EXISTS idx_returns_date ON returns(return_date)",
                "CREATE INDEX IF NOT EXISTS idx_returns_balance ON returns(balance)",
                "CREATE INDEX IF NOT EXISTS idx_audit_table_record ON audit_log(table_name, record_id)",
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(changed_at)",
                "CREATE INDEX IF NOT EXISTS idx_installments_rental_id ON installments(rental_id)"
            ]
            for index_sql in indexes: c.execute(index_sql)
            self.conn.commit()
        except Exception as e: print(f"[ERROR] Failed to create indexes: {e}")

    def create_triggers(self):
        try:
            c = self.conn.cursor()
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS update_rentals_timestamp 
                AFTER UPDATE ON rentals
                FOR EACH ROW
                BEGIN
                    UPDATE rentals SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END
            """)
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS audit_rentals_update
                AFTER UPDATE ON rentals
                FOR EACH ROW
                BEGIN
                    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
                    VALUES ('rentals', NEW.id, 'UPDATE', 
                            json_object('bill_no', OLD.bill_no, 'total', OLD.total, 'advance', OLD.advance),
                            json_object('bill_no', NEW.bill_no, 'total', NEW.total, 'advance', NEW.advance));
                END
            """)
            self.conn.commit()
        except Exception as e: print(f"[WARN] Could not create triggers: {e}")

    def get_connection(self):
        if self.conn is None:
            try:
                self.conn = sqlite3.connect(self.db_name)
                self.conn.row_factory = sqlite3.Row
                self.conn.execute("PRAGMA foreign_keys = ON")
            except Exception as e: raise
        try:
            self.conn.execute("SELECT 1")
        except sqlite3.Error:
            try:
                self.conn.close()
                self.conn = sqlite3.connect(self.db_name)
                self.conn.row_factory = sqlite3.Row
                self.conn.execute("PRAGMA foreign_keys = ON")
            except Exception as e: raise
        return self.conn

    def validate_database(self):
        try:
            c = self.conn.cursor()
            for table in ['rentals', 'returns', 'audit_log', 'installments']:
                c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                if not c.fetchone(): return False, f"Missing table: {table}"
            c.execute("PRAGMA foreign_key_check")
            if c.fetchall(): return False, "Foreign key violations found"
            return True, "Database validation passed"
        except Exception as e: return False, f"Validation error: {e}"

    def backup_database(self, backup_path=None):
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.db_name}.backup_{timestamp}"
        try:
            backup_conn = sqlite3.connect(backup_path)
            with backup_conn: self.conn.backup(backup_conn)
            backup_conn.close()
            return True
        except Exception as e: return False

    def get_database_size(self):
        try: return round(os.path.getsize(self.db_name) / (1024 * 1024), 2)
        except Exception: return 0

    def close(self):
        if self.conn:
            try:
                self.backup_database()
                self.conn.close()
                self.conn = None
            except Exception as e: pass

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()