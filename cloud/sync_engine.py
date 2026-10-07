# cloud/sync_engine.py - upload local changes / download this branch's changes.
#
# Database work is passed to `run_db(fn, *args)` so it executes on the app's
# single database thread (the same thread the billing logic uses). That keeps
# the "applying" flag safe: no app write can slip in while downloaded rows are
# being applied with change-tracking switched off.
#
# Identity in the cloud:
#   rentals, rental_items, installments, refunds_history -> uuid from sync_ids
#   returns   -> its rental (the app keeps one return row per bill)
#   customers -> (branch, phone)   (phone is the customer key in the app)
# Conflicts: "branch wins" - a downloaded change is skipped when this PC still
# has an unsent change for the same record; the PC's version is uploaded next.
import csv
import hashlib
import os
import threading
import time
from datetime import datetime, timezone, timedelta

from cloud import config, local_sync as LS
from cloud.client import CloudError, AuthError

COLUMNS = {
    "rentals": ["bill_no", "name", "phone", "phone2", "address", "id_proof", "machine_codes", "machines", "rents",
                "quantities", "total", "advance", "date", "time", "vehicle", "payment_mode", "adv_mode",
                "cashier_name", "cancelled", "created_at"],
    "rental_items": ["machine_code", "machine_name", "quantity", "unit_price", "total_price"],
    "returns": ["return_date", "return_time", "rental_days", "due_amount", "deduction", "damage", "balance",
                "amount_paid", "refund", "returned_items", "returned_quantities", "payment_mode", "paid_mode",
                "cashier_name", "created_at"],
    "installments": ["amount", "payment_mode", "cashier_name", "date_time", "created_at"],
    "refunds_history": ["amount", "cashier_name", "payment_mode", "date_time", "created_at"],
    "customers": ["name", "phone", "phone2", "address", "is_regular"],
}
CHILD_TABLES = ("rental_items", "returns", "installments", "refunds_history")
# Cloud text columns that hold whatever the app stored (SQLite is dynamically typed)
TEXT_NUMBERS = {("rentals", "total"), ("rentals", "advance")}
NUMERIC = {
    "rentals": {"cancelled"}, "rental_items": {"quantity", "unit_price", "total_price"},
    "returns": {"rental_days", "due_amount", "deduction", "damage", "balance", "amount_paid", "refund"},
    "installments": {"amount"}, "refunds_history": {"amount"}, "customers": {"is_regular"},
}


def to_cloud(tbl, col, v):
    """Convert a local SQLite value for the matching cloud column (lossless for real numbers)."""
    if (tbl, col) in TEXT_NUMBERS:
        if v is None:
            return None
        return repr(v) if isinstance(v, float) else str(v)
    if col in NUMERIC.get(tbl, ()) and isinstance(v, str):
        try:
            return float(v) if v.strip() else None
        except ValueError:
            return None
    return v
ORDER = ["rentals", "customers", "rental_items", "returns", "installments", "refunds_history"]
BATCH = 400


def _uuid_for(conn, tbl, local_id):
    row = conn.execute("SELECT uuid FROM sync_ids WHERE tbl = ? AND local_id = ?", (tbl, local_id)).fetchone()
    return row[0] if row else None


def _local_for(conn, tbl, uuid):
    row = conn.execute("SELECT local_id FROM sync_ids WHERE tbl = ? AND uuid = ?", (tbl, uuid)).fetchone()
    return row[0] if row else None


def _has_pending(conn, tbl, local_id):
    return conn.execute("SELECT 1 FROM sync_outbox WHERE tbl = ? AND local_id = ? LIMIT 1",
                        (tbl, local_id)).fetchone() is not None


# ============================================================== upload (DB part)
def collect_outbox(db, branch, device):
    """Read the outbox and turn it into cloud operations. Returns (max_seq, plan)."""
    conn = db.get_connection()
    max_seq = conn.execute("SELECT MAX(seq) FROM sync_outbox").fetchone()[0]
    if max_seq is None:
        return None, None
    latest = {}
    for seq, tbl, local_id, op, uuid, extra in conn.execute(
            "SELECT seq, tbl, local_id, op, uuid, extra FROM sync_outbox WHERE seq <= ? ORDER BY seq", (max_seq,)):
        latest[(tbl, local_id)] = (op, uuid, extra)

    plan = {t: {"upsert": [], "delete_ids": [], "delete_returns_of": [], "skip": 0} for t in ORDER}
    returns_rentals = set()
    for (tbl, local_id), (op, uuid, extra) in latest.items():
        if tbl == "returns":
            # decided per rental from the current state (handles delete + re-insert)
            rid = conn.execute("SELECT rental_id FROM returns WHERE id = ?", (local_id,)).fetchone()
            returns_rentals.add(rid[0] if rid else (int(extra) if extra not in (None, "") else None))
            continue
        row = conn.execute(f"SELECT * FROM {tbl} WHERE id = ?", (local_id,)).fetchone() if op == "U" else None
        if row is None:
            if tbl in ("rental_items", "installments", "refunds_history") and uuid:
                plan[tbl]["delete_ids"].append(uuid)
            continue                                   # rentals/customers are never deleted by the app
        rec = {c: to_cloud(tbl, c, row[c]) for c in COLUMNS[tbl]}
        rec.update(branch_id=branch, updated_by=device, deleted=False)
        if tbl == "customers":
            pass                                        # keyed by (branch_id, phone)
        else:
            rec["id"] = _uuid_for(conn, tbl, local_id)
            if tbl != "rentals":
                rec["rental_id"] = _uuid_for(conn, "rentals", row["rental_id"])
                if not rec["rental_id"]:
                    plan[tbl]["skip"] += 1
                    continue
        plan[tbl]["upsert"].append(rec)

    for rental_local in returns_rentals:
        if rental_local is None:
            continue
        rental_uuid = _uuid_for(conn, "rentals", rental_local)
        if not rental_uuid:
            continue
        row = conn.execute("SELECT * FROM returns WHERE rental_id = ? ORDER BY id DESC LIMIT 1", (rental_local,)).fetchone()
        if row is None:
            plan["returns"]["delete_returns_of"].append(rental_uuid)
        else:
            rec = {c: to_cloud("returns", c, row[c]) for c in COLUMNS["returns"]}
            rec.update(branch_id=branch, updated_by=device, deleted=False, rental_id=rental_uuid)
            plan["returns"]["upsert"].append(rec)
    return max_seq, plan


def clear_outbox(db, max_seq):
    conn = db.get_connection()
    conn.execute("DELETE FROM sync_outbox WHERE seq <= ?", (max_seq,))
    conn.commit()


# ============================================================== download (DB part)
def apply_remote(db, tbl, rows, device):
    """Apply downloaded rows for one table. Returns (applied, skipped)."""
    conn = db.get_connection()
    applied = skipped = 0
    conn.execute("INSERT INTO sync_meta (key, value) VALUES ('applying', '1') "
                 "ON CONFLICT(key) DO UPDATE SET value = '1'")
    try:
        for r in rows:
            if r.get("updated_by") == device:
                continue
            cols = COLUMNS[tbl]
            vals = {c: r.get(c) for c in cols}
            if tbl == "customers":
                local = conn.execute("SELECT id FROM customers WHERE phone = ?", (r["phone"],)).fetchone()
                if local and _has_pending(conn, tbl, local[0]):
                    skipped += 1; continue
                if r.get("deleted"):
                    continue
                if local:
                    conn.execute("UPDATE customers SET name=?, phone2=?, address=?, is_regular=? WHERE id=?",
                                 (vals["name"], vals["phone2"], vals["address"], vals["is_regular"], local[0]))
                else:
                    conn.execute("INSERT INTO customers (name, phone, phone2, address, is_regular) VALUES (?,?,?,?,?)",
                                 (vals["name"], vals["phone"], vals["phone2"], vals["address"], vals["is_regular"]))
                applied += 1
                continue

            if tbl != "rentals":
                rental_local = _local_for(conn, "rentals", r["rental_id"])
                if rental_local is None:
                    skipped += 1; continue
                vals["rental_id"] = rental_local

            if tbl == "returns":
                local = conn.execute("SELECT id FROM returns WHERE rental_id = ?", (rental_local,)).fetchone()
                local_id = local[0] if local else None
                pending = conn.execute("SELECT 1 FROM sync_outbox WHERE tbl='returns' AND (local_id = ? OR extra = ?) LIMIT 1",
                                       (local_id if local_id is not None else -1, str(rental_local))).fetchone()
                if pending:
                    skipped += 1; continue
            else:
                local_id = _local_for(conn, tbl, r["id"])
                if local_id is not None and _has_pending(conn, tbl, local_id):
                    skipped += 1; continue
                if local_id is not None and not conn.execute(f"SELECT 1 FROM {tbl} WHERE id = ?", (local_id,)).fetchone():
                    local_id = None if not r.get("deleted") else local_id

            if r.get("deleted"):
                if local_id is not None:
                    conn.execute(f"DELETE FROM {tbl} WHERE id = ?", (local_id,))
                    applied += 1
                continue

            keys = list(vals.keys())
            if local_id is not None:
                conn.execute(f"UPDATE {tbl} SET " + ", ".join(f"{k} = ?" for k in keys) + " WHERE id = ?",
                             [vals[k] for k in keys] + [local_id])
            else:
                if vals.get("created_at") is None:
                    keys.remove("created_at") if "created_at" in keys else None
                cur = conn.execute(f"INSERT INTO {tbl} (" + ", ".join(keys) + ") VALUES (" +
                                   ", ".join("?" for _ in keys) + ")", [vals[k] for k in keys])
                if tbl != "returns":
                    conn.execute("INSERT OR REPLACE INTO sync_ids (tbl, local_id, uuid) VALUES (?, ?, ?)",
                                 (tbl, cur.lastrowid, r["id"]))
            applied += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("UPDATE sync_meta SET value = '0' WHERE key = 'applying'")
        conn.commit()
    return applied, skipped


# ============================================================== engine
class SyncEngine:
    def __init__(self, db_provider, run_db, notify=None, materials_path="materials.csv"):
        self.db_provider = db_provider          # () -> DBManager or None
        self.run_db = run_db
        self.notify = notify or (lambda *a: None)
        self.materials_path = materials_path
        self.session = None
        self.state = {"online": False, "last_sync": None, "pending": 0, "error": None, "running": False,
                      "needs_login": False}
        self._wake = threading.Event()
        self._stop = False
        self._lock = threading.Lock()
        self._thread = None

    # ------------------------------------------------------------ control
    def start(self, session):
        self.session = session
        self.state["needs_login"] = False
        if not self._thread:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="cloud-sync")
            self._thread.start()
        self.kick()

    def kick(self):
        self._wake.set()

    def stop(self):
        self._stop = True
        self._wake.set()

    def _loop(self):
        while not self._stop:
            self.sync_once()
            self._wake.wait(config.SYNC_INTERVAL_SECONDS)
            self._wake.clear()

    # ------------------------------------------------------------ one round
    def sync_once(self):
        with self._lock:
            db = self.db_provider()
            if db is None or self.session is None:
                return False
            self.state["running"] = True
            try:
                meta = self.run_db(lambda: {k: LS.get_meta(db.get_connection(), k) for k in
                                            ("branch_code", "device_id", "pull_cursor")})
                branch, device = meta["branch_code"], meta["device_id"]
                if not branch:
                    return False
                pushed = self._push(db, branch, device)
                pulled = self._pull(db, branch, device, meta["pull_cursor"])
                self._push_materials(db, branch, device)
                self.state["pending"] = self.run_db(lambda: LS.pending_count(db.get_connection()))
                self._report_status(branch, device)
                self.state.update(online=True, error=None, last_sync=datetime.now().strftime("%d-%m-%y %I:%M:%S %p"))
                if pulled:
                    self.notify("pulled", pulled)
                return True
            except AuthError as e:
                self.state.update(online=True, error=f"Sign in again to sync ({e})", needs_login=True)
            except CloudError as e:
                self.state.update(online=not e.offline, error=None if e.offline else str(e))
            except Exception as e:
                self.state.update(error=str(e))
                print(f"[SYNC] error: {e}")
            finally:
                self.state["running"] = False
                try:
                    self.state["pending"] = self.run_db(lambda: LS.pending_count(db.get_connection()))
                except Exception:
                    pass
            return False

    def _push(self, db, branch, device):
        total = 0
        while True:
            max_seq, plan = self.run_db(collect_outbox, db, branch, device)
            if max_seq is None:
                return total
            s = self.session
            for tbl in ORDER:
                p = plan[tbl]
                conflict = {"customers": "branch_id,phone", "returns": "rental_id"}.get(tbl, "id")
                for i in range(0, len(p["upsert"]), BATCH):
                    s.upsert(tbl, p["upsert"][i:i + BATCH], conflict)
                for i in range(0, len(p["delete_ids"]), 100):
                    ids = ",".join(p["delete_ids"][i:i + 100])
                    s.update(tbl, {"id": f"in.({ids})"}, {"deleted": True, "updated_by": device})
                for i in range(0, len(p["delete_returns_of"]), 100):
                    ids = ",".join(p["delete_returns_of"][i:i + 100])
                    s.update(tbl, {"rental_id": f"in.({ids})"}, {"deleted": True, "updated_by": device})
                total += len(p["upsert"]) + len(p["delete_ids"]) + len(p["delete_returns_of"])
            self.run_db(clear_outbox, db, max_seq)

    def _pull(self, db, branch, device, cursor):
        since = cursor or "1970-01-01T00:00:00+00:00"
        try:
            since_dt = datetime.fromisoformat(since) - timedelta(seconds=config.PULL_OVERLAP_SECONDS)
        except ValueError:
            since_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        since_q = since_dt.isoformat()
        newest = cursor
        applied_total = 0
        for tbl in ORDER:
            offset = 0
            while True:
                rows = self.session.select(tbl, {"branch_id": f"eq.{branch}", "updated_at": f"gt.{since_q}",
                                                 "or": f"(updated_by.is.null,updated_by.neq.{device})",
                                                 "order": "updated_at.asc,id.asc", "limit": 1000, "offset": offset,
                                                 "select": "*"})
                if not rows:
                    break
                applied, _ = self.run_db(apply_remote, db, tbl, rows, device)
                applied_total += applied
                for r in rows:
                    if newest is None or r["updated_at"] > newest:
                        newest = r["updated_at"]
                if len(rows) < 1000:
                    break
                offset += 1000
        if newest and newest != cursor:
            self.run_db(lambda: LS.set_meta(db.get_connection(), "pull_cursor", newest))
        return applied_total

    def _push_materials(self, db, branch, device):
        """Upload this branch's materials.csv (prices + stock) when it changes."""
        if not os.path.exists(self.materials_path):
            return
        with open(self.materials_path, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()
        if self.run_db(lambda: LS.get_meta(db.get_connection(), "materials_hash")) == digest:
            return
        rows, seen = [], set()
        with open(self.materials_path, newline="", encoding="utf-8") as f:
            for i, r in enumerate(csv.DictReader(f)):
                code = (r.get("code") or "").strip()
                code = str(int(code)) if code.isdigit() else code.upper()
                name = (r.get("name") or "").strip()
                try:
                    price = float((r.get("price") or "").strip())
                except ValueError:
                    continue
                if not code or not name or code in seen:
                    continue
                seen.add(code)
                try:
                    qty = int(float((r.get("quantity") or "0").strip() or 0))
                except ValueError:
                    qty = 0
                rows.append({"branch_id": branch, "code": code, "name": name, "price": price, "quantity": qty,
                             "sort_order": i, "updated_by": device, "deleted": False})
        for i in range(0, len(rows), BATCH):
            self.session.upsert("materials", rows[i:i + BATCH], "branch_id,code")
        existing = self.session.select("materials", {"branch_id": f"eq.{branch}", "deleted": "eq.false", "select": "code"})
        gone = [m["code"] for m in existing if m["code"] not in seen]
        for code in gone:
            self.session.update("materials", {"branch_id": f"eq.{branch}", "code": f"eq.{code}"},
                                {"deleted": True, "updated_by": device})
        self.run_db(lambda: LS.set_meta(db.get_connection(), "materials_hash", digest))

    def _report_status(self, branch, device):
        try:
            self.session.upsert("sync_status", [{"branch_id": branch, "device_id": device,
                                                 "last_sync_at": datetime.now(timezone.utc).isoformat(),
                                                 "pending": self.state["pending"], "app_version": "2.0"}], "branch_id")
        except CloudError:
            pass
