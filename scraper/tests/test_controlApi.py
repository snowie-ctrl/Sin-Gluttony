import pytest

import config
import controlApi
import controlRequests
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
