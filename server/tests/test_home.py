from datetime import datetime, timezone

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
