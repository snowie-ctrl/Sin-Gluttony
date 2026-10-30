import json

import controlApi
import surrogateContract as contract
from test_contractView import WAITING


def client(monkeypatch, lines=None):
    monkeypatch.setattr(controlApi, "_statusJson", lambda: WAITING)
    monkeypatch.setattr(controlApi, "_scraperAlive", lambda: True)
    monkeypatch.setattr(controlApi, "_runLines", lambda: lines if lines is not None else [json.dumps(WAITING["lastRun"])])
    controlApi.app.testing = True
    c = controlApi.app.test_client()
    c.environ_base["HTTP_X_CONTROL_TOKEN"] = "test-control-token"
    return c


def test_the_contract_routes_need_the_token():
    assert controlApi.app.test_client().get("/surrogate/v1/status").status_code == 401


def test_status_needs_you_and_daily_answer_the_contract(monkeypatch):
    c = client(monkeypatch)
    doc = c.get("/surrogate/v1/status").get_json()
    assert contract.checkStatus(doc) == [] and doc["app"] == "gluttony"
    assert c.get("/surrogate/v1/needs-you").get_json() == {"items": []}
    assert contract.checkDaily(c.get("/surrogate/v1/daily?days=7").get_json()) == []


def test_a_cut_short_runs_line_is_skipped(monkeypatch):
    c = client(monkeypatch, lines=['{"outcome": "ok", "recipes": 3, "endedAt": 1792312200}', '{"outcome": "o'])
    days = c.get("/surrogate/v1/daily?days=30").get_json()["days"]
    assert sum(d["items"] for d in days) in (0, 3)
