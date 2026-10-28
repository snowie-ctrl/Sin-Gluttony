import pytest

import matching
import rulesData
import tagging
from models import IngredientLine, Recipe, Step

RULES = rulesData.load()
PREP = set(RULES["prepWords"])
TABLE = matching.IngredientTable.fromSeed(RULES["ingredients"], PREP)


def recipe(steps=("Cook.",), ingredients=("salt",), **fields):
    base = dict(source="wikibooks", sourceId="x", kind="food", title="Thing",
                ingredients=[IngredientLine(line=i, name=i) for i in ingredients],
                steps=[Step(text=s) for s in steps])
    base.update(fields)
    return Recipe(**base)


@pytest.mark.parametrize("text, expected", [
    ("Bake for 25 minutes.", [25]), ("Simmer 1 hour 20 minutes", [60, 20]), ("1½ hours", [90]),
    ("rest 1-2 hours", [120]), ("45 mins", [45]), ("leave overnight", []),
])
def test_durations(text, expected):
    assert tagging.durations(text) == expected


def test_parseTimeTextReadsLabels():
    assert tagging.parseTimeText("Prep: 20 minutes Cooking: 1 hour") == (20, 60, 80)
    assert tagging.parseTimeText("Total time: 45 minutes") == (None, None, 45)
    assert tagging.parseTimeText("30 minutes") == (None, None, 30)
    assert tagging.parseTimeText("a while") is None


def test_timeFromStepsTakesEachStepsLongestDuration():
    steps = [Step(text="Bake 25 minutes, checking after 20 minutes."), Step(text="Cool for 10 minutes.")]
    assert tagging.timeFromSteps(steps) == 35


@pytest.mark.parametrize("text", [
    "Refrigerate until firm, about 1 hour. (You can refrigerate each portion for up to 3 days or freeze it.)",
    "Refrigerate until firm, about 1 hour. LEFTOVERS! The chicken keeps well in the fridge for 5 days.",
    "Refrigerate until firm, about 1 hour. Store in an airtight jar for 2 days.",
    "Refrigerate until firm, about 1 hour. It will keep for 4 days; leftovers reheat in 10 minutes.",
    "Refrigerate at least 1 hour, and use within 5 days.",
    "Chill for 1 hour (it will last for 3 days in the fridge).",
    "Chill for 1 hour. It can be kept in the refrigerator for 4 days.",
    "Chill for 1 hour. Refrigerate at under 40°F for no more than 3 days.",
    "Chill for 1 hour. You may make the sauce about 2 days in advance.",
    "Chill for 1 hour. The brie can be prepared up to this point and refrigerated for 2 days before baking.",
])
def test_howLongFoodKeepsIsNotCookingTime(text):
    assert tagging.timeFromSteps([Step(text=text)]) == 60


@pytest.mark.parametrize("text, expected", [
    ("Keep stirring for 10 minutes.", 10),
    ("Marinate at least 2 hours, or up to 24 hours.", 1440),
    ("Add the store-bought stock and simmer 20 minutes.", 20),
])
def test_cookingTimesNearStorageWordsStillCount(text, expected):
    assert tagging.timeFromSteps([Step(text=text)]) == expected


def test_statedTimeWinsAndIsMarkedSource():
    r = tagging.tagRecipe(recipe(steps=("Bake 90 minutes.",), hints={"timeText": "Total: 30 minutes"}), TABLE, RULES)
    assert (r.totalMinutes, r.timeFrom) == (30, "source")


def test_aTimeOverAWeekIsUnknown():
    over = tagging.tagRecipe(recipe(steps=("Stir.",), hints={"timeText": "Total: 14 days"}), TABLE, RULES)
    assert (over.totalMinutes, over.timeFrom) == (None, None)
    weeks = tagging.tagRecipe(recipe(steps=("Ferment for 3 weeks.",)), TABLE, RULES)
    assert weeks.totalMinutes is None
    days = tagging.tagRecipe(recipe(steps=("Ferment for 8 days.",)), TABLE, RULES)
    assert (days.totalMinutes, days.timeFrom) == (None, None)


def test_aDrinkWithNoDurationsTakesAboutFiveMinutes():
    r = tagging.tagRecipe(recipe(kind="drink", source="cocktaildb", steps=("Shake.",), ingredients=("gin",)),
                          TABLE, RULES)
    assert (r.totalMinutes, r.timeFrom) == (5, "rule")


def test_difficultyFromTheWikibooksRatingOrTheScore():
    assert [tagging.difficultyFromRating(n) for n in (1, 2, 3, 4, 5)] == [1, 1, 2, 3, 3]
    rated = tagging.tagRecipe(recipe(hints={"difficultyRating": 4}), TABLE, RULES)
    assert (rated.difficulty, rated.difficultyFrom) == (3, "source")
    short = tagging.tagRecipe(recipe(), TABLE, RULES)
    assert (short.difficulty, short.difficultyFrom) == (1, "rule")
    long = recipe(steps=["Temper the chocolate."] + ["Stir."] * 16, ingredients=["salt"] * 10)
    assert tagging.tagRecipe(long, TABLE, RULES).difficulty == 3


def test_courseAndCuisineComeFromSourceCategories():
    meal = tagging.tagRecipe(recipe(source="mealdb", hints={"category": "Dessert", "area": "Japanese"}), TABLE, RULES)
    assert (meal.course, meal.cuisine) == ("dessert", "Japanese")
    page = tagging.tagRecipe(recipe(hints={"categories": ["Soup recipes", "Thai recipes"]}), TABLE, RULES)
    assert (page.course, page.cuisine) == ("main", "Thai")
    unknown = tagging.tagRecipe(recipe(source="mealdb", hints={"area": "Unknown"}), TABLE, RULES)
    assert unknown.cuisine is None


def test_aCourseThatDoesNotFitTheKindIsDropped():
    drink = tagging.tagRecipe(recipe(kind="drink", ingredients=("orange juice",),
                                     hints={"categories": ["Dessert recipes"]}), TABLE, RULES)
    assert drink.course == "mocktail"
    food = tagging.tagRecipe(recipe(hints={"categories": ["Cocktail recipes"]}), TABLE, RULES)
    assert food.course is None
    both = tagging.tagRecipe(recipe(hints={"categories": ["Cocktail recipes", "Dessert recipes"]}), TABLE, RULES)
    assert both.course == "dessert"


def test_aNonAlcoholicCocktailIsAMocktail():
    r = tagging.tagRecipe(recipe(source="cocktaildb", kind="drink", alcohol="non-alcoholic",
                                 hints={"category": "Ordinary Drink"}, ingredients=("lime juice",)), TABLE, RULES)
    assert r.course == "mocktail"


def test_aWikibooksDrinksAlcoholComesFromItsIngredients():
    boozy = tagging.tagRecipe(recipe(kind="drink", ingredients=("vodka", "orange juice")), TABLE, RULES)
    assert (boozy.alcohol, boozy.course) == ("alcoholic", "cocktail")
    soft = tagging.tagRecipe(recipe(kind="drink", ingredients=("orange juice", "soda water")), TABLE, RULES)
    assert (soft.alcohol, soft.course) == ("non-alcoholic", "mocktail")


def flavours(r):
    return {t["tag"]: t["origin"] for t in r.tags if t["type"] == "flavour"}


def test_flavourRules():
    spicy = tagging.tagRecipe(recipe(ingredients=("chicken", "jalapeno"), hints={"category": "Chicken"},
                                     source="mealdb"), TABLE, RULES)
    assert flavours(spicy) == {"spicy": "rule", "savoury": "rule"}
    sweet = tagging.tagRecipe(recipe(ingredients=("flour", "sugar", "butter"), hints={"categories": []}), TABLE, RULES)
    assert "sweet" in flavours(sweet) and "savoury" not in flavours(sweet)
    tagged = tagging.tagRecipe(recipe(source="mealdb", hints={"tags": ["Spicy"], "category": "Beef"}), TABLE, RULES)
    assert flavours(tagged)["spicy"] == "source"


def occasions(r):
    return {t["tag"] for t in r.tags if t["type"] == "occasion"}


def test_occasionRules():
    weeknight = tagging.tagRecipe(recipe(source="mealdb", hints={"category": "Beef"}, steps=("Fry 20 minutes.",)),
                                  TABLE, RULES)
    assert "weeknight" in occasions(weeknight)
    party = tagging.tagRecipe(recipe(servings=10, hints={"categories": ["Christmas recipes"]}), TABLE, RULES)
    assert occasions(party) >= {"party", "holiday"}
    brunch = tagging.tagRecipe(recipe(source="mealdb", hints={"category": "Breakfast"}), TABLE, RULES)
    assert "brunch" in occasions(brunch)


def test_holidayNeedsWholeWords():
    eastern = tagging.tagRecipe(recipe(hints={"categories": ["Middle Eastern recipes"]}), TABLE, RULES)
    assert "holiday" not in occasions(eastern)
    easter = tagging.tagRecipe(recipe(hints={"categories": ["Easter recipes"]}), TABLE, RULES)
    assert "holiday" in occasions(easter)


def test_sourceTagsAreKeptOnceEach():
    r = tagging.tagRecipe(recipe(source="mealdb", hints={"tags": ["Meat", "meat", "Casserole"]}), TABLE, RULES)
    assert [t["tag"] for t in r.tags if t["type"] == "source"] == ["Meat", "Casserole"]


def test_blankSourceTagsAreSkipped():
    r = tagging.tagRecipe(recipe(source="mealdb", hints={"tags": [" Meat ", "  ", "meat"]}), TABLE, RULES)
    assert [t["tag"] for t in r.tags if t["type"] == "source"] == ["Meat"]
