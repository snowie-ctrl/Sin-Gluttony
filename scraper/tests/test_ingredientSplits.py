"""
Names that used to share one ingredient but are different foods: an egg yolk
is not a whole egg, puff pastry is not shortcrust. Each is a child of the
general ingredient, so it keeps the parent's facts (an egg yolk contains egg)
but gets its own USDA food.
"""
import pytest

import matching
import rulesData

RULES = rulesData.load()
TABLE = matching.IngredientTable.fromSeed(RULES["ingredients"], set(RULES["prepWords"]), RULES["modifierWords"])


def nameOf(line):
    ingredientId, _ = TABLE.match(line)
    return TABLE.rows[ingredientId]["name"] if ingredientId else None


@pytest.mark.parametrize("line, expected, parent", [
    ("2 large egg yolks", "egg yolk", "egg"),
    ("yolk", "egg yolk", "egg"),
    ("1 egg white", "egg white", "egg"),
    ("pasteurised egg white", "egg white", "egg"),
    ("eggs", "egg", None),
    ("single cream", "single cream", "cream"),
    ("double cream", "cream", None),
    ("dried breadcrumbs", "breadcrumbs", "bread"),
    ("panko breadcrumbs", "breadcrumbs", "bread"),
    ("crusty bread", "bread", None),
    ("ground ginger", "ground ginger", "ginger"),
    ("fresh root ginger", "ginger", None),
    ("creamed coconut", "creamed coconut", "coconut cream"),
    ("cream of coconut", "cream of coconut", "coconut cream"),
    ("coconut cream", "coconut cream", "coconut"),
    ("ready-rolled puff pastry", "puff pastry", "pastry"),
    ("shortcrust pastry", "pastry", None),
])
def test_eachNameFindsItsOwnIngredient(line, expected, parent):
    assert nameOf(line) == expected
    ingredientId, _ = TABLE.match(line)
    parentId = TABLE.rows[ingredientId]["parentId"]
    if parent:
        assert TABLE.rows[parentId]["name"] == parent


def test_aChildKeepsItsParentsFacts():
    yolk, _ = TABLE.match("egg yolk")
    assert "egg" in TABLE.containsOf(yolk)
    puff, _ = TABLE.match("puff pastry")
    assert {"gluten", "dairy"} <= TABLE.containsOf(puff)


def test_everyUsdaOverrideNamesASeedIngredient():
    names = {entry["name"] for entry in RULES["ingredients"]}
    assert set(RULES["fdcMap"]) - names == set()


def test_eachSplitHasItsOwnUsdaFood():
    fdcMap = RULES["fdcMap"]
    for child, parent in [("egg yolk", "egg"), ("egg white", "egg"), ("single cream", "cream"),
                          ("breadcrumbs", "bread"), ("ground ginger", "ginger"), ("puff pastry", "pastry"),
                          ("creamed coconut", "coconut cream"), ("cream of coconut", "coconut cream")]:
        assert fdcMap[child]["fdcId"] != fdcMap[parent]["fdcId"], child
