import pytest

import adaptWikibooks
import rulesData
from models import Skipped

UNITS = rulesData.load()["unitMap"]

PAGE = """{{recipe summary
| Name = Grilled Cheese Sandwich
| Category = Sandwich recipes
| Servings = 2
| Time = Prep: 5 minutes<br>Cooking: 10 minutes
| Difficulty = 2
| Image = [[File:Grilled cheese.jpg|300px]]
| Cuisine = American
}}
A quick lunch.

== Ingredients ==
* 4 [[Cookbook:Slice|slices]] [[Cookbook:Bread|bread]]
* {{convert|50|g}} [[Cookbook:Butter|butter]], softened
=== For the filling ===
* 2 slices [[Cookbook:Cheddar Cheese|cheddar]] &amp; Swiss<ref>Any melting cheese works.</ref>

== Procedure ==
# Butter the bread.<br>
# Fry until golden.
## Turn once.

[[Category:Sandwich recipes]]
[[Category:Recipes using cheese]]
"""


def raw(text, title="Cookbook:Grilled Cheese Sandwich"):
    return {"source": "wikibooks", "sourceId": title, "revision": "1", "timestamp": "t", "wikitext": text}


def test_cleanTurnsMarkupIntoPlainWords():
    assert adaptWikibooks.clean("{{convert|50|g}} [[Cookbook:Butter|butter]], softened") == "50 g butter, softened"
    assert adaptWikibooks.clean("[[Cookbook:Cheddar Cheese|cheddar]] &amp; Swiss<ref>note</ref>") == "cheddar & Swiss"
    assert adaptWikibooks.clean("Butter the bread.<br>") == "Butter the bread."
    assert adaptWikibooks.clean("Prep: 5 minutes<br>Cooking: 10 minutes") == "Prep: 5 minutes Cooking: 10 minutes"
    assert adaptWikibooks.clean("[[Cookbook:Salt]] to taste") == "Salt to taste"


def test_aRecipePageBecomesARecipe():
    recipe = adaptWikibooks.adaptPage(raw(PAGE), UNITS)
    assert (recipe.kind, recipe.title, recipe.servings, recipe.servingsFrom) == \
        ("food", "Grilled Cheese Sandwich", 2, "source")
    assert [(i.quantity, i.unit, i.name, i.note, i.group) for i in recipe.ingredients] == [
        (4.0, "slice", "bread", None, None),
        (50.0, "g", "butter", "softened", None),
        (2.0, "slice", "cheddar & Swiss", None, "For the filling")]
    assert [s.text for s in recipe.steps] == ["Butter the bread.", "Fry until golden.", "Turn once."]
    assert recipe.hints["timeText"] == "Prep: 5 minutes Cooking: 10 minutes"
    assert recipe.hints["difficultyRating"] == 2
    assert recipe.hints["imageFile"] == "Grilled cheese.jpg"
    assert recipe.hints["cuisineText"] == "American"
    assert "Recipes using cheese" in recipe.hints["categories"] and "Sandwich recipes" in recipe.hints["categories"]
    assert recipe.licence == "CC BY-SA 4.0"
    assert recipe.sourceUrl == "https://en.wikibooks.org/wiki/Cookbook:Grilled_Cheese_Sandwich"


def test_aTopicPageIsSkipped():
    with pytest.raises(Skipped, match="topic page"):
        adaptWikibooks.adaptPage(raw("{{cookdp}}\n== Ingredients ==\n* milk\n== Procedure ==\n# stir"), UNITS)


def test_aPageWithoutStepsIsSkipped():
    with pytest.raises(Skipped, match="no steps"):
        adaptWikibooks.adaptPage(raw("{{recipe summary}}\n== Ingredients ==\n* milk\n"), UNITS)


def test_aDrinkCategoryMakesADrink():
    text = "{{recipe summary}}\n== Ingredients ==\n* 1 cup milk\n== Procedure ==\n# Stir.\n[[Category:Beverage recipes]]"
    assert adaptWikibooks.adaptPage(raw(text, "Cookbook:Warm Milk"), UNITS).kind == "drink"


def test_aDifficultyOutsideOneToFiveIsIgnored():
    text = "{{recipe summary|Difficulty=9}}\n== Ingredients ==\n* milk\n== Procedure ==\n# Stir."
    assert adaptWikibooks.adaptPage(raw(text), UNITS).hints["difficultyRating"] is None


def test_servingsOutsideOneToHundredAreDropped():
    for field in ("Servings = 0", "Yield = 2000 g"):
        text = "{{recipe summary|" + field + "}}\n== Ingredients ==\n* milk\n== Procedure ==\n# Stir."
        recipe = adaptWikibooks.adaptPage(raw(text), UNITS)
        assert (recipe.servings, recipe.servingsFrom) == (None, None)
