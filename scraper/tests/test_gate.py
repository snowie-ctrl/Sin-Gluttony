import pytest

import gate
import rulesData
from models import IngredientLine, Recipe, Step

UNITS = rulesData.load()["unitMap"]


def line(name, text=None, **fields):
    return IngredientLine(line=text or name, name=name, **fields)


def candidate(**changes):
    base = dict(source="testsite", sourceId="1", kind="food", title="Made-up Stew",
                ingredients=[line("olive oil", "2 tbsp olive oil", quantity=2.0, unit="tbsp"),
                             line("Salt", "Salt, to taste", note="to taste")],
                steps=[Step(text="Cook.")], imagePath="abc.jpg", imageWidth=1200, totalMinutes=30, servings=4,
                nutrition={"calories": 400.0})
    base.update(changes)
    return Recipe(**base)


def test_aCompleteRecipeIsListed():
    r = candidate()
    assert gate.apply(r, UNITS) is None and r.hiddenReason is None


@pytest.mark.parametrize("changes, reason", [
    ({"imagePath": None}, "no-photo"),
    ({"imageWidth": 799}, "small-photo"),
    ({"imageWidth": None}, "small-photo"),
    ({"totalMinutes": None}, "no-time"),
    ({"servings": None}, "no-servings"),
    ({"ingredients": [line("x 400g cans tomatoes", "2 x 400g cans tomatoes", quantity=2.0)]}, "unparsed-line"),
    ({"ingredients": []}, "unparsed-line"),
    ({"nutrition": None}, "no-nutrition"),
    ({"nutrition": {"calories": None}}, "no-nutrition"),
])
def test_eachCheckHasItsReason(changes, reason):
    assert gate.check(candidate(**changes), UNITS) == reason


def test_theFirstFailingCheckWinsInTheSpecsOrder():
    broken = dict(imagePath=None, imageWidth=None, totalMinutes=None, servings=None,
                  ingredients=[line("")], nutrition=None)
    found = []
    for fix in ({}, {"imagePath": "a.jpg"}, {"imageWidth": 800}, {"totalMinutes": 10}, {"servings": 2},
                {"ingredients": [line("salt")]}, {"nutrition": {"calories": 1.0}}):
        broken.update(fix)
        found.append(gate.check(candidate(**broken), UNITS))
    assert found == [*gate.REASONS, None]


@pytest.mark.parametrize("name, parsed", [
    ("olive oil", True), ("Salt", True), ("Lemon wedge", True), ("00 flour", True), ("2% milk", True),
    ("Chinese 5-spice powder", True), ("lemon", True),
    ("x 400g cans chopped tomatoes", False), ("g/7oz plain flour", False), ("plain flour 200g", False),
    ("⁄2 cup sugar", False), ("", False), ("½", False), ("2", False),
])
def test_aLineIsParsedWhenANameIsFoundAndNoAmountIsLeftInIt(name, parsed):
    assert gate.lineParsed(line(name), UNITS) is parsed


def test_linesWithoutAQuantityCountAsParsedWhenTheNameIsFound():
    r = candidate(ingredients=[line("Salt", "Salt, to taste", note="to taste"),
                               line("Lemon wedge", "Lemon wedge for garnish", note="for garnish", optional=True)])
    assert gate.check(r, UNITS) is None


def test_milestone1HasNoEstimateSoNoSiteNutritionHidesTheRecipe():
    """Milestone 2 adds the USDA estimate; until then a site without per-serving nutrition is no-nutrition."""
    r = candidate(nutrition=None)
    assert gate.apply(r, UNITS) == "no-nutrition" and not gate.hasNutrition(r)


def test_theGateIsRecheckedEveryPass():
    r = candidate(totalMinutes=None)
    assert gate.apply(r, UNITS) == "no-time"
    r.totalMinutes = 25
    assert gate.apply(r, UNITS) is None and r.hiddenReason is None


def test_theGateLeavesTheSafetyRuleAlone():
    facts = {"complete": False, "contains": [], "diets": []}
    r = candidate(facts=dict(facts))
    gate.apply(r, UNITS)
    assert r.facts == facts


def test_aChosenEstimatePassesCheckFiveAndNoneFails():
    import matching, nutrition
    rules = rulesData.load()
    table = matching.IngredientTable.fromSeed([{"name": "gin"}], set())
    gin = IngredientLine(line="50 ml gin", name="gin", quantity=50.0, unit="ml", ingredientId=1)
    r = candidate(kind="drink", nutrition=None, ingredients=[gin])
    nutrition.choose(r, table, {}, {}, rules)
    assert r.nutritionFrom == "estimate" and gate.check(r, UNITS) is None
    assert gate.check(candidate(nutrition=None), UNITS) == "no-nutrition"
