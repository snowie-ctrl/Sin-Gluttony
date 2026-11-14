from types import SimpleNamespace

import pytest

import rulesData
from models import Skipped
from sources import schemaSite
from conftest import FIXTURES

UNITS = rulesData.load()["unitMap"]
SITES_DIR = FIXTURES / "sites"
WPRM = (SITES_DIR / "schema-wprm.html").read_text(encoding="utf-8")
PLAIN = (SITES_DIR / "schema-plain.html").read_text(encoding="utf-8")
SITE = {"site": "testsite", "name": "Test Site", "host": "www.example-recipes.test", "sitemaps": [],
        "recipeUrl": "^https://www\\.example-recipes\\.test/[a-z0-9-]+/$", "parser": "schema", "kind": "food",
        "enabled": True}
WPRM_URL = "https://www.example-recipes.test/made-up-lemon-test-chicken/"
PLAIN_URL = "https://www.example-recipes.test/made-up-test-pasta-bake/"


def amounts(recipe):
    return [(line.quantity, line.unit, line.name, line.note) for line in recipe.ingredients]


def test_aWprmPageBecomesARecipe():
    r = schemaSite.extractSchema(WPRM, WPRM_URL, SITE, UNITS)
    assert (r.source, r.sourceId, r.kind, r.title) == ("testsite", schemaSite.sourceIdFor(WPRM_URL), "food",
                                                       "Made-up Lemon Test Chicken")
    assert (r.sourceUrl, r.licence, r.credit, r.imageCredit) == (WPRM_URL, "personal use", "Test Site", "Test Site")
    assert r.description == "A made-up recipe written for Gluttony's tests."
    assert r.imageUrl == "https://www.example-recipes.test/wp-content/uploads/made-up-test-chicken.jpg"
    assert (r.prepMinutes, r.cookMinutes, r.totalMinutes, r.timeFrom) == (10, 25, 35, "source")
    assert (r.servings, r.servingsFrom) == (4, "source")
    assert amounts(r) == [(500.0, "g", "chicken thighs", None), (1.0, "tbsp", "olive oil", None),
                          (2.0, "clove", "garlic", "minced"), (1.0, "cup", "chicken stock", None),
                          (0.5, "tsp", "salt", None)]
    texts = [step.text for step in r.steps]
    assert "Pour in the stock and simmer for 20 minutes." in texts and len(texts) >= 3
    assert r.nutrition == {"calories": 410.0, "proteinG": 32.0, "carbsG": 6.0, "fatG": 28.0, "satFatG": 7.0,
                           "fibreG": 1.0, "sugarG": 2.0, "sodiumMg": 640.0}
    assert r.hints["tags"] == ["made-up", "test dinner"]


def test_aPlainSchemaPageBecomesARecipe():
    r = schemaSite.extractSchema(PLAIN, PLAIN_URL, SITE, UNITS)
    assert r.title == "Made-up Test Pasta Bake"
    assert r.imageUrl == "https://images.example-food.test/made-up-test-pasta-bake.jpg"
    assert (r.prepMinutes, r.cookMinutes, r.totalMinutes) == (15, 60, 75)
    assert (r.servings, r.servingsFrom) == (2, "source")
    assert amounts(r) == [(300.0, "g", "dried pasta", None), (1.0, "tbsp", "olive oil", None),
                          (2.0, None, "garlic cloves", "crushed"), (50.0, "g", "parmesan", "grated")]
    assert r.nutrition["sodiumMg"] == 471.6 and r.nutrition["calories"] == 612.0


def test_entitiesAndTagsInThePageTextAreCleaned():
    page = PLAIN.replace('"name":"Made-up Test Pasta Bake"', '"name":"Made-up Test Pasta &amp; Bake"')
    r = schemaSite.extractSchema(page, PLAIN_URL, SITE, UNITS)
    assert r.title == "Made-up Test Pasta & Bake"
    assert r.description == "A made-up weeknight bake written for Gluttony's tests & nothing else."
    assert r.steps[0].text == "Heat the oven to 200C."


def test_aRelativePictureAddressIsMadeAbsolute():
    page = PLAIN.replace("https://images.example-food.test/made-up-test-pasta-bake.jpg", "/images/made-up-bake.jpg")
    r = schemaSite.extractSchema(page, PLAIN_URL, SITE, UNITS)
    assert r.imageUrl == "https://www.example-recipes.test/images/made-up-bake.jpg"


def test_groupsFromTheRecipeCardBecomeHeadings():
    scraper = SimpleNamespace(
        ingredient_groups=lambda: [SimpleNamespace(ingredients=["500 g chicken thighs"], purpose="Chicken"),
                                   SimpleNamespace(ingredients=["1/2 tsp salt"], purpose="Sauce")],
        ingredients=lambda: ["500 g chicken thighs", "1/2 tsp salt"])
    lines = schemaSite.ingredientLines(scraper, UNITS)
    assert [(line.name, line.group) for line in lines] == [("chicken thighs", "Chicken"), ("salt", "Sauce")]


def test_headingLinesInsideTheIngredientListBecomeGroups():
    def noGroups():
        raise AttributeError("this site has no groups")
    scraper = SimpleNamespace(ingredient_groups=noGroups,
                              ingredients=lambda: ["300g dried pasta", "For the dressing:", "2 tbsp olive oil"])
    lines = schemaSite.ingredientLines(scraper, UNITS)
    assert [(line.name, line.group) for line in lines] == [("dried pasta", None), ("olive oil", "For the dressing")]


def test_aPageWithoutARecipeIsSkipped():
    with pytest.raises(Skipped):
        schemaSite.extractSchema("<html><head><title>Made-up</title></head><body><p>Made-up post.</p></body></html>",
                                 PLAIN_URL, SITE, UNITS)


def test_aRecipeWithoutIngredientsIsSkipped():
    page = PLAIN.replace('"300g dried pasta","1 tbsp olive oil","2 garlic cloves, crushed","50g parmesan, grated"', "")
    with pytest.raises(Skipped):
        schemaSite.extractSchema(page, PLAIN_URL, SITE, UNITS)


@pytest.mark.parametrize("url, page", [
    ("https://www.bbcgoodfood.com/recipes/made-up-test-pasta-bake", PLAIN),
    ("https://www.budgetbytes.com/made-up-lemon-test-chicken/", WPRM),
    ("https://www.recipetineats.com/made-up-lemon-test-chicken/", WPRM),
    ("https://pinchofyum.com/made-up-lemon-test-chicken", WPRM),
    ("https://www.loveandlemons.com/made-up-lemon-test-chicken/", WPRM),
])
def test_eachMealSiteReadsAPageInItsShape(url, page):
    """recipe-scrapers has its own class for each of these hosts; the shaped fixture must satisfy it too."""
    r = schemaSite.extractSchema(page, url, SITE, UNITS)
    assert r.title.startswith("Made-up") and len(r.ingredients) >= 4 and r.steps and r.totalMinutes


def test_everySiteFixtureIsMadeUp():
    """Fixtures copy a site's structure, never its text."""
    for path in SITES_DIR.glob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "Made-up" in text, path.name
        for host in ("bbcgoodfood.com", "budgetbytes.com", "recipetineats.com", "pinchofyum.com", "loveandlemons.com", "diffordsguide.com"):
            assert host not in text, path.name


def test_aTickBoxGlyphInFrontOfAnIngredientLineIsDropped():
    lines = schemaSite.linesFrom(["▢ 2 cups made-up flour", "☐ 1 tablespoon made-up oil, melted"], UNITS)
    assert [l.quantity for l in lines] == [2, 1]
    assert all("▢" not in l.name and "☐" not in l.name for l in lines)
    assert [l.name for l in lines][0].startswith("made-up flour")
