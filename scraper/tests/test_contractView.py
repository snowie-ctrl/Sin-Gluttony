from datetime import date, timedelta, timezone

import contractView as view
import surrogateContract as contract

CDT = timezone(timedelta(hours=-5))
WAITING = {"running": False, "current": {"state": "idle"},
           "lastRun": {"mode": "full", "outcome": "ok", "error": None, "startedAt": 1792310400, "endedAt": 1792312200,
                       "recipes": 4310, "changed": 37, "removed": 1},
           "schedule": {"on": True, "nextDue": "2026-11-01T03:00:00-05:00"}}
RUNNING = dict(WAITING, running=True, current={"state": "running", "mode": "full", "stage": "images",
                                               "detail": "1200 of 4310", "startedAt": 1792310400, "updatedAt": 1792311000})


def test_waiting_for_the_weekly_pass_is_green():
    doc = view.statusDoc(WAITING, True, 0)
    assert contract.checkStatus(doc) == []
    assert (doc["light"], doc["reason"], doc["cadence"]) == ("green", "waiting for the next pass (Sun 03:00)", "weekly")


def test_a_running_pass_shows_its_progress():
    doc = view.statusDoc(RUNNING, True, 0)
    assert contract.checkStatus(doc) == []
    assert doc["reason"] == "full pass: images"
    assert doc["runners"][0]["step"] == {"label": "images: 1200 of 4310", "done": 1200, "total": 4310}


def test_failed_pass_off_schedule_and_dead_worker():
    failed = dict(WAITING, lastRun=dict(WAITING["lastRun"], outcome="failed", error="wikibooks timed out"))
    doc = view.statusDoc(failed, True, 0)
    assert (doc["light"], doc["reason"], doc["needsYou"]) == ("attention", "the last pass failed: wikibooks timed out", 1)
    assert view.statusDoc(dict(WAITING, schedule={"on": False}), True, 0)["light"] == "yellow"
    assert view.statusDoc(WAITING, False, 0)["light"] == "red"
    assert view.statusDoc(WAITING, None, 0)["light"] == "green"
    stopped = dict(WAITING, lastRun=dict(WAITING["lastRun"], outcome="stopped"))
    assert view.statusDoc(stopped, True, 0)["light"] == "green"


def test_needs_you_has_the_failed_pass_only():
    assert view.needsYouDoc(WAITING["lastRun"]) == {"items": []}
    assert view.needsYouDoc(None) == {"items": []}
    doc = view.needsYouDoc(dict(WAITING["lastRun"], outcome="failed", error="boom"))
    assert contract.checkNeedsYou(doc) == []
    assert doc["items"][0]["id"] == "gl-run-1792310400" and doc["items"][0]["detail"] == "boom"


def test_daily_counts_recipes_per_pass_day():
    runs = [WAITING["lastRun"], dict(WAITING["lastRun"], outcome="failed", recipes=0, endedAt=1792312300),
            {"outcome": "ok", "recipes": 5, "endedAt": None}]
    doc = view.dailyDoc(runs, 2, date(2026, 10, 18), tz=CDT)
    assert contract.checkDaily(doc) == []
    assert doc["days"][-1] == {"date": "2026-10-18", "items": 4310, "failed": 1, "bytes": None}


def test_a_last_run_of_the_wrong_shape_reads_as_no_run():
    doc = view.statusDoc(dict(WAITING, lastRun=["garbled"]), True, 0)
    assert doc["light"] == "green" and contract.checkStatus(doc) == []
    assert view.needsYouDoc(["garbled"]) == {"items": []}
    assert view.dailyDoc([["garbled"], 7], 2, date(2026, 10, 18))["days"][-1]["items"] == 0
