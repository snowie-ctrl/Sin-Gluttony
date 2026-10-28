from conftest import UID

A = "/api/gluttony"


def test_theProfileIsReadBack(userClient, useDb):
    useDb(fetchall=[[{"Kind": "diet", "Value": "vegetarian"}, {"Kind": "avoid", "Value": "peanut"}]])
    assert userClient.get(f"{A}/me/diet").get_json() == {"status": "ok",
                                                         "data": {"diets": ["vegetarian"], "avoid": ["peanut"]}}


def test_savingReplacesTheProfileInOneTransaction(userClient, useDb):
    conn = useDb()
    answer = userClient.post(f"{A}/me/diet", json={"diets": ["vegan"], "avoid": ["sesame", "peanut"]}).get_json()
    assert answer == {"status": "ok", "data": {"diets": ["vegan"], "avoid": ["peanut", "sesame"]}}
    assert conn.cur.statements("DELETE FROM UserDiets")[0][1] == (UID,)
    assert conn.cur.statements("DELETE FROM UserAvoids")[0][1] == (UID,)
    assert [p for _, p in conn.cur.statements("INSERT INTO UserAvoids")] == [(UID, "peanut"), (UID, "sesame")]
    assert conn.commits == 1


def test_anUnknownWordIs400BeforeAnyQuery(userClient):
    answer = userClient.post(f"{A}/me/diet", json={"diets": ["keto"]})
    assert answer.status_code == 400 and answer.get_json()["message"] == "unknown diet: keto"


def test_theProfileNeedsASession(anonUserClient):
    assert anonUserClient.get(f"{A}/me/diet").status_code == 401


def test_recipesAddTheSavedProfile(readClient, useDb):
    conn = useDb(fetchall=[[{"Kind": "diet", "Value": "vegetarian"}], []], fetchone=[{"n": 0}])
    readClient.get(f"{A}/recipes?kind=food")
    profile, count, rows = conn.cur.executed
    assert "FROM UserDiets" in profile[0] and profile[1] == (UID, UID)
    assert "fa.Complete = 1" in count[0] and "vegetarian" in count[1]


def test_profileOffSkipsTheProfileQuery(readClient, useDb):
    conn = useDb(fetchall=[[]], fetchone=[{"n": 0}])
    readClient.get(f"{A}/recipes?kind=food&profile=off")
    assert not any("UserDiets" in sql for sql, _ in conn.cur.executed)
