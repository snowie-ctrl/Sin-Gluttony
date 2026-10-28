# Copied from Pageturner/server/pageturnerRoutes.py at 062da3b; changes: the session, rate-limit and
# error-hiding pieces only, as a module both Gluttony app blueprints install; database() names gluttonyDB;
# profileOf is new.
"""
Who is asking, for Gluttony's app routes at /api/gluttony: the read API (gluttonyRoutes.py) and accounts
(gluttonyUserRoutes.py) share one session check, one rate limiter and one way of hiding server errors from
internet callers. Every view needs a session unless PUBLIC_ROUTES names it, so a route added later cannot
forget the check. The admin blueprint (/api/gluttony-admin) has its own token and never installs this.
"""
from collections import deque
from contextlib import contextmanager
import functools
import ipaddress
import threading
import time

from flask import current_app, g, jsonify, request
from werkzeug.exceptions import HTTPException

from . import DBUtils

DB_NAME = "gluttony"
SESSION_DAYS = 30
# Signing in, device sign-in, and the reachability check the app runs before it knows which address to use.
PUBLIC_ROUTES = {"ping", "auth", "identifyDevice"}


def fail(message, code, status="error"):
    return jsonify({"status": status, "message": message}), code


@contextmanager
def database():
    """A connection and dictionary cursor for one request, always in a transaction: nothing is committed unless
    the route commits, and whatever is still open when the request ends is rolled back so its locks are let go.
    The connection is always closed."""
    conn = DBUtils.initConnection(DB_NAME)
    conn.autocommit = False
    cur = conn.cursor(dictionary=True)
    try:
        yield conn, cur
    finally:
        try:
            conn.rollback()
        finally:
            try:
                cur.close()
            finally:
                conn.close()


def clientIP():
    """The caller's real address. Through the tunnel Cloudflare names it in CF-Connecting-IP; on the LAN nginx
    sets X-Real-IP. X-Forwarded-For is never read: any caller can write it."""
    for value in (request.headers.get("CF-Connecting-IP"), request.headers.get("X-Real-IP"), request.remote_addr):
        if value:
            return value.strip()[:45]
    return ""


def isPublicRequest():
    """Whether this request came through the Cloudflare Tunnel, which sets CF-Connecting-IP on every request it
    carries; requests from the home network never have it."""
    return bool(request.headers.get("CF-Connecting-IP"))


def sessionToken():
    return (request.headers.get("X-Session-Token") or "")[:64]


def sessionUID(token):
    """The user of a live session token, or None, on a connection of its own so the check can run before any
    route opens one. No token needs no database."""
    if not token:
        return None
    with database() as (conn, cur):
        cur.execute("SELECT UserID FROM Sessions WHERE Token = %s AND ExpiresAt > NOW()", (token[:64],))
        row = cur.fetchone()
        return row["UserID"] if row else None


def requireSession():
    view = (request.endpoint or "").rsplit(".", 1)[-1]
    g.uid = None
    if view in PUBLIC_ROUTES:
        return None
    g.uid = sessionUID(request.headers.get("X-Session-Token"))
    if not g.uid:
        return fail("not signed in", 401)
    return None


def requestUID():
    """The signed-in user, as requireSession established it. Routes never read a user from the request."""
    return g.get("uid")


def profileOf(cur, uid):
    """The account's saved diets and allergens to avoid, in one query: (diets, avoids)."""
    cur.execute("SELECT 'diet' AS Kind, Diet AS Value FROM UserDiets WHERE UserID = %s "
                "UNION ALL SELECT 'avoid' AS Kind, Item AS Value FROM UserAvoids WHERE UserID = %s", (uid, uid))
    rows = cur.fetchall()
    return [r["Value"] for r in rows if r["Kind"] == "diet"], [r["Value"] for r in rows if r["Kind"] == "avoid"]


class RateLimiter:
    """A sliding window per key, in this process's memory. Caduceus runs as a single process, so one window
    covers all of its threads."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits = {}
        self._lastSweep = clock()
        self._lock = threading.Lock()

    def allow(self, key, limit, window):
        now = self._clock()
        with self._lock:
            # Callers come from the internet, so keys that have gone quiet are dropped rather than kept forever.
            if now - self._lastSweep >= window:
                self._lastSweep = now
                for stale in [k for k, h in self._hits.items() if not h or h[-1] <= now - window]:
                    del self._hits[stale]
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window:
                hits.popleft()
            # A refused attempt is not recorded, so hammering does not keep the caller locked out.
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


RATE_LIMITER = RateLimiter()


def limiterKey(ip):
    """An IPv6 connection is handed a whole /64, so the /64 is what the limiter counts."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if address.version == 6:
        return str(ipaddress.IPv6Network((address, 64), strict=False))
    return ip


def rateLimited(limit, window=60):
    """Refuse a view once one caller has used it `limit` times in `window` seconds. RATE_LIMITER is looked up at
    call time, so tests can replace it."""
    def decorate(view):
        @functools.wraps(view)
        def limited(*args, **kwargs):
            if not RATE_LIMITER.allow((view.__name__, limiterKey(clientIP())), limit, window):
                return fail("too many attempts", 429)
            return view(*args, **kwargs)
        return limited
    return decorate


def answerServerError(error):
    """Any failure inside a view answers JSON, so the app's error path can read it."""
    if isinstance(error, HTTPException):
        return fail(error.description or error.name, error.code)
    current_app.logger.exception("[gluttony] %s failed", request.path)
    return fail(f"{type(error).__name__}: {error}", 500)


def hideServerErrors(response):
    """Internet callers get no internals: a 5xx becomes a plain message and the detail goes to Caduceus's log.
    Home callers keep the detail, which is what debugging needs."""
    if response.status_code < 500 or not isPublicRequest():
        return response
    detail = ""
    try:
        detail = (response.get_json(silent=True) or {}).get("message") or ""
    except Exception:
        pass
    current_app.logger.error("[gluttony] %s answered %s through the tunnel: %s", request.path,
                             response.status_code, detail)
    scrubbed = jsonify({"status": "error", "message": "server error"})
    scrubbed.status_code = response.status_code
    return scrubbed


def install(blueprint):
    blueprint.before_request(requireSession)
    blueprint.register_error_handler(Exception, answerServerError)
    blueprint.after_request(hideServerErrors)
