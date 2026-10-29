from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import UID

A = "/api/gluttony"
TILE = {"RecipeID": 7, "Kind": "food", "Title": "Cheese Toast", "Course": "main", "Cuisine": None,
        "TotalMinutes": 10, "TimeFrom": "rule", "Difficulty": 1, "ImagePath": "0123456789abcdef0123.jpg",
        "Source": "mealdb"}


def tileOf(rid, title):
    return dict(TILE, RecipeID=rid, Title=title)


def test_localDateIsTheViewersDay(rules):
    late = datetime(2026, 10, 28, 3, 30, tzinfo=timezone.utc)       # 22:30 the day before in Chicago
    assert rules.localDate("America/Chicago", late) == "2026-10-27"
    assert rules.localDate("Asia/Tokyo", late) == "2026-10-28"


@pytest.mark.parametrize("tz", ["", "Not/AZone", "../etc", "W. Europe Standard Time", "America"])
def test_anUnknownTimeZoneMeansUtc(rules, tz):
    late = datetime(2026, 10, 28, 3, 30, tzinfo=timezone.utc)
    assert rules.localDate(tz, late) == "2026-10-28"


def test_homeOrderHashesRecipeAccountAndDay(rules):
    sql, params = rules.homeOrder(7, "2026-10-27")
    assert sql == "SHA1(CONCAT(r.RecipeID, ':', %s, ':', %s)), r.RecipeID" and params == [7, "2026-10-27"]


def test_homeIsAPickAndEightMore(readClient, useDb):
    rows = [tileOf(i, f"Dish {i}") for i in range(1, 10)]
    conn = useDb(fetchall=[[], rows])
    data = readClient.get(f"{A}/home?tz=America/Chicago").get_json()["data"]
    assert data["pick"]["id"] == 1 and [t["id"] for t in data["picks"]] == list(range(2, 10))
    sql, params = conn.cur.executed[1]
    assert "r.Kind = %s" in sql and "r.Course IN (%s, %s)" in sql and "r.ImagePath IS NOT NULL" in sql
    assert "ORDER BY SHA1(CONCAT(r.RecipeID, ':', %s, ':', %s))" in sql
    assert params[:3] == ["food", "main", "breakfast"] and params[-3:] == [UID, data["date"], 9]


def test_aProfileThatRulesEverythingOutGivesAnEmptyHome(readClient, useDb):
    profile = [{"Kind": "diet", "Value": "vegan"}] + [{"Kind": "avoid", "Value": v} for v in ("gluten", "soy", "peanut")]
    conn = useDb(fetchall=[profile, []])
    answer = readClient.get(f"{A}/home?tz=UTC")
    assert answer.status_code == 200
    data = answer.get_json()["data"]
    assert data["pick"] is None and data["picks"] == []
    assert "fa.Complete = 1" in conn.cur.executed[1][0]


def test_homeCanLeaveTheProfileOut(readClient, useDb):
    conn = useDb(fetchall=[[TILE]])
    readClient.get(f"{A}/home?tz=UTC&profile=off")
    assert not any("UserDiets" in sql for sql, _ in conn.cur.executed)
    assert readClient.get(f"{A}/home?profile=sometimes").status_code == 400


def test_goOnThenIsOneRandomRecipeThatFits(readClient, useDb):
    conn = useDb(fetchall=[[]], fetchone=[TILE])
    data = readClient.get(f"{A}/random?kind=food").get_json()["data"]
    assert data == {"recipe": {"id": 7, "kind": "food", "title": "Cheese Toast", "course": "main", "cuisine": None,
                               "totalMinutes": 10, "timeFrom": "rule", "difficulty": 1, "hasImage": True,
                               "source": "mealdb", "craving": False, "devouredCount": 0, "stars": None}}
    assert conn.cur.executed[1][0].endswith("ORDER BY RAND() LIMIT 1")


def test_goOnThenWithNothingThatFitsSaysNull(readClient, useDb):
    useDb(fetchall=[[]], fetchone=[None])
    assert readClient.get(f"{A}/random").get_json() == {"status": "ok", "data": {"recipe": None}}


def test_homeAndRandomNeedASession(anonReadClient):
    assert anonReadClient.get(f"{A}/home").status_code == 401
    assert anonReadClient.get(f"{A}/random").status_code == 401


def test_todaysPickSkipsWhatWasDevouredInTheLast30Days(readClient, useDb):
    conn = useDb(fetchall=[[], [tileOf(1, "Dish 1")]])
    day = readClient.get(f"{A}/home?tz=UTC").get_json()["data"]["date"]
    sql, params = conn.cur.executed[1]
    assert ("NOT EXISTS (SELECT 1 FROM Devoured d WHERE d.UserID = %s AND d.RecipeID = r.RecipeID "
            "AND d.MadeOn > %s)") in sql
    cutoff = (date.fromisoformat(day) - timedelta(days=30)).isoformat()
    at = params.index(cutoff)
    assert params[at - 1] == UID


def test_homeHasTheCravingsAndAgainRows(readClient, useDb):
    cravings = [dict(tileOf(5, "Kept"), RemovedAt=None), dict(tileOf(6, "Gone"), RemovedAt=datetime(2026, 10, 1))]
    again = [dict(tileOf(1, "Made"), RemovedAt=None, LastMade=date(2026, 10, 26))]
    useDb(fetchall=[[], [tileOf(1, "Dish 1")], cravings, again,
                    [{"RecipeID": 5, "Craving": 1, "DevouredCount": 0, "Stars": None},
                     {"RecipeID": 1, "Craving": 0, "DevouredCount": 2, "Stars": 4}]])
    data = readClient.get(f"{A}/home?tz=UTC").get_json()["data"]
    assert [t["id"] for t in data["cravings"]] == [5, 6] and data["cravings"][1]["removed"] is True
    assert data["cravings"][0]["craving"] is True
    assert [t["id"] for t in data["again"]] == [1] and data["again"][0]["devouredCount"] == 2
    assert data["pick"]["stars"] == 4


def test_theRowsAreThePersonsOwnAndNotFilteredByTheProfile(readClient, useDb):
    profile = [{"Kind": "diet", "Value": "vegan"}]
    conn = useDb(fetchall=[profile, [], [], []])
    readClient.get(f"{A}/home?tz=UTC")
    rows = [(sql, p) for sql, p in conn.cur.executed if "l.Kind = 'cravings'" in sql or "GROUP BY r.RecipeID" in sql]
    assert len(rows) == 2
    for sql, params in rows:
        assert params == (UID, 12) and "fa.Complete" not in sql and "RemovedAt IS NULL" not in sql


def test_homeAsksAFixedNumberOfQueries(readClient, useDb):
    picks = [tileOf(i, f"Dish {i}") for i in range(1, 10)]
    conn = useDb(fetchall=[[], picks, [dict(t, RemovedAt=None) for t in picks], []])
    readClient.get(f"{A}/home?tz=UTC")
    assert len(conn.cur.executed) == 5
    conn = useDb(fetchall=[[], [], []])
    readClient.get(f"{A}/home?tz=UTC&profile=off")
    assert len(conn.cur.executed) == 3          # picks, Cravings, Again?; nothing to flag
