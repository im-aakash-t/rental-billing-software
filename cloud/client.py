# cloud/client.py - minimal Supabase REST client (auth, tables, storage, rpc).
# Uses only the standard library so it bundles cleanly into the .exe.
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from cloud import config


class CloudError(Exception):
    def __init__(self, message, status=None, offline=False):
        super().__init__(message)
        self.status = status
        self.offline = offline


class AuthError(CloudError):
    pass


def _send_urllib(method, url, headers, data, timeout):
    """Desktop transport. Returns (status, body bytes, content type)."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "") if e.headers else ""
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise CloudError(f"No internet connection ({e})", offline=True)


def _send_browser(method, url, headers, data, timeout):
    """Browser (Pyodide) transport: a synchronous request made by the page's JS (pyHttp)."""
    from js import pyHttp
    from pyodide.ffi import to_js
    res = pyHttp(method, url, json.dumps(headers), to_js(data) if data is not None else None)
    error = getattr(res, "error", None)
    if error:
        raise CloudError(f"No internet connection ({error})", offline=True)
    return int(res.status), str(res.text).encode("utf-8"), str(getattr(res, "ctype", "") or "")


_send = _send_browser if sys.platform == "emscripten" else _send_urllib


def _request(method, path, body=None, token=None, headers=None, raw=None, content_type="application/json", timeout=30):
    url = config.SUPABASE_URL + path
    h = {"apikey": config.SUPABASE_KEY}
    if token:
        h["Authorization"] = "Bearer " + token
    if body is not None or raw is not None:
        h["Content-Type"] = content_type
    if headers:
        h.update(headers)
    data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
    status, text, ctype = _send(method, url, h, data, timeout)
    if status >= 400:
        detail = text.decode("utf-8", "replace")
        try:
            j = json.loads(detail)
            detail = j.get("msg") or j.get("message") or j.get("error_description") or j.get("error") or detail
        except Exception:
            pass
        cls = AuthError if status in (400, 401, 403) and path.startswith("/auth/") else CloudError
        raise cls(f"{detail}", status=status)
    if not text:
        return None
    return json.loads(text) if "json" in ctype else text


class Session:
    """A signed-in user. Refreshes its access token automatically."""

    def __init__(self, access_token, refresh_token, expires_at, user_id, on_refresh=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.user_id = user_id
        self.on_refresh = on_refresh          # called with the new refresh token (to persist it)
        self._lock = threading.Lock()

    @classmethod
    def _from_auth(cls, data, on_refresh=None):
        return cls(data["access_token"], data["refresh_token"],
                   time.time() + int(data.get("expires_in", 3600)), data["user"]["id"], on_refresh)

    @classmethod
    def sign_in(cls, username, password, on_refresh=None):
        data = _request("POST", "/auth/v1/token?grant_type=password",
                        {"email": config.username_to_email(username), "password": password})
        return cls._from_auth(data, on_refresh)

    @classmethod
    def from_refresh_token(cls, refresh_token, on_refresh=None):
        s = cls(None, refresh_token, 0, None, on_refresh)
        s.token()
        return s

    def token(self):
        with self._lock:
            if self.access_token and time.time() < self.expires_at - 120:
                return self.access_token
            data = _request("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": self.refresh_token})
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.expires_at = time.time() + int(data.get("expires_in", 3600))
            self.user_id = data["user"]["id"]
            if self.on_refresh:
                self.on_refresh(self.refresh_token)
            return self.access_token

    # ---------------------------------------------------------------- data API
    def select(self, table, params):
        return _request("GET", f"/rest/v1/{table}?" + urllib.parse.urlencode(params, safe="(),.*:"), token=self.token())

    def upsert(self, table, rows, on_conflict):
        if not rows:
            return
        _request("POST", f"/rest/v1/{table}?on_conflict={on_conflict}", rows, token=self.token(),
                 headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def update(self, table, filters, values):
        _request("PATCH", f"/rest/v1/{table}?" + urllib.parse.urlencode(filters, safe="(),.*:"), values,
                 token=self.token(), headers={"Prefer": "return=minimal"})

    def rpc(self, name, args=None):
        return _request("POST", f"/rest/v1/rpc/{name}", args or {}, token=self.token())

    def upload(self, bucket, path, data, content_type="image/jpeg"):
        _request("POST", f"/storage/v1/object/{bucket}/{urllib.parse.quote(path)}", raw=data, token=self.token(),
                 content_type=content_type, headers={"x-upsert": "true"}, timeout=120)

    def profile(self):
        rows = self.select("profiles", {"user_id": f"eq.{self.user_id}", "select": "*"})
        return rows[0] if rows else None


def sign_up(username, password, display_name):
    """Create a login (it starts inactive until the owner assigns it)."""
    return _request("POST", "/auth/v1/signup", {"email": config.username_to_email(username), "password": password,
                                               "data": {"display_name": display_name}})
