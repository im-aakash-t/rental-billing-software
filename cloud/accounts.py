# cloud/accounts.py - sign-in for branch PCs (online, with offline fallback).
#
# First sign-in on a PC must be online: it links the PC to a branch (the
# cashier's branch, or the branch the owner picks). After that, the last
# successful online sign-in of each user is remembered (salted PBKDF2 hash,
# never the password) so cashiers can still sign in during an internet outage.
import hashlib
import hmac
import os

from cloud import config, local_sync as LS
from cloud.client import Session, CloudError, AuthError


class LoginError(Exception):
    def __init__(self, message, code="error", extra=None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


def _ensure_tables(conn):
    LS.install(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS local_users (
                        username TEXT PRIMARY KEY, user_id TEXT, display_name TEXT,
                        role TEXT, branch_id TEXT, salt TEXT, pw_hash TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000).hex()


def _remember(conn, username, profile, password):
    salt = os.urandom(16).hex()
    conn.execute("""INSERT INTO local_users (username, user_id, display_name, role, branch_id, salt, pw_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET user_id=excluded.user_id, display_name=excluded.display_name,
                      role=excluded.role, branch_id=excluded.branch_id, salt=excluded.salt, pw_hash=excluded.pw_hash,
                      updated_at=CURRENT_TIMESTAMP""",
                 (username, profile["user_id"], profile.get("display_name") or username, profile["role"],
                  profile.get("branch_id"), salt, _hash(password, salt)))
    conn.commit()


def online_sign_in(username, password):
    """Network part (runs outside the DB thread). Returns (session, profile)."""
    try:
        session = Session.sign_in(username, password)
    except AuthError as e:
        raise LoginError("Incorrect username or password." if e.status in (400, 401) else str(e))
    profile = session.profile()
    if not profile or not profile.get("active") or profile.get("role") not in ("owner", "cashier"):
        raise LoginError("This login is not activated yet. Ask the owner to assign it to a branch.")
    return session, profile


def finish_online(db, username, password, session, profile, chosen_branch=None):
    """DB part after an online sign-in: link the PC to a branch, remember the login."""
    conn = db.get_connection()
    _ensure_tables(conn)
    pc_branch = LS.get_meta(conn, "branch_code")
    role = profile["role"]
    first_setup = False
    if not pc_branch:
        if role == "cashier":
            pc_branch = profile["branch_id"]
        else:
            if not chosen_branch:
                raise LoginError("Choose which branch this computer belongs to.", code="choose_branch",
                                 extra={"branches": config.BRANCHES, "suggested": profile.get("branch_id")})
            pc_branch = chosen_branch
        if pc_branch not in config.BRANCHES:
            raise LoginError("Unknown branch.")
        LS.set_meta(conn, "branch_code", pc_branch)
        first_setup = True
    elif role == "cashier" and profile.get("branch_id") != pc_branch:
        raise LoginError(f"This computer belongs to {config.BRANCHES.get(pc_branch, pc_branch)}. "
                         f"Your login is for {config.BRANCHES.get(profile.get('branch_id'), profile.get('branch_id'))}.")
    _remember(conn, username, profile, password)
    LS.set_meta(conn, "refresh_token", session.refresh_token)
    return {"username": username, "display_name": profile.get("display_name") or username, "role": role,
            "branch": pc_branch, "branch_name": config.BRANCHES.get(pc_branch, pc_branch),
            "first_setup": first_setup, "offline": False}


def offline_sign_in(db, username, password):
    conn = db.get_connection()
    _ensure_tables(conn)
    pc_branch = LS.get_meta(conn, "branch_code")
    if not pc_branch:
        raise LoginError("No internet connection. The first sign-in on this computer must be online.")
    row = conn.execute("SELECT * FROM local_users WHERE username = ?", (username,)).fetchone()
    if not row or not hmac.compare_digest(_hash(password, row["salt"]), row["pw_hash"]):
        raise LoginError("No internet connection, and this username/password has not been used online "
                         "on this computer before (or the password is wrong).")
    if row["role"] == "cashier" and row["branch_id"] != pc_branch:
        raise LoginError("This login does not belong to this branch.")
    return {"username": username, "display_name": row["display_name"], "role": row["role"], "branch": pc_branch,
            "branch_name": config.BRANCHES.get(pc_branch, pc_branch), "first_setup": False, "offline": True}


def stored_refresh_token(db):
    conn = db.get_connection()
    return LS.get_meta(conn, "refresh_token") if LS.is_installed(conn) else None


def first_upload_needed(db, session, branch):
    """When a PC with existing history is linked to a branch whose cloud data is empty,
    queue its whole history for upload (done once)."""
    conn = db.get_connection()
    if LS.get_meta(conn, "history_queued") == "1":
        return False
    local_count = conn.execute("SELECT COUNT(*) FROM rentals").fetchone()[0]
    return local_count > 0


def queue_history(db):
    conn = db.get_connection()
    LS.queue_everything(conn)
    LS.set_meta(conn, "history_queued", "1")
