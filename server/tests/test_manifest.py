from datetime import datetime

from conftest import UID

A = "/api/gluttony"
LISTS = [{"ListID": 3, "Title": "Cravings", "Kind": "cravings"}, {"ListID": 11, "Title": "Weeknights", "Kind": "custom"}]
ITEMS = [{"ListID": 3, "RecipeID": 7}, {"ListID": 3, "RecipeID": 2}, {"ListID": 11, "RecipeID": 2}]
CHANGED = datetime(2026, 10, 20, 8, 30, 15)


def recipeRow(rid, removed=False):
    return {"RecipeID": rid, "UpdatedAt": CHANGED, "RemovedAt": CHANGED if removed else None}


def test_theManifestHoldsEveryListInOrderAndEachRecipeOnce(userClient, useDb):
    conn = useDb(fetchall=[LISTS, ITEMS, [recipeRow(2), recipeRow(7)]])
    data = userClient.get(f"{A}/saved/manifest").get_json()["data"]
    assert data["lists"] == [{"id": 3, "title": "Cravings", "kind": "cravings", "recipeIds": [7, 2]},
                             {"id": 11, "title": "Weeknights", "kind": "custom", "recipeIds": [2]}]
    assert data["recipes"] == [{"id": 2, "updatedAt": "2026-10-20T08:30:15", "removed": False},
                               {"id": 7, "updatedAt": "2026-10-20T08:30:15", "removed": False}]
    lists, items, recipes = (conn.cur.statements(prefix)[0] for prefix in
                             ("SELECT ListID, Title, Kind", "SELECT li.ListID", "SELECT RecipeID, UpdatedAt"))
    assert lists[1] == (UID,) and "ORDER BY Kind = 'custom', OrderIndex, ListID" in lists[0]
    assert items[1] == (UID,) and "ORDER BY li.ListID, li.OrderIndex, li.AddedAt DESC, li.RecipeID" in items[0]
    assert recipes[1] == (2, 7)


def test_cookModeRecipesComeBesideTheListedOnes(userClient, useDb):
    conn = useDb(fetchall=[LISTS, ITEMS, [recipeRow(2), recipeRow(7), recipeRow(9)]])
    data = userClient.get(f"{A}/saved/manifest?extra=9,7").get_json()["data"]
    assert [r["id"] for r in data["recipes"]] == [2, 7, 9]
    assert conn.cur.statements("SELECT RecipeID, UpdatedAt")[0][1] == (2, 7, 9)


def test_aRemovedRecipeStaysForItsSaverButAnExtraOneTheyNoLongerKeepGoes(userClient, useDb):
    # 7 is on a list: still theirs. 9 was only opened in cook mode, and its source removed it: no longer theirs.
    # 12 was opened in cook mode and devoured, so it is kept (keptBy) and stays.
    useDb(fetchall=[LISTS, ITEMS, [recipeRow(2), recipeRow(7, removed=True), recipeRow(9, removed=True),
                                   recipeRow(12, removed=True)]],
          fetchone=[{"Kept": 0}, {"Kept": 1}])
    data = userClient.get(f"{A}/saved/manifest?extra=9,12").get_json()["data"]
    assert [(r["id"], r["removed"]) for r in data["recipes"]] == [(2, False), (7, True), (12, True)]


def test_nothingKeptAsksNothingMore(userClient, useDb):
    conn = useDb(fetchall=[[{"ListID": 3, "Title": "Cravings", "Kind": "cravings"}], []])
    data = userClient.get(f"{A}/saved/manifest").get_json()["data"]
    assert data == {"lists": [{"id": 3, "title": "Cravings", "kind": "cravings", "recipeIds": []}], "recipes": []}
    assert not conn.cur.statements("SELECT RecipeID, UpdatedAt")


def test_badExtraIs400(userClient):
    answer = userClient.get(f"{A}/saved/manifest?extra=a,b")
    assert answer.status_code == 400
    assert answer.get_json()["message"] == "extra must be up to 200 recipe ids, comma separated"


def test_theManifestNeedsASession(anonUserClient):
    assert anonUserClient.get(f"{A}/saved/manifest").status_code == 401
