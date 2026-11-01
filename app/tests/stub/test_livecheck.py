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
