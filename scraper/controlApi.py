"""
Surrogate's window on the Gluttony scraper: what it is doing, its last report,
and Run now / Re-tag / Stop. The API never runs a pass itself: it leaves a
request (controlRequests) or a stop flag that the scraper's loop acts on, so
only the scraper ever writes data/ and run/state.json.
"""
import hmac
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

import config
import contractView
import controlRequests
import progress
import report
import schedule
import store

app = Flask(__name__)


def error(message, code=400):
    return jsonify({"status": "error", "message": message}), code


@app.before_request
def requireToken():
    supplied = request.headers.get("X-Control-Token", "")
    if not config.CONTROL_TOKEN or not hmac.compare_digest(supplied.encode(), config.CONTROL_TOKEN.encode()):
        return error("bad or missing X-Control-Token", 401)


@app.get("/ping")
def ping():
    return jsonify({"status": "ok"})


@app.get("/status")
def status():
    now = datetime.now(timezone.utc)
    return jsonify({"status": "ok", "running": progress.isRunning(), "current": progress.read(),
                    "lastRun": report.lastRun(), "pending": [r.get("kind") for r in controlRequests.pending()],
                    "schedule": {"on": config.SCHEDULE == "on", "nextDue": schedule.nextDue(now).isoformat()},
                    "publish": config.PUBLISH})


def _ask(kind, message):
    if progress.isRunning() or controlRequests.pending():
        return error("a pass is already running or waiting", 409)
    controlRequests.ask(kind)
    return jsonify({"status": "ok", "message": message}), 202


@app.post("/run")
def run():
    return _ask("run", "a full pass starts within a few seconds")


@app.post("/retag")
def retag():
    return _ask("retag", "a re-tag starts within a few seconds")


@app.post("/stop")
def stop():
    if not progress.isRunning():
        return error("nothing is running", 409)
    if progress.read().get("stage") == "publish":
        return error("publishing has started; it finishes by itself", 409)
    config.STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.STOP_FILE.write_text("stop", encoding="utf-8")
    return jsonify({"status": "ok", "message": "the pass stops at its next safe point"}), 202


@app.get("/report")
def lastReport():
    data = store.readJson(config.LAST_REPORT_FILE, None)
    if data is None:
        return error("no pass has finished yet", 404)
    return jsonify({"status": "ok", "report": data})


# ========== SURROGATE CONTRACT ==========
# /surrogate/v1/: the routes every scraper serves the same way, for
# Surrogate's Overview and its standard app page. contractView.py has the
# rules. Read-only for now: Run now, Re-tag and Stop move here with the
# standard app page.

def _statusJson():
    return status().get_json()


def _scraperAlive():
    """Whether the scraper's loop (main.py in this folder) is up; None where that can't be told."""
    if sys.platform == "win32":
        return None
    here = Path(__file__).resolve().parent
    try:
        # Anchored at the end: run.sh's tmux pane is a bash -c whose command line
        # also holds main.py, and it waits at `read` after the scraper dies.
        pids = subprocess.run(["pgrep", "-f", r"[m]ain\.py$"], capture_output=True, text=True, timeout=5).stdout.split()
        return any(Path(f"/proc/{pid}/cwd").resolve() == here for pid in pids)
    except (OSError, subprocess.SubprocessError):
        return None


def _runLines():
    try:
        return config.RUNS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _runs():
    out = []
    for line in _runLines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


@app.get("/surrogate/v1/status")
def contractStatus():
    return jsonify(contractView.statusDoc(_statusJson(), _scraperAlive(), datetime.now(timezone.utc)))


@app.get("/surrogate/v1/needs-you")
def contractNeedsYou():
    return jsonify(contractView.needsYouDoc(_statusJson().get("lastRun")))


@app.get("/surrogate/v1/daily")
def contractDaily():
    try:
        days = max(1, min(90, int(request.args.get("days", 30))))
    except ValueError:
        days = 30
    return jsonify(contractView.dailyDoc(_runs(), days, date.today()))


if __name__ == "__main__":
    if not config.CONTROL_TOKEN:
        raise SystemExit("CONTROL_TOKEN is not set in .env: the control API will not serve without it")
    app.run(host="0.0.0.0", port=config.CONTROL_PORT, threaded=True)
