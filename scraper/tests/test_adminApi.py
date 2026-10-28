import pytest

import adminApi
import config


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data

    def json(self):
        if self._data is None:
            raise ValueError("no JSON")
        return self._data


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "tok")
    monkeypatch.setattr(config, "ADMIN_HOST", "host.example")


def test_nothingIsSentWithoutSettings():
    with pytest.raises(adminApi.AdminError, match="ADMIN_TOKEN and ADMIN_HOST"):
        adminApi.get("/state")


def test_aRequestCarriesTheToken(configured, monkeypatch):
    seen = []
    def request(method, url, json=None, timeout=None, headers=None):
        seen.append((method, url, headers["X-Admin-Token"]))
        return FakeResponse(200, {"status": "ok", "recipes": []})
    monkeypatch.setattr(adminApi._http, "request", request)
    assert adminApi.get("/state") == {"status": "ok", "recipes": []}
    assert seen == [("GET", "http://host.example:5000/api/gluttony-admin/state", "tok")]


def test_aRefusalIsRaisedAtOnceWithItsMessage(configured, monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        return FakeResponse(400, {"status": "error", "message": "recipes must be a list of 1 to 200"})
    monkeypatch.setattr(adminApi._http, "request", request)
    with pytest.raises(adminApi.AdminError, match="1 to 200"):
        adminApi.post("/recipes/batch", {"recipes": []})
    assert len(calls) == 1


def test_aServerErrorIsTriedThreeTimes(configured, monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        return FakeResponse(502, None)
    monkeypatch.setattr(adminApi._http, "request", request)
    with pytest.raises(adminApi.AdminError, match="after 3 attempts"):
        adminApi.get("/state")
    assert len(calls) == 3


def test_rsyncNeedsAnUploadHostAndSendsTheFolder(monkeypatch, tmp_path):
    with pytest.raises(adminApi.AdminError, match="UPLOAD_HOST"):
        adminApi.rsync(tmp_path, "/pool/appFiles/gluttony/images")
    monkeypatch.setattr(config, "UPLOAD_HOST", "user@host.example")
    commands = []
    monkeypatch.setattr(adminApi.subprocess, "run",
                        lambda command, **kw: commands.append(command) or type("R", (), {"returncode": 0})())
    adminApi.rsync(tmp_path / "images", "/pool/appFiles/gluttony/images")
    assert commands[0][-2:] == [f"{tmp_path / 'images'}/", "user@host.example:/pool/appFiles/gluttony/images/"]
