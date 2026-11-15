import pytest

import config
import controlApi
import controlRequests
import fdc
import fdcMatch
from conftest import FIXTURES
import progress
import rulesData
import store


@pytest.fixture
def client():
    controlApi.app.testing = True
    client = controlApi.app.test_client()
    client.environ_base["HTTP_X_CONTROL_TOKEN"] = "test-control-token"
    return client


def test_everyRouteNeedsTheToken():
    assert controlApi.app.test_client().get("/status").status_code == 401


def test_statusSaysWhatIsHappening(client):
    progress.stage("full", "tag", "", startedAt=1.0)
    data = client.get("/status").get_json()
    assert data["running"] is True and data["current"]["stage"] == "tag"
    assert data["schedule"]["on"] is False and data["publish"] == "dry" and data["pending"] == []


def test_runIsAskedOnceAndRefusedWhileWaiting(client):
    assert client.post("/run").status_code == 202
    assert [r["kind"] for r in controlRequests.pending()] == ["run"]
    answer = client.post("/retag")
    assert answer.status_code == 409 and "already" in answer.get_json()["message"]


def test_runIsRefusedWhileAPassRuns(client):
    progress.stage("full", "fetch")
    assert client.post("/run").status_code == 409


def test_stopNeedsARunningPassBeforePublishing(client):
    assert client.post("/stop").status_code == 409
    progress.stage("full", "publish")
    assert client.post("/stop").status_code == 409 and not config.STOP_FILE.exists()
    progress.stage("full", "tag")
    assert client.post("/stop").status_code == 202 and config.STOP_FILE.exists()


def test_reportIsTheLastPasses(client):
    assert client.get("/report").status_code == 404
    store.writeJson(config.LAST_REPORT_FILE, {"outcome": "ok"})
    assert client.get("/report").get_json() == {"status": "ok", "report": {"outcome": "ok"}}


# ---- FDC mapping routes ----

def _installFoods():
    import shutil
    shutil.copytree(FIXTURES / "fdc" / "sr", config.FDC_DIR / "sr")
    fdc.importFolders(log=lambda *_: None)


def test_fdcQueueIsEmptyWithoutAFile(client):
    assert client.get("/fdc/queue").get_json() == {"status": "ok", "generatedAt": None, "queue": [], "picks": {}}


def test_fdcQueueIsTheWrittenFileAsItIs(client):
    rows = [{"ingredient": "onion", "unlocks": 4, "blocks": 4, "candidates": [], "extra": "kept"}]
    store.writeJson(config.FDC_QUEUE_FILE, {"generatedAt": "2026-11-14T00:00:00+00:00", "queue": rows})
    data = client.get("/fdc/queue").get_json()
    assert data["generatedAt"] == "2026-11-14T00:00:00+00:00" and data["queue"] == rows


def test_fdcSearchFindsTheFixtureOnion(client):
    _installFoods()
    results = client.get("/fdc/search?q=onions raw&limit=3").get_json()["results"]
    assert 900001 in [r["fdcId"] for r in results] and len(results) <= 3


def test_fdcSearchChecksItsInput(client):
    _installFoods()
    assert client.get("/fdc/search?q=a").status_code == 400
    assert client.get("/fdc/search?q=" + "x" * 81).status_code == 400
    assert len(client.get("/fdc/search?q=onions&limit=999").get_json()["results"]) <= 25


def test_fdcSearchNeverImportsFromARequest(client):
    import shutil
    shutil.copytree(FIXTURES / "fdc" / "sr", config.FDC_DIR / "sr")
    assert client.get("/fdc/search?q=onions").status_code == 503
    assert not config.FDC_FOODS_FILE.exists()


def test_fdcSearchWithoutImportedFoodsIs503(client):
    answer = client.get("/fdc/search?q=onions")
    assert answer.status_code == 503 and answer.get_json()["message"] == "FDC data not imported"


def test_fdcPickIsSavedAndShownInTheQueue(client):
    _installFoods()
    assert client.post("/fdc/pick", json={"ingredient": "onion", "fdcId": 900001}).get_json() == {"status": "ok"}
    assert client.post("/fdc/pick", json={"ingredient": "mystery", "fdcId": None}).status_code == 200
    assert client.get("/fdc/queue").get_json()["picks"] == {"onion": 900001, "mystery": None}
    assert fdcMatch.loadPicks() == {"onion": 900001, "mystery": None}


def test_fdcPickOfAnUnknownIdIs404(client):
    _installFoods()
    assert client.post("/fdc/pick", json={"ingredient": "onion", "fdcId": 1}).status_code == 404
    assert fdcMatch.loadPicks() == {}


def test_fdcPickChecksItsInput(client):
    _installFoods()
    for body in ({}, {"ingredient": ""}, {"ingredient": "x" * 101, "fdcId": None},
                 {"ingredient": "onion", "fdcId": "900001"}, {"ingredient": "onion", "fdcId": True}, {"ingredient": "onion"}):
        assert client.post("/fdc/pick", json=body).status_code == 400, body


def test_fdcPickNeedsTheToken():
    assert controlApi.app.test_client().post("/fdc/pick", json={"ingredient": "a", "fdcId": None}).status_code == 401


# ---- Sites page routes ----

@pytest.fixture
def newCatalog(monkeypatch):
    monkeypatch.setattr(config, "CATALOG", "new")
    monkeypatch.setattr(rulesData, "load", lambda: {"sites": [
        {"site": "alpha.com", "name": "Alpha", "host": "alpha.com", "parser": "schema", "kind": "food", "recipeUrl": "/r/",
         "sitemaps": ["https://alpha.com/s.xml"], "enabled": True},
        {"site": "off.com", "name": "Off", "host": "off.com", "parser": "schema", "kind": "food", "recipeUrl": "/r/",
         "sitemaps": ["https://off.com/s.xml"], "enabled": False}]})


def test_statusSaysWhichCatalog(client, monkeypatch):
    assert client.get("/status").get_json()["catalog"] == "new"
    monkeypatch.setattr(config, "CATALOG", "old")
    assert client.get("/status").get_json()["catalog"] == "old"


def test_regateQueuesARetagUnderTheNewCatalog(client, newCatalog):
    answer = client.post("/regate")
    assert answer.status_code == 202
    assert answer.get_json() == {"status": "ok", "message": "a re-gate starts within a few seconds"}
    assert [r["kind"] for r in controlRequests.pending()] == ["retag"]
    assert client.post("/regate").status_code == 409


def test_everyPassRequestIsRefusedUnderTheRetiredCatalog(client, newCatalog, monkeypatch):
    monkeypatch.setattr(config, "CATALOG", "old")
    for path in ("/run", "/retag", "/regate", "/crawl/alpha.com"):
        answer = client.post(path)
        assert answer.status_code == 409
        assert answer.get_json()["message"] == "the old catalog was retired at the switch; set CATALOG=new"
    assert controlRequests.pending() == []


def test_regateIsRefusedWhileAPassRuns(client, newCatalog):
    progress.stage("full", "fetch")
    assert client.post("/regate").status_code == 409


def test_crawlQueuesOneSite(client, newCatalog):
    answer = client.post("/crawl/alpha.com")
    assert answer.status_code == 202
    assert [(r["kind"], r.get("site")) for r in controlRequests.pending()] == [("run", "alpha.com")]
    assert client.post("/crawl/alpha.com").status_code == 409


def test_crawlRefusesASiteNotEnabled(client, newCatalog):
    assert client.post("/crawl/off.com").status_code == 404
    assert client.post("/crawl/nowhere.com").status_code == 404
    assert controlRequests.pending() == []


def test_sitesServesTheSitesFile(client, newCatalog):
    empty = client.get("/sites").get_json()
    assert empty == {"status": "ok", "catalog": "new", "generatedAt": None, "mode": None, "sites": []}
    store.writeJson(config.SITES_FILE, {"generatedAt": "2026-11-14T01:00:00+00:00", "mode": "dryrun",
                                        "sites": [{"site": "alpha.com", "state": "ok"}]})
    data = client.get("/sites").get_json()
    assert data["generatedAt"] == "2026-11-14T01:00:00+00:00" and data["mode"] == "dryrun"
    assert data["sites"] == [{"site": "alpha.com", "state": "ok"}] and data["catalog"] == "new"


def test_sitesToleratesAGarbledFile(client):
    config.SITES_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SITES_FILE.write_text("not json", encoding="utf-8")
    assert client.get("/sites").get_json()["sites"] == []


def test_askStoresTheSiteOnlyWhenGiven():
    controlRequests.ask("run")
    controlRequests.ask("run", site="alpha.com")
    first, second = controlRequests.pending()
    assert "site" not in first and second["site"] == "alpha.com"
