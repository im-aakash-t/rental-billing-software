# cloud/local_sync.py - change tracking inside the local SQLite database.
#
# Tables added (the business tables are not altered):
#   sync_meta    key/value settings: branch_code, device_id, pull cursor, ...
#   sync_ids     local integer id  <->  global uuid, per table
#   sync_outbox  one row per local change waiting to be uploaded
#
# Triggers on the business tables fill sync_ids/sync_outbox for every insert,
# update and delete, whoever makes it (web UI, old Tk UI, scripts). While the
# sync engine applies downloaded changes it sets sync_meta.applying = '1' so
# those writes are not echoed back to the cloud.
import uuid

SYNCED_TABLES = ["rentals", "rental_items", "returns", "installments", "refunds_history", "customers"]

# SQLite expression producing a random (version 4) uuid string
_UUID_SQL = ("lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || "
             "substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || "
             "substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6)))")
_NOT_APPLYING = "(SELECT value FROM sync_meta WHERE key = 'applying') IS NOT '1'"


def install(conn):
    """Create the sync tables/triggers (idempotent) and give every existing row a uuid."""
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS sync_meta (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS sync_ids (
                    tbl TEXT NOT NULL, local_id INTEGER NOT NULL, uuid TEXT NOT NULL,
                    PRIMARY KEY (tbl, local_id))""")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS sync_ids_uuid ON sync_ids (tbl, uuid)")
    c.execute("""CREATE TABLE IF NOT EXISTS sync_outbox (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    tbl TEXT NOT NULL, local_id INTEGER NOT NULL, op TEXT NOT NULL,
                    uuid TEXT, extra TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("CREATE INDEX IF NOT EXISTS sync_outbox_row ON sync_outbox (tbl, local_id)")
    if get_meta(conn, "device_id") is None:
        set_meta(conn, "device_id", "pc-" + uuid.uuid4().hex[:12])

    for t in SYNCED_TABLES:
        # returns rows are identified in the cloud by their rental, so a delete
        # must remember which rental it belonged to (extra = local rental id)
        extra_old = "OLD.rental_id" if t != "rentals" and t != "customers" else "NULL"
        if t == "customers":
            extra_old = "OLD.phone"
        c.executescript(f"""
            CREATE TRIGGER IF NOT EXISTS sync_{t}_ins AFTER INSERT ON {t} WHEN {_NOT_APPLYING}
            BEGIN
              INSERT OR IGNORE INTO sync_ids (tbl, local_id, uuid) VALUES ('{t}', NEW.id, {_UUID_SQL});
              INSERT INTO sync_outbox (tbl, local_id, op) VALUES ('{t}', NEW.id, 'U');
            END;
            CREATE TRIGGER IF NOT EXISTS sync_{t}_upd AFTER UPDATE ON {t} WHEN {_NOT_APPLYING}
            BEGIN
              INSERT OR IGNORE INTO sync_ids (tbl, local_id, uuid) VALUES ('{t}', NEW.id, {_UUID_SQL});
              INSERT INTO sync_outbox (tbl, local_id, op) VALUES ('{t}', NEW.id, 'U');
            END;
            CREATE TRIGGER IF NOT EXISTS sync_{t}_del AFTER DELETE ON {t} WHEN {_NOT_APPLYING}
            BEGIN
              INSERT INTO sync_outbox (tbl, local_id, op, uuid, extra)
              VALUES ('{t}', OLD.id, 'D',
                      (SELECT uuid FROM sync_ids WHERE tbl = '{t}' AND local_id = OLD.id), {extra_old});
            END;
        """)
        # rows that existed before sync was installed get their uuid now
        c.execute(f"""INSERT OR IGNORE INTO sync_ids (tbl, local_id, uuid)
                      SELECT '{t}', id, {_UUID_SQL} FROM {t}""")
    conn.commit()


def is_installed(conn):
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_meta'").fetchone()
    return row is not None


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn, key, value):
    conn.execute("INSERT INTO sync_meta (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, None if value is None else str(value)))
    conn.commit()


def queue_everything(conn):
    """Put every existing row in the outbox (first upload of a branch's history)."""
    for t in SYNCED_TABLES:
        conn.execute(f"INSERT INTO sync_outbox (tbl, local_id, op) SELECT '{t}', id, 'U' FROM {t}")
    conn.commit()


def pending_count(conn):
    return conn.execute("SELECT COUNT(*) FROM sync_outbox").fetchone()[0]
