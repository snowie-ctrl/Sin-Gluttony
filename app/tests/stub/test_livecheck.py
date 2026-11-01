import json
import sys
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

import stub_server as stub

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server"))
import liveCheck  # noqa: E402

PASSWORD = "check-password-123"


@pytest.fixture
def stubBase(monkeypatch, tmp_path):
    # The four fixture recipes, as test_stub.py uses, so the check never depends on a snapshot. The fixture folder
    # holds no picture files (its recipes still say hasImage), so the folder served here is a copy with a stand-in
    # JPEG for each recipe that has one: the check's picture step then has something real to fetch.
    fixture = json.loads((stub.HERE / "fixture" / "recipes.json").read_text(encoding="utf-8"))
    (tmp_path / "recipes.json").write_text(json.dumps(fixture), encoding="utf-8")
    for folder in ("images", "thumbs"):
        (tmp_path / folder).mkdir()
        for recipe in fixture["recipes"]:
            if recipe["hasImage"]:
                (tmp_path / folder / f"{recipe['id']}.jpg").write_bytes(b"\xff\xd8stub picture\xff\xd9")
    monkeypatch.setenv("STUB_SNAPSHOT", str(tmp_path))
    stub.reset()
    server = make_server("127.0.0.1", 0, stub.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/api/gluttony"
    server.shutdown()


@pytest.fixture
def secrets(monkeypatch):
    monkeypatch.setenv("GLUTTONY_CHECK_PASSWORD", PASSWORD)
    monkeypatch.setenv("GLUTTONY_CHECK_KEY", "stub-key")


def test_theLiveCheckPassesAgainstTheStub(stubBase, secrets, capsys):
    code = liveCheck.main(["--base", stubBase, "--username", "claude-check", "--sign-up", "--outside"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "FAIL" not in out and out.count("PASS") >= 15
    # Nothing secret is ever printed.
    assert "stub-key" not in out and PASSWORD not in out


def test_aSecondRunSignsInToTheSameAccount(stubBase, secrets, capsys):
    assert liveCheck.main(["--base", stubBase, "--username", "claude-check", "--sign-up"]) == 0
    assert liveCheck.main(["--base", stubBase, "--username", "claude-check"]) == 0, capsys.readouterr().out


def test_aServerThatDoesNotAnswerFailsAtTheFirstStep(secrets, capsys):
    assert liveCheck.main(["--base", "http://127.0.0.1:1/api/gluttony", "--username", "claude-check"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL  ping") and out.count("FAIL") == 1


def test_signingUpNeedsTheKey(stubBase, monkeypatch, capsys):
    monkeypatch.setenv("GLUTTONY_CHECK_PASSWORD", PASSWORD)
    monkeypatch.delenv("GLUTTONY_CHECK_KEY", raising=False)
    assert liveCheck.main(["--base", stubBase, "--username", "claude-check", "--sign-up"]) == 2


def checker(stubBase):
    return [r for r in stub.state["readers"].values() if r["username"] == "claude-check"][0]


def leftBehind(reader):
    # Everything a step keeps on the server: custom lists, Cravings, marks, stars and notes.
    return {"lists": [l["title"] for l in reader["lists"] if l["kind"] != "cravings"],
            "cravings": reader["lists"][0]["items"], "devoured": reader["devoured"],
            "ratings": reader["ratings"], "notes": reader["notes"]}


def test_aRunThatFailsMidWayTakesBackWhatItKept(stubBase, secrets, capsys):
    original = stub.app.view_functions["savedManifest"]
    stub.app.view_functions["savedManifest"] = lambda: stub.fail("error", 500, "boom")
    try:
        assert liveCheck.main(["--base", stubBase, "--username", "claude-check", "--sign-up"]) == 1
    finally:
        stub.app.view_functions["savedManifest"] = original
    out = capsys.readouterr().out
    assert out.count("FAIL") == 1 and "FAIL  manifest" in out and "PASS  yours" in out
    assert leftBehind(checker(stubBase)) == {"lists": [], "cravings": [], "devoured": [], "ratings": {}, "notes": {}}
    # The session ended too: no token of the check's account is left.
    assert [t for t, rid in stub.state["tokens"].items() if rid != stub.UID] == []
    assert liveCheck.main(["--base", stubBase, "--username", "claude-check"]) == 0, capsys.readouterr().out


def test_aListLeftByAnEarlierRunIsClearedBeforeTheNextOne(stubBase, secrets, capsys):
    assert liveCheck.main(["--base", stubBase, "--username", "claude-check", "--sign-up"]) == 0
    checker(stubBase)["lists"].append({"id": 900, "title": "claude-check renamed", "kind": "custom", "items": [1]})
    checker(stubBase)["lists"].append({"id": 901, "title": "Weeknights", "kind": "custom", "items": []})
    assert liveCheck.main(["--base", stubBase, "--username", "claude-check"]) == 0, capsys.readouterr().out
    assert leftBehind(checker(stubBase))["lists"] == ["Weeknights"]


def test_aStepThatBreaksOffTheContractIsOneFailLine(stubBase, secrets, capsys):
    recipes = "recipes"
    original = stub.app.view_functions[recipes]
    stub.app.view_functions[recipes] = lambda: stub.ok({})
    try:
        assert liveCheck.main(["--base", stubBase, "--username", "claude-check", "--sign-up"]) == 1
    finally:
        stub.app.view_functions[recipes] = original
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL")]
    assert lines == ["FAIL  catalog: KeyError: 'total'"]
    assert [t for t, rid in stub.state["tokens"].items() if rid != stub.UID] == []


def test_aBaseThatIsNotTheApiIsRefused(secrets, capsys):
    assert liveCheck.main(["--base", "http://127.0.0.1:1/somewhere", "--username", "claude-check"]) == 2
    assert "/api/gluttony" in capsys.readouterr().out


def test_failureTextIsAsciiWhateverTheServerSays(stubBase, secrets, capsys):
    recipes = "recipes"
    original = stub.app.view_functions[recipes]
    # UTF-8 on the wire, as a server that does not escape sends it.
    raw = json.dumps({"status": "error", "message": "caf" + chr(0xe9)}, ensure_ascii=False).encode("utf-8")
    stub.app.view_functions[recipes] = lambda: stub.app.response_class(raw, 500, mimetype="application/json")
    try:
        assert liveCheck.main(["--base", stubBase, "--username", "claude-check", "--sign-up"]) == 1
    finally:
        stub.app.view_functions[recipes] = original
    out = capsys.readouterr().out
    assert out.isascii() and "FAIL  catalog" in out
