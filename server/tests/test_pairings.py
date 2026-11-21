"""Pairings on plutus (spec 2026-11-19 part 3, 2.3 and 2.4): POST /pairings stores each recipe's whole set, and
GET /recipes/<id> gives per slot the first 2 that are shown and fit the profile. Every recipe here is made up."""
import pytest


def post(client, body):
    return client.post("/api/gluttony-admin/pairings", json=body)


def pair(slot="side", key="mealdb:2", rank=1, why="same cuisine"):
    return {"slot": slot, "key": key, "rank": rank, "why": why}


def known(*rows):
    """The Recipes rows the route's look-up finds: (RecipeID, source, sourceId)."""
    return [{"RecipeID": rid, "Source": source, "SourceID": sid} for rid, source, sid in rows]


# ---- POST /pairings ----

def test_theRouteNeedsTheToken(anonClient):
    assert post(anonClient, {"items": [{"key": "mealdb:1", "pairings": []}]}).status_code == 401


def test_aSetReplacesTheRecipesWholeSet(client, useDb):
    conn = useDb(fetchall=[known((11, "mealdb", "1"), (12, "mealdb", "2"), (13, "mealdb", "3"))])
    item = {"key": "mealdb:1", "pairings": [pair(), pair("drink", "mealdb:3", 1, "a fresh drink for a rich main")]}
    answer = post(client, {"items": [item]})
    assert answer.status_code == 200
    assert answer.get_json() == {"status": "ok", "stored": ["mealdb:1"], "failed": []}
    look = conn.cur.executed[0]
    assert "FROM Recipes WHERE RemovedAt IS NULL AND (Source, SourceID) IN ((%s, %s), (%s, %s), (%s, %s))" in look[0]
    sqls = [sql for sql, _ in conn.cur.executed]
    delete = sqls.index("DELETE FROM RecipePairings WHERE RecipeID = %s")
    inserts = conn.cur.statements("INSERT INTO RecipePairings")
    assert all(sqls.index(sql) > delete for sql, _ in inserts)
    assert [params for _, params in inserts] == [(11, "side", 1, 12, "same cuisine"),
                                                 (11, "drink", 1, 13, "a fresh drink for a rich main")]
    assert conn.commits == 1


def test_anEmptySetClearsTheOldOne(client, useDb):
    conn = useDb(fetchall=[known((11, "mealdb", "1"))])
    assert post(client, {"items": [{"key": "mealdb:1", "pairings": []}]}).get_json()["stored"] == ["mealdb:1"]
    assert conn.cur.statements("DELETE FROM RecipePairings") and not conn.cur.statements("INSERT INTO RecipePairings")


def test_anUnknownOrRemovedKeyRefusesThatItemOnly(client, useDb):
    conn = useDb(fetchall=[known((12, "mealdb", "2")), known((11, "mealdb", "1")),
                           known((13, "mealdb", "3"), (12, "mealdb", "2"))])
    items = [{"key": "mealdb:1", "pairings": [pair()]},                    # mealdb:1 is unknown
             {"key": "mealdb:1", "pairings": [pair()]},                    # mealdb:2 is unknown
             {"key": "mealdb:3", "pairings": [pair()]}]
    answer = post(client, {"items": items}).get_json()
    assert answer["stored"] == ["mealdb:3"]
    assert answer["failed"] == [{"key": "mealdb:1", "message": "unknown or removed recipe: mealdb:1"},
                                {"key": "mealdb:1", "message": "unknown or removed recipe: mealdb:2"}]
    assert conn.commits == 1


def test_sourceIdsAreComparedExactly(client, useDb):
    useDb(fetchall=[known((11, "mealdb", "abc"), (12, "mealdb", "x"))])
    answer = post(client, {"items": [{"key": "mealdb:ABC", "pairings": [pair(key="mealdb:x")]}]}).get_json()
    assert answer["failed"] == [{"key": "mealdb:ABC", "message": "unknown or removed recipe: mealdb:ABC"}]


@pytest.mark.parametrize("bad, words", [
    ({"key": "nosuchsite:1", "pairings": []}, "key"),
    ({"key": "mealdb:1"}, "pairings"),
    ({"key": "mealdb:1", "pairings": [pair(slot="pudding")]}, "slot"),
    ({"key": "mealdb:1", "pairings": [pair(rank=0)]}, "rank"),
    ({"key": "mealdb:1", "pairings": [pair(rank=9)]}, "rank"),
    ({"key": "mealdb:1", "pairings": [pair(rank=True)]}, "rank"),
    ({"key": "mealdb:1", "pairings": [pair(why="")]}, "why"),
    ({"key": "mealdb:1", "pairings": [pair(why="x" * 121)]}, "why"),
    ({"key": "mealdb:1", "pairings": [pair(key="mealdb")]}, "key"),
    ({"key": "mealdb:1", "pairings": [pair(key="mealdb:1")]}, "itself"),
    ({"key": "mealdb:1", "pairings": [pair(), pair(key="mealdb:3")]}, "twice"),
    ({"key": "mealdb:1", "pairings": ["side"]}, "pairing"),
    ({"key": "mealdb:1", "pairings": [pair(rank=n + 1, slot=s, key=f"mealdb:{100 + 8 * i + n}")
                                      for i, s in enumerate(("side", "sauce", "dessert", "drink", "goes-on", "snack"))
                                      for n in range(8)] + [pair(rank=1, slot="side", key="mealdb:999")]},
     "pairings"),
    ("mealdb:1", "item"),
])
def test_aBadItemIsRefusedWithAReason(client, useDb, bad, words):
    conn = useDb()
    answer = post(client, {"items": [bad]}).get_json()
    assert answer["stored"] == [] and words in answer["failed"][0]["message"]
    assert conn.cur.executed == []


@pytest.mark.parametrize("body", [{}, {"items": []}, {"items": "x"}, {"items": [{}] * 201}])
def test_aBadBodyIsA400(client, body):
    answer = post(client, body)
    assert answer.status_code == 400 and "items" in answer.get_json()["message"]


def test_aDatabaseFailureRollsBackOnlyThatItem(client, useDb):
    conn = useDb(fetchall=[known((11, "mealdb", "1"), (12, "mealdb", "2")),
                           known((13, "mealdb", "3"), (12, "mealdb", "2"))],
                 failOn=lambda sql, params: sql.startswith("INSERT INTO RecipePairings") and params[0] == 11)
    answer = post(client, {"items": [{"key": "mealdb:1", "pairings": [pair()]},
                                     {"key": "mealdb:3", "pairings": [pair()]}]}).get_json()
    assert answer["stored"] == ["mealdb:3"]
    assert answer["failed"] == [{"key": "mealdb:1", "message": "database write failed: RuntimeError"}]
    assert conn.commits == 1 and conn.rollbacks >= 1


# ---- GET /recipes/<id> ----

DETAIL = {"RecipeID": 7, "Kind": "food", "Title": "Stub Curry", "Course": "main", "Cuisine": "Indian",
          "TotalMinutes": 40, "TimeFrom": "source", "Difficulty": 1, "ImagePath": None, "Source": "bbcgoodfood",
          "Servings": 4, "ServingsFrom": "source", "PrepMinutes": None, "CookMinutes": None, "DifficultyFrom": "rule",
          "Alcohol": None, "Glass": None, "ImageCredit": None, "VideoUrl": None, "SourceUrl": "https://example.test/c",
          "Licence": None, "Credit": None, "Complete": 1, "DishKey": "curry", "RemovedAt": None, "HiddenReason": None,
          "Description": None}


def paired(slot, rank, rid, why="same cuisine", course="side"):
    return {"Slot": slot, "Position": rank, "Why": why, "RecipeID": rid, "Kind": "food", "Title": f"Dish {rid}",
            "Course": course, "Cuisine": "Indian", "TotalMinutes": 15, "TimeFrom": "source", "Difficulty": 1,
            "ImagePath": "0123456789abcdef0123.jpg", "Source": "bbcgoodfood"}


def detail(readClient, useDb, rows, profile=(), query=""):
    """The recipe page with `rows` as the pairings query's answer; the profile query answers `profile`."""
    queued = [[], [], [], [], [], []]                       # ingredients, steps, tags, contains, diets, versions
    if query != "?profile=off":
        queued.append(list(profile))
    queued.append(rows)
    conn = useDb(fetchone=[DETAIL, None], fetchall=queued)
    answer = readClient.get(f"/api/gluttony/recipes/7{query}")
    return answer, conn


def pairingsSql(conn):
    return next((sql, params) for sql, params in conn.cur.executed if "FROM RecipePairings" in sql)


def test_pairingsComePerSlotInSlotOrderTwoAtMost(readClient, useDb):
    rows = [paired("drink", 1, 30, "a fresh drink for a rich main", "cocktail"),
            paired("side", 1, 20), paired("side", 2, 21), paired("side", 3, 22), paired("sauce", 2, 25)]
    answer, conn = detail(readClient, useDb, rows)
    data = answer.get_json()["data"]
    assert [p["slot"] for p in data["pairings"]] == ["side", "sauce", "drink"]
    assert [t["id"] for t in data["pairings"][0]["items"]] == [20, 21]
    first = data["pairings"][0]["items"][0]
    assert first == {"id": 20, "kind": "food", "title": "Dish 20", "course": "side", "cuisine": "Indian",
                     "totalMinutes": 15, "timeFrom": "source", "difficulty": 1, "hasImage": True,
                     "source": "bbcgoodfood", "why": "same cuisine", "craving": False, "devouredCount": 0,
                     "stars": None}
    sql, params = pairingsSql(conn)
    assert "JOIN Recipes r ON r.RecipeID = p.PairedID" in sql
    assert "r.RemovedAt IS NULL AND r.HiddenReason IS NULL" in sql
    assert "ORDER BY p.Slot, p.Position" in sql and params[0] == 7


def test_theProfileNarrowsThePairings(readClient, useDb):
    profile = [{"Kind": "diet", "Value": "vegan"}, {"Kind": "avoid", "Value": "peanut"}]
    answer, conn = detail(readClient, useDb, [], profile)
    assert answer.get_json()["data"]["pairings"] == []
    sql, params = pairingsSql(conn)
    assert "fa.Complete = 1" in sql and "d.Diet = %s" in sql and "c.Item IN (%s)" in sql
    assert params == [7, "vegan", "peanut"]
    assert any("FROM UserDiets" in s for s, _ in conn.cur.executed)


def test_profileOffReadsNoProfile(readClient, useDb):
    answer, conn = detail(readClient, useDb, [paired("side", 1, 20)], query="?profile=off")
    assert answer.status_code == 200 and len(answer.get_json()["data"]["pairings"]) == 1
    assert not any("FROM UserDiets" in s for s, _ in conn.cur.executed)
    sql, params = pairingsSql(conn)
    assert "fa.Complete" not in sql and params == [7]


def test_aBadProfileIsA400BeforeAnyQuery(readClient):
    answer = readClient.get("/api/gluttony/recipes/7?profile=maybe")
    assert answer.status_code == 400 and "profile" in answer.get_json()["message"]


def test_noPairingsIsAnEmptyList(readClient, useDb):
    answer, _ = detail(readClient, useDb, [])
    assert answer.get_json()["data"]["pairings"] == []


def test_aSlotPlutusDoesNotKnowIsLeftOut(readClient, useDb):
    answer, _ = detail(readClient, useDb, [paired("pudding", 1, 20), paired("side", 1, 21)])
    assert [p["slot"] for p in answer.get_json()["data"]["pairings"]] == ["side"]
