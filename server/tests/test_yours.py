from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import UID

A = "/api/gluttony"
CID = "6f1c2b9e-3d4a-4b5c-8d7e-9f0a1b2c3d4e"
VISIBLE = {"RecipeID": 7, "RemovedAt": None, "ImagePath": None}
TILE = {"RecipeID": 7, "Kind": "food", "Title": "Cheese Toast", "Course": "main", "Cuisine": None,
        "TotalMinutes": 10, "TimeFrom": "rule", "Difficulty": 1, "ImagePath": None, "Source": "mealdb",
        "RemovedAt": None}


def post(client, path, body):
    return client.post(f"{A}{path}", json=body)


def utcToday():
    return datetime.now(timezone.utc).date()


def test_aMarkIsStoredWithItsClientId(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, None, {"n": 1}], lastrowids={"Devoured": [41]})
    answer = post(userClient, "/devoured/add", {"recipeId": 7, "on": "2026-10-27", "clientId": CID}).get_json()
    assert answer["data"] == {"id": 41, "recipeId": 7, "on": "2026-10-27", "count": 1, "already": False}
    assert conn.cur.statements("SELECT DevouredID")[0][1] == (CID, UID)
    assert conn.cur.statements("INSERT INTO Devoured")[0][1] == (UID, 7, date(2026, 10, 27), CID)
    assert conn.commits == 1


def test_aResentMarkIsStoredOnce(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, {"DevouredID": 41, "RecipeID": 7, "MadeOn": date(2026, 10, 27)}, {"n": 1}])
    answer = post(userClient, "/devoured/add", {"recipeId": 7, "on": "2026-10-27", "clientId": CID}).get_json()
    assert answer["data"] == {"id": 41, "recipeId": 7, "on": "2026-10-27", "count": 1, "already": True}
    assert not conn.cur.statements("INSERT INTO Devoured")


class DuplicateKey(Exception):
    errno = 1062


def duplicateOnInsert(conn):
    """The unique key on ClientID refuses the INSERT, as MySQL does when another request stored the id first."""
    real = conn.cur.execute

    def execute(sql, params=None):
        if " ".join(sql.split()).startswith("INSERT INTO Devoured"):
            conn.cur.executed.append((" ".join(sql.split()), params))
            raise DuplicateKey("Duplicate entry for key 'ux_devoured_client'")
        return real(sql, params)

    conn.cur.execute = execute


def test_aResendThatRacesItsTwinIsAnsweredAsStored(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, None, {"DevouredID": 41, "RecipeID": 7, "MadeOn": date(2026, 10, 27), "UserID": UID},
                           {"n": 1}])
    duplicateOnInsert(conn)
    answer = post(userClient, "/devoured/add", {"recipeId": 7, "on": "2026-10-27", "clientId": CID})
    assert answer.status_code == 200
    assert answer.get_json()["data"] == {"id": 41, "recipeId": 7, "on": "2026-10-27", "count": 1, "already": True}
    # The second look is a locking read: the transaction's snapshot predates the twin's commit.
    assert conn.cur.statements("SELECT DevouredID, RecipeID, MadeOn, UserID")[0][0].endswith("LOCK IN SHARE MODE")
    assert conn.commits == 1


def test_aClientIdHeldByAnotherAccountIs409(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, None, {"DevouredID": 90, "RecipeID": 7, "MadeOn": date(2026, 10, 27), "UserID": UID + 1}])
    duplicateOnInsert(conn)
    answer = post(userClient, "/devoured/add", {"recipeId": 7, "on": "2026-10-27", "clientId": CID})
    assert answer.status_code == 409 and answer.get_json()["message"] == "that clientId is in use"
    assert "90" not in answer.get_data(as_text=True) and conn.commits == 0


def test_anotherErrorOnTheInsertIsNotHiddenAsAConflict(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE, None], failOn="INSERT INTO Devoured")
    answer = post(userClient, "/devoured/add", {"recipeId": 7, "on": "2026-10-27", "clientId": CID})
    assert answer.status_code == 500 and conn.commits == 0


def test_todayInAZoneAheadOfUtcIsNotTheFuture(rules, userClient, useDb):
    # 08:00 in Tokyo on the 28th is still the 27th in UTC: the person's own today must be accepted.
    assert rules.madeOn("2026-10-28", date(2026, 10, 27)) == (date(2026, 10, 28), None)
    assert rules.madeOn("2026-10-29", date(2026, 10, 27))[1] == "on must be a date (YYYY-MM-DD), not after tomorrow"
    tomorrow = (utcToday() + timedelta(days=1)).isoformat()
    useDb(fetchone=[VISIBLE, None, {"n": 1}], lastrowids={"Devoured": [41]})
    assert post(userClient, "/devoured/add", {"recipeId": 7, "on": tomorrow, "clientId": CID}).status_code == 200
    later = (utcToday() + timedelta(days=2)).isoformat()
    assert post(userClient, "/devoured/add", {"recipeId": 7, "on": later, "clientId": CID}).status_code == 400


@pytest.mark.parametrize("on", ["2026-02-30", "27/10/2026", "2026-1-5", 20261027, None, "1899-12-31", ""])
def test_aBadDayIs400BeforeAnyQuery(userClient, on):
    answer = post(userClient, "/devoured/add", {"recipeId": 7, "on": on, "clientId": CID})
    assert answer.status_code == 400 and answer.get_json()["message"] == "on must be a date (YYYY-MM-DD), not after tomorrow"


@pytest.mark.parametrize("clientId", ["abc", CID.upper(), None, "", CID + "0", 5])
def test_aClientIdMustBeAUuid(userClient, clientId):
    answer = post(userClient, "/devoured/add", {"recipeId": 7, "on": "2026-10-27", "clientId": clientId})
    assert answer.status_code == 400 and answer.get_json()["message"] == "clientId must be a UUID"


def test_aRecipeThePersonCannotSeeIsNotMarked(userClient, useDb):
    useDb(fetchone=[None])
    answer = post(userClient, "/devoured/add", {"recipeId": 70000, "on": "2026-10-27", "clientId": CID})
    assert answer.status_code == 404 and answer.get_json()["message"] == "no such recipe"


def test_aMarkIsRemoved(userClient, useDb):
    conn = useDb(fetchone=[{"RecipeID": 7}, {"n": 0}])
    assert post(userClient, "/devoured/remove", {"id": 41}).get_json()["data"] == {"id": 41, "recipeId": 7, "count": 0}
    assert conn.cur.statements("DELETE FROM Devoured")[0][1] == (41, UID) and conn.commits == 1


def test_someoneElsesMarkIs404(userClient, useDb):
    conn = useDb(fetchone=[None])
    answer = post(userClient, "/devoured/remove", {"id": 41})
    assert answer.status_code == 404 and answer.get_json()["message"] == "no such Devoured mark"
    assert conn.cur.executed[0][1] == (41, UID) and not conn.cur.statements("DELETE")


def test_theHistoryIsNewestFirstWithADayPerMark(userClient, useDb):
    rows = [dict(TILE, DevouredID=42, MadeOn=date(2026, 10, 27)),
            dict(TILE, DevouredID=41, MadeOn=date(2026, 9, 1), RemovedAt=datetime(2026, 10, 20))]
    conn = useDb(fetchone=[{"n": 2}], fetchall=[rows, []])
    data = userClient.get(f"{A}/devoured").get_json()["data"]
    assert data["total"] == 2 and data["page"] == 1 and data["pageSize"] == 24
    assert [(t["devouredId"], t["on"], t["removed"]) for t in data["recipes"]] == [(42, "2026-10-27", False),
                                                                                    (41, "2026-09-01", True)]
    sql, params = conn.cur.statements("SELECT r.RecipeID")[0]
    assert "ORDER BY d.MadeOn DESC, d.DevouredID DESC" in sql and params == (UID, 24, 0)


def test_theHistoryCanBeSortedByYourStars(userClient, useDb):
    conn = useDb(fetchone=[{"n": 0}], fetchall=[[]])
    userClient.get(f"{A}/devoured?sort=stars")
    assert "ORDER BY t.Stars IS NULL, t.Stars DESC, d.MadeOn DESC" in conn.cur.statements("SELECT r.RecipeID")[0][0]
    assert userClient.get(f"{A}/devoured?sort=best").status_code == 400


def test_starsAreSetAndCleared(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE])
    assert post(userClient, "/rating", {"recipeId": 7, "stars": 4}).get_json()["data"] == {"recipeId": 7, "stars": 4}
    assert conn.cur.statements("INSERT INTO Ratings")[0][1] == (UID, 7, 4)
    conn = useDb(fetchone=[VISIBLE])
    assert post(userClient, "/rating", {"recipeId": 7, "stars": None}).get_json()["data"] == {"recipeId": 7, "stars": None}
    assert conn.cur.statements("DELETE FROM Ratings")[0][1] == (UID, 7)


@pytest.mark.parametrize("body", [{"recipeId": 7, "stars": 0}, {"recipeId": 7, "stars": 6},
                                  {"recipeId": 7, "stars": 4.5}, {"recipeId": 7, "stars": True},
                                  {"recipeId": 7, "stars": "4"}, {"recipeId": 7}])
def test_badStarsAre400(userClient, body):
    answer = post(userClient, "/rating", body)
    assert answer.status_code == 400 and answer.get_json()["message"] == "stars must be a whole number from 1 to 5, or null"


def test_aNoteIsCountedInCharactersNotBytes(userClient, useDb):
    # Each cake is one character to Python and MySQL, four bytes in UTF-8 and two units in Qt's UTF-16.
    conn = useDb(fetchone=[VISIBLE])
    full = "🍰" * 2000
    assert post(userClient, "/note", {"recipeId": 7, "text": full}).get_json()["data"] == {"recipeId": 7, "note": full}
    assert conn.cur.statements("INSERT INTO Notes")[0][1] == (UID, 7, full)
    answer = post(userClient, "/note", {"recipeId": 7, "text": "🍰" * 2001})
    assert answer.status_code == 400 and answer.get_json()["message"] == "a note is at most 2000 characters"


def test_aNoteIsTrimmedAndAnEmptyOneDeletes(userClient, useDb):
    conn = useDb(fetchone=[VISIBLE])
    post(userClient, "/note", {"recipeId": 7, "text": "  less salt \n"})
    assert conn.cur.statements("INSERT INTO Notes")[0][1] == (UID, 7, "less salt")
    conn = useDb(fetchone=[VISIBLE])
    assert post(userClient, "/note", {"recipeId": 7, "text": "  \n "}).get_json()["data"] == {"recipeId": 7, "note": None}
    assert conn.cur.statements("DELETE FROM Notes")[0][1] == (UID, 7)


@pytest.mark.parametrize("text", [None, 5, ["a"]])
def test_aNoteMustBeText(userClient, text):
    assert post(userClient, "/note", {"recipeId": 7, "text": text}).status_code == 400


def test_starsAndNotesNeedARecipeThePersonCanSee(userClient, useDb):
    useDb(fetchone=[None])
    assert post(userClient, "/rating", {"recipeId": 7, "stars": 3}).status_code == 404
    useDb(fetchone=[None])
    assert post(userClient, "/note", {"recipeId": 7, "text": "x"}).status_code == 404


def test_yoursNeedsASession(anonUserClient):
    assert anonUserClient.get(f"{A}/devoured").status_code == 401
    assert post(anonUserClient, "/rating", {"recipeId": 7, "stars": 3}).status_code == 401
