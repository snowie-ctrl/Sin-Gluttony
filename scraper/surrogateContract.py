"""
The Surrogate contract, version 1: the shapes every scraper's /surrogate/v1/
routes answer with, written as checks. One file with no dependencies, so each
scraper repo keeps a copy and tests its own routes against it (the VMs and
plutus have no JSON Schema library).

Each check returns a list of problems, one sentence each; an empty list means
the document is fine. Extra keys are allowed: a scraper may say more than the
contract asks, and Surrogate ignores what it doesn't know.
"""
import re
from datetime import datetime

CONTRACT = 1
LIGHTS = ("green", "yellow", "attention", "red")
CADENCES = ("continuous", "weekly")
SUPPORTS = ("queue", "schedule")
SPECIAL = ("forced", "afterHours", "waitingForSpace", "retrying")
INPUTS = ("choice", "text")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def worstLight(lights):
    """The worst of several lights (red, attention, yellow, green); green when there are none."""
    ranked = [light for light in lights if light in LIGHTS]
    return max(ranked, key=LIGHTS.index) if ranked else "green"


def isTime(value):
    """An ISO 8601 time with its offset, as every contract time is. Without one, Surrogate can't tell whose clock it is."""
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _isCount(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _isText(value):
    return isinstance(value, str) and value.strip() != ""


def _isBytes(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _checkButtons(buttons, where):
    if not isinstance(buttons, list):
        return [f"{where} must be a list"]
    return [f"{where}[{i}] needs a key and a label" for i, b in enumerate(buttons)
            if not isinstance(b, dict) or not _isText(b.get("key")) or not _isText(b.get("label"))]


def _checkRunner(runner, where):
    if not isinstance(runner, dict):
        return [f"{where} is not an object"]
    problems = [f"{where}.{key} must be non-empty text" for key in ("key", "name", "reason") if not _isText(runner.get(key))]
    if runner.get("light") not in LIGHTS:
        problems.append(f"{where}.light must be one of {', '.join(LIGHTS)}")
    step = runner.get("step")
    if step is not None:
        if not isinstance(step, dict) or not _isText(step.get("label")):
            problems.append(f"{where}.step needs a label")
        else:
            problems += [f"{where}.step.{key} must be a whole number" for key in ("done", "total")
                         if step.get(key) is not None and not _isCount(step[key])]
    download = runner.get("download")
    if download is not None:
        if not isinstance(download, dict) or not _isText(download.get("title")):
            problems.append(f"{where}.download needs a title")
        else:
            problems += [f"{where}.download.{key} must be a number of bytes" for key in ("bytes", "totalBytes", "bytesPerSec")
                         if download.get(key) is not None and not _isBytes(download[key])]
    problems += [f"{where}.{key} must be an ISO time with its offset" for key in ("startedAt", "lastProgressAt")
                 if runner.get(key) is not None and not isTime(runner[key])]
    if runner.get("subject") is not None and not isinstance(runner["subject"], str):
        problems.append(f"{where}.subject must be text")
    problems += _checkButtons(runner.get("controls", []), f"{where}.controls")
    return problems


def checkStatus(doc):
    """GET status."""
    if not isinstance(doc, dict):
        return ["status is not an object"]
    problems = []
    if doc.get("contract") != CONTRACT:
        problems.append(f"contract must be {CONTRACT}")
    if not _isText(doc.get("app")):
        problems.append("app must be non-empty text")
    if doc.get("light") not in LIGHTS:
        problems.append(f"light must be one of {', '.join(LIGHTS)}")
    if not _isText(doc.get("reason")):
        problems.append("reason must be non-empty text")
    if doc.get("cadence") not in CADENCES:
        problems.append(f"cadence must be one of {', '.join(CADENCES)}")
    supports = doc.get("supports")
    if not isinstance(supports, list) or any(s not in SUPPORTS for s in supports):
        problems.append(f"supports must be a list drawn from {', '.join(SUPPORTS)}")
    runners = doc.get("runners")
    if not isinstance(runners, list) or not runners:
        problems.append("runners must be a non-empty list")
        runners = []
    for i, runner in enumerate(runners):
        problems += _checkRunner(runner, f"runners[{i}]")
    lights = [r.get("light") for r in runners if isinstance(r, dict) and r.get("light") in LIGHTS]
    if lights and doc.get("light") in LIGHTS and doc["light"] != worstLight(lights):
        problems.append("light must be the worst runner's light")
    special = doc.get("special")
    if special is not None and (not isinstance(special, dict)
                                or any(k not in SPECIAL or not _isCount(v) for k, v in special.items())):
        problems.append(f"special must map {', '.join(SPECIAL)} to counts")
    disk = doc.get("disk")
    if disk is not None and (not isinstance(disk, dict) or any(not _isCount(v) for v in disk.values())):
        problems.append("disk must map names to byte counts")
    hours = doc.get("afterHours")
    if hours is not None and (not isinstance(hours, dict) or not all(
            isinstance(hours.get(k), str) and _CLOCK.match(hours[k]) for k in ("from", "to"))):
        problems.append("afterHours needs from and to as HH:MM")
    if not _isCount(doc.get("needsYou")):
        problems.append("needsYou must be a count")
    return problems


def checkNeedsYou(doc):
    """GET needs-you."""
    if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
        return ["needs-you must be an object with an items list"]
    problems, seen = [], set()
    for i, item in enumerate(doc["items"]):
        where = f"items[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{where} is not an object")
            continue
        problems += [f"{where}.{key} must be non-empty text" for key in ("id", "runner", "title") if not _isText(item.get(key))]
        ident = item.get("id")
        if isinstance(ident, str):
            if ident in seen:
                problems.append(f"{where}.id {ident} is used twice")
            seen.add(ident)
        if item.get("detail") is not None and not isinstance(item["detail"], str):
            problems.append(f"{where}.detail must be text")
        if item.get("since") is not None and not isTime(item["since"]):
            problems.append(f"{where}.since must be an ISO time with its offset")
        actions = item.get("actions")
        if not isinstance(actions, list) or not actions:
            problems.append(f"{where}.actions must be a non-empty list")
            continue
        problems += _checkButtons(actions, f"{where}.actions")
        for j, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            kind = action.get("input")
            if kind is not None and kind not in INPUTS:
                problems.append(f"{where}.actions[{j}].input must be choice or text")
            if kind == "choice":
                choices = action.get("choices")
                if not isinstance(choices, list) or not choices or not all(
                        isinstance(c, dict) and _isText(c.get("value")) and _isText(c.get("label")) for c in choices):
                    problems.append(f"{where}.actions[{j}] needs choices, each with a value and a label")
    return problems


def checkDaily(doc):
    """GET daily."""
    if not isinstance(doc, dict):
        return ["daily is not an object"]
    problems = []
    if not _isText(doc.get("unit")):
        problems.append("unit must be non-empty text")
    days = doc.get("days")
    if not isinstance(days, list):
        return problems + ["days must be a list"]
    last = None
    for i, day in enumerate(days):
        where = f"days[{i}]"
        if not isinstance(day, dict) or not isinstance(day.get("date"), str) or not _DATE.match(day["date"]):
            problems.append(f"{where}.date must be YYYY-MM-DD")
            continue
        if last is not None and day["date"] <= last:
            problems.append(f"{where}.date must come after {last}")
        last = day["date"]
        problems += [f"{where}.{key} must be a count" for key in ("items", "failed") if not _isCount(day.get(key))]
        if day.get("bytes") is not None and not _isCount(day["bytes"]):
            problems.append(f"{where}.bytes must be a byte count or null")
    return problems


def checkWrite(doc):
    """Any POST: {"ok": true} or {"ok": false, "error": "<sentence for a toast>"}."""
    if not isinstance(doc, dict) or not isinstance(doc.get("ok"), bool):
        return ["a write must answer ok: true or false"]
    if doc["ok"] is False and not _isText(doc.get("error")):
        return ["a refused write must say why in error"]
    return []
