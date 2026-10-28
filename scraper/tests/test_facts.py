import facts
import matching
import rulesData
from models import IngredientLine, Recipe, Step

PREP = set(rulesData.load()["prepWords"])
TABLE = matching.IngredientTable.fromSeed([
    {"name": "bread", "contains": ["gluten"]},
    {"name": "butter", "contains": ["dairy"]},
    {"name": "tomato"},
    {"name": "honey", "contains": ["honey"]},
    {"name": "olive oil"},
], PREP)


def recipe(*names):
    return Recipe(source="wikibooks", sourceId="x", kind="food", title="x",
                  ingredients=[IngredientLine(line=n, name=n) for n in names], steps=[Step(text="Cook.")])


def tagged(*names):
    r = recipe(*names)
    facts.applyMatching(r, TABLE)
    facts.applyFacts(r, TABLE)
    return r


def test_dietsFollowWhatTheIngredientsContain():
    assert facts.dietsFor(set()) == ["vegetarian", "vegan", "gluten-free", "dairy-free"]
    assert facts.dietsFor({"dairy"}) == ["vegetarian", "gluten-free"]
    assert facts.dietsFor({"honey"}) == ["vegetarian", "gluten-free", "dairy-free"]
    assert facts.dietsFor({"fish"}) == ["gluten-free", "dairy-free"]


def test_aCompleteRecipeGetsItsContainsAndDiets():
    r = tagged("bread", "butter")
    assert r.facts == {"complete": True, "contains": ["dairy", "gluten"], "diets": ["vegetarian"]}


def test_oneUnknownIngredientMeansNoDietsAtAll():
    r = tagged("tomato", "mystery sauce")
    assert r.facts == {"complete": False, "contains": [], "diets": []}
    assert r.ingredients[1].unknownName == "mystery sauce" and r.ingredients[1].ingredientId is None


def test_anUnknownOptionalIngredientStillCountsAgainstComplete():
    r = recipe("tomato", "mystery nuts")
    r.ingredients[1].optional = True
    facts.applyMatching(r, TABLE)
    facts.applyFacts(r, TABLE)
    assert r.facts["complete"] is False


def test_aLineWithTwoOptionsContainsWhatEitherOneContains():
    r = tagged("bread", "butter or olive oil")
    assert r.facts == {"complete": True, "contains": ["dairy", "gluten"], "diets": ["vegetarian"]}
    assert r.ingredients[1].ingredientId == TABLE.aliases["butter"]
    assert r.ingredients[1].alternativeIds == [TABLE.aliases["olive oil"]]


def test_andOrCountsAsTwoOptionsToo():
    r = tagged("olive oil and/or butter")
    assert r.facts["contains"] == ["dairy"] and "dairy-free" not in r.facts["diets"]


def test_anUnknownOptionMakesTheLineUnknownUnderItsOwnName():
    r = tagged("tomato", "butter or mystery spread")
    assert r.facts == {"complete": False, "contains": [], "diets": []}
    assert r.ingredients[1].ingredientId is None and r.ingredients[1].alternativeIds == []
    assert r.ingredients[1].unknownName == "mystery spread"
