# webapp/web_runtime.py - runs the app's own Python inside the browser (Pyodide)
# for the phone / web version.
#
# The phone is "a branch computer that is always online": for the selected
# branch it keeps a local copy of that branch's data (SQLite, saved in the
# browser), runs exactly the same billing/report code as the desktop app, and
# uploads every change immediately. Bills made here use the branch's phone
# series (VDV-M0001...) so they never clash with the branch PC's numbers.
#
# Only things a browser can't do are replaced: threads, the Windows scanner,
# Google Drive, native file dialogs and opening files (PDFs are handed to the
# page instead).
import base64
import csv
import json
import os
import sys
import types
import uuid

APP_DIR = "/app"
DATA_ROOT = "/data"


# ---------------------------------------------------------------- stand-ins for desktop-only modules
class _Any:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return _Any()
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Any()


def _stub(name):
    m = types.ModuleType(name)
    def __getattr__(attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        return type(attr, (_Any,), {})
    m.__getattr__ = __getattr__
    m.__path__ = []
    sys.modules[name] = m


for _n in ["tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.simpledialog", "tkinter.filedialog",
           "win32com", "win32com.client", "pythoncom",
           "google", "google.auth", "google.auth.transport", "google.auth.transport.requests",
           "google.oauth2", "google.oauth2.credentials", "google_auth_oauthlib", "google_auth_oauthlib.flow",
           "googleapiclient", "googleapiclient.discovery", "googleapiclient.http",
           "flask", "werkzeug", "werkzeug.serving", "webview"]:
    _stub(_n)

# Files the app "opens" (PDF reports, bills) are captured and handed to the page
import webbrowser
_opened = []
webbrowser.open = webbrowser.open_new = lambda url, *a, **k: _opened.append(url) or True

os.makedirs(DATA_ROOT, exist_ok=True)
os.chdir(DATA_ROOT)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import drive_backup                                   # noqa: E402
drive_backup.backup_files = lambda silent=False: None  # Supabase is the backup on the web

from webapp import server, services, reports          # noqa: E402
from webapp.services import UserError                  # noqa: E402
from cloud import accounts, config as cloud_config, local_sync as LS  # noqa: E402
from cloud.client import CloudError                    # noqa: E402
from cloud.sync_engine import SyncEngine               # noqa: E402
from shared_imports import DBManager                   # noqa: E402
import materials                                       # noqa: E402

services.run_initial_regular_sync = lambda db: None    # a PC-side maintenance task (needs threads)
backend = server.backend
backend.run = lambda fn, *a, **k: fn(*a, **k)          # single-threaded in the browser
drive_backup.set_notifier(backend.notify)


# ---------------------------------------------------------------- branch replicas
def _materials_to_csv(rows):
    paths = [materials.MATERIALS_CSV, os.path.join(os.getcwd(), "materials.csv")]
    for path in paths:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["code", "name", "price", "quantity"])
            for r in rows:
                w.writerow([r["code"], r["name"], repr(float(r["price"])), r.get("quantity") or 0])
    materials.reload_materials()


def _load_materials(session, branch):
    try:
        rows = session.select("materials", {"branch_id": f"eq.{branch}", "deleted": "eq.false",
                                            "order": "sort_order.asc", "select": "code,name,price,quantity"})
        _materials_to_csv(rows)
    except CloudError:
        local = os.path.join(os.getcwd(), "materials.csv")    # offline: last downloaded list
        if os.path.exists(local):
            with open(local, "rb") as src, open(materials.MATERIALS_CSV, "wb") as dst:
                dst.write(src.read())
            materials.reload_materials()


def _open_branch(branch, session):
    """Open (or create) this browser's copy of a branch and bring it up to date."""
    folder = os.path.join(DATA_ROOT, branch)
    os.makedirs(folder, exist_ok=True)
    if backend.db is not None:
        try:
            backend.db.conn.close()
        except Exception:
            pass
    os.chdir(folder)
    backend.db = DBManager()
    conn = backend.db.get_connection()
    LS.install(conn)
    if not str(LS.get_meta(conn, "device_id", "")).startswith("web-"):
        LS.set_meta(conn, "device_id", "web-" + uuid.uuid4().hex[:12])
    LS.set_meta(conn, "branch_code", branch)
    LS.set_meta(conn, "bill_series", "M")
    LS.set_meta(conn, "history_queued", "1")        # the phone never uploads a "history"
    backend.engine = SyncEngine(lambda: backend.db, backend.run, materials_path=os.path.join(folder, "__no_upload__"))
    if session is not None:
        session.on_refresh = server._persist_refresh_token
        backend.engine.session = session
        backend.engine.sync_once()
        _load_materials(session, branch)
    else:
        _load_materials(_OfflineSession(), branch)
    return {"branch": branch, "branch_name": cloud_config.BRANCHES.get(branch, branch),
            "bills": backend.db.get_connection().execute("SELECT COUNT(*) FROM rentals").fetchone()[0]}


class _OfflineSession:
    def select(self, *a, **k):
        raise CloudError("offline", offline=True)


def web_login(username="", password="", branch=None):
    username = (username or "").strip().lower()
    if not username or not password:
        raise UserError("Sign In", "Enter your username and password.", kind="warning")
    try:
        session, profile = accounts.online_sign_in(username, password)
    except accounts.LoginError as e:
        raise UserError("Sign In", str(e))
    except CloudError as e:
        if not e.offline:
            raise UserError("Sign In", str(e))
        raise UserError("No Internet", "The phone app needs internet. Please check the connection.", kind="warning")
    role = profile["role"]
    target = profile.get("branch_id") if role == "cashier" else branch
    if role == "owner" and not target:
        return {"choose_branch": True, "branches": cloud_config.BRANCHES, "suggested": profile.get("branch_id"),
                "phone": True}
    if target not in cloud_config.BRANCHES:
        raise UserError("Sign In", "Unknown branch.")
    opened = _open_branch(target, session)
    # (no offline sign-in on the phone, so the password is not remembered here)
    LS.set_meta(backend.db.get_connection(), "refresh_token", session.refresh_token)
    info = {"username": username, "display_name": profile.get("display_name") or username, "role": role,
            "branch": target, "branch_name": opened["branch_name"], "first_setup": False, "offline": False,
            "phone": True}
    backend.session, backend.user, backend.is_owner = session, info, role == "owner"
    return info


def switch_branch(branch=""):
    server._owner_only()
    if backend.session is None:
        raise UserError("No Internet", "Switching branches needs internet.", kind="warning")
    if branch not in cloud_config.BRANCHES:
        raise UserError("Switch Branch", "Unknown branch.")
    opened = _open_branch(branch, backend.session)
    backend.user = dict(backend.user, branch=branch, branch_name=opened["branch_name"])
    return backend.user


def sync_now():
    if backend.engine:
        backend.engine.sync_once()
    return server._sync_status()


def upload_id_photo(bill_no="", name="", id_type="", data_b64=""):
    """Phone camera instead of the scanner: same file name as a scanned ID, uploaded on sync."""
    if not name.strip() or not id_type.strip():
        raise UserError("Incomplete Data", "Please enter the Customer Name and ID Proof Type (e.g. 'Aadhar') before scanning!",
                        kind="warning")
    import scanner_helper    # its Windows-only parts are stand-ins here; only the naming rule is used
    filename = scanner_helper.id_photo_filename(bill_no, name, id_type)
    os.makedirs("ID_Proofs", exist_ok=True)
    with open(os.path.join("ID_Proofs", filename), "wb") as f:
        f.write(base64.b64decode(data_b64))
    return {"status": "saved", "message": f"ID Proof saved securely as:\n{filename}"}


def export_equipment_csv(rows=None):
    if not rows:
        raise UserError("No Data", "There are no records to export.", kind="info")
    path = os.path.join(os.getcwd(), "Equipment_Analytics.csv")
    reports.equipment_csv(rows, path)
    _opened.append(path)
    return {"message": "Downloaded Equipment_Analytics.csv"}


WEB_API = {
    "login": web_login,
    "switch_branch": switch_branch,
    "sync_now": sync_now,
    "upload_id_photo": upload_id_photo,
    "export_equipment_csv": export_equipment_csv,
    "scan_id": lambda **p: (_ for _ in ()).throw(UserError("Use the Camera", "On the phone, use the camera button to add the ID proof.", kind="info")),
    "cloud_backup": lambda: True,
    "quit": lambda: True,
}

# Writes are uploaded straight away (the phone is online-first)
WRITES = server.WRITES | {"upload_id_photo"}


def _file_payload(path):
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    mime = "application/pdf" if name.lower().endswith(".pdf") else ("text/csv" if name.lower().endswith(".csv") else "application/octet-stream")
    return {"name": name, "mime": mime, "b64": base64.b64encode(data).decode("ascii")}


def call(method, params_json="{}"):
    """Entry point used by the page's worker. Returns a JSON string."""
    params = json.loads(params_json or "{}")
    handler = WEB_API.get(method) or server.API.get(method)
    if handler is None:
        return json.dumps({"ok": False, "error": {"title": "Error", "message": f"Unknown action {method}", "kind": "error"}})
    if method not in server.PUBLIC and method not in ("login",) and backend.is_owner is None:
        return json.dumps({"ok": False, "error": {"title": "Signed out", "message": "Please sign in again.", "kind": "warning"}})
    del _opened[:]
    try:
        result = handler(**params)
        out = {"ok": True, "result": result}
        if method in WRITES and backend.engine is not None:
            if not backend.engine.sync_once():
                st = backend.engine.state
                out["warning"] = ("Saved on this phone, but it could not be uploaded yet"
                                  + (f": {st['error']}" if st.get("error") else " (no internet)")
                                  + ". It will upload automatically when the connection is back.")
    except UserError as e:
        out = {"ok": False, "error": {"title": e.title, "message": e.message, "kind": e.kind}}
    except Exception as e:
        import traceback
        traceback.print_exc()
        out = {"ok": False, "error": {"title": "Error", "message": str(e), "kind": "error"}}
    files = []
    for path in _opened:
        p = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
        if os.path.exists(p):
            files.append(_file_payload(p))
    if files:
        out["files"] = files
    return json.dumps(out)
