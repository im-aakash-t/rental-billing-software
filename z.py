import sqlite3

# POINT THIS TO YOUR OLD DATABASE
DB_PATH = 'old_rental.db' 

def migrate_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Starting migration...")
        # Turn off foreign keys temporarily so we can safely rebuild tables
        cursor.execute("PRAGMA foreign_keys=OFF;")
        cursor.execute("BEGIN TRANSACTION;")
        
        # 1. MIGRATE: rentals (Removes strict CHECK constraints)
        print("Migrating 'rentals' table...")
        cursor.execute("ALTER TABLE rentals RENAME TO temp_rentals;")
        cursor.execute("""
            CREATE TABLE rentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_no TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                phone2 TEXT,
                address TEXT,
                id_proof TEXT,
                machine_codes TEXT,
                machines TEXT,
                rents TEXT,
                quantities TEXT,
                total REAL NOT NULL,
                advance REAL NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                vehicle TEXT,
                payment_mode TEXT DEFAULT 'Cash',
                adv_mode TEXT DEFAULT 'Cash',
                cashier_name TEXT,
                cancelled INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO rentals (
                id, bill_no, name, phone, phone2, address, id_proof, machine_codes, machines, 
                rents, quantities, total, advance, date, time, vehicle, payment_mode, adv_mode, 
                cashier_name, cancelled, created_at, updated_at
            )
            SELECT 
                id, bill_no, name, phone, phone2, address, id_proof, machine_codes, machines, 
                rents, quantities, total, advance, date, time, vehicle, payment_mode, adv_mode, 
                cashier_name, cancelled, created_at, updated_at
            FROM temp_rentals;
        """)
        cursor.execute("DROP TABLE temp_rentals;")

        # 2. MIGRATE: rental_items (Removes CHECK constraints)
        print("Migrating 'rental_items' table...")
        cursor.execute("ALTER TABLE rental_items RENAME TO temp_rental_items;")
        cursor.execute("""
            CREATE TABLE rental_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rental_id INTEGER NOT NULL,
                machine_code TEXT,
                machine_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                FOREIGN KEY(rental_id) REFERENCES rentals(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            INSERT INTO rental_items (id, rental_id, machine_code, machine_name, quantity, unit_price, total_price)
            SELECT id, rental_id, machine_code, machine_name, quantity, unit_price, total_price FROM temp_rental_items;
        """)
        cursor.execute("DROP TABLE temp_rental_items;")

        # 3. MIGRATE: returns (Removes CHECK constraints)
        print("Migrating 'returns' table...")
        cursor.execute("ALTER TABLE returns RENAME TO temp_returns;")
        cursor.execute("""
            CREATE TABLE returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rental_id INTEGER NOT NULL,
                return_date TEXT NOT NULL,
                return_time TEXT NOT NULL,
                rental_days INTEGER NOT NULL,
                due_amount REAL NOT NULL,
                deduction REAL DEFAULT 0,
                damage REAL DEFAULT 0,
                balance REAL NOT NULL,
                amount_paid REAL DEFAULT 0,
                refund REAL DEFAULT 0,
                returned_items TEXT NOT NULL,
                returned_quantities TEXT NOT NULL,
                payment_mode TEXT DEFAULT 'Cash',
                paid_mode TEXT DEFAULT 'Cash',
                cashier_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(rental_id) REFERENCES rentals(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            INSERT INTO returns (
                id, rental_id, return_date, return_time, rental_days, due_amount, 
                deduction, damage, balance, amount_paid, refund, returned_items, 
                returned_quantities, payment_mode, paid_mode, cashier_name, created_at
            ) 
            SELECT 
                id, rental_id, return_date, return_time, rental_days, due_amount, 
                deduction, damage, balance, amount_paid, refund, returned_items, 
                returned_quantities, payment_mode, paid_mode, cashier_name, created_at 
            FROM temp_returns;
        """)
        cursor.execute("DROP TABLE temp_returns;")

        # 4. MIGRATE: installments (Adds DEFAULT 'Cash', NOT NULL, and Foreign Key)
        print("Migrating 'installments' table...")
        cursor.execute("ALTER TABLE installments RENAME TO temp_installments;")
        cursor.execute("""
            CREATE TABLE installments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rental_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_mode TEXT DEFAULT 'Cash',
                cashier_name TEXT,
                date_time TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(rental_id) REFERENCES rentals(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            INSERT INTO installments (id, rental_id, amount, payment_mode, cashier_name, date_time, created_at)
            SELECT id, rental_id, amount, COALESCE(payment_mode, 'Cash'), cashier_name, date_time, created_at FROM temp_installments;
        """)
        cursor.execute("DROP TABLE temp_installments;")

        # 5. CREATE NEW: refunds_history
        print("Creating 'refunds_history' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refunds_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rental_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                cashier_name TEXT,
                payment_mode TEXT DEFAULT 'Cash',
                date_time TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(rental_id) REFERENCES rentals(id) ON DELETE CASCADE
            )
        """)

        # 6. RECREATE INDEXES (Required because dropping tables removes their indexes)
        print("Rebuilding Indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_rentals_phone ON rentals(phone);",
            "CREATE INDEX IF NOT EXISTS idx_rentals_bill_no ON rentals(bill_no);",
            "CREATE INDEX IF NOT EXISTS idx_rentals_date ON rentals(date);",
            "CREATE INDEX IF NOT EXISTS idx_rentals_cancelled ON rentals(cancelled);",
            "CREATE INDEX IF NOT EXISTS idx_rentals_name ON rentals(name);",
            "CREATE INDEX IF NOT EXISTS idx_returns_rental_id ON returns(rental_id);",
            "CREATE INDEX IF NOT EXISTS idx_returns_date ON returns(return_date);",
            "CREATE INDEX IF NOT EXISTS idx_returns_balance ON returns(balance);",
            "CREATE INDEX IF NOT EXISTS idx_installments_rental_id ON installments(rental_id);"
        ]
        for idx in indexes:
            cursor.execute(idx)

        # 7. RECREATE TRIGGERS (Required for timestamps and audit logs)
        print("Rebuilding Triggers...")
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_rentals_timestamp 
            AFTER UPDATE ON rentals
            FOR EACH ROW
            BEGIN
                UPDATE rentals SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS audit_rentals_update
            AFTER UPDATE ON rentals
            FOR EACH ROW
            BEGIN
                INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
                VALUES ('rentals', NEW.id, 'UPDATE', 
                        json_object('bill_no', OLD.bill_no, 'total', OLD.total, 'advance', OLD.advance),
                        json_object('bill_no', NEW.bill_no, 'total', NEW.total, 'advance', NEW.advance));
            END;
        """)

        conn.commit()
        print("\n✅ Success! Database structure has been fully updated.")

    except sqlite3.Error as e:
        conn.rollback()
        print(f"\n❌ [ERROR] Migration failed: {e}")
        print("Changes rolled back. Data is safe.")
    finally:
        cursor.execute("PRAGMA foreign_keys=ON;")
        conn.close()

if __name__ == "__main__":
    migrate_db()