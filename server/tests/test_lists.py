from datetime import datetime

import pytest

from conftest import UID

# The person's row, read under FOR UPDATE before a list is made (so two creates can't both be the fiftieth).
LOCKED = {"UserID": UID}

A = "/api/gluttony"
CUSTOM = {"ListID": 11, "Title": "Weeknights", "Kind": "custom", "OrderIndex": 3}
CRAVINGS = {"ListID": 3, "Title": "Cravings", "Kind": "cravings", "OrderIndex": 0}
VISIBLE = {"RecipeID": 7, "RemovedAt": None, "ImagePath": None}
TILE = {"RecipeID": 7, "Kind": "food", "Title": "Cheese Toast", "Course": "main", "Cuisine": None,
        "TotalMinutes": 10, "TimeFrom": "rule", "Difficulty": 1, "ImagePath": None, "Source": "mealdb",
        "RemovedAt": None}


def post(client, path, body):
    return client.post(f"{A}{path}", json=body)


def test_theListsComeCravingsFirst(userClient, useDb):
    conn = useDb(fetchall=[[dict(CRAVINGS, Count=2), dict(CUSTOM, Count=0)]])
    data = userClient.get(f"{A}/lists").get_json()["data"]
    assert data == [{"id": 3, "title": "Cravings", "kind": "cravings", "count": 2},
                    {"id": 11, "title": "Weeknights", "kind": "custom", "count": 0}]
    sql, params = conn.cur.executed[0]
    assert "WHERE l.UserID = %s" in sql and "ORDER BY l.Kind = 'custom', l.OrderIndex, l.ListID" in sql
    assert params == (UID,)


def test_aNewListGoesLastAndIsTrimmed(userClient, useDb):
    conn = useDb(fetchone=[LOCKED, {"n": 3, "top": 2}], lastrowids={"Lists": [12]})
    answer = post(userClient, "/lists/create", {"title": "  Weeknights  "}).get_json()
    assert answer == {"status": "ok", "data": {"id": 12, "title": "Weeknights", "kind": "custom", "count": 0}}
    assert conn.cur.executed[0] == ("SELECT UserID FROM Users WHERE UserID = %s FOR UPDATE", (UID,))
    assert conn.cur.statements("INSERT INTO Lists")[0][1] == (UID, "Weeknights", 3)
    assert conn.commits == 1


def test_aCustomListLeavesCravingsOfNull(userClient, useDb):
    # CravingsOf is the user's id only on Cravings; the unique key then allows any number of custom lists.
    conn = useDb(fetchone=[LOCKED, {"n": 1, "top": 0}], lastrowids={"Lists": [12]})
    post(userClient, "/lists/create", {"title": "Weeknights"})
    sql = conn.cur.statements("INSERT INTO Lists")[0][0]
    assert "CravingsOf" not in sql and "'custom'" in sql


def test_aTitleOfSixtyIsFine(userClient, useDb):
    useDb(fetchone=[LOCKED, {"n": 1, "top": 0}], lastrowids={"Lists": [12]})
    assert post(userClient, "/lists/create", {"title": "x" * 60}).status_code == 200


@pytest.mark.parametrize("title", ["", "   ", "x" * 61, 5, None, ["a"]])
def test_aBadTitleIs400BeforeAnyQuery(userClient, title):
    # No database installed: a refusal must come before any query.
    answer = post(userClient, "/lists/create", {"title": title})
    assert answer.status_code == 400 and answer.get_json()["message"] == "a list title is 1 to 60 characters"


def test_theFiftyFirstListIsRefused(userClient, useDb):
    conn = useDb(fetchone=[LOCKED, {"n": 50, "top": 49}])
    answer = post(userClient, "/lists/create", {"title": "One more"})
    assert answer.status_code == 400 and answer.get_json()["message"] == "you can have at most 50 lists"
    assert not conn.cur.statements("INSERT INTO Lists") and conn.commits == 0


def test_aListIsRenamed(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, {"n": 4}])
    answer = post(userClient, "/lists/rename", {"id": 11, "title": "Fridays"}).get_json()
    assert answer["data"] == {"id": 11, "title": "Fridays", "kind": "custom", "count": 4}
    assert conn.cur.statements("SELECT ListID, Title, Kind, OrderIndex FROM Lists")[0][1] == (11, UID)
    assert conn.cur.statements("UPDATE Lists SET Title")[0][1] == ("Fridays", 11, UID)


@pytest.mark.parametrize("route, body, message", [
    ("/lists/rename", {"id": 3, "title": "Wants"}, "Cravings can't be renamed"),
    ("/lists/delete", {"id": 3}, "Cravings can't be deleted"),
    ("/lists/reorder", {"id": 3, "after": None}, "Cravings stays first"),
])
def test_cravingsStaysPut(userClient, useDb, route, body, message):
    conn = useDb(fetchone=[CRAVINGS])
    answer = post(userClient, route, body)
    assert answer.status_code == 400 and answer.get_json()["message"] == message
    assert conn.commits == 0


@pytest.mark.parametrize("route, body", [
    ("/lists/rename", {"id": 99, "title": "Mine now"}), ("/lists/delete", {"id": 99}),
    ("/lists/reorder", {"id": 99, "after": None}), ("/lists/items/add", {"listId": 99, "recipeId": 7}),
    ("/lists/items/remove", {"listId": 99, "recipeId": 7}),
    ("/lists/items/reorder", {"listId": 99, "recipeId": 7, "after": None}),
])
def test_someoneElsesListIs404(userClient, useDb, route, body):
    conn = useDb(fetchone=[None])
    answer = post(userClient, route, body)
    assert answer.status_code == 404 and answer.get_json()["message"] == "no such list"
    lookup = [p for sql, p in conn.cur.executed if sql.startswith("SELECT ListID, Title, Kind, OrderIndex FROM Lists")]
    assert lookup[0] == (99, UID)


def test_someoneElsesListsRecipesAre404(userClient, useDb):
    useDb(fetchone=[None])
    assert userClient.get(f"{A}/lists/99/recipes").status_code == 404


@pytest.mark.parametrize("body", [{}, {"id": "11"}, {"id": True}, {"id": 0}, {"id": -3}])
def test_aListIdMustBeAWholeNumber(userClient, body):
    assert post(userClient, "/lists/delete", body).status_code == 400


def test_aListIsDeletedWithItsItems(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM])
    assert post(userClient, "/lists/delete", {"id": 11}).get_json() == {"status": "ok"}
    assert conn.cur.statements("DELETE FROM Lists")[0][1] == (11, UID) and conn.commits == 1


def test_aListMovesAfterAnother(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, dict(CUSTOM, ListID=12, OrderIndex=1)])
    assert post(userClient, "/lists/reorder", {"id": 11, "after": 12}).get_json() == {"status": "ok"}
    shift, place = conn.cur.statements("UPDATE Lists")
    assert "OrderIndex = OrderIndex + 1" in shift[0] and "Kind = 'custom'" in shift[0]
    assert shift[1] == (UID, 1, 11) and place[1] == (2, UID, 11)


def test_aListMovesFirst(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, {"low": 1}])
    post(userClient, "/lists/reorder", {"id": 11, "after": None})
    assert conn.cur.statements("UPDATE Lists")[0][1] == (0, UID, 11)


def test_aListMovedAfterCravingsGoesFirst(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, CRAVINGS, {"low": 1}])
    post(userClient, "/lists/reorder", {"id": 11, "after": 3})
    assert conn.cur.statements("UPDATE Lists")[0][1] == (0, UID, 11)


def test_aListCannotGoAfterItself(userClient):
    assert post(userClient, "/lists/reorder", {"id": 11, "after": 11}).status_code == 400


def test_anAddedRecipeGoesOnTop(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, VISIBLE, {"n": 2, "low": -1, "here": 0}])
    answer = post(userClient, "/lists/items/add", {"listId": 11, "recipeId": 7}).get_json()
    assert answer["data"] == {"listId": 11, "recipeId": 7, "count": 3}
    assert conn.cur.statements("SELECT ListID, Title, Kind, OrderIndex FROM Lists")[0][0].endswith("FOR UPDATE")
    assert conn.cur.statements("INSERT INTO ListItems")[0][1] == (11, 7, -2)
    assert conn.commits == 1


def test_addingTwiceKeepsOneRow(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, VISIBLE, {"n": 2, "low": -1, "here": 1}])
    assert post(userClient, "/lists/items/add", {"listId": 11, "recipeId": 7}).get_json()["data"]["count"] == 2
    assert not conn.cur.statements("INSERT INTO ListItems")


def test_theTwoThousandAndFirstRecipeIsRefused(userClient, useDb):
    useDb(fetchone=[CUSTOM, VISIBLE, {"n": 2000, "low": -1999, "here": 0}])
    answer = post(userClient, "/lists/items/add", {"listId": 11, "recipeId": 7})
    assert answer.status_code == 400 and answer.get_json()["message"] == "a list holds at most 2000 recipes"


def test_aRecipeThePersonCannotSeeIsNotAdded(userClient, useDb):
    useDb(fetchone=[CUSTOM, None])
    answer = post(userClient, "/lists/items/add", {"listId": 11, "recipeId": 70000})
    assert answer.status_code == 404 and answer.get_json()["message"] == "no such recipe"


def test_aRecipeLeavesAList(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, {"n": 1}])
    answer = post(userClient, "/lists/items/remove", {"listId": 11, "recipeId": 7}).get_json()
    assert answer["data"] == {"listId": 11, "recipeId": 7, "count": 1}
    assert conn.cur.statements("DELETE FROM ListItems")[0][1] == (11, 7)


def test_anItemMovesAfterAnother(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, {"OrderIndex": 5}, {"OrderIndex": 2}])
    assert post(userClient, "/lists/items/reorder", {"listId": 11, "recipeId": 7, "after": 8}).status_code == 200
    shift, place = conn.cur.statements("UPDATE ListItems")
    assert shift[1] == (11, 2, 7) and place[1] == (3, 11, 7) and conn.commits == 1


def test_anItemMovesToTheTop(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, {"OrderIndex": 5}, {"low": -4}])
    post(userClient, "/lists/items/reorder", {"listId": 11, "recipeId": 7, "after": None})
    assert conn.cur.statements("UPDATE ListItems")[0][1] == (-5, 11, 7)


def test_aMoveAfterAnItemThatHasGoneIs404(userClient, useDb):
    conn = useDb(fetchone=[CUSTOM, {"OrderIndex": 5}, None])
    answer = post(userClient, "/lists/items/reorder", {"listId": 11, "recipeId": 7, "after": 8})
    assert answer.status_code == 404 and answer.get_json()["message"] == "that recipe is not on this list"
    assert not conn.cur.statements("UPDATE ListItems") and conn.commits == 0


def test_aListStillShowsARemovedRecipe(userClient, useDb):
    gone = dict(TILE, RemovedAt=datetime(2026, 10, 20))
    conn = useDb(fetchone=[CUSTOM, {"n": 1}], fetchall=[[gone], []])
    data = userClient.get(f"{A}/lists/11/recipes?page=1&pageSize=24").get_json()["data"]
    assert data["total"] == 1 and data["list"] == {"id": 11, "title": "Weeknights", "kind": "custom", "count": 1}
    assert data["recipes"][0]["removed"] is True and data["recipes"][0]["craving"] is False
    sql, params = conn.cur.statements("SELECT r.RecipeID")[0]
    assert "RemovedAt IS NULL" not in sql and "ORDER BY li.OrderIndex" in sql and params == (11, 24, 0)


def test_aListsPagesAreChecked(userClient):
    assert userClient.get(f"{A}/lists/11/recipes?pageSize=61").status_code == 400


def test_listsNeedASession(anonUserClient):
    assert anonUserClient.get(f"{A}/lists").status_code == 401
    assert post(anonUserClient, "/lists/create", {"title": "x"}).status_code == 401


def test_theListRules(rules):
    assert rules.listTitle("  a  ") == ("a", None)
    assert rules.listTitle("é" * 60)[0] == "é" * 60
    assert rules.positiveId(7) == 7 and rules.positiveId(True) is None and rules.positiveId(2 ** 31) is None
    assert rules.pageArgs({}) == (1, 24, None)
