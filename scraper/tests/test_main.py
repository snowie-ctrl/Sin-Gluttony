from datetime import datetime, timezone

import config
import main
import pipeline
import store

NOW = datetime(2026, 10, 21, 17, 0, tzinfo=timezone.utc)


def test_chooseMode(monkeypatch):
    assert main.chooseMode([{"kind": "retag"}, {"kind": "run"}], NOW, {}) == "full"
    assert main.chooseMode([{"kind": "retag"}], NOW, {}) == "retag"
    assert main.chooseMode([], NOW, {}) is None                     # SCHEDULE is off in tests
    monkeypatch.setattr(config, "SCHEDULE", "on")
    assert main.chooseMode([], NOW, {}) == "full"
    assert main.chooseMode([], NOW, {"lastFullAt": NOW.timestamp()}) is None


def fakePass(monkeypatch, outcome):
    seen = {}
    def runPass(mode, log=print, stopRequested=None, images=True):
        seen["stop"] = stopRequested()
        return {"mode": mode, "outcome": outcome, "startedAt": 100.0, "endedAt": 200.0}
    monkeypatch.setattr(pipeline, "runPass", runPass)
    return seen


def test_aFinishedFullPassRecordsWhenItStarted(monkeypatch):
    config.STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.STOP_FILE.write_text("stop")                            # a stale stop from an earlier pass
    seen = fakePass(monkeypatch, "ok")
    main.runOnce("full", log=lambda *a: None)
    assert seen["stop"] is False and not config.STOP_FILE.exists()
    assert store.readJson(config.STATE_FILE) == {"lastFullAt": 100.0}


def test_aFailedFullPassRecordsWhenItFailed(monkeypatch):
    fakePass(monkeypatch, "failed")
    main.runOnce("full", log=lambda *a: None)
    assert store.readJson(config.STATE_FILE) == {"failedAt": 200.0}


def test_aRetagLeavesTheScheduleAlone(monkeypatch):
    fakePass(monkeypatch, "ok")
    main.runOnce("retag", log=lambda *a: None)
    assert store.readJson(config.STATE_FILE) == {}


def test_onceRunsOnePassAndSaysHowItWent(monkeypatch):
    fakePass(monkeypatch, "failed")
    assert main.main(["--once", "full", "--no-images"]) == 1
