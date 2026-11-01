from types import SimpleNamespace

import pytest

from conftest import loadModule


def test_theRealDatabaseIsRefused():
    smoke = loadModule("gluttonySmoke")
    with pytest.raises(ValueError):
        smoke.scratchConnections("gluttonyDB", lambda name: None)
    with pytest.raises(ValueError):
        smoke.scratchConnections("bad name;", lambda name: None)
    with pytest.raises(ValueError):
        smoke.scratchConnections("pageturnerDB", lambda name: None)


def test_everyConnectionSwitchesToTheScratchDatabase():
    smoke = loadModule("gluttonySmoke")
    executed = []
    cursor = SimpleNamespace(execute=lambda sql: executed.append(sql), close=lambda: None)
    conn = SimpleNamespace(cursor=lambda: cursor)
    connect = smoke.scratchConnections("gluttony_smoke", lambda name: conn)
    assert connect("gluttony") is conn and executed == ["USE `gluttony_smoke`"]


def test_mainRefusesABadNameWithExitTwo(capsys):
    smoke = loadModule("gluttonySmoke")
    assert smoke.main(["--database", "gluttonydb"]) == 2


def test_aFailedConnectionIsPrintedBeforeItRaises(capsys):
    smoke = loadModule("gluttonySmoke")

    def refuse(name):
        raise RuntimeError("Access denied for user")
    connect = smoke.scratchConnections("gluttony_smoke", refuse)
    with pytest.raises(RuntimeError):
        connect("gluttony")
    err = capsys.readouterr().err
    assert "smoke: could not open the scratch database: " in err and "Access denied" in err


@pytest.mark.parametrize("seedAnswer", [{"added": 0, "updated": 3, "kept": 0}, {"added": 0, "updated": 0, "kept": 3}])
def test_aNonEmptyScratchDatabaseFailsTheSeedStep(capsys, tmp_path, seedAnswer):
    smoke = loadModule("gluttonySmoke")
    answer = SimpleNamespace(status_code=200, mimetype="application/json", get_json=lambda silent=True: {"status": "ok", **seedAnswer},
                             get_data=lambda as_text=False: "")
    client = SimpleNamespace(open=lambda path, method, json: answer)
    assert smoke.runSteps(client, tmp_path) == 1
    assert "FAIL  seed: the scratch database is not empty: drop and recreate it" in capsys.readouterr().out


def test_aPictureAnswerIsReturnedWithoutReadingItAsText():
    from werkzeug.wrappers import Response
    smoke = loadModule("gluttonySmoke")
    picture = Response(b"\xff\xd8smoke", mimetype="image/jpeg")
    client = SimpleNamespace(open=lambda path, method, json: picture)
    assert smoke.call(client, "GET", "/images/1").data == b"\xff\xd8smoke"
    refused = Response(b"\xff\xd8", status=500, mimetype="image/jpeg")
    client = SimpleNamespace(open=lambda path, method, json: refused)
    with pytest.raises(smoke.SmokeFailed, match="GET /images/1 gave 500"):
        smoke.call(client, "GET", "/images/1")


def test_theStepsSignUpBeforeBrowsingAndSignOutLast(tmp_path):
    smoke = loadModule("gluttonySmoke")
    assert [name for name, _ in smoke.steps(tmp_path)] == [
        "seed", "store", "unknown", "account", "browse", "diet", "home", "lists", "yours", "sync", "manifest",
        "strangers", "remove", "signout"]
