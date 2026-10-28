import hashlib

import pytest
from werkzeug.security import generate_password_hash

from conftest import UID

A = "/api/gluttony"
HASH = generate_password_hash("right-password")


def post(client, path, body):
    return client.post(f"{A}{path}", json=body)


def test_anUnknownDeviceIsNew(anonUserClient, useDb):
    useDb(fetchone=[None])
    assert post(anonUserClient, "/device/identify", {"fingerprint": "f1"}).get_json() == {"status": "new"}


def test_aKnownDeviceGetsANewSession(anonUserClient, useDb):
    conn = useDb(fetchone=[{"UserID": 7}, {"Username": "ann"}])
    answer = post(anonUserClient, "/device/identify", {"fingerprint": "f1"}).get_json()
    assert answer["status"] == "ok" and answer["UID"] == 7 and answer["username"] == "ann"
    assert len(answer["token"]) == 64
    insert = conn.cur.statements("INSERT INTO Sessions")[0]
    assert insert[1][:3] == (answer["token"], 7, "f1") and conn.commits == 1


def test_identifyNeedsAFingerprint(anonUserClient):
    assert post(anonUserClient, "/device/identify", {}).status_code == 400


def test_signInWithTheRightPassword(anonUserClient, useDb):
    conn = useDb(fetchone=[{"UserID": 7, "Username": "ann", "PasswordHash": HASH}])
    answer = post(anonUserClient, "/auth", {"username": "ann", "password": "right-password", "fingerprint": "f1"})
    assert answer.status_code == 200 and answer.get_json()["UID"] == 7
    assert conn.cur.statements("INSERT INTO Devices")[0][1] == ("f1", 7)


def test_aWrongPasswordIs401(anonUserClient, useDb):
    useDb(fetchone=[{"UserID": 7, "Username": "ann", "PasswordHash": HASH}])
    answer = post(anonUserClient, "/auth", {"username": "ann", "password": "nope", "fingerprint": "f1"})
    assert answer.status_code == 401 and answer.get_json()["status"] == "invalid_credentials"


def test_signUpSpendsTheKeyInOneTransaction(anonUserClient, useDb):
    conn = useDb(fetchone=[{"KeyValue": "k1", "Used": 0}, None], lastrowids={"Users": [12]})
    answer = post(anonUserClient, "/auth", {"username": "bea", "password": "long-enough", "fingerprint": "f2",
                                            "key": "k1"}).get_json()
    assert answer["status"] == "ok" and answer["UID"] == 12 and answer["username"] == "bea"
    executed = [sql for sql, _ in conn.cur.executed]
    assert executed[0] == "SELECT KeyValue, Used FROM LoginKeys WHERE KeyValue = %s FOR UPDATE"
    assert conn.cur.statements("UPDATE LoginKeys SET Used = 1, UsedBy = %s")[0][1] == (12, "k1")
    assert conn.commits == 1


@pytest.mark.parametrize("found", [None, {"KeyValue": "k1", "Used": 1}])
def test_anUnknownOrUsedKeyIs403(anonUserClient, useDb, found):
    useDb(fetchone=[found])
    answer = post(anonUserClient, "/auth", {"username": "bea", "password": "long-enough", "fingerprint": "f2",
                                            "key": "k1"})
    assert answer.status_code == 403 and answer.get_json()["status"] == "invalid_key"


def test_aTakenUsernameIs409(anonUserClient, useDb):
    useDb(fetchone=[{"KeyValue": "k1", "Used": 0}, {"UserID": 3}])
    answer = post(anonUserClient, "/auth", {"username": "ann", "password": "long-enough", "fingerprint": "f2",
                                            "key": "k1"})
    assert answer.status_code == 409 and answer.get_json()["status"] == "username_taken"


@pytest.mark.parametrize("username, password", [("ab", "long-enough"), ("x" * 33, "long-enough"),
                                                ("bea", "short"), ("bea", "y" * 257)])
def test_signUpChecksLengthsBeforeAnyQuery(anonUserClient, username, password):
    # No database installed: a refusal must come before any query.
    answer = post(anonUserClient, "/auth", {"username": username, "password": password, "fingerprint": "f2",
                                            "key": "k1"})
    assert answer.status_code == 400


def test_theSixthSignInAMinuteIsRefused(anonUserClient, useDb):
    for _ in range(5):
        useDb(fetchone=[None])
        post(anonUserClient, "/auth", {"username": "ann", "password": "x", "fingerprint": "f"})
    assert post(anonUserClient, "/auth", {"username": "ann", "password": "x", "fingerprint": "f"}).status_code == 429


def test_signingOutForgetsThisDeviceOnly(userClient, useDb):
    conn = useDb()
    assert post(userClient, "/auth/logout", {"fingerprint": "f1"}).get_json() == {"status": "ok"}
    assert conn.cur.statements("DELETE FROM Devices")[0][1] == ("f1", UID)
    assert conn.cur.statements("DELETE FROM Sessions")[0][1] == ("f1", UID)


def test_signingOutNeedsASession(anonUserClient):
    assert post(anonUserClient, "/auth/logout", {"fingerprint": "f1"}).status_code == 401


def test_aNewUsernameMustBeFree(userClient, useDb):
    useDb(fetchone=[{"UserID": 3}])
    assert post(userClient, "/user/username", {"username": "taken"}).status_code == 409
    useDb(fetchone=[None])
    assert post(userClient, "/user/username", {"username": "fresh"}).get_json() == {"status": "ok", "username": "fresh"}
    assert post(userClient, "/user/username", {"username": "ab"}).status_code == 400


def test_aNewPasswordNeedsTheCurrentOne(userClient, useDb):
    useDb(fetchone=[{"PasswordHash": HASH}])
    wrong = post(userClient, "/user/password", {"current": "nope", "password": "a-new-password"})
    assert wrong.status_code == 401 and wrong.get_json()["status"] == "invalid_credentials"
    conn = useDb(fetchone=[{"PasswordHash": HASH}])
    assert post(userClient, "/user/password", {"current": "right-password", "password": "a-new-password"}).status_code == 200
    assert conn.cur.statements("DELETE FROM Sessions WHERE UserID = %s AND Token <> %s")


def test_devicesAreNamedNeverByTheirFingerprint(userClient, useDb):
    from datetime import datetime
    useDb(fetchone=[{"DeviceFingerprint": "here"}],
          fetchall=[[{"Fingerprint": "here", "LastExpiry": datetime(2026, 11, 26, 8, 0)},
                     {"Fingerprint": "there", "LastExpiry": None}]])
    rows = userClient.get(f"{A}/devices").get_json()["data"]
    here = hashlib.sha256(b"here").hexdigest()[:16]
    assert rows[0] == {"id": here, "label": here[:8], "current": True, "lastSignIn": "2026-10-27T08:00:00Z"}
    assert rows[1]["current"] is False and rows[1]["lastSignIn"] is None
    assert "here" not in str(rows) and "there" not in str(rows)


def test_thisDeviceCannotBeRemoved(userClient, useDb):
    useDb(fetchone=[{"DeviceFingerprint": "here"}])
    here = hashlib.sha256(b"here").hexdigest()[:16]
    assert post(userClient, "/devices/remove", {"id": here}).status_code == 400


def test_anotherDeviceIsRemovedWithItsSessions(userClient, useDb):
    conn = useDb(fetchone=[{"DeviceFingerprint": "here"}], fetchall=[[{"Fingerprint": "here"}, {"Fingerprint": "there"}]])
    there = hashlib.sha256(b"there").hexdigest()[:16]
    assert post(userClient, "/devices/remove", {"id": there}).get_json() == {"status": "ok"}
    assert conn.cur.statements("DELETE FROM Devices")[0][1] == (UID, "there")
