from datetime import date, datetime

from conftest import UID

A = "/api/gluttony"
TILE = {"RecipeID": 7, "Kind": "food", "Title": "Cheese Toast", "Course": "main", "Cuisine": None,
        "TotalMinutes": 10, "TimeFrom": "rule", "Difficulty": 1, "ImagePath": "0123456789abcdef0123.jpg",
        "Source": "mealdb"}
DETAIL = dict(TILE, Servings=2, ServingsFrom="source", PrepMinutes=None, CookMinutes=None, DifficultyFrom="rule",
              Alcohol=None, Glass=None, ImageCredit="TheMealDB", VideoUrl=None, SourceUrl="https://x",
              Licence="TheMealDB", Credit="Recipe data and imagery: TheMealDB", Complete=1, DishKey="cheese toast",
              RemovedAt=None)
SIX_EMPTY = [[], [], [], [], [], []]


def flagQueries(conn):
    return [s for s in conn.cur.executed if s[0].startswith("SELECT r.RecipeID, EXISTS")]


def test_flagsComeInOneQueryWhateverThePageSize(readClient, useDb):
    for size in (1, 60):
        rows = [dict(TILE, RecipeID=i) for i in range(1, size + 1)]
        conn = useDb(fetchone=[{"n": size}], fetchall=[[], rows])
        readClient.get(f"{A}/recipes?pageSize=60")
        assert len(flagQueries(conn)) == 1, size
        sql, params = flagQueries(conn)[0]
        assert params[:3] == (UID, UID, UID) and list(params[3:]) == list(range(1, size + 1))


def test_anEmptyPageAsksForNoFlags(readClient, useDb):
    conn = useDb(fetchone=[{"n": 0}], fetchall=[[], []])
    readClient.get(f"{A}/recipes")
    assert flagQueries(conn) == []


def test_flagsSayCravingDevouredAndStars(kept, sessions, useDb):
    useDb(fetchall=[[{"RecipeID": 7, "Craving": 1, "DevouredCount": 3, "Stars": 4}]])
    tiles = [{"id": 7}, {"id": 8}]
    with sessions.database() as (_, cur):
        kept.attachTileFlags(cur, UID, tiles)
    assert tiles[0] == {"id": 7, "craving": True, "devouredCount": 3, "stars": 4}
    assert tiles[1] == {"id": 8, "craving": False, "devouredCount": 0, "stars": None}


def test_aRecipeCarriesWhatIsMine(readClient, useDb):
    useDb(fetchone=[DETAIL, {"Stars": 5, "Note": "less salt"}],
          fetchall=SIX_EMPTY + [[{"ListID": 3, "Kind": "cravings"}, {"ListID": 9, "Kind": "custom"}],
                                [{"DevouredID": 41, "MadeOn": date(2026, 10, 27)},
                                 {"DevouredID": 40, "MadeOn": date(2026, 9, 1)}]])
    data = readClient.get(f"{A}/recipes/7").get_json()["data"]
    assert data["removed"] is False
    assert data["mine"] == {"craving": True, "lists": [9], "stars": 5, "note": "less salt",
                            "devoured": [{"id": 41, "on": "2026-10-27"}, {"id": 40, "on": "2026-09-01"}]}


def test_mineIsReadForThisPersonOnly(readClient, useDb):
    conn = useDb(fetchone=[DETAIL], fetchall=SIX_EMPTY)
    readClient.get(f"{A}/recipes/7")
    mine = [p for sql, p in conn.cur.executed if "FROM Devoured WHERE UserID" in sql or "l.UserID = %s" in sql]
    assert mine and all(p[0] == UID for p in mine)


def test_aRemovedRecipeOpensOnlyForSomeoneWhoKeptIt(readClient, useDb):
    removed = dict(DETAIL, RemovedAt=datetime(2026, 10, 20))
    conn = useDb(fetchone=[removed, {"Kept": 0}])
    assert readClient.get(f"{A}/recipes/7").status_code == 404
    kept = conn.cur.statements("SELECT EXISTS (SELECT 1 FROM ListItems")[0]
    assert kept[1] == (UID, 7, UID, 7, UID, 7)
    useDb(fetchone=[removed, {"Kept": 1}], fetchall=SIX_EMPTY)
    answer = readClient.get(f"{A}/recipes/7")
    assert answer.status_code == 200 and answer.get_json()["data"]["removed"] is True


def test_aRecipeInTheCatalogNeedsNoKeptCheck(readClient, useDb):
    conn = useDb(fetchone=[DETAIL], fetchall=SIX_EMPTY)
    assert readClient.get(f"{A}/recipes/7").status_code == 200
    assert not conn.cur.statements("SELECT EXISTS (SELECT 1 FROM ListItems")


def test_aRemovedRecipesPictureFollowsTheSameRule(readClient, useDb, media):
    (media / "thumbs" / "0123456789abcdef0123.jpg").write_bytes(b"\xff\xd8thumb")
    row = {"RecipeID": 7, "RemovedAt": datetime(2026, 10, 20), "ImagePath": "0123456789abcdef0123.jpg"}
    useDb(fetchone=[row, {"Kept": 0}])
    assert readClient.get(f"{A}/thumbs/7").status_code == 404
    useDb(fetchone=[row, {"Kept": 1}])
    assert readClient.get(f"{A}/thumbs/7").data == b"\xff\xd8thumb"


def test_secondsTilesCarryFlagsToo(readClient, useDb):
    versions = [{"RecipeID": 8, "Title": "Cheese on Toast", "Source": "wikibooks", "ImagePath": None}]
    useDb(fetchone=[DETAIL, {}], fetchall=[[], [], [], [], [], versions, [], [],
                                           [{"RecipeID": 8, "Craving": 1, "DevouredCount": 0, "Stars": None}]])
    data = readClient.get(f"{A}/recipes/7").get_json()["data"]
    assert data["versions"] == [{"id": 8, "title": "Cheese on Toast", "source": "wikibooks", "hasImage": False,
                                 "craving": True, "devouredCount": 0, "stars": None}]


def test_savedTilesSayWhetherTheRecipeHasGone(kept):
    assert kept.savedTile(dict(TILE, RemovedAt=None))["removed"] is False
    assert kept.savedTile(dict(TILE, RemovedAt=datetime(2026, 10, 20)))["removed"] is True


def test_isoDateReadsWhatMysqlGives(rules):
    assert rules.isoDate(date(2026, 3, 9)) == "2026-03-09"
    assert rules.isoDate(datetime(2026, 3, 9, 23, 59)) == "2026-03-09"
    assert rules.isoDate(None) is None


def test_aDeletedNoteKeepsNothing(kept):
    # A deleted note is a row with no text (it remembers when it was deleted); it must not keep a removed recipe.
    assert "FROM Notes WHERE UserID = %s AND RecipeID = %s AND Text <> ''" in kept.KEPT_SQL


def test_mineReadsADeletedNoteAsNone(kept):
    from fakes import FakeCursor
    cur = FakeCursor(fetchall=[[], []], fetchone=[{"Stars": None, "Note": None}])
    kept.mineOf(cur, 7, 1)
    assert "NULLIF(Text, '')" in cur.statements("SELECT (SELECT Stars")[0][0]
