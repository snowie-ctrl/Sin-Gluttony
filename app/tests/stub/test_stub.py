"""Checks that the stub serves what docs/api.md promises, so the app is built against the real shapes."""
import json

import pytest

import stub_server as stub

API = stub.API
AUTH = {"X-Session-Token": stub.TOKEN}


@pytest.fixture
def client(monkeypatch):
    for name in ("STUB_NEW_DEVICE", "STUB_DIET", "STUB_HOME_DOWN", "STUB_PICTURES_FAIL", "STUB_SLOW"):
        monkeypatch.delenv(name, raising=False)
    # The four fixture recipes, even once a real snapshot sits in snapshot/, so these checks never depend on it.
    monkeypatch.setenv("STUB_SNAPSHOT", str(stub.HERE / "fixture"))
    stub.reset()
    stub.app.config["TESTING"] = True
    return stub.app.test_client()


def get(client, path):
    return client.get(API + path, headers=AUTH)


def ids(answer):
    return [t["id"] for t in answer.get_json()["data"]["recipes"]]


def test_routesNeedTheTokenButPingDoesNot(client):
    assert client.get(API + "/recipes").status_code == 401
    assert client.get(API + "/ping").get_json() == {"status": "ok"}


def test_aKnownDeviceSignsInAndANewOneDoesNot(client, monkeypatch):
    answer = client.post(API + "/device/identify", json={"fingerprint": "x"}).get_json()
    assert answer == {"status": "ok", "UID": 7, "username": "stub", "token": "stub"}
    monkeypatch.setenv("STUB_NEW_DEVICE", "1")
    stub.reset()
    assert client.post(API + "/device/identify", json={"fingerprint": "x"}).get_json() == {"status": "new"}


def test_signInSignUpAndTheirRefusals(client):
    assert client.post(API + "/auth", json={"username": "stub", "password": "nope", "fingerprint": "x"}).status_code == 401
    made = client.post(API + "/auth", json={"username": "newbie", "password": "long-enough", "fingerprint": "x",
                                            "key": "stub-key"}).get_json()
    assert made["status"] == "ok" and made["UID"] >= 100
    wrongKey = client.post(API + "/auth", json={"username": "other", "password": "long-enough", "fingerprint": "x",
                                                "key": "nope"})
    assert wrongKey.status_code == 403 and wrongKey.get_json()["status"] == "invalid_key"
    taken = client.post(API + "/auth", json={"username": "taken", "password": "long-enough", "fingerprint": "x",
                                             "key": "stub-key"})
    assert taken.status_code == 409


def test_filtersNarrowAsTheServerDoes(client):
    assert ids(get(client, "/recipes?kind=drink")) == [3]
    assert sorted(ids(get(client, "/recipes?course=main"))) == [1, 2]
    assert ids(get(client, "/recipes?maxMinutes=30&kind=food")) == [4]
    assert ids(get(client, "/recipes?alcohol=alcoholic")) == [3]
    assert ids(get(client, "/recipes?include=301")) == [4]
    assert sorted(ids(get(client, "/recipes?exclude=101"))) == [3, 4]


def test_theSafetyRuleHoldsForTheProfileToo(client, monkeypatch):
    monkeypatch.setenv("STUB_DIET", ";alcohol")
    stub.reset()
    # Recipe 1 is incomplete, so it can never pass an avoid, whatever it lists.
    assert sorted(ids(get(client, "/recipes"))) == [4]
    assert sorted(ids(get(client, "/recipes?profile=off"))) == [1, 2, 3, 4]


def test_anIncompleteRecipeNeverMeetsADietOrAvoidsAnAllergen(client, monkeypatch):
    # Recipe 1 is incomplete and does not list egg, so only the completeness check keeps it out of "avoid egg".
    assert sorted(ids(get(client, "/recipes?avoid=egg"))) == [2, 3]
    monkeypatch.setenv("STUB_DIET", ";egg")
    stub.reset()
    assert sorted(ids(get(client, "/recipes"))) == [2, 3]
    assert sorted(ids(get(client, "/recipes?profile=off"))) == [1, 2, 3, 4]
    # Even if an incomplete recipe claimed a diet (the real server never says so), it still may not meet it.
    monkeypatch.delenv("STUB_DIET")
    stub.reset()
    stub.state["recipes"][1]["facts"] = {"complete": False, "contains": [], "diets": ["vegetarian"]}
    assert 1 not in ids(get(client, "/recipes?diet=vegetarian"))
    assert 1 in ids(get(client, "/recipes?profile=off"))
    assert client.post(API + "/me/diet", headers=AUTH, json={"diets": ["vegetarian"]}).status_code == 200
    assert 1 not in ids(get(client, "/recipes"))


def refusal(client, path):
    answer = get(client, path)
    assert answer.status_code == 400
    return answer.get_json()["message"]


# The stub refuses what server/gluttonyRules.py parseFilters refuses, in its words, so the app meets them here first.
def test_moreThanTenCuisinesIsRefused(client):
    eleven = ",".join(f"Cuisine{i}" for i in range(11))
    assert refusal(client, "/recipes?cuisine=" + eleven) == "cuisine takes up to 10 names of at most 40 characters"
    assert refusal(client, "/recipes?cuisine=" + "x" * 41) == "cuisine takes up to 10 names of at most 40 characters"
    assert get(client, "/recipes?cuisine=" + ",".join(f"Cuisine{i}" for i in range(10))).status_code == 200


def test_aSearchOverAHundredCharactersIsRefused(client):
    assert refusal(client, "/recipes?q=" + "a" * 101) == "q must be at most 100 characters"
    assert get(client, "/recipes?q=" + "a" * 100).status_code == 200


def test_aDifficultyOutsideOneToThreeIsRefused(client):
    for bad in ("0", "4", "1,5", "easy"):
        assert refusal(client, "/recipes?difficulty=" + bad) == "difficulty must be 1, 2 or 3"
    assert get(client, "/recipes?difficulty=1,3").status_code == 200


def test_aPageSizeOutsideOneToSixtyIsRefused(client):
    for bad in ("0", "61", "x"):
        assert refusal(client, "/recipes?pageSize=" + bad) == "pageSize must be a whole number from 1 to 60"
    assert get(client, "/recipes?pageSize=60").status_code == 200


def test_quickestAndSearch(client):
    assert ids(get(client, "/recipes?sort=quickest"))[:2] == [3, 4]
    assert ids(get(client, "/recipes?q=lardons")) == [1]
    assert ids(get(client, "/recipes?q=coq"))[0] in (1, 2)


def test_aRecipeIsServedWholeAndAMissingOneIs404(client):
    detail = get(client, "/recipes/2").get_json()["data"]
    assert detail["ingredients"][0]["quantityMax"] == 3 and detail["steps"][0]["group"] == "For the sauce"
    assert get(client, "/recipes/999").status_code == 404


def test_homeIsAPictureOfFoodToCookAndHoldsForTheDay(client):
    first = get(client, "/home?tz=America/Chicago").get_json()["data"]
    assert first["pick"]["hasImage"] and first["pick"]["course"] in ("main", "breakfast")
    assert get(client, "/home?tz=America/Chicago").get_json()["data"] == first
    assert get(client, "/home?tz=Not/AZone").status_code == 200


def test_homeCanFail(client, monkeypatch):
    monkeypatch.setenv("STUB_HOME_DOWN", "1")
    stub.reset()
    assert get(client, "/home").status_code == 500


def test_randomGivesOneThatFitsOrNull(client):
    assert get(client, "/random?kind=drink").get_json()["data"]["recipe"]["id"] == 3
    assert get(client, "/random?kind=drink&course=shake").get_json()["data"] == {"recipe": None}


def test_filterCountsComeFromTheRecipes(client):
    data = get(client, "/filters").get_json()["data"]
    assert {"value": "food", "count": 3} in data["kinds"] and "peanut" in data["avoid"]


def test_theDietProfileRoundTrips(client):
    saved = client.post(API + "/me/diet", headers=AUTH, json={"diets": ["vegan"], "avoid": ["sesame", "peanut"]})
    assert saved.get_json()["data"] == {"diets": ["vegan"], "avoid": ["peanut", "sesame"]}
    assert get(client, "/me/diet").get_json()["data"] == {"diets": ["vegan"], "avoid": ["peanut", "sesame"]}
    assert client.post(API + "/me/diet", headers=AUTH, json={"diets": ["keto"]}).status_code == 400


def test_picturesComeFromTheSnapshotFolder(client, monkeypatch, tmp_path):
    fixture = json.loads((stub.HERE / "fixture" / "recipes.json").read_text(encoding="utf-8"))
    (tmp_path / "recipes.json").write_text(json.dumps(fixture), encoding="utf-8")
    (tmp_path / "thumbs").mkdir()
    (tmp_path / "thumbs" / "1.jpg").write_bytes(b"\xff\xd8thumb")
    monkeypatch.setenv("STUB_SNAPSHOT", str(tmp_path))
    stub.reset()
    assert get(client, "/thumbs/1").data == b"\xff\xd8thumb"
    assert get(client, "/images/1").status_code == 404
