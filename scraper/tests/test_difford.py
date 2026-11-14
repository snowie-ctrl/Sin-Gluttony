import json

import pytest

import rulesData
from models import Skipped
from sources import difford, schemaSite
from conftest import FIXTURES

RULES = rulesData.load()
UNITS = RULES["unitMap"]
PAGE = (FIXTURES / "sites" / "difford.html").read_text(encoding="utf-8")
SITE = {"site": "difford", "name": "Difford's Guide", "host": "www.example-drinks.test", "sitemaps": [],
        "recipeUrl": "^https://www\\.example-drinks\\.test/cocktails/recipe/[0-9]+/[a-z0-9-]+$",
        "parser": "difford", "kind": "drink", "enabled": True}
URL = "https://www.example-drinks.test/cocktails/recipe/1/made-up-test-sour"


def drinkPage(steps, total=None, recipeYield=None, image="https://images.example-drinks.test/made-up.jpg",
              name="Made-up Test Drink", body=""):
    data = {"@context": "https://schema.org", "@type": "Recipe", "name": name, "image": image,
            "recipeIngredient": ["2 fl oz Made-up rum", "1 fl oz Lime juice"],
            "recipeInstructions": [{"@type": "HowToStep", "text": steps}]}
    if total:
        data["totalTime"] = total
    if recipeYield:
        data["recipeYield"] = recipeYield
    return (f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head>'
            f"<body>{body}</body></html>")


def test_aDiffordsPageBecomesADrink():
    r = difford.extractDifford(PAGE, URL, SITE, UNITS, RULES)
    assert (r.source, r.sourceId, r.kind, r.title) == ("difford", schemaSite.sourceIdFor(URL), "drink", "Made-up Test Sour")
    assert (r.licence, r.credit, r.imageCredit) == ("personal use", "Difford's Guide", "Difford's Guide")
    assert r.description == "A made-up sour written for Gluttony's tests."
    assert r.imageUrl == "https://images.example-drinks.test/made-up-test-sour.jpg"
    assert r.glass == "Coupe glass"
    assert [(l.quantity, l.unit, l.name, l.note, l.optional, l.group) for l in r.ingredients] == [
        (2.0, "fl oz", "Made-up gin", None, False, None),
        (0.75, "fl oz", "Lemon juice", "freshly squeezed", False, None),
        (0.5, "fl oz", "Sugar syrup", None, False, None),
        (1.0, "dash", "Aromatic bitters", None, False, None),
        (None, None, "Lemon zest twist", None, True, "Garnish")]
    assert r.hints["method"] == "shaken"
    assert (r.totalMinutes, r.timeFrom, r.servings, r.servingsFrom) == (3, "source", 1, "source")
    assert r.nutrition is None


def test_aLabelledGlassAndGarnishAreReadToo():
    body = "<div><span>Glass:</span> <span>Rocks glass</span></div><div>Garnish: Orange slice.</div>"
    r = difford.extractDifford(drinkPage("STIR with ice.", body=body), URL, SITE, UNITS, RULES)
    assert r.glass == "Rocks glass"
    assert r.ingredients[-1].name == "Orange slice" and r.ingredients[-1].group == "Garnish"


@pytest.mark.parametrize("steps, method, minutes", [
    ("STIR all ingredients with ice and strain.", "stirred", 4),
    ("POUR ingredients into an ice-filled glass.", "built", 3),
    ("BLEND all ingredients with crushed ice.", "blended", 5),
    ("SHAKE with ice, strain and top with soda.", "shaken", 4),
])
def test_withoutAStatedTimeTheMethodGivesIt(steps, method, minutes):
    r = difford.extractDifford(drinkPage(steps), URL, SITE, UNITS, RULES)
    assert (r.hints["method"], r.totalMinutes, r.timeFrom) == (method, minutes, "rule")
    assert (r.servings, r.servingsFrom) == (1, "rule")


def test_aStatedTimeWinsOverTheMethodRule():
    r = difford.extractDifford(drinkPage("SHAKE with ice.", total="PT6M", recipeYield="2"), URL, SITE, UNITS, RULES)
    assert (r.totalMinutes, r.timeFrom, r.servings, r.servingsFrom) == (6, "source", 2, "source")


def test_aDrinkWithNoMethodWordsLeavesTheTimeToTagging():
    r = difford.extractDifford(drinkPage("Serve."), URL, SITE, UNITS, RULES)
    assert (r.hints["method"], r.totalMinutes, r.timeFrom) == (None, None, None)


def test_aProtocolRelativePictureIsMadeAbsolute():
    r = difford.extractDifford(drinkPage("SHAKE.", image="//images.example-drinks.test/made-up.jpg"), URL, SITE,
                               UNITS, RULES)
    assert r.imageUrl == "https://images.example-drinks.test/made-up.jpg"


def test_entitiesInTheTitleAreDecoded():
    r = difford.extractDifford(drinkPage("SHAKE.", name="Made-up Test Sour &amp; Co"), URL, SITE, UNITS, RULES)
    assert r.title == "Made-up Test Sour & Co"


def test_aPageWithoutRecipeMarkupIsSkipped():
    with pytest.raises(Skipped, match="no recipe"):
        difford.extractDifford("<html><body>Made-up</body></html>", URL, SITE, UNITS, RULES)


@pytest.mark.parametrize("steps, method", [
    ("SHAKE with ice, then STIR gently.", "shaken"),      # order: blended, shaken, thrown, stirred, built
    ("STIR with ice, then BLEND.", "blended"),
    ("BUILD in the glass and TOP WITH soda.", "built"),
    ("BLEND with ice, then SHAKE.", "blended"),
])
def test_whenSeveralMethodsAppearTheEarlierOneInTheOrderWins(steps, method):
    assert difford.extractDifford(drinkPage(steps), URL, SITE, UNITS, RULES).hints["method"] == method


def test_aBareGlassLabelBeforeUnrelatedTextSetsNoGlass():
    body = "<div>Glass</div><div>Made-up unrelated text</div>"
    assert difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES).glass is None


def test_aServeInValueWithoutTheWordGlassSetsNoGlass():
    body = "<h3>Serve in a made-up jug</h3>"
    assert difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES).glass is None
