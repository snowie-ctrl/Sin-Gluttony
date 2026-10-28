import unicodedata

import pytest

import facts
import matching
import rulesData

RULES = rulesData.load()


def sameNameKey(name):
    """How MySQL's utf8mb4_0900_ai_ci sees a name: no accents, case folded."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def test_theSeedIsConsistent():
    seed = RULES["ingredients"]
    names = [e["name"] for e in seed]
    assert len(names) == len(set(names)), "a name appears twice"
    keyed = {}
    for name in names:
        clash = keyed.setdefault(sameNameKey(name), name)
        assert clash == name, f"{name!r} and {clash!r} are the same name once accents and case are dropped"
    for entry in seed:
        assert set(entry) <= {"name", "parent", "category", "contains", "aliases"}, entry["name"]
        assert entry.get("parent") is None or entry["parent"] in names, entry["name"]
        assert set(entry.get("contains", [])) <= set(facts.CONTAINS_ITEMS), entry["name"]


@pytest.mark.parametrize("name, allergens", [
    ("soy sauce", {"soy", "gluten"}),
    ("mayonnaise", {"egg"}),
    ("bread", {"gluten", "dairy", "soy"}),
    ("chocolate", {"dairy", "soy"}),
    ("beef stock", {"meat", "gluten", "soy"}),
    ("vegetable stock", {"gluten", "soy"}),
    ("beer", {"gluten", "alcohol"}),
    ("worcestershire sauce", {"fish", "gluten"}),
    ("parmesan", {"dairy", "meat"}),
    ("peanut butter", {"peanut"}),
    ("chicken stock", {"poultry", "gluten", "soy"}),
    ("pasta", {"gluten", "egg"}),
    ("shrimp", {"shellfish"}),
    ("almond", {"tree-nut"}),
    ("sesame oil", {"sesame"}),
    ("honey", {"honey"}),
])
def test_knownCarriersCarryTheirAllergens(name, allergens):
    table = matching.IngredientTable.fromSeed(RULES["ingredients"], set(RULES["prepWords"]),
                                              set(RULES["modifierWords"]))
    ingredientId, _ = table.match(name)
    assert ingredientId is not None, name
    assert allergens <= table.containsOf(ingredientId)


def test_noAliasPointsAtTwoIngredients():
    owner = {}
    for entry in matching.seedPayload(RULES["ingredients"], set(RULES["prepWords"])):
        for alias in entry["aliases"]:
            assert owner.setdefault(alias, entry["name"]) == entry["name"], \
                f"{alias!r} is claimed by {owner[alias]!r} and {entry['name']!r}"
