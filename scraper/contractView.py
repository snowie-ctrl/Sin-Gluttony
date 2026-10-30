"""
Gluttony's answers to the Surrogate contract (status, needs-you, daily),
built from /status and run/runs.jsonl. Pure functions, so the rules are
tested without Flask; the /surrogate/v1/ routes in controlApi.py feed them.

The scraper runs one pass a week, so waiting for the next pass is green
(spec: Lights): a light that sat yellow six days out of seven would teach the
owner to ignore yellow. A failed pass needs the owner; a stopped one was the
owner's own doing.
"""
import re
from datetime import datetime, timedelta, timezone

_OF = re.compile(r"^(\d+) of (\d+)$")


def iso(seconds, tz=None):
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return None
    return datetime.fromtimestamp(seconds, timezone.utc).astimezone(tz).isoformat(timespec="seconds")


def _failed(last):
    return isinstance(last, dict) and last.get("outcome") == "failed"


def _when(text):
    try:
        return datetime.fromisoformat(text).strftime("%a %H:%M")
    except (TypeError, ValueError):
        return "not scheduled"


def statusDoc(status, alive, now):
    """alive: whether the scraper's loop is up, or None when that can't be told."""
    current = status.get("current") or {}
    last = status.get("lastRun") if isinstance(status.get("lastRun"), dict) else {}
    schedule = status.get("schedule") or {}
    runner = {"key": "scraper", "name": "Recipe scraper", "controls": []}
    if status.get("running"):
        runner["subject"] = f"{current.get('mode') or 'full'} pass"
        if iso(current.get("startedAt")):
            runner["startedAt"] = iso(current["startedAt"])
        if iso(current.get("updatedAt")):
            runner["lastProgressAt"] = iso(current["updatedAt"])
        detail = str(current.get("detail") or "")
        label = f"{current.get('stage') or 'running'}" + (f": {detail}" if detail else "")
        counts = _OF.match(detail)
        runner["step"] = {"label": label, **({"done": int(counts.group(1)), "total": int(counts.group(2))} if counts else {})}
    if alive is False:
        light, reason = "red", "the scraper isn't running"
    elif status.get("running"):
        light, reason = "green", f"{current.get('mode') or 'full'} pass: {current.get('stage') or 'starting'}"
    elif _failed(last):
        light, reason = "attention", f"the last pass failed: {last.get('error') or 'no error recorded'}"
    elif not schedule.get("on"):
        light, reason = "yellow", "the weekly schedule is off"
    else:
        light, reason = "green", f"waiting for the next pass ({_when(schedule.get('nextDue'))})"
    runner.update(light=light, reason=reason)
    return {"contract": 1, "app": "gluttony", "light": light, "reason": reason, "cadence": "weekly",
            "supports": [], "runners": [runner], "needsYou": 1 if _failed(last) else 0}


def needsYouDoc(lastRun):
    if not _failed(lastRun):
        return {"items": []}
    return {"items": [{"id": f"gl-run-{int(lastRun.get('startedAt') or 0)}", "runner": "scraper",
                       "title": "The last pass failed", "detail": lastRun.get("error") or "no error recorded",
                       "since": iso(lastRun.get("endedAt")),
                       "actions": [{"key": "run", "label": "Run again"}, {"key": "dismiss", "label": "Dismiss"}]}]}


def dailyDoc(runs, days, today, tz=None):
    """Recipes each pass went through, on the local day it ended; failed passes counted."""
    start = today - timedelta(days=days - 1)
    byDay = {(start + timedelta(days=d)).isoformat(): [0, 0] for d in range(days)}
    for run in runs:
        if not isinstance(run, dict):
            continue
        ended = iso(run.get("endedAt"), tz)
        if not ended or ended[:10] not in byDay:
            continue
        if _failed(run):
            byDay[ended[:10]][1] += 1
        else:
            byDay[ended[:10]][0] += int(run.get("recipes") or 0)
    return {"unit": "recipes", "days": [{"date": day, "items": c[0], "failed": c[1], "bytes": None} for day, c in byDay.items()]}
