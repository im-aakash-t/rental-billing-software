# webapp/server.py - Local API server + desktop window for the web UI.
#
# * Flask serves the HTML/JS/CSS and a small JSON API on 127.0.0.1 only.
# * Every database operation runs on ONE worker thread (like the Tkinter
#   mainloop did), so the SQLite connection is never shared across threads.
# * A random token generated at launch must accompany every API call, so other
#   programs or web pages on this PC cannot call the API.
import logging
import os
import secrets
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, abort, jsonify, request, send_from_directory
from werkzeug.serving import make_server

from webapp import services, reports
from webapp.services import UserError

APP_TITLE = "Rental Billing Software v2.0"

if getattr(sys, 'frozen', False):
    WEBAPP_DIR = os.path.join(sys._MEIPASS, "webapp")
else:
    WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(WEBAPP_DIR, "static")
ICON_PATH = os.path.join(WEBAPP_DIR, "app.ico")


class Backend:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-worker")
        self.token = secrets.token_urlsafe(32)
        self.db = None
        self.is_owner = None
        self.window = None
        self.quit_confirmed = False
        self._notes = []
        self._notes_lock = threading.Lock()

    def run(self, fn, *args, **kwargs):
        """Run fn on the database worker thread and wait for its result."""
        return self.executor.submit(fn, *args, **kwargs).result()

    def with_db(self, fn, *args, **kwargs):
        if self.db is None:
            raise UserError("Not Ready", "The database is not open yet.")
        return self.run(fn, self.db, *args, **kwargs)

    def notify(self, kind, title, message):
        with self._notes_lock:
            self._notes.append({"kind": kind, "title": title, "message": message})

    def take_notes(self):
        with self._notes_lock:
            notes, self._notes = self._notes, []
        return notes

    def shutdown(self):
        """Same as on_closing() in main.py once the user confirmed."""
        if self.db is None:
            return
        def _close(db):
            try:
                db.backup_database()
                try:
                    from drive_backup import backup_files
                    backup_files(silent=True)
                except Exception as e:
                    print(f"Cloud backup skipped: {e}")
                db.close()
            except Exception as e:
                print(f"[ERROR] During shutdown: {e}")
        try:
            self.run(_close, self.db)
        finally:
            self.db = None


backend = Backend()


# ---------------------------------------------------------------------------
# API methods: name -> handler(**params)
# ---------------------------------------------------------------------------

def _login(password=""):
    result = services.check_password(password)
    backend.is_owner = result["is_owner"]
    return result


def _init():
    if backend.is_owner is None:
        raise UserError("Access Denied", "Please log in first.")
    if backend.db is None:
        db, warning = backend.run(services.initialize_database)
        backend.db = db
        try:
            from drive_backup import backup_files
            backup_files(silent=True)
            print("☁️ Background Smart Sync triggered on startup.")
        except Exception as e:
            print(f"Startup sync skipped: {e}")
    else:
        warning = None
    return {
        "is_owner": backend.is_owner,
        "warning": warning,
        "materials": services.materials_list(),
        "bill_no": backend.with_db(services.next_bill_no),
    }


def _owner_only():
    if not backend.is_owner:
        raise UserError("Access Denied", "This report is only available in the owner view.")


def _export_equipment_csv(rows):
    if not rows:
        raise UserError("No Data", "There are no records to export.", kind="info")
    import webview
    result = backend.window.create_file_dialog(
        webview.FileDialog.SAVE, save_filename="Equipment_Analytics.csv",
        file_types=("CSV Files (*.csv)", "All Files (*.*)"))
    if not result:
        return None
    filepath = result if isinstance(result, str) else result[0]
    if not os.path.splitext(filepath)[1]:
        filepath += ".csv"
    return reports.equipment_csv(rows, filepath)


def _scan_id(bill_no, name, id_type):
    """Run the WIA scanner on its own COM-initialised thread (it shows its own dialog)."""
    outcome = {}
    def work():
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pythoncom = None
        try:
            from scanner_helper import scan_id_image
            outcome["result"] = scan_id_image(bill_no, name, id_type)
        except ImportError as e:
            outcome["import_error"] = e
        except Exception as e:
            outcome["result"] = ("error", e)
        finally:
            if pythoncom:
                try: pythoncom.CoUninitialize()
                except Exception: pass
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join()
    if "import_error" in outcome:
        raise UserError("Error", f"scanner_helper.py missing or dependency import failed! Cannot scan.\n\nDetails: {outcome['import_error']}")
    status, value = outcome["result"]
    if status == "saved":
        return {"status": "saved", "message": f"ID Proof saved securely as:\n{value[1]}"}
    if status == "error":
        raise UserError("Scanner Error ⚠️",
                        f"Could not connect to the scanner.\n\n"
                        f"1. Check if the scanner is plugged in and turned on.\n"
                        f"2. Check if Windows recognizes the scanner.\n\n"
                        f"Technical Error: {value}")
    return {"status": "cancelled"}


def _quit():
    backend.quit_confirmed = True
    if backend.window:
        threading.Thread(target=backend.window.destroy, daemon=True).start()
    return True


D = backend.with_db
API = {
    # shell
    "login": _login,
    "init": _init,
    "status": lambda: D(services.status_counts),
    "notes": backend.take_notes,
    "quit": _quit,
    "cloud_backup": lambda: services.start_cloud_backup(),
    # outward billing form
    "next_bill_no": lambda: D(services.next_bill_no),
    "outward_table": lambda **p: D(services.outward_table, **p),
    "phone_info": lambda phone, rental_id=None: D(services.phone_info, phone, rental_id),
    "phone_suggestions": lambda query, second=False: D(services.phone_suggestions, query, second),
    "pick_customer": lambda key, second=False: D(services.pick_customer, key, second),
    "select_record": lambda bill_no: D(services.select_record, bill_no),
    "submit_form": lambda payload: D(services.submit_form, payload),
    "cancel_record": lambda record_id: D(services.cancel_record, record_id),
    "print_bill": lambda bill_no, image_path="bill-layout.jpg": D(services.print_bill, bill_no, image_path),
    "print_outward_list": lambda rows: backend.run(reports.outward_list, rows),
    "scan_id": _scan_id,
    # return processing
    "return_load": lambda rental_id: D(services.return_load, rental_id),
    "return_submit": lambda rental_id, fields, steppers, cashier_name: D(services.return_submit, rental_id, fields, steppers, cashier_name),
    "return_add_payment": lambda **p: D(services.return_add_payment, **p),
    "return_split": lambda rental_id, qty_to_return, fields, cashier_name: D(services.return_split, rental_id, qty_to_return, fields, cashier_name),
    "return_print": lambda rental_id, image_path, fields: D(services.return_print, rental_id, image_path, fields),
    # other tabs
    "pending_returns": lambda **p: D(services.pending_returns_table, **p),
    "rental_id_for_bill": lambda bill_no: D(services.rental_id_for_bill, bill_no),
    "print_pending_returns": lambda records: backend.run(reports.pending_returns_list, records),
    "pending_payments": lambda **p: D(services.pending_payments_table, **p),
    "print_pending_payments": lambda rows, filter_type: backend.run(reports.pending_payments_list, rows, filter_type),
    "daily_overview": lambda **p: D(services.daily_overview, **p),
    "print_daily": lambda rows, from_date, to_date, totals: backend.run(reports.daily_ledger, rows, from_date, to_date, totals),
    "customer_report": lambda search="": D(services.customer_report, search),
    "print_customer_report": lambda rows: backend.run(reports.customer_report_list, rows),
    "customers": lambda **p: D(services.customers_table, **p),
    "save_customer": lambda **p: D(services.save_customer, **p),
    "print_customers": lambda rows: backend.run(reports.customers_list, rows),
    "analytics_kpis": lambda **p: D(services.analytics_kpis, **p),
    "analytics_splits": lambda **p: D(services.analytics_splits, **p),
    "analytics_stock": lambda search="": D(services.analytics_stock, search),
    "print_stock": lambda rows: backend.run(reports.stock_list, rows),
    "analytics_top_customers": lambda **p: D(services.analytics_top_customers, **p),
    "delete_old_data": lambda start_str, end_str: D(services.delete_old_data, start_str, end_str),
    "equipment_analytics": lambda **p: (_owner_only(), D(services.equipment_analytics, **p))[1],
    "print_equipment": lambda **p: (_owner_only(), backend.run(reports.equipment_report, **p))[1],
    "export_equipment_csv": lambda rows: (_owner_only(), _export_equipment_csv(rows))[1],
}

# Calls that are allowed before the user has logged in
PUBLIC = {"login", "quit", "notes"}


def create_app():
    app = Flask(__name__, static_folder=None)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    @app.get("/")
    def index():
        with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
            html = f.read().replace("__APP_TOKEN__", backend.token)
        resp = app.response_class(html, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/static/<path:path>")
    def static_files(path):
        resp = send_from_directory(STATIC_DIR, path)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/api/<method>")
    def api(method):
        if request.headers.get("X-App-Token") != backend.token:
            abort(403)
        handler = API.get(method)
        if handler is None:
            abort(404)
        if method not in PUBLIC and backend.is_owner is None:
            abort(403)
        params = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "result": handler(**params)})
        except UserError as e:
            return jsonify({"ok": False, "error": {"title": e.title, "message": e.message, "kind": e.kind}})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"ok": False, "error": {"title": "Error", "message": str(e), "kind": "error"}})

    return app


def start_server(host="127.0.0.1", port=0):
    server = make_server(host, port, create_app(), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(open_window=True):
    # The status messages contain emoji; a Windows console using a legacy code
    # page would raise UnicodeEncodeError on them, so never let printing crash.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print("🚀 Starting Rental Billing Software v2.0...")
    try:
        from drive_backup import set_notifier
        set_notifier(backend.notify)
    except Exception as e:
        print(f"[WARN] Cloud backup messages unavailable: {e}")

    server = start_server()
    url = f"http://127.0.0.1:{server.server_port}/"
    if not open_window:
        print(f"Serving on {url}  (token: {backend.token})")
        return server

    import webview
    window = webview.create_window(
        APP_TITLE, url, width=1280, height=720, min_size=(1024, 650),
        maximized=True, background_color="#F4F5F7", text_select=True)
    backend.window = window

    def on_closing():
        # Before login (like cancelling the password prompt) the app just closes.
        if backend.quit_confirmed or backend.is_owner is None:
            return True
        # Otherwise ask inside the app; it calls the "quit" API if confirmed.
        # (This handler runs on the GUI thread and run_js waits for the page,
        # so it must be called from another thread or it would deadlock.)
        threading.Thread(
            target=lambda: window.run_js("window.__requestQuit && window.__requestQuit()"),
            daemon=True).start()
        return False

    window.events.closing += on_closing
    try:
        webview.start(private_mode=True, icon=ICON_PATH if os.path.isfile(ICON_PATH) else None)
    finally:
        backend.shutdown()
        server.shutdown()
        backend.executor.shutdown(wait=True)
