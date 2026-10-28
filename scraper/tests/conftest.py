"""
Keeps every test away from the outside world and from the VM's real files:
network calls are refused, plutus is unconfigured, publishing is dry, and
every file the scraper writes points into the test's own temporary folder.
"""
from pathlib import Path

import pytest

import config
import net

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PATHS = ("DATA_DIR", "RAW_DIR", "IMAGE_DIR", "CACHE_DIR", "NORMALISED_FILE", "PUBLISHED_FILE", "RUN_DIR",
         "REPORT_DIR", "FETCH_FILE", "STATE_FILE", "CURRENT_FILE", "RUNS_FILE", "LAST_REPORT_FILE",
         "CONTROL_REQUESTS_FILE", "STOP_FILE", "LOCK_FILE")


@pytest.fixture(autouse=True)
def noNetwork(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not touch the network")
    monkeypatch.setattr(net._session, "request", refuse)
    monkeypatch.setattr(net._session, "get", refuse)
    monkeypatch.setattr(net.time, "sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def isolatedFiles(tmp_path, monkeypatch):
    """Every path in config moves under tmp_path, keeping its place relative to the scraper folder."""
    for name in PATHS:
        real = getattr(config, name)
        monkeypatch.setattr(config, name, tmp_path / real.relative_to(config.BASE_DIR))


@pytest.fixture(autouse=True)
def safeModes(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_HOST", "")
    monkeypatch.setattr(config, "UPLOAD_HOST", "")
    monkeypatch.setattr(config, "PUBLISH", "dry")
    monkeypatch.setattr(config, "SCHEDULE", "off")
    monkeypatch.setattr(config, "CONTROL_TOKEN", "test-control-token")


@pytest.fixture(autouse=True)
def noPlutus(monkeypatch):
    """adminApi has its own HTTP session and runs rsync: both are refused, so no test can reach plutus."""
    import adminApi

    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not reach plutus")
    monkeypatch.setattr(adminApi._http, "request", refuse)
    monkeypatch.setattr(adminApi.subprocess, "run", refuse)
    monkeypatch.setattr(adminApi.time, "sleep", lambda seconds: None)
