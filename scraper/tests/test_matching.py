import pytest

import matching
import rulesData

RULES = rulesData.load()
PREP = set(RULES["prepWords"])


def table(seed):
    return matching.IngredientTable.fromSeed(seed, PREP)


SEED = [
    {"name": "cheese", "category": "dairy", "contains": ["dairy"]},
    {"name": "cheddar", "parent": "cheese", "aliases": ["cheddar cheese"]},
    {"name": "chicken", "contains": ["poultry"]},
    {"name": "chicken thigh", "parent": "chicken"},
    {"name": "jalapeno", "category": "chilli"},
    {"name": "tomato", "aliases": ["tomatoes"]},
]


@pytest.mark.parametrize("word, expected", [
    ("tomatoes", "tomato"), ("berries", "berry"), ("peaches", "peach"), ("eggs", "egg"),
    ("leaves", "leaf"), ("asparagus", "asparagus"), ("glass", "glass"), ("gas", "gas"),
])
def test_singular(word, expected):
    assert matching.singular(word) == expected


def test_normaliseDropsPreparationWordsAndPlurals():
    assert matching.normaliseName("2 Large Free-Range EGGS, beaten", PREP) == "free range egg"
    assert matching.normaliseName("Juice of ½ lemon", PREP) == "juice lemon"
    assert matching.normaliseName("Finely chopped fresh tomatoes", PREP) == "tomato"


def test_exactAliasesMatchFirst():
    assert table(SEED).match("Cheddar Cheese")[0] == 2


def test_theLongestKnownNameInsideALineWins():
    # "boneless" and "skinless" are preparation words, the comma goes, and "thighs" becomes "thigh".
    t = matching.IngredientTable.fromSeed(SEED, PREP, set(RULES["modifierWords"]))
    ingredientId, key = t.match("boneless skinless chicken thighs, cut up")
    assert ingredientId == 4 and key == "chicken thigh cut"


REAL = matching.IngredientTable.fromSeed(RULES["ingredients"], PREP, set(RULES["modifierWords"]))


@pytest.mark.parametrize("name", [
    "cashew butter", "soybean oil", "cashew oil", "hazelnut chocolate", "cashew cream", "spelt pasta",
])
def test_aWordThatIsNotAModifierMakesTheLineUnknown(name):
    assert REAL.match(name)[0] is None


@pytest.mark.parametrize("name, expected", [
    ("unsalted butter", "butter"), ("smoked salmon", "salmon"), ("free range egg", "egg"),
    ("white chocolate", "chocolate"),
])
def test_modifiersStillMatch(name, expected):
    ingredientId, _ = REAL.match(name)
    assert ingredientId == REAL.match(expected)[0]


def test_tiesAreDeterministic():
    seed = [{"name": "ab"}, {"name": "cd"}]
    t = matching.IngredientTable.fromSeed(seed, PREP, {"ab", "cd"})
    assert t.match("ab cd")[0] == 1
    assert t.match("cd ab")[0] == 2


def test_matchingIgnoresAccents():
    assert table(SEED).match("Jalapeño")[0] == 5


def test_anUnknownNameGivesItsNormalisedForm():
    assert table(SEED).match("Dragon fruit") == (None, "dragon fruit")


def test_containsAndCategoriesComeFromTheWholeLineage():
    t = table(SEED)
    assert t.containsOf(2) == {"dairy"}
    assert t.categoriesOf(2) == {"dairy"}
    assert t.lineage(4) == [4, 3]


def test_aParentCycleDoesNotLoop():
    t = matching.IngredientTable({1: {"id": 1, "name": "a", "parentId": 2, "category": None, "contains": set()},
                                  2: {"id": 2, "name": "b", "parentId": 1, "category": None, "contains": {"egg"}}},
                                 {"a": 1}, PREP)
    assert t.containsOf(1) == {"egg"}


def test_fromServerReadsTheAdminPayload():
    payload = {"ingredients": [{"id": 7, "name": "cheese", "parentId": None, "category": "dairy", "origin": "seed",
                                "contains": ["dairy"]}],
               "aliases": [{"alias": "cheese", "ingredientId": 7}, {"alias": "stray", "ingredientId": 99}]}
    t = matching.IngredientTable.fromServer(payload, PREP)
    assert t.match("cheese") == (7, "cheese") and t.match("stray")[0] is None


def test_seedPayloadNormalisesAliasesAndKeepsTheName():
    payload = matching.seedPayload([{"name": "tomato", "aliases": ["Tomatoes", "chopped tomatoes"]}], PREP)
    assert payload == [{"name": "tomato", "parent": None, "category": None, "contains": [], "aliases": ["tomato"]}]


OPTIONS = matching.IngredientTable.fromSeed([
    {"name": "sugar"}, {"name": "brown sugar", "parent": "sugar"}, {"name": "salt"},
    {"name": "black pepper", "aliases": ["pepper"]}, {"name": "bell pepper"}, {"name": "lemon"},
    {"name": "sweet and sour sauce", "contains": ["soy"]}, {"name": "cream"}, {"name": "half and half"},
], PREP, set(RULES["modifierWords"]))


def ids(*names):
    return [OPTIONS.aliases[matching.normaliseName(n, PREP)] for n in names]


@pytest.mark.parametrize("name, expected", [
    ("salt and pepper", ["salt", "black pepper"]),
    ("salt & pepper", ["salt", "black pepper"]),
    ("white or brown sugar", ["sugar", "brown sugar"]),           # "white" borrows "sugar"
    ("red or yellow bell pepper", ["bell pepper"]),
    ("sweet and sour sauce", ["sweet and sour sauce"]),           # a known name is never split
    ("juice of 1 lemon", ["lemon"]),
    ("cream or half and half", ["cream", "half and half"]),     # "or" splits first, "and" only if still needed
    ("salt and/or pepper", ["salt", "black pepper"]),
])
def test_matchOptionsReadsEveryOptionALineOffers(name, expected):
    assert OPTIONS.matchOptions(name)[0] == ids(*expected)


@pytest.mark.parametrize("name, unknown", [
    ("salt and vinegar crisps", "vinegar crisp"),                 # the one option nobody knows
    ("sweet and sour pork", "sweet sour pork"),                   # no option known: the whole line
])
def test_anUnknownLineIsNamedByWhatCuratingWouldFix(name, unknown):
    assert OPTIONS.matchOptions(name) == ([], unknown)


def test_fromServerCopiesTheFdcColumns():
    payload = {"ingredients": [{"id": 1, "name": "egg", "fdcId": 900003, "fdcFrom": "owner"},
                               {"id": 2, "name": "salt"}], "aliases": []}
    t = matching.IngredientTable.fromServer(payload, PREP)
    assert (t.rows[1]["fdcId"], t.rows[1]["fdcFrom"]) == (900003, "owner")
    assert (t.rows[2]["fdcId"], t.rows[2]["fdcFrom"]) == (None, None)


# The recipe sites' drinks name spirits the old drink database did not (2026-11-20): 159 shown "cocktails" had unknown
# alcohol, so alcohol-free ones were filed as cocktails.
@pytest.mark.parametrize("name, expected", [
    ("blanco tequila", "tequila"), ("tequila blanco", "tequila"), ("reposado tequila", "tequila"),
    ("silver tequila", "tequila"), ("bottle vodka", "vodka"), ("bottle gin", "gin"), ("pink gin", "gin"),
    ("orange liqueur", "triple sec"), ("irish cream liqueur", "irish cream"), ("disaronno", "amaretto"),
    ("bottle red wine", "wine"), ("bottle prosecco", "champagne"), ("espadin mezcal", "mezcal"),
])
def test_theSitesSpiritNamesAreKnown(name, expected):
    ingredientId, _ = REAL.match(name)
    assert ingredientId is not None and ingredientId == REAL.match(expected)[0]


@pytest.mark.parametrize("name", ["pimm s", "limoncello", "hazelnut liqueur", "ginger wine", "poitin"])
def test_newSpiritsAreAlcohol(name):
    ingredientId, _ = REAL.match(name)
    assert ingredientId is not None and "alcohol" in REAL.containsOf(ingredientId)


def test_anAlcoholFreeSpiritIsNotTheSpirit():
    assert REAL.match("non alcoholic gin")[0] != REAL.match("gin")[0]


@pytest.mark.parametrize("line, name", [
    ("mint sprig", "mint"), ("strawberries hulled and halved", "strawberry"), ("ice to serve", "ice"),
    ("lemon wheels", "lemon"), ("sparkling water to top up", "sparkling water"), ("golden caster sugar", "sugar"),
])
def test_drinkGarnishWordsAreIgnored(line, name):
    # the words drink recipes add to an ingredient (2026-11-20: these left soft drinks with unknown lines)
    real = matching.IngredientTable.fromSeed(RULES["ingredients"], PREP, RULES["modifierWords"])
    ids, _ = real.matchOptions(line)
    assert ids and ids[0] == real.matchOptions(name)[0][0]
