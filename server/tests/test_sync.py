import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import UID
from test_yours import CID, VISIBLE, duplicateOnInsert

A = "/api/gluttony"
AT = "2026-10-29T10:00:00.000Z"
AT_TIME = datetime(2026, 10, 29, 10, 0)


def sync(client, ops):
    return client.post(f"{A}/sync/batch", json={"ops": ops})


def results(answer):
    assert answer.status_code == 200, answer.get_json()
    return answer.get_json()["data"]["results"]


def stars(value, at=AT, recipeId=7):
    return {"op": "stars", "recipeId": recipeId, "stars": value, "at": at}


def note(text, at=AT, recipeId=7):
    return {"op": "note", "recipeId": recipeId, "text": text, "at": at}


def mark(on="2026-10-28", clientId=CID, at=AT):
    return {"op": "devoured", "recipeId": 7, "on": on, "clientId": clientId, "at": at}


def test_changesApplyOldestFirstAndAreAnsweredInTheOrderSent(userClient, useDb):
    later = "2026-10-29T11:00:00.000Z"
    # Asked for in the order the changes are applied: the stars (older) first, then the note.
    conn = useDb(fetchone=[VISIBLE, None, VISIBLE, None])
    answered = results(sync(userClient, [note("less salt", at=later), stars(4)]))
    assert answered == [{"result": "applied", "recipeId": 7, "note": "less salt"},
                        {"result": "applied", "recipeId": 7, "stars": 4}]
    inserts = [sql for sql, _ in conn.cur.executed if sql.startswith("INSERT INTO")]
    assert inserts[0].startswith("INSERT INTO Ratings") and inserts[1].startswith("INSERT INTO Notes")
    assert conn.cur.statements("INSERT INTO Ratings")[0][1] == (UID, 7, 4, AT_TIME)
    assert conn.commits == 1


def test_aLateQueuedStarNeverOverwritesANewerOne(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, {"Stars": 5, "UpdatedAt": AT_TIME + timedelta(minutes=5)}])
    assert results(sync(userClient, [stars(2)])) == [{"result": "already", "recipeId": 7, "stars": 5}]
    assert not conn.cur.statements("INSERT INTO Ratings")
    assert conn.cur.statements("SELECT Stars, UpdatedAt FROM Ratings")[0][0].endswith("FOR UPDATE")


def test_aClearedRatingIsNotBroughtBackByALateQueue(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, {"Stars": None, "UpdatedAt": AT_TIME + timedelta(seconds=1)}])
    assert results(sync(userClient, [stars(3)])) == [{"result": "already", "recipeId": 7, "stars": None}]
    assert not conn.cur.statements("INSERT INTO Ratings")


def test_aDeletedNoteIsNotBroughtBackByALateQueue(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, {"Text": "", "UpdatedAt": AT_TIME + timedelta(seconds=1)}])
    assert results(sync(userClient, [note("old words")])) == [{"result": "already", "recipeId": 7, "note": None}]
    assert not conn.cur.statements("INSERT INTO Notes")


def test_aNewerQueuedChangeWinsAndAClearIsKeptAsARow(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, {"Stars": 5, "UpdatedAt": AT_TIME - timedelta(minutes=5)}])
    assert results(sync(userClient, [stars(None)])) == [{"result": "applied", "recipeId": 7, "stars": None}]
    assert conn.cur.statements("INSERT INTO Ratings")[0][1] == (UID, 7, None, AT_TIME)


def test_theSameMomentIsAlreadyApplied(userClient, useDb):
    # The batch sent again after its answer was lost finds its own change: that is "already", not a second write.
    conn = useDb(fetchone=[VISIBLE, {"Text": "less salt", "UpdatedAt": AT_TIME}])
    assert results(sync(userClient, [note("less salt")]))[0]["result"] == "already"
    assert not conn.cur.statements("INSERT INTO Notes")


def test_aResentBatchStoresEachMarkOnce(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, {"DevouredID": 41, "RecipeID": 7, "MadeOn": date(2026, 10, 28)}, {"n": 1}])
    assert results(sync(userClient, [mark()])) == [
        {"result": "already", "id": 41, "recipeId": 7, "on": "2026-10-28", "count": 1}]
    assert not conn.cur.statements("INSERT INTO Devoured")


def test_aNewMarkIsStoredWithItsClientId(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, None, {"n": 2}], lastrowids={"Devoured": [42]})
    assert results(sync(userClient, [mark()])) == [
        {"result": "applied", "id": 42, "recipeId": 7, "on": "2026-10-28", "count": 2}]
    assert conn.cur.statements("INSERT INTO Devoured")[0][1] == (UID, 7, date(2026, 10, 28), CID)


def test_aMarkWhoseClientIdIsAnotherAccountsIsRefused(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, None, {"DevouredID": 90, "RecipeID": 7, "MadeOn": date(2026, 10, 28),
                                           "UserID": UID + 1}])
    duplicateOnInsert(conn)
    assert results(sync(userClient, [mark()])) == [{"result": "refused", "message": "that clientId is in use"}]


def test_aClockAheadIsStoredAsNow(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, None])
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    results(sync(userClient, [stars(4, at="2099-01-01T00:00:00.000Z")]))
    stored = conn.cur.statements("INSERT INTO Ratings")[0][1][3]
    assert before <= stored <= datetime.now(timezone.utc).replace(tzinfo=None)


def test_aBadChangeIsRefusedAndTheOthersStillApply(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, None])
    answered = results(sync(userClient, [{"op": "bake", "recipeId": 7, "at": AT}, stars(4),
                                         {"op": "stars", "recipeId": "7", "stars": 4, "at": AT},
                                         {"op": "stars", "recipeId": 7, "stars": 4, "at": "yesterday"},
                                         {"op": "stars", "recipeId": 7, "at": AT},
                                         {"op": "stars", "recipeId": 7, "stars": 9, "at": AT},
                                         note("🍰" * 2001),
                                         mark(on="2026-13-01"), mark(clientId="not-a-uuid")]))
    assert answered[0] == {"result": "refused", "message": "op must be devoured, stars or note"}
    assert answered[1] == {"result": "applied", "recipeId": 7, "stars": 4}
    assert answered[2] == {"result": "refused", "message": "recipeId must be a recipe id"}
    assert answered[3] == {"result": "refused", "message": "at must be a UTC time (YYYY-MM-DDTHH:MM:SS.sssZ)"}
    assert answered[4] == answered[5] == {"result": "refused",
                                          "message": "stars must be a whole number from 1 to 5, or null"}
    assert answered[6] == {"result": "refused", "message": "a note is at most 2000 characters"}
    assert answered[7] == {"result": "refused", "message": "on must be a date (YYYY-MM-DD), not after tomorrow"}
    assert answered[8] == {"result": "refused", "message": "clientId must be a UUID"}
    assert conn.commits == 1


def test_aChangeOnARecipeThePersonCannotSeeIsRefused(userClient, useDb):
    useDb(fetchone=[None, None, None])
    answered = results(sync(userClient, [stars(4), note("x"), mark()]))
    assert answered == [{"result": "refused", "message": "no such recipe"}] * 3


def test_theBatchIsOneToFiveHundredChanges(userClient):
    for ops in ([], [stars(4)] * 501, "x", None):
        answer = sync(userClient, ops)
        assert answer.status_code == 400
        assert answer.get_json()["message"] == "ops must be a list of 1 to 500 changes"


def test_syncNeedsASession(anonUserClient):
    assert anonUserClient.post(f"{A}/sync/batch", json={"ops": [stars(4)]}).status_code == 401


class LockConflict(Exception):
    """What mysql.connector raises for a deadlock (1213) or a lock wait that ran out (1205)."""
    def __init__(self, errno):
        super().__init__(f"lock conflict {errno}")
        self.errno = errno


def conflictOnce(errno, times=1):
    """A failOn that raises a lock conflict on the first `times` reads of the stars row, then lets them through."""
    left = [times]

    def failOn(sql, params):
        if sql.startswith("SELECT Stars, UpdatedAt FROM Ratings") and left[0] > 0:
            left[0] -= 1
            raise LockConflict(errno)
        return False
    return failOn


def userRoutes():
    return sys.modules["gluttony_server.gluttonyUserRoutes"]


@pytest.fixture(autouse=True)
def pauses(monkeypatch, anonUserClient):
    """The wait before a retry is recorded, not slept, so the retry tests stay fast."""
    waited = []
    monkeypatch.setattr(userRoutes(), "retryPause", waited.append)
    return waited


def test_aBatchCaughtInADeadlockIsTriedAgainWhole(userClient, useDb, pauses):
    before = userRoutes().lockRetries
    # The first try reads the recipe, then dies on the stars row; the second reads both again.
    conn = useDb(fetchone=[VISIBLE, VISIBLE, None], failOn=conflictOnce(1213))
    assert results(sync(userClient, [stars(4)])) == [{"result": "applied", "recipeId": 7, "stars": 4}]
    assert len(conn.cur.statements("SELECT Stars, UpdatedAt FROM Ratings")) == 2
    assert len(conn.cur.statements("INSERT INTO Ratings")) == 1
    assert conn.commits == 1
    assert userRoutes().lockRetries == before + 1
    assert pauses == [0]


def test_aLockWaitTimeoutIsTriedAgainToo(userClient, useDb, pauses):
    conn = useDb(fetchone=[VISIBLE, VISIBLE, None], failOn=conflictOnce(1205))
    assert results(sync(userClient, [stars(4)])) == [{"result": "applied", "recipeId": 7, "stars": 4}]
    assert conn.commits == 1
    assert pauses == [0]


def test_aBatchStillDeadlockedAfterThreeTriesIsAServerError(userClient, useDb, pauses):
    conn = useDb(fetchone=[VISIBLE] * 3, failOn=conflictOnce(1213, times=3))
    answer = sync(userClient, [stars(4)])
    assert answer.status_code == 500
    assert len(conn.cur.statements("SELECT Stars, UpdatedAt FROM Ratings")) == 3
    assert conn.commits == 0
    # One pause between each pair of tries, none after the last.
    assert pauses == [0, 1]


def test_anyOtherFailureIsNotTriedAgain(userClient, useDb, pauses):
    conn = useDb(fetchone=[VISIBLE], failOn="SELECT Stars, UpdatedAt FROM Ratings")
    assert sync(userClient, [stars(4)]).status_code == 500
    assert len(conn.cur.statements("SELECT Stars, UpdatedAt FROM Ratings")) == 1
    assert conn.commits == 0
    assert pauses == []
