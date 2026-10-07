# cloud/config.py - Supabase connection settings.
#
# Defaults below point at the TEST project. To switch projects without
# rebuilding, put a cloud_config.json next to the app (or the .exe):
#   {"supabase_url": "https://xxxx.supabase.co", "supabase_key": "sb_publishable_..."}
# Only the publishable/anon key belongs here - never the service_role key.
import json
import os
import sys

SUPABASE_URL = "https://bufavftgsiuaufsprwwb.supabase.co"
SUPABASE_KEY = "sb_publishable_V7AWnHPaUwvuSEBLKE-7XQ_udKJ8lAZ"

# Logins are usernames; Supabase needs an email, so "ravi" becomes this:
EMAIL_DOMAIN = "users.rentalbilling.app"

SYNC_INTERVAL_SECONDS = 20       # how often a branch PC syncs while online
PULL_OVERLAP_SECONDS = 120       # re-read a little history each pull (safe, idempotent)

BRANCHES = {"VDV": "Vadavalli", "BMP": "Bommanampalayam", "KVP": "Kalveerampalayam"}


def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


def _load_overrides():
    global SUPABASE_URL, SUPABASE_KEY
    path = os.path.join(_app_dir(), "cloud_config.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            SUPABASE_URL = data.get("supabase_url", SUPABASE_URL).rstrip("/")
            SUPABASE_KEY = data.get("supabase_key", SUPABASE_KEY)
        except Exception as e:
            print(f"[WARN] Could not read cloud_config.json: {e}")


_load_overrides()


def username_to_email(username):
    return f"{username.strip().lower()}@{EMAIL_DOMAIN}"
