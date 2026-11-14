import pytest

import config
import controlApi
import controlRequests
import fdcMatch
from conftest import FIXTURES
import progress
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
                 {"ingredient": "onion", "fdcId": "900001"}, {"ingredient": "onion", "fdcId": True}):
        assert client.post("/fdc/pick", json=body).status_code == 400, body


def test_fdcPickNeedsTheToken():
    assert controlApi.app.test_client().post("/fdc/pick", json={"ingredient": "a", "fdcId": None}).status_code == 401
