"""
Loads gluttonyAdminRoutes.py and gluttonyRoutes.py the way Caduceus does, minus the server. Both do
`from . import DBUtils, gluttonyRules`, so they are imported as submodules of a stand-in package whose DBUtils refuses
to connect: a test that reaches the database by accident fails loudly instead of touching data.
"""
import importlib.util
import json
import pathlib
import sys
import types

import flask
import pytest

SERVER = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fakes import FakeConn, FakeCursor  # noqa: E402

TOKEN = "test-admin-token"
SESSION = "test-session-token"
UID = 7


def _refuseConnection(name):
    raise RuntimeError("tests must not open a database connection")


def _load(name):
    if "gluttony_server" not in sys.modules:
        package = types.ModuleType("gluttony_server")
        package.__path__ = [str(SERVER)]
        dbutils = types.ModuleType("gluttony_server.DBUtils")
        dbutils.initConnection = _refuseConnection
        package.DBUtils = dbutils
        sys.modules["gluttony_server"] = package
        sys.modules["gluttony_server.DBUtils"] = dbutils
    spec = importlib.util.spec_from_file_location(f"gluttony_server.{name}", SERVER / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def loadModule(name):
    """Any server module, loaded inside the stand-in package (the rules, the smoke test...)."""
    return sys.modules.get(f"gluttony_server.{name}") or _load(name)


# The real lookup, kept before isolated() replaces it in every test, so test_session can check its SQL.
REAL_SESSION_UID = loadModule("gluttonySession").sessionUID


def _sessionFor(token):
    return UID if token == SESSION else None


@pytest.fixture
def rules():
    return loadModule("gluttonyRules")


@pytest.fixture
def routes():
    return loadModule("gluttonyAdminRoutes")


@pytest.fixture
def sessions():
    return loadModule("gluttonySession")


@pytest.fixture
def userRoutes():
    return loadModule("gluttonyUserRoutes")


@pytest.fixture
def readRoutes():
    return loadModule("gluttonyRoutes")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Each test gets its own token file and media root, and no database."""
    admin = loadModule("gluttonyAdminRoutes")
    read = loadModule("gluttonyRoutes")
    config = tmp_path / "gluttonyAdminConfig.json"
    config.write_text(json.dumps({"token": TOKEN}))
    monkeypatch.setattr(admin, "CONFIG_FILE", config)
    admin._tokenCache.update({"mtime": None, "token": None})
    media = tmp_path / "media"
    (media / "images").mkdir(parents=True)
    (media / "thumbs").mkdir()
    monkeypatch.setattr(read, "MEDIA_ROOT", media)
    sessions = loadModule("gluttonySession")
    monkeypatch.setattr(sessions, "sessionUID", _sessionFor)
    # A fresh limiter per test, so one test's sign-ins never use up another's.
    monkeypatch.setattr(sessions, "RATE_LIMITER", sessions.RateLimiter())
    monkeypatch.setattr(sys.modules["gluttony_server.DBUtils"], "initConnection", _refuseConnection)


@pytest.fixture
def media(readRoutes):
    return readRoutes.MEDIA_ROOT


@pytest.fixture
def useDb(monkeypatch):
    """Installs a FakeConn answering the queued rows; returns it."""
    def install(fetchone=(), fetchall=(), lastrowids=None, failOn=None, rowcounts=()):
        conn = FakeConn(FakeCursor(fetchone, fetchall, lastrowids, failOn, rowcounts))

        def connect(name):
            assert name == "gluttony", f"connected to {name!r}"
            return conn

        monkeypatch.setattr(sys.modules["gluttony_server.DBUtils"], "initConnection", connect)
        return conn
    return install


@pytest.fixture
def client(routes):
    app = flask.Flask("gluttony-admin-tests")
    app.register_blueprint(routes.gluttonyAdminBP, url_prefix="/api/gluttony-admin")
    client = app.test_client()
    client.environ_base["HTTP_X_ADMIN_TOKEN"] = TOKEN
    return client


@pytest.fixture
def anonClient(routes):
    app = flask.Flask("gluttony-admin-anon")
    app.register_blueprint(routes.gluttonyAdminBP, url_prefix="/api/gluttony-admin")
    return app.test_client()


def _appClient(*blueprints):
    app = flask.Flask("gluttony-app-tests")
    for blueprint in blueprints:
        app.register_blueprint(blueprint, url_prefix="/api/gluttony")
    return app.test_client()


@pytest.fixture
def anonReadClient(readRoutes):
    return _appClient(readRoutes.gluttonyBP)


@pytest.fixture
def readClient(anonReadClient):
    anonReadClient.environ_base["HTTP_X_SESSION_TOKEN"] = SESSION
    return anonReadClient


@pytest.fixture
def tunnelClient(readClient):
    readClient.environ_base["HTTP_CF_CONNECTING_IP"] = "203.0.113.9"
    return readClient


@pytest.fixture
def anonUserClient(userRoutes):
    return _appClient(userRoutes.gluttonyUserBP)


@pytest.fixture
def userClient(anonUserClient):
    anonUserClient.environ_base["HTTP_X_SESSION_TOKEN"] = SESSION
    return anonUserClient
