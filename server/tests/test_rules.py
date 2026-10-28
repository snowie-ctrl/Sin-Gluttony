import pytest
from werkzeug.datastructures import MultiDict

import samples


def test_aGoodRecipeHasNoProblem(rules):
    assert rules.recipeProblem(samples.recipe()) is None


@pytest.mark.parametrize("changes, words", [
    ({"kind": "soup"}, "kind"),
    ({"key": "mealdb:2"}, "key"),
    ({"source": "allrecipes"}, "source"),
    ({"course": "cocktail"}, "course"),
    ({"difficulty": 4}, "difficulty"),
    ({"totalMinutes": True}, "totalMinutes"),
    ({"imagePath": "../../etc/passwd"}, "imagePath"),
    ({"contentHash": "xyz"}, "contentHash"),
    ({"ingredients": []}, "ingredients"),
    ({"steps": [{"text": "  "}]}, "step"),
    ({"tags": [{"type": "flavour", "tag": "umami", "origin": "rule"}]}, "flavour"),
    ({"facts": {"complete": False, "contains": [], "diets": ["vegan"]}}, "incomplete"),
    ({"facts": {"complete": True, "contains": ["plutonium"], "diets": []}}, "contains"),
])
def test_badRecipesSayWhatIsWrong(rules, changes, words):
    problem = rules.recipeProblem(samples.recipe(**changes))
    assert problem and words in problem


def test_aBadIngredientLineIsCaught(rules):
    bad = samples.recipe()
    bad["ingredients"][0]["ingredientId"] = 0
    assert "ingredientId" in rules.recipeProblem(bad)


def test_recipeRowClipsLongText(rules):
    row = rules.recipeRow(samples.recipe(title="x" * 400))
    assert len(row[rules.RECIPE_COLUMNS.index("Title")]) == 255


def test_seedAndMapProblems(rules):
    assert rules.seedProblem([{"name": "cheese", "contains": ["dairy"], "aliases": ["cheese"]},
                              {"name": "cheddar", "parent": "cheese", "aliases": ["cheddar"]}]) is None
    assert "parent" in rules.seedProblem([{"name": "cheddar", "parent": "cheese", "aliases": []}])
    assert "contains" in rules.seedProblem([{"name": "x", "contains": ["plutonium"], "aliases": []}])
    assert rules.mapProblem({"alias": "dragon fruit", "ingredientId": 5}) is None
    assert rules.mapProblem({"alias": "dragon fruit", "create": {"name": "Dragon fruit", "contains": []}}) is None
    assert "one of" in rules.mapProblem({"alias": "x", "ingredientId": 5, "create": {"name": "x"}})
    assert "alias" in rules.mapProblem({"ingredientId": 5})


def test_parseFiltersReadsEveryKind(rules):
    f, problem = rules.parseFilters(MultiDict([
        ("kind", "food"), ("course", "main,side"), ("cuisine", "Japanese"), ("maxMinutes", "30"),
        ("difficulty", "1"), ("difficulty", "2"), ("flavour", "sweet"), ("occasion", "party"),
        ("diet", "vegan"), ("avoid", "peanut,tree-nut"), ("include", "4"), ("exclude", "9"),
        ("q", "cheese toast"), ("page", "2"), ("pageSize", "12")]))
    assert problem is None
    assert f == {"kind": "food", "course": ["main", "side"], "cuisine": ["Japanese"], "maxMinutes": 30,
                 "difficulty": [1, 2], "flavour": ["sweet"], "occasion": ["party"], "diet": ["vegan"],
                 "avoid": ["peanut", "tree-nut"], "include": [4], "exclude": [9], "q": "cheese toast",
                 "sort": "relevance", "page": 2, "pageSize": 12, "profile": True}


def test_parseFiltersDefaultsToAShuffledFirstPage(rules):
    assert rules.parseFilters(MultiDict()) == ({"sort": "shuffle", "page": 1, "pageSize": 24, "profile": True}, None)
    assert rules.parseFilters(MultiDict([("sort", "relevance")]))[0]["sort"] == "shuffle"


@pytest.mark.parametrize("pairs, words", [
    ([("maxMinutes", "abc")], "maxMinutes"), ([("maxMinutes", "²")], "maxMinutes"),
    ([("pageSize", "100000")], "pageSize"), ([("difficulty", "7")], "difficulty"),
    ([("avoid", "unicorn")], "avoid"), ([("include", "0")], "include"), ([("kind", "pizza")], "kind"),
    ([("sort", "best")], "sort"), ([("q", "x" * 101)], "q"), ([("page", "0")], "page"),
])
def test_badFiltersSayWhy(rules, pairs, words):
    f, problem = rules.parseFilters(MultiDict(pairs))
    assert f is None and words in problem


def test_descendantsFollowTheTree(rules):
    rows = [{"IngredientID": 1, "ParentID": None}, {"IngredientID": 2, "ParentID": 1},
            {"IngredientID": 3, "ParentID": 2}, {"IngredientID": 4, "ParentID": None}]
    assert rules.descendants(rows, [1]) == {1, 2, 3}
    assert rules.descendants(rows, [4, 9]) == {4, 9}


def test_booleanQueryKeepsWordsOfThreeOrMore(rules):
    assert rules.booleanQuery("Grilled cheese, on toast!") == "+grilled* +cheese* +toast*"
    assert rules.booleanQuery("a ox") == ""


def test_recipeWhereBuildsEveryFilter(rules):
    f = {"kind": "food", "course": ["main"], "maxMinutes": 30, "flavour": ["sweet"], "diet": ["vegan"],
         "avoid": ["peanut"], "q": "toast", "sort": "relevance", "page": 1, "pageSize": 24}
    sql, params = rules.recipeWhere(f, includeSets=[{1, 2}], excludeIds={9})
    assert sql.startswith("r.RemovedAt IS NULL AND r.Kind = %s AND r.Course IN (%s)")
    assert "r.TotalMinutes IS NOT NULL AND r.TotalMinutes <= %s" in sql
    assert "fa.Complete = 1" in sql
    assert "NOT EXISTS (SELECT 1 FROM RecipeContains c WHERE c.RecipeID = r.RecipeID AND c.Item IN (%s))" in sql
    assert "MATCH(r.SearchText) AGAINST (%s IN BOOLEAN MODE)" in sql
    assert params == ["food", "main", 30, "flavour", "sweet", "vegan", "peanut", 1, 2, 9, "+toast*"]


def test_aShortSearchFallsBackToTheTitle(rules):
    sql, params = rules.recipeWhere({"q": "ox", "sort": "shuffle", "page": 1, "pageSize": 24})
    assert sql.endswith("r.Title LIKE %s") and params == ["%ox%"]


def test_recipeOrder(rules):
    assert rules.recipeOrder({"sort": "quickest"}, "2026-10-19") == ("r.TotalMinutes IS NULL, r.TotalMinutes, r.Title", [])
    assert rules.recipeOrder({"sort": "shuffle"}, "2026-10-19") == \
        ("SHA1(CONCAT(r.RecipeID, ':', %s)), r.RecipeID", ["2026-10-19"])
    assert rules.recipeOrder({"sort": "relevance", "q": "toast"}, "2026-10-19") == \
        ("MATCH(r.SearchText) AGAINST (%s IN BOOLEAN MODE) DESC, r.Title", ["+toast*"])


def test_validatorsNeverRaiseOnMalformedShapes(rules):
    facts = samples.recipe()["facts"]
    assert rules.recipeProblem(samples.recipe(facts={**facts, "contains": [[1]]}))
    assert rules.recipeProblem(samples.recipe(facts={**facts, "diets": [{"a": 1}]}))
    assert rules.seedProblem([{"name": ["x"], "parent": None}])
    assert rules.seedProblem([{"name": "x", "parent": ["y"]}])
    assert rules.seedProblem([{"name": "x", "contains": [[1]]}])
    assert rules.mapProblem({"alias": "x", "create": {"name": "y", "contains": [[1]]}})
    assert rules.batchProblem([])
    assert rules.batchProblem("x")
    assert rules.mapProblem("x")
    assert rules.mapProblem([])


def test_booleanQueryDropsInnoDbStopwords(rules):
    assert rules.booleanQuery("cheese and the bread") == "+cheese* +and* +bread*"
    assert rules.booleanQuery("the with from") == ""


def test_theProfileIsOnUnlessAskedOff(rules):
    assert rules.parseFilters(MultiDict({}))[0]["profile"] is True
    assert rules.parseFilters(MultiDict({"profile": "off"}))[0]["profile"] is False
    assert rules.parseFilters(MultiDict({"profile": "maybe"}))[1] == "profile must be on or off"


def test_alcoholIsAFilterOfItsOwn(rules):
    f, problem = rules.parseFilters(MultiDict({"alcohol": "non-alcoholic,optional"}))
    assert problem is None and f["alcohol"] == ["non-alcoholic", "optional"]
    assert rules.parseFilters(MultiDict({"alcohol": "lots"}))[1] == "unknown alcohol: lots"
    where, params = rules.recipeWhere(f)
    assert "r.Alcohol IN (%s, %s)" in where and params[-2:] == ["non-alcoholic", "optional"]


def test_withProfileAddsSavedWordsOnce(rules):
    f = rules.withProfile({"diet": ["vegan"], "kind": "food"}, ["vegetarian", "vegan"], ["peanut"])
    assert f == {"diet": ["vegan", "vegetarian"], "avoid": ["peanut"], "kind": "food"}
    assert rules.withProfile({"kind": "food"}, [], []) == {"kind": "food"}


def test_theProfileFollowsTheSafetyRule(rules):
    where, _ = rules.recipeWhere(rules.withProfile({}, [], ["peanut"]))
    assert "fa.Complete = 1" in where


def test_dietProblemKeepsKnownWordsInTheCatalogsOrder(rules):
    assert rules.dietProblem({"diets": ["vegan", "vegetarian", "vegan"], "avoid": ["sesame", "peanut"]}) == \
        (["vegetarian", "vegan"], ["peanut", "sesame"], None)
    assert rules.dietProblem({})[:2] == ([], [])
    assert rules.dietProblem({"diets": ["keto"]})[2] == "unknown diet: keto"
    assert rules.dietProblem({"avoid": ["spinach"]})[2] == "unknown avoid: spinach"
    assert rules.dietProblem({"diets": "vegan"})[2] == "diets must be a list of words"
