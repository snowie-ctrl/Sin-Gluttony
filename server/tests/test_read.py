import pytest

TILE = {"RecipeID": 7, "Kind": "food", "Title": "Cheese Toast", "Course": "main", "Cuisine": None,
        "TotalMinutes": 10, "TimeFrom": "rule", "Difficulty": 1, "ImagePath": "0123456789abcdef0123.jpg",
        "Source": "mealdb"}


def get(client, path):
    return client.get(f"/api/gluttony{path}")


def test_pingAnswers(readClient):
    assert get(readClient, "/ping").get_json() == {"status": "ok"}


def test_recipesAreFilteredCountedAndPaged(readClient, useDb):
    conn = useDb(fetchone=[{"n": 31}], fetchall=[[], [TILE]])
    answer = get(readClient, "/recipes?course=main&pageSize=12&page=2").get_json()
    assert answer["data"]["total"] == 31 and answer["data"]["page"] == 2
    assert answer["data"]["recipes"] == [{"id": 7, "kind": "food", "title": "Cheese Toast", "course": "main",
                                          "cuisine": None, "totalMinutes": 10, "timeFrom": "rule", "difficulty": 1,
                                          "hasImage": True, "source": "mealdb", "craving": False,
                                          "devouredCount": 0, "stars": None}]
    _, count, rows, flags = conn.cur.executed
    assert count[0].startswith("SELECT COUNT(*) AS n FROM Recipes r LEFT JOIN RecipeFacts fa")
    assert "ORDER BY SHA1(CONCAT(r.RecipeID, ':', %s))" in rows[0]
    assert rows[1][-2:] == [12, 12]                         # LIMIT 12 OFFSET 12
    assert flags[0].startswith("SELECT r.RecipeID, EXISTS")


def test_includeFindsChildIngredientsToo(readClient, useDb):
    conn = useDb(fetchall=[[], [{"IngredientID": 1, "ParentID": None}, {"IngredientID": 2, "ParentID": 1}], [TILE]],
                 fetchone=[{"n": 1}])
    get(readClient, "/recipes?include=1")
    assert conn.cur.executed[1][0] == "SELECT IngredientID, ParentID FROM Ingredients"
    assert conn.cur.executed[2][1][-2:] == [1, 2]


@pytest.mark.parametrize("query, words", [
    ("maxMinutes=abc", "maxMinutes"), ("pageSize=100000", "pageSize"), ("difficulty=7", "difficulty"),
    ("avoid=unicorn", "avoid"), ("include=0", "include"), ("sort=best", "sort"),
])
def test_badParametersAre400sThatSayWhy(readClient, query, words):
    # No database is installed: the request must be refused before any query.
    answer = get(readClient, f"/recipes?{query}")
    assert answer.status_code == 400 and words in answer.get_json()["message"]


def test_aRecipeComesWithEverythingAboutIt(readClient, useDb):
    row = dict(TILE, Servings=2, ServingsFrom="source", PrepMinutes=None, CookMinutes=None, DifficultyFrom="rule",
               Alcohol=None, Glass=None, ImageCredit="TheMealDB", VideoUrl=None, SourceUrl="https://x",
               Licence="TheMealDB", Credit="Recipe data and imagery: TheMealDB", Complete=1, DishKey="cheese toast")
    useDb(fetchone=[row], fetchall=[
        [{"Position": 1, "Line": "2 slices bread", "Quantity": 2, "QuantityMax": None, "Unit": "slice",
          "IngredientID": 1, "Name": "bread", "Note": None, "Optional": 0, "GroupHeading": None}],
        [{"Position": 1, "Text": "Toast it.", "GroupHeading": None}],
        [{"Type": "flavour", "Tag": "savoury"}],
        [{"Item": "gluten"}],
        [{"Diet": "vegetarian"}],
        [{"RecipeID": 8, "Title": "Cheese on Toast", "Source": "wikibooks", "ImagePath": None}]])
    data = get(readClient, "/recipes/7").get_json()["data"]
    assert data["ingredients"][0]["name"] == "bread" and data["ingredients"][0]["optional"] is False
    assert data["tags"]["flavour"] == ["savoury"] and data["facts"] == {"complete": True, "contains": ["gluten"],
                                                                      "diets": ["vegetarian"]}
    assert data["versions"] == [{"id": 8, "title": "Cheese on Toast", "source": "wikibooks", "hasImage": False,
                                 "craving": False, "devouredCount": 0, "stars": None}]


def test_aMissingOrRemovedRecipeIs404(readClient, useDb):
    useDb(fetchone=[None])
    assert get(readClient, "/recipes/99").status_code == 404


DETAIL = dict(TILE, Servings=2, ServingsFrom="source", PrepMinutes=None, CookMinutes=None, DifficultyFrom="rule",
              Alcohol=None, Glass=None, ImageCredit=None, VideoUrl=None, SourceUrl="https://example.test/x",
              Licence=None, Credit=None, Complete=1, DishKey="cheese toast", RemovedAt=None, HiddenReason=None,
              Description="A quick supper.")


def test_aHiddenRecipeIs404(readClient, useDb):
    conn = useDb(fetchone=[dict(DETAIL, HiddenReason="small-photo")])
    assert get(readClient, "/recipes/7").status_code == 404
    assert len(conn.cur.executed) == 1


def test_aRecipeHasItsDescriptionAndPerServingNutrition(readClient, useDb):
    from decimal import Decimal
    nutrition = {"Calories": Decimal("420.00"), "ProteinG": Decimal("18.50"), "CarbsG": Decimal("40.00"),
                 "FatG": Decimal("20.00"), "SatFatG": Decimal("6.00"), "FibreG": Decimal("4.00"),
                 "SugarG": Decimal("7.00"), "SodiumMg": Decimal("650.00"), "NutritionFrom": "source", "Flagged": 0}
    conn = useDb(fetchone=[DETAIL, nutrition], fetchall=[[], [], [{"Type": "technique", "Tag": "stirred"}], [], [], []])
    data = get(readClient, "/recipes/7").get_json()["data"]
    assert data["description"] == "A quick supper." and data["tags"]["technique"] == ["stirred"]
    assert data["nutrition"] == {"calories": 420, "proteinG": 18.5, "carbsG": 40, "fatG": 20, "satFatG": 6,
                                 "fibreG": 4, "sugarG": 7, "sodiumMg": 650, "from": "source", "flagged": False}
    sql, params = conn.cur.statements("SELECT Calories")[0]
    assert "FROM RecipeNutrition WHERE RecipeID = %s" in sql and params == (7,)
    assert "NutritionFrom, Flagged" in sql
    versions = conn.cur.statements("SELECT RecipeID, Title, Source, ImagePath FROM Recipes")[0][0]
    assert "RemovedAt IS NULL AND HiddenReason IS NULL" in versions


def test_aRecipeWithoutNutritionSaysNull(readClient, useDb):
    useDb(fetchone=[DETAIL, None], fetchall=[[], [], [], [], [], []])
    data = get(readClient, "/recipes/7").get_json()["data"]
    assert data["nutrition"] is None and data["removed"] is False


def test_filtersCountEveryOption(readClient, useDb):
    useDb(fetchall=[[{"v": "food", "n": 4000}], [{"v": "main", "n": 900}], [{"v": "Japanese", "n": 40}],
                    [{"v": 1, "n": 2000}], [{"Type": "flavour", "v": "sweet", "n": 700},
                                            {"Type": "occasion", "v": "party", "n": 90}],
                    [{"v": "vegan", "n": 300}]])
    data = get(readClient, "/filters").get_json()["data"]
    assert data["kinds"] == [{"value": "food", "count": 4000}]
    assert data["flavours"] == [{"value": "sweet", "count": 700}] and data["occasions"] == [{"value": "party", "count": 90}]
    assert data["diets"] == [{"value": "vegan", "count": 300}]
    assert "peanut" in data["avoid"]


def test_filtersCountOnlyShownRecipes(readClient, useDb):
    conn = useDb(fetchall=[[], [], [], [], [], []])
    get(readClient, "/filters")
    assert len(conn.cur.executed) == 6
    assert all("RemovedAt IS NULL AND" in sql and "HiddenReason IS NULL" in sql for sql, _ in conn.cur.executed)


def test_ingredientSearchForTheIncludeFilter(readClient, useDb):
    useDb(fetchall=[[{"IngredientID": 1, "Name": "cheese"}]])
    assert get(readClient, "/ingredients?q=che").get_json()["data"] == [{"id": 1, "name": "cheese"}]


def test_picturesAreServedFromTheMediaRoot(readClient, useDb, media):
    (media / "images" / "0123456789abcdef0123.jpg").write_bytes(b"\xff\xd8jpeg")
    useDb(fetchone=[{"ImagePath": "0123456789abcdef0123.jpg"}])
    answer = get(readClient, "/images/7")
    assert answer.status_code == 200 and answer.data == b"\xff\xd8jpeg" and answer.mimetype == "image/jpeg"


@pytest.mark.parametrize("gone", [{"HiddenReason": "no-photo"}, {"RemovedAt": "2026-10-20"}])
def test_anUnshownRecipesPictureIs404(readClient, useDb, media, gone):
    (media / "images" / "0123456789abcdef0123.jpg").write_bytes(b"\xff\xd8jpeg")
    row = dict({"RecipeID": 7, "RemovedAt": None, "HiddenReason": None, "ImagePath": "0123456789abcdef0123.jpg"}, **gone)
    conn = useDb(fetchone=[row])
    assert get(readClient, "/images/7").status_code == 404
    assert "HiddenReason" in conn.cur.executed[0][0] and len(conn.cur.executed) == 1


def test_aRecipeWithoutAPictureIs404(readClient, useDb):
    useDb(fetchone=[{"ImagePath": None}])
    assert get(readClient, "/thumbs/7").status_code == 404
