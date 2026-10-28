"""
Surrogate's window on the Gluttony scraper: what it is doing, its last report,
and Run now / Re-tag / Stop. The API never runs a pass itself: it leaves a
request (controlRequests) or a stop flag that the scraper's loop acts on, so
only the scraper ever writes data/ and run/state.json.
"""
import hmac
from datetime import datetime, timezone

from flask import Flask, jsonify, request

import config
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


if __name__ == "__main__":
    if not config.CONTROL_TOKEN:
        raise SystemExit("CONTROL_TOKEN is not set in .env: the control API will not serve without it")
    app.run(host="0.0.0.0", port=config.CONTROL_PORT, threaded=True)
