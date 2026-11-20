import pytest
from datetime import datetime, timezone

import config
import main
import pipeline
import store

NOW = datetime(2026, 10, 21, 17, 0, tzinfo=timezone.utc)


def test_chooseMode(monkeypatch):
    assert main.chooseMode([{"kind": "retag"}, {"kind": "run"}], NOW, {}) == ("full", None)
    assert main.chooseMode([{"kind": "retag"}], NOW, {}) == ("retag", None)
    assert main.chooseMode([], NOW, {}) == (None, None)               # SCHEDULE is off in tests
    monkeypatch.setattr(config, "SCHEDULE", "on")
    assert main.chooseMode([], NOW, {}) == ("full", None)
    assert main.chooseMode([], NOW, {"lastFullAt": NOW.timestamp()}) == (None, None)


def test_chooseModeKeepsARunRequestsSite():
    assert main.chooseMode([{"kind": "run", "site": "difford"}], NOW, {}) == ("full", "difford")
    assert main.chooseMode([{"kind": "retag"}, {"kind": "run", "site": "difford"},
                            {"kind": "run", "site": "difford"}], NOW, {}) == ("full", "difford")
    # a plain run, or runs of two different sites, cover every site
    assert main.chooseMode([{"kind": "run", "site": "difford"}, {"kind": "run"}], NOW, {}) == ("full", None)
    assert main.chooseMode([{"kind": "run", "site": "difford"}, {"kind": "run", "site": "budgetbytes"}],
                           NOW, {}) == ("full", None)


def test_handlePassesARunRequestsSiteToRunOnce(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "runOnce", lambda mode, log=print, images=True, site=None: seen.append((mode, site)))
    assert main.handle([{"kind": "run", "site": "difford"}], NOW) == "full"
    assert main.handle([], NOW) is None
    assert seen == [("full", "difford")]


def fakePass(monkeypatch, outcome):
    seen = {}
    def runPass(mode, log=print, stopRequested=None, images=True, site=None):
        seen["stop"] = stopRequested()
        seen["site"] = site
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


def test_aOneSitePassPassesItsSiteAndLeavesTheScheduleAlone(monkeypatch):
    seen = fakePass(monkeypatch, "ok")
    main.runOnce("full", log=lambda *a: None, site="difford")
    assert seen["site"] == "difford" and store.readJson(config.STATE_FILE) == {}


@pytest.mark.parametrize("catalog, message", [
    ("old", "the old catalog was retired at the switch; set CATALOG=new"),
    ("olde", "CATALOG='olde' is not a catalog; set CATALOG=new"),
])
def test_anyCatalogButNewIsRefusedBeforeAnythingRuns(monkeypatch, catalog, message):
    monkeypatch.setattr(config, "CATALOG", catalog)
    refuse = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran under a retired catalog"))
    for module, name in ((main, "acquireLock"), (main.progress, "idle"), (pipeline, "runPass"),
                         (main.controlRequests, "take")):
        monkeypatch.setattr(module, name, refuse)
    for argv in (["--once", "full"], ["--dry-run"], []):
        with pytest.raises(SystemExit) as stopped:
            main.main(argv)
        assert message in str(stopped.value.code)          # a message for SystemExit means exit status 1
    assert not config.STATE_FILE.exists() and not config.CURRENT_FILE.exists()


def test_noImagesSaysItIsNeverForPublishing(capsys):
    with pytest.raises(SystemExit):
        main.main(["--help"])
    assert "never for publishing" in " ".join(capsys.readouterr().out.split())


def test_onceRunsOnePassAndSaysHowItWent(monkeypatch):
    fakePass(monkeypatch, "failed")
    assert main.main(["--once", "full", "--no-images"]) == 1


def test_dryRunRunsOnlyTheDryRun(monkeypatch):
    import dryrun
    seen = []
    monkeypatch.setattr(dryrun, "run", lambda pages=200, log=print, today=None, crawl=True, serverTable=False:
                        seen.append((pages, crawl, serverTable)))
    monkeypatch.setattr(pipeline, "runPass", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a pass ran")))
    assert main.main(["--dry-run", "--pages", "5"]) == 0
    assert main.main(["--dry-run", "--no-fetch"]) == 0
    assert main.main(["--dry-run", "--pages", "0", "--server-table"]) == 0      # the M4 full trial
    assert seen == [(5, True, False), (200, False, False), (None, True, True)]
