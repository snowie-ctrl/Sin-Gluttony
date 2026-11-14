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


def test_aGlassHeadingHasOnlyAPhotoCaptionNextAndTheGlassIsInThePreChillStep():
    # the real pages: a "Glass" heading, a "Photographed in ..." caption (the prop, not the glass), and the glass
    # named in the method's first step, upper-cased and sometimes with a size in brackets
    body = ("<h3>Glass</h3><p>Photographed in a Made-up Retro Coupe</p>"
            "<ol><li>Select and pre-chill a HIGHBALL (MAX 10OZ/300ML) GLASS.</li><li>STIR.</li></ol>")
    assert difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES).glass == "Highball glass"


def test_aServeInLineStillGivesTheGlass():
    body = '<section><h3>Serve in a <a href="/made-up">Rocks glass</a></h3></section>'
    assert difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES).glass == "Rocks glass"


def test_aPreChillLineThatIsNotAGlassIsIgnored():
    body = "<p>Select and pre-chill the made-up ingredients and then relax for a good long while, as the saying goes.</p>"
    assert difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES).glass is None


@pytest.mark.parametrize("sentence", [
    "Select and pre-chill the shaker.", "Select and pre-chill your freezer.", "Select and pre-chill ingredients.",
    "Select and pre-chill a COUPE.", "Select and pre-chill a made-up thing"])
def test_aPreChillSentenceWithoutTheWordGlassSetsNoGlass(sentence):
    body = f"<ol><li>{sentence}</li></ol>"
    assert difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES).glass is None


def test_theGlassIsCutAtTheFirstFullStop():
    body = "<ol><li>Select and pre-chill a COUPE GLASS. SHAKE with ice and strain.</li></ol>"
    assert difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES).glass == "Coupe glass"


def test_theGarnishNameComesFromThePrepareGarnishStep():
    body = ("<ol><li>Select and pre-chill a COUPE GLASS.</li><li>Prepare garnish of lime wedge and mint sprig.</li></ol>"
            "<h3>Garnish</h3><p>Garnish with lime wedge on the rim and add a made-up stirrer for the drinker.</p>")
    r = difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES)
    assert [(l.name, l.group, l.optional) for l in r.ingredients[-1:]] == [("lime wedge and mint sprig", "Garnish", True)]


def test_withoutAPrepareGarnishStepTheGarnishTextIsUsedAsBefore():
    body = "<h3>Garnish</h3><p>Orange slice</p>"
    r = difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES)
    assert r.ingredients[-1].name == "Orange slice" and r.ingredients[-1].group == "Garnish"


def test_theLargestPictureThePageOffersIsUsed():
    page = drinkPage("STIR.", image={"@type": "ImageObject", "url": "https://images.example-drinks.test/x/square/512x512.webp",
                                     "width": 512, "height": 512})
    page = page.replace("</head>", '<meta property="og:image" content="https://images.example-drinks.test/x/lifestyle/1024x.webp"></head>')
    assert difford.extractDifford(page, URL, SITE, UNITS, RULES).imageUrl == "https://images.example-drinks.test/x/lifestyle/1024x.webp"


@pytest.mark.parametrize("sentence, name", [
    ("Garnish with lime wedge on rim", "lime wedge on rim"),
    ("Garnish each individual serve with an orange slice wheel", "an orange slice wheel"),
    ("Serve naked, without garnish", None),
])
def test_aGarnishSentenceWithoutAPrepareStepIsReducedToTheGarnish(sentence, name):
    body = f"<h3>Garnish</h3><p>{sentence}</p>"
    ingredients = difford.extractDifford(drinkPage("STIR.", body=body), URL, SITE, UNITS, RULES).ingredients
    garnish = [l.name for l in ingredients if l.group == "Garnish"]
    assert garnish == ([name] if name else [])
