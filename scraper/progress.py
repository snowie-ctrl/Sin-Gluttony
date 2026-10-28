"""
What the scraper is doing right now, in run/current.json, for the control
API's /status. Written at every stage and every 50 pictures, so a state that
hasn't changed for STALE_SECONDS means the scraper died mid-pass.
"""
import time

import config
import store

STALE_SECONDS = 3600


def read():
    return store.readJson(config.CURRENT_FILE, None) or {"state": "idle"}


def _write(state):
    store.writeJson(config.CURRENT_FILE, {**state, "updatedAt": time.time()})


def idle():
    _write({"state": "idle"})


def stage(mode, name, detail="", startedAt=None):
    _write({"state": "running", "mode": mode, "stage": name, "detail": detail, "startedAt": startedAt})


def isRunning(now=None):
    current = read()
    return current.get("state") == "running" and (now or time.time()) - current.get("updatedAt", 0) < STALE_SECONDS
