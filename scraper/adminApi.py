"""
plutus's admin routes (/api/gluttony-admin, LAN only) and the rsync that sends
pictures there. A transport failure or a 5xx is tried 3 times with backoff; a
refusal (a 4xx, or {"status": "error"}) is raised at once, because sending the
same thing again would be refused again.
"""
import subprocess
import time

import requests

import config

RETRIES = 3
_http = requests.Session()


class AdminError(Exception):
    pass


def configured():
    return bool(config.ADMIN_TOKEN and config.ADMIN_HOST)


def adminBase():
    return f"http://{config.ADMIN_HOST}:{config.ADMIN_PORT}/api/gluttony-admin"


def _request(method, path, payload=None, timeout=120):
    if not configured():
        raise AdminError("ADMIN_TOKEN and ADMIN_HOST must be set in .env")
    lastError = None
    for attempt in range(RETRIES):
        try:
            resp = _http.request(method, adminBase() + path, json=payload, timeout=timeout,
                                 headers={"X-Admin-Token": config.ADMIN_TOKEN})
        except requests.RequestException as e:
            lastError = f"{type(e).__name__}: {e}"
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
            continue
        if resp.status_code >= 500:
            lastError = f"{resp.status_code} from plutus"
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
            continue
        try:
            data = resp.json()
        except ValueError:
            raise AdminError(f"{method} {path}: plutus answered {resp.status_code} without JSON")
        if resp.status_code >= 400 or data.get("status") == "error":
            raise AdminError(f"{method} {path} refused ({resp.status_code}): {data.get('message')}")
        return data
    raise AdminError(f"{method} {path} failed after {RETRIES} attempts ({lastError})")


def get(path, timeout=60):
    return _request("GET", path, timeout=timeout)


def post(path, payload, timeout=120):
    return _request("POST", path, payload, timeout)


def rsync(src, dest):
    """Send a folder's pictures to a folder on plutus; rsync itself skips the ones already there."""
    if not config.UPLOAD_HOST:
        raise AdminError("UPLOAD_HOST must be set in .env to send pictures")
    command = ["rsync", "-a", "--partial", "-e", "ssh -o BatchMode=yes", f"{src}/", f"{config.UPLOAD_HOST}:{dest}/"]
    result = None
    for attempt in range(2):
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            return
        time.sleep(5)
    raise AdminError(f"rsync to {dest} failed: {(result.stderr or '').strip()[:200]}")
