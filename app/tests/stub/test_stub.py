"""Checks that the stub serves what docs/api.md promises, so the app is built against the real shapes."""
import json

import pytest

import stub_server as stub

API = stub.API
AUTH = {"X-Session-Token": stub.TOKEN}


@pytest.fixture
def client(monkeypatch):
    for name in ("STUB_NEW_DEVICE", "STUB_DIET", "STUB_HOME_DOWN", "STUB_PICTURES_FAIL", "STUB_SLOW", "STUB_KEPT",
                 "STUB_REMOVED"):
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


CID = "6f1c2b9e-3d4a-4b5c-8d7e-9f0a1b2c3d4e"


def post(client, path, body):
    return client.post(API + path, headers=AUTH, json=body)


def cravingsId(client):
    return get(client, "/lists").get_json()["data"][0]["id"]


def test_aReaderStartsWithCravingsOnly(client):
    assert [(l["title"], l["kind"], l["count"]) for l in get(client, "/lists").get_json()["data"]] == [
        ("Cravings", "cravings", 0)]
    made = client.post(API + "/auth", json={"username": "newbie", "password": "long-enough", "fingerprint": "x",
                                            "key": "stub-key"}).get_json()
    theirs = client.get(API + "/lists", headers={"X-Session-Token": made["token"]}).get_json()["data"]
    assert [l["kind"] for l in theirs] == ["cravings"] and theirs[0]["id"] != cravingsId(client)


def test_listsAreMadeMovedRenamedAndDeleted(client):
    a = post(client, "/lists/create", {"title": "  Weeknights "}).get_json()["data"]
    b = post(client, "/lists/create", {"title": "Parties"}).get_json()["data"]
    assert a == {"id": a["id"], "title": "Weeknights", "kind": "custom", "count": 0}
    assert post(client, "/lists/reorder", {"id": b["id"], "after": None}).status_code == 200
    assert [l["id"] for l in get(client, "/lists").get_json()["data"]][1:] == [b["id"], a["id"]]
    assert post(client, "/lists/reorder", {"id": b["id"], "after": a["id"]}).status_code == 200
    assert [l["id"] for l in get(client, "/lists").get_json()["data"]][1:] == [a["id"], b["id"]]
    assert post(client, "/lists/rename", {"id": a["id"], "title": "Fridays"}).get_json()["data"]["title"] == "Fridays"
    assert post(client, "/lists/delete", {"id": b["id"]}).get_json() == {"status": "ok"}
    assert len(get(client, "/lists").get_json()["data"]) == 2


@pytest.mark.parametrize("route, body, message", [
    ("/lists/rename", {"title": "Wants"}, "Cravings can't be renamed"),
    ("/lists/delete", {}, "Cravings can't be deleted"),
    ("/lists/reorder", {"after": None}, "Cravings stays first"),
])
def test_cravingsStaysPutAsOnTheServer(client, route, body, message):
    answer = post(client, route, dict(body, id=cravingsId(client)))
    assert answer.status_code == 400 and answer.get_json()["message"] == message


@pytest.mark.parametrize("title", ["", "   ", "x" * 61, 5, None])
def test_theStubRefusesABadTitleAsTheServerDoes(client, title):
    answer = post(client, "/lists/create", {"title": title})
    assert answer.status_code == 400 and answer.get_json()["message"] == "a list title is 1 to 60 characters"
    assert post(client, "/lists/create", {"title": "x" * 60}).status_code == 200


def test_theStubRefusesTheFiftyFirstList(client):
    for i in range(49):
        assert post(client, "/lists/create", {"title": f"List {i}"}).status_code == 200
    answer = post(client, "/lists/create", {"title": "One more"})
    assert answer.status_code == 400 and answer.get_json()["message"] == "you can have at most 50 lists"


def test_theStubRefusesTheTwoThousandAndFirstRecipe(client):
    listId = cravingsId(client)
    stub.state["readers"][stub.UID]["lists"][0]["items"] = list(range(10000, 12000))
    answer = post(client, "/lists/items/add", {"listId": listId, "recipeId": 1})
    assert answer.status_code == 400 and answer.get_json()["message"] == "a list holds at most 2000 recipes"


def test_itemsGoOnTopMoveAndLeave(client):
    listId = cravingsId(client)
    for rid in (1, 4, 2):
        post(client, "/lists/items/add", {"listId": listId, "recipeId": rid})
    assert post(client, "/lists/items/add", {"listId": listId, "recipeId": 2}).get_json()["data"]["count"] == 3
    assert ids(get(client, f"/lists/{listId}/recipes")) == [2, 4, 1]
    assert post(client, "/lists/items/reorder", {"listId": listId, "recipeId": 2, "after": 1}).status_code == 200
    assert ids(get(client, f"/lists/{listId}/recipes")) == [4, 1, 2]
    gone = post(client, "/lists/items/reorder", {"listId": listId, "recipeId": 4, "after": 3})
    assert gone.status_code == 404 and gone.get_json()["message"] == "that recipe is not on this list"
    assert post(client, "/lists/items/remove", {"listId": listId, "recipeId": 4}).get_json()["data"]["count"] == 2
    page = get(client, f"/lists/{listId}/recipes?pageSize=1").get_json()["data"]
    assert page["total"] == 2 and len(page["recipes"]) == 1 and page["list"]["kind"] == "cravings"
    assert get(client, f"/lists/{listId}/recipes?pageSize=61").status_code == 400


def test_someoneElsesListIs404InTheStub(client):
    made = client.post(API + "/auth", json={"username": "other", "password": "long-enough", "fingerprint": "x",
                                            "key": "stub-key"}).get_json()
    other = {"X-Session-Token": made["token"]}
    listId = cravingsId(client)
    assert client.get(API + f"/lists/{listId}/recipes", headers=other).status_code == 404
    answer = client.post(API + "/lists/items/add", headers=other, json={"listId": listId, "recipeId": 1})
    assert answer.status_code == 404 and answer.get_json()["message"] == "no such list"


def test_tilesCarryTheFlags(client):
    post(client, "/lists/items/add", {"listId": cravingsId(client), "recipeId": 4})
    post(client, "/devoured/add", {"recipeId": 4, "on": "2026-10-27", "clientId": CID})
    post(client, "/rating", {"recipeId": 4, "stars": 5})
    tile = next(t for t in get(client, "/recipes").get_json()["data"]["recipes"] if t["id"] == 4)
    assert (tile["craving"], tile["devouredCount"], tile["stars"]) == (True, 1, 5)
    other = next(t for t in get(client, "/recipes").get_json()["data"]["recipes"] if t["id"] == 1)
    assert (other["craving"], other["devouredCount"], other["stars"]) == (False, 0, None)
    versions = get(client, "/recipes/2").get_json()["data"]["versions"]
    assert versions[0]["id"] == 1 and versions[0]["craving"] is False


def test_aMarkIsStoredOncePerClientIdAndShowsInMine(client):
    first = post(client, "/devoured/add", {"recipeId": 1, "on": "2026-10-27", "clientId": CID}).get_json()["data"]
    again = post(client, "/devoured/add", {"recipeId": 1, "on": "2026-10-27", "clientId": CID}).get_json()["data"]
    assert first["already"] is False and again == dict(first, already=True) and again["count"] == 1
    post(client, "/note", {"recipeId": 1, "text": "  less salt  "})
    mine = get(client, "/recipes/1").get_json()["data"]["mine"]
    assert mine == {"craving": False, "lists": [], "devoured": [{"id": first["id"], "on": "2026-10-27"}],
                    "stars": None, "note": "less salt"}
    assert post(client, "/devoured/remove", {"id": first["id"]}).get_json()["data"]["count"] == 0
    assert post(client, "/devoured/remove", {"id": first["id"]}).status_code == 404


def test_aClientIdHeldByAnotherAccountIs409AndNeverRevealsTheirMark(client):
    theirs = post(client, "/devoured/add", {"recipeId": 1, "on": "2026-10-27", "clientId": CID}).get_json()["data"]
    made = client.post(API + "/auth", json={"username": "other", "password": "long-enough", "fingerprint": "x",
                                            "key": "stub-key"}).get_json()
    other = {"X-Session-Token": made["token"]}
    mark = {"recipeId": 4, "on": "2026-10-28", "clientId": CID}
    answer = client.post(API + "/devoured/add", headers=other, json=mark)
    assert answer.status_code == 409 and answer.get_json() == {"status": "error", "message": "that clientId is in use"}
    assert client.get(API + "/devoured", headers=other).get_json()["data"]["total"] == 0
    # The first account's mark is untouched, and its own resend is still answered as stored.
    again = post(client, "/devoured/add", {"recipeId": 1, "on": "2026-10-27", "clientId": CID}).get_json()["data"]
    assert again == dict(theirs, already=True)
    # An unknown recipe is still 404 first, as on the server, so the clientId is not given away to a stranger.
    gone = client.post(API + "/devoured/add", headers=other, json=dict(mark, recipeId=999))
    assert gone.status_code == 404 and gone.get_json()["message"] == "no such recipe"


@pytest.mark.parametrize("body, message", [
    ({"on": "2026-02-30"}, "on must be a date (YYYY-MM-DD), not after tomorrow"),
    ({"on": "1899-12-31"}, "on must be a date (YYYY-MM-DD), not after tomorrow"),
    ({"clientId": "abc"}, "clientId must be a UUID"),
    ({"clientId": CID.upper()}, "clientId must be a UUID"),
])
def test_theStubRefusesABadMarkAsTheServerDoes(client, body, message):
    answer = post(client, "/devoured/add", dict({"recipeId": 1, "on": "2026-10-27", "clientId": CID}, **body))
    assert answer.status_code == 400 and answer.get_json()["message"] == message


def test_theStubTakesTomorrowInUtcButNotTheDayAfter(client):
    today = stub.datetime.now(stub.timezone.utc).date()
    tomorrow = (today + stub.timedelta(days=1)).isoformat()
    later = (today + stub.timedelta(days=2)).isoformat()
    assert post(client, "/devoured/add", {"recipeId": 1, "on": tomorrow, "clientId": CID}).status_code == 200
    other = "6f1c2b9e-3d4a-4b5c-8d7e-9f0a1b2c3d4f"
    assert post(client, "/devoured/add", {"recipeId": 1, "on": later, "clientId": other}).status_code == 400


def test_theStubCountsANoteAsTheServerDoes(client):
    full = "🍰" * 2000
    assert post(client, "/note", {"recipeId": 1, "text": full}).get_json()["data"] == {"recipeId": 1, "note": full}
    answer = post(client, "/note", {"recipeId": 1, "text": full + "🍰"})
    assert answer.status_code == 400 and answer.get_json()["message"] == "a note is at most 2000 characters"
    assert post(client, "/note", {"recipeId": 1, "text": "   "}).get_json()["data"] == {"recipeId": 1, "note": None}


@pytest.mark.parametrize("stars", [0, 6, 4.5, True, "4"])
def test_theStubRefusesBadStarsAsTheServerDoes(client, stars):
    answer = post(client, "/rating", {"recipeId": 1, "stars": stars})
    assert answer.status_code == 400 and answer.get_json()["message"] == "stars must be a whole number from 1 to 5, or null"
    assert post(client, "/rating", {"recipeId": 1, "stars": None}).get_json()["data"] == {"recipeId": 1, "stars": None}


def test_theHistoryIsNewestFirstOrByStars(client):
    post(client, "/devoured/add", {"recipeId": 1, "on": "2026-10-01", "clientId": CID})
    post(client, "/devoured/add", {"recipeId": 4, "on": "2026-10-20", "clientId": "6f1c2b9e-3d4a-4b5c-8d7e-9f0a1b2c3d4f"})
    post(client, "/rating", {"recipeId": 1, "stars": 5})
    recent = get(client, "/devoured").get_json()["data"]["recipes"]
    assert [(t["id"], t["on"]) for t in recent] == [(4, "2026-10-20"), (1, "2026-10-01")]
    assert ids(get(client, "/devoured?sort=stars")) == [1, 4]
    assert get(client, "/devoured?sort=best").status_code == 400


def test_aRemovedRecipeIsHiddenExceptFromItsSaver(client, monkeypatch):
    monkeypatch.setenv("STUB_REMOVED", "1")
    stub.reset()
    assert 1 not in ids(get(client, "/recipes?profile=off"))
    assert get(client, "/recipes/1").status_code == 404
    assert get(client, "/images/1").status_code == 404
    assert [v["id"] for v in get(client, "/recipes/2").get_json()["data"]["versions"]] == []
    stub.state["readers"][stub.UID]["notes"][1] = "kept"
    detail = get(client, "/recipes/1").get_json()["data"]
    assert detail["removed"] is True
    post(client, "/lists/items/add", {"listId": cravingsId(client), "recipeId": 1})
    assert get(client, f"/lists/{cravingsId(client)}/recipes").get_json()["data"]["recipes"][0]["removed"] is True
    assert 1 not in ids(get(client, "/recipes?profile=off"))


def test_aRemovedRecipesPictureAnswersOnlyItsSaver(client, monkeypatch, tmp_path):
    fixture = json.loads((stub.HERE / "fixture" / "recipes.json").read_text(encoding="utf-8"))
    (tmp_path / "recipes.json").write_text(json.dumps(fixture), encoding="utf-8")
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "1.jpg").write_bytes(b"\xff\xd8image")
    monkeypatch.setenv("STUB_SNAPSHOT", str(tmp_path))
    monkeypatch.setenv("STUB_REMOVED", "1")
    stub.reset()
    assert get(client, "/images/1").status_code == 404
    assert post(client, "/note", {"recipeId": 1, "text": "kept"}).status_code == 404
    stub.state["readers"][stub.UID]["notes"][1] = "kept"
    assert get(client, "/images/1").data == b"\xff\xd8image"
    # A star alone does not keep a removed recipe (spec section 3); unkeeping it closes the picture again.
    del stub.state["readers"][stub.UID]["notes"][1]
    stub.state["readers"][stub.UID]["ratings"][1] = 5
    assert get(client, "/images/1").status_code == 404


def test_aRemovedRecipeIsLeftOutOfTheFilterCounts(client, monkeypatch):
    before = get(client, "/filters").get_json()["data"]
    monkeypatch.setenv("STUB_REMOVED", "1")
    stub.reset()
    after = get(client, "/filters").get_json()["data"]
    assert {"value": "food", "count": 3} in before["kinds"] and {"value": "food", "count": 2} in after["kinds"]


def test_homeHasTheRowsAndSkipsWhatWasJustDevoured(client):
    first = get(client, "/home?tz=UTC").get_json()["data"]
    assert first["cravings"] == [] and first["again"] == []
    pick = first["pick"]["id"]
    today = first["date"]
    post(client, "/devoured/add", {"recipeId": pick, "on": today, "clientId": CID})
    post(client, "/lists/items/add", {"listId": cravingsId(client), "recipeId": pick})
    data = get(client, "/home?tz=UTC").get_json()["data"]
    assert (data["pick"] or {}).get("id") != pick and pick not in [t["id"] for t in data["picks"]]
    assert [t["id"] for t in data["again"]] == [pick] and data["again"][0]["devouredCount"] == 1
    assert [t["id"] for t in data["cravings"]] == [pick] and data["cravings"][0]["craving"] is True


def test_thirtyOneDaysAgoIsBackOnHome(client):
    day = get(client, "/home?tz=UTC").get_json()["data"]["date"]
    pick = get(client, "/home?tz=UTC").get_json()["data"]["pick"]["id"]
    old = (stub.date.fromisoformat(day) - stub.timedelta(days=30)).isoformat()
    post(client, "/devoured/add", {"recipeId": pick, "on": old, "clientId": CID})
    assert get(client, "/home?tz=UTC").get_json()["data"]["pick"]["id"] == pick
    recent = (stub.date.fromisoformat(day) - stub.timedelta(days=29)).isoformat()
    post(client, "/devoured/add", {"recipeId": pick, "on": recent, "clientId": "6f1c2b9e-3d4a-4b5c-8d7e-9f0a1b2c3d4f"})
    assert (get(client, "/home?tz=UTC").get_json()["data"]["pick"] or {}).get("id") != pick


def test_homeRefusesAProfileThatIsNeitherOnNorOff(client):
    answer = get(client, "/home?profile=maybe")
    assert answer.status_code == 400 and answer.get_json()["message"] == "profile must be on or off"


def test_stubKeptSeedsSomethingToShow(client, monkeypatch):
    monkeypatch.setenv("STUB_KEPT", "1")
    stub.reset()
    shown = get(client, "/lists").get_json()["data"]
    assert [(l["kind"], l["count"]) for l in shown] == [("cravings", 2), ("custom", 1)]
    assert get(client, "/devoured").get_json()["data"]["total"] == 1
    assert get(client, "/recipes/1").get_json()["data"]["mine"]["stars"] == 4


import time


def post(client, path, body):
    return client.post(API + path, json=body, headers=AUTH)


def batch(client, ops):
    answer = post(client, "/sync/batch", {"ops": ops})
    assert answer.status_code == 200, answer.get_json()
    return answer.get_json()["data"]["results"]


HOUR_AGO = "2000-01-01T00:00:00.000Z"
LATER = "2099-01-01T00:00:00.000Z"
QUEUED_MARK = "11111111-2222-4333-8444-555555555555"


def test_theStubAppliesABatchAndStoresAMarkOnce(client):
    ops = [{"op": "devoured", "recipeId": 1, "on": "2026-10-28", "clientId": QUEUED_MARK, "at": HOUR_AGO},
           {"op": "stars", "recipeId": 1, "stars": 3, "at": HOUR_AGO},
           {"op": "note", "recipeId": 1, "text": " less salt ", "at": HOUR_AGO}]
    first = batch(client, ops)
    assert [r["result"] for r in first] == ["applied", "applied", "applied"]
    assert first[0]["count"] == 1 and first[1] == {"result": "applied", "recipeId": 1, "stars": 3}
    assert first[2] == {"result": "applied", "recipeId": 1, "note": "less salt"}
    again = batch(client, ops)
    assert [r["result"] for r in again] == ["already", "already", "already"] and again[0]["id"] == first[0]["id"]
    mine = get(client, "/recipes/1").get_json()["data"]["mine"]
    assert mine["stars"] == 3 and mine["note"] == "less salt" and len(mine["devoured"]) == 1


def test_theStubKeepsTheNewestChange(client):
    post(client, "/rating", {"recipeId": 1, "stars": 5})
    assert batch(client, [{"op": "stars", "recipeId": 1, "stars": 2, "at": HOUR_AGO}]) == [
        {"result": "already", "recipeId": 1, "stars": 5}]
    post(client, "/rating", {"recipeId": 1, "stars": None})
    assert batch(client, [{"op": "stars", "recipeId": 1, "stars": 2, "at": HOUR_AGO}]) == [
        {"result": "already", "recipeId": 1, "stars": None}]
    post(client, "/note", {"recipeId": 1, "text": ""})
    assert batch(client, [{"op": "note", "recipeId": 1, "text": "old", "at": HOUR_AGO}]) == [
        {"result": "already", "recipeId": 1, "note": None}]
    # A clock ahead of the stub's counts as now: newer than what was stored a moment ago.
    time.sleep(0.01)
    assert batch(client, [{"op": "stars", "recipeId": 1, "stars": 2, "at": LATER}])[0]["result"] == "applied"


def test_theStubRefusesBadChangesAsTheServerDoes(client):
    answered = batch(client, [{"op": "bake", "recipeId": 1, "at": HOUR_AGO},
                              {"op": "stars", "recipeId": 1, "stars": 9, "at": HOUR_AGO},
                              {"op": "stars", "recipeId": 1, "stars": 2, "at": "soon"},
                              {"op": "note", "recipeId": 999, "text": "x", "at": HOUR_AGO},
                              {"op": "devoured", "recipeId": 1, "on": "2026-10-28", "clientId": "x", "at": HOUR_AGO}])
    assert [r.get("message") for r in answered] == [
        "op must be devoured, stars or note", "stars must be a whole number from 1 to 5, or null",
        "at must be a UTC time (YYYY-MM-DDTHH:MM:SS.sssZ)", "no such recipe", "clientId must be a UUID"]
    for ops in ([], [{}] * 501):
        answer = post(client, "/sync/batch", {"ops": ops})
        assert answer.status_code == 400 and answer.get_json()["message"] == "ops must be a list of 1 to 500 changes"


def test_theStubsManifestHasTheListsAndTheirRecipes(client, monkeypatch):
    monkeypatch.setenv("STUB_KEPT", "1")
    stub.reset()
    data = get(client, "/saved/manifest?extra=3").get_json()["data"]
    assert data["lists"][0]["kind"] == "cravings" and data["lists"][0]["recipeIds"] == [1, 4]
    assert data["lists"][1] == {"id": data["lists"][1]["id"], "title": "Weeknights", "kind": "custom", "recipeIds": [2]}
    assert [r["id"] for r in data["recipes"]] == [1, 2, 3, 4]
    assert all(r["updatedAt"] and r["removed"] is False for r in data["recipes"])
    bad = get(client, "/saved/manifest?extra=a")
    assert bad.status_code == 400 and bad.get_json()["message"] == "extra must be up to 200 recipe ids, comma separated"


def test_aRemovedExtraTheReaderDoesNotKeepIsLeftOut(client, monkeypatch):
    monkeypatch.setenv("STUB_REMOVED", "3")
    stub.reset()
    assert get(client, "/saved/manifest?extra=3").get_json()["data"]["recipes"] == []

def test_theStubTakesOneClockForTheWholeBatch(client, monkeypatch):
    # Every reading of the clock is a millisecond later than the last. Both changes are ahead of it, so both must
    # clamp to the batch's one now: the first is applied and the second ties with it, as on the server.
    ticks = iter(range(10000))
    monkeypatch.setattr(stub, "nowStamp", lambda: "2026-10-28T00:00:%02d.%03dZ" % divmod(next(ticks), 1000))
    answered = batch(client, [{"op": "stars", "recipeId": 1, "stars": 2, "at": LATER},
                              {"op": "stars", "recipeId": 1, "stars": 4, "at": LATER}])
    assert [r["result"] for r in answered] == ["applied", "already"]
    assert answered[1]["stars"] == 2
    assert get(client, "/recipes/1").get_json()["data"]["mine"]["stars"] == 2
