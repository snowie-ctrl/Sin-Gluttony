import pytest

import matching
import rulesData
import tagging
from models import IngredientLine, Recipe, Step

RULES = rulesData.load()
# rules/courses.json maps a source's own categories to courses, per source; a made-up site's map for these tests.
RULES["courses"] = {"madeupsite": {"dessert": "dessert", "breakfast": "breakfast", "beef": "main", "chicken": "main",
                                   "cocktail": "cocktail", "ordinary drink": "cocktail"}}
PREP = set(RULES["prepWords"])
TABLE = matching.IngredientTable.fromSeed(RULES["ingredients"], PREP)


def recipe(steps=("Cook.",), ingredients=("salt",), **fields):
    base = dict(source="madeupsite", sourceId="x", kind="food", title="Thing",
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
    r = tagging.tagRecipe(recipe(kind="drink", steps=("Shake.",), ingredients=("gin",)),
                          TABLE, RULES)
    assert (r.totalMinutes, r.timeFrom) == (5, "rule")


def test_difficultyFromAStatedRatingOrTheScore():
    assert [tagging.difficultyFromRating(n) for n in (1, 2, 3, 4, 5)] == [1, 1, 2, 3, 3]
    rated = tagging.tagRecipe(recipe(hints={"difficultyRating": 4}), TABLE, RULES)
    assert (rated.difficulty, rated.difficultyFrom) == (3, "source")
    short = tagging.tagRecipe(recipe(), TABLE, RULES)
    assert (short.difficulty, short.difficultyFrom) == (1, "rule")
    long = recipe(steps=["Temper the chocolate."] + ["Stir."] * 16, ingredients=["salt"] * 10)
    assert tagging.tagRecipe(long, TABLE, RULES).difficulty == 3


def test_courseAndCuisineComeFromTheSourcesCategoryAndCuisine():
    meal = tagging.tagRecipe(recipe(hints={"category": "Dessert", "cuisineText": "Japanese"}), TABLE, RULES)
    assert (meal.course, meal.cuisine) == ("dessert", "Japanese")
    unmapped = tagging.tagRecipe(recipe(source="othersite", hints={"category": "Dessert"}), TABLE, RULES)
    assert unmapped.course is None          # no course map for that source
    unknown = tagging.tagRecipe(recipe(hints={"cuisineText": "Unknown"}), TABLE, RULES)
    assert unknown.cuisine is None


def test_aCourseThatDoesNotFitTheKindIsDropped():
    drink = tagging.tagRecipe(recipe(kind="drink", ingredients=("orange juice",), hints={"category": "Dessert"}),
                              TABLE, RULES)
    assert drink.course == "mocktail"
    food = tagging.tagRecipe(recipe(hints={"category": "Cocktail"}), TABLE, RULES)
    assert food.course is None


def test_aNonAlcoholicCocktailIsAMocktail():
    r = tagging.tagRecipe(recipe(kind="drink", alcohol="non-alcoholic",
                                 hints={"category": "Ordinary Drink"}, ingredients=("lime juice",)), TABLE, RULES)
    assert r.course == "mocktail"


def test_aDrinksAlcoholComesFromItsIngredients():
    boozy = tagging.tagRecipe(recipe(kind="drink", ingredients=("vodka", "orange juice")), TABLE, RULES)
    assert (boozy.alcohol, boozy.course) == ("alcoholic", "cocktail")
    soft = tagging.tagRecipe(recipe(kind="drink", ingredients=("orange juice", "soda water")), TABLE, RULES)
    assert (soft.alcohol, soft.course) == ("non-alcoholic", "mocktail")


def flavours(r):
    return {t["tag"]: t["origin"] for t in r.tags if t["type"] == "flavour"}


def test_flavourRules():
    spicy = tagging.tagRecipe(recipe(ingredients=("chicken", "jalapeno"), hints={"category": "Chicken"}),
                          TABLE, RULES)
    assert flavours(spicy) == {"spicy": "rule", "savoury": "rule"}
    sweet = tagging.tagRecipe(recipe(ingredients=("flour", "sugar", "butter"), hints={"categories": []}), TABLE, RULES)
    assert "sweet" in flavours(sweet) and "savoury" not in flavours(sweet)
    tagged = tagging.tagRecipe(recipe(hints={"tags": ["Spicy"], "category": "Beef"}), TABLE, RULES)
    assert flavours(tagged)["spicy"] == "source"


def occasions(r):
    return {t["tag"] for t in r.tags if t["type"] == "occasion"}


def test_occasionRules():
    weeknight = tagging.tagRecipe(recipe(hints={"category": "Beef"}, steps=("Fry 20 minutes.",)),
                                  TABLE, RULES)
    assert "weeknight" in occasions(weeknight)
    party = tagging.tagRecipe(recipe(servings=10, hints={"categories": ["Christmas recipes"]}), TABLE, RULES)
    assert occasions(party) >= {"party", "holiday"}
    brunch = tagging.tagRecipe(recipe(hints={"category": "Breakfast"}), TABLE, RULES)
    assert "brunch" in occasions(brunch)


def test_holidayNeedsWholeWords():
    eastern = tagging.tagRecipe(recipe(hints={"categories": ["Middle Eastern recipes"]}), TABLE, RULES)
    assert "holiday" not in occasions(eastern)
    easter = tagging.tagRecipe(recipe(hints={"categories": ["Easter recipes"]}), TABLE, RULES)
    assert "holiday" in occasions(easter)


def test_sourceTagsAreKeptOnceEach():
    r = tagging.tagRecipe(recipe(hints={"tags": ["Meat", "meat", "Casserole"]}), TABLE, RULES)
    assert [t["tag"] for t in r.tags if t["type"] == "source"] == ["Meat", "Casserole"]


def test_blankSourceTagsAreSkipped():
    r = tagging.tagRecipe(recipe(hints={"tags": [" Meat ", "  ", "meat"]}), TABLE, RULES)
    assert [t["tag"] for t in r.tags if t["type"] == "source"] == ["Meat"]


def test_aTimeTheSiteGaveIsKept():
    r = tagging.tagRecipe(recipe(source="recipetineats", steps=("Bake 90 minutes.",), prepMinutes=10,
                                 cookMinutes=25, totalMinutes=35, timeFrom="source"), TABLE, RULES)
    assert (r.prepMinutes, r.cookMinutes, r.totalMinutes, r.timeFrom) == (10, 25, 35, "source")


def test_aDrinkTimeTheAdapterSetByRuleIsKept():
    r = tagging.tagRecipe(recipe(kind="drink", source="difford", steps=("Stir for 2 minutes.",), ingredients=("gin",),
                                 totalMinutes=4, timeFrom="rule", hints={"method": "stirred"}), TABLE, RULES)
    assert (r.totalMinutes, r.timeFrom) == (4, "rule")


def test_anAdapterTimeOverAWeekIsDropped():
    r = tagging.tagRecipe(recipe(steps=("Stir.",), totalMinutes=20000, timeFrom="source"), TABLE, RULES)
    assert (r.totalMinutes, r.timeFrom) == (None, None)


def test_servingsTheSiteGaveAreKept():
    r = tagging.tagRecipe(recipe(source="recipetineats", servings=6, servingsFrom="source"), TABLE, RULES)
    assert (r.servings, r.servingsFrom) == (6, "source")


def test_aDrinksMethodBecomesATechniqueTag():
    r = tagging.tagRecipe(recipe(kind="drink", source="difford", ingredients=("gin",), hints={"method": "shaken"}),
                          TABLE, RULES)
    assert {"type": "technique", "tag": "shaken", "origin": "rule"} in r.tags


def test_aDiffordsShapedRecipeGetsItsTechniqueTagFromTheKeyDiffordSets():
    from sources import difford
    import inspect
    assert 'hints={"method": method' in inspect.getsource(difford)
    r = tagging.tagRecipe(recipe(kind="drink", source="difford", ingredients=("gin", "dry vermouth"), glass="coupe",
                                 totalMinutes=4, timeFrom="rule", servings=1, servingsFrom="rule",
                                 hints={"method": "stirred", "category": "Cocktail"}), TABLE, RULES)
    assert [t["tag"] for t in r.tags if t["type"] == "technique"] == ["stirred"]
    assert (r.totalMinutes, r.timeFrom, r.servings, r.servingsFrom) == (4, "rule", 1, "rule")
    plain = tagging.tagRecipe(recipe(kind="drink", ingredients=("gin",)), TABLE, RULES)
    assert not [t for t in plain.tags if t["type"] == "technique"]


def test_aSiteRecipesCourseHintFillsTheGap():
    side = tagging.tagRecipe(recipe(source="othersite", hints={"course": "side"}), TABLE, RULES)
    assert side.course == "side"
    shake = tagging.tagRecipe(recipe(source="othersite", kind="drink", ingredients=("milk",),
                                     hints={"course": "shake"}), TABLE, RULES)
    assert shake.course == "shake"


def test_aPerSourceMapWinsOverTheHint():
    meal = tagging.tagRecipe(recipe(hints={"category": "Dessert", "course": "main"}), TABLE, RULES)
    assert meal.course == "dessert"


def test_aHintThatDoesNotFitTheKindIsDropped():
    drink = tagging.tagRecipe(recipe(source="othersite", kind="drink", ingredients=("orange juice",),
                                     hints={"course": "dessert"}), TABLE, RULES)
    assert drink.course == "mocktail"


@pytest.mark.parametrize("title", ["Alcohol-free amaretto sour", "A Really Good Non-Alcoholic Margarita",
                                   "Virgin mojito", "Zero-proof spritz"])
def test_aDrinkWhoseTitleSaysAlcoholFreeIsAMocktail(title):
    # its ingredients may be unknown, so its facts cannot say (2026-11-20)
    r = tagging.tagRecipe(recipe(kind="drink", title=title, ingredients=("made-up syrup",)), TABLE, RULES)
    assert (r.alcohol, r.course) == ("non-alcoholic", "mocktail")


def test_aTitleWordDoesNotOverruleKnownAlcohol():
    r = tagging.tagRecipe(recipe(kind="drink", title="Virgin Islands rum punch", ingredients=("white rum",)),
                          TABLE, RULES)
    assert r.alcohol == "alcoholic"


def test_aKnownSpiritMakesADrinkAlcoholicEvenWithAnUnknownGarnish():
    # one unknown line ("made-up garnish") leaves the facts incomplete; the vodka still says alcohol is in it
    r = tagging.tagRecipe(recipe(kind="drink", ingredients=("vodka", "made-up garnish")), TABLE, RULES)
    assert (r.alcohol, r.course) == ("alcoholic", "cocktail")
    assert r.facts["contains"] == []            # the published facts keep their safety rule
    unsure = tagging.tagRecipe(recipe(kind="drink", ingredients=("orange juice", "made-up garnish")), TABLE, RULES)
    assert (unsure.alcohol, unsure.course) == (None, "cocktail")


@pytest.mark.parametrize("line", ["gin London dry", "rum we used white rum", "bottle of decent gin", "cachaça liqueur",
                                  "Disaronno Or other amaretto", "Barefoot Bubbly Brut Cuvée Champagne"])
def test_aSpiritNamedInAnUnknownLineMakesADrinkAlcoholic(line):
    r = tagging.tagRecipe(recipe(kind="drink", ingredients=(line, "orange juice")), TABLE, RULES)
    assert r.alcohol == "alcoholic"


@pytest.mark.parametrize("line", ["made-up ginger syrup", "made-up rum extract", "made-up rice wine vinegar",
                                  "made-up alcohol-free gin", "made-up non-alcoholic sparkling wine",
                                  "made-up ginger beer to top up", "sachet made-up wine yeast"])
def test_aLineThatOnlyLooksLikeASpiritSaysNothing(line):
    r = tagging.tagRecipe(recipe(kind="drink", ingredients=(line, "orange juice")), TABLE, RULES)
    assert r.alcohol is None
