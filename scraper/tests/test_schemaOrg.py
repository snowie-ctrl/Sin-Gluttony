import pytest

from sources import schemaOrg


@pytest.mark.parametrize("value, minutes", [
    ("PT1H30M", 90), ("PT45M", 45), ("P0DT0H5M", 5), ("PT90S", 2), ("P1D", 1440), ("PT0S", None),
    (25, 25), ("10", 10), (None, None), ("", None), ("soon", None), (0, None),
])
def test_isoMinutes(value, minutes):
    assert schemaOrg.isoMinutes(value) == minutes


@pytest.mark.parametrize("value, servings", [
    ("4 servings", 4), (["4", "4 servings"], 4), (6, 6), ("Serves 2-3", 2), ("Makes one loaf", None),
    (None, None), ("0", None), ([], None),
])
def test_servingsOf(value, servings):
    assert schemaOrg.servingsOf(value) == servings


@pytest.mark.parametrize("value, url", [
    ("https://x.test/a.jpg", "https://x.test/a.jpg"),
    (["https://x.test/a.jpg", "https://x.test/b.jpg"], "https://x.test/a.jpg"),
    ({"@type": "ImageObject", "url": "https://x.test/c.jpg"}, "https://x.test/c.jpg"),
    ([{"@type": "ImageObject", "contentUrl": "https://x.test/d.jpg"}], "https://x.test/d.jpg"),
    (None, None), ([], None), ("  ", None),
])
def test_imageOf(value, url):
    assert schemaOrg.imageOf(value) == url


def test_stepsOfReadsEveryShape():
    assert [s.text for s in schemaOrg.stepsOf("Chop.\nFry.\n\n")] == ["Chop.", "Fry."]
    steps = schemaOrg.stepsOf([
        {"@type": "HowToSection", "name": "Sauce", "itemListElement": [{"@type": "HowToStep", "text": "<p>Stir&nbsp;well.</p>"}]},
        {"@type": "HowToStep", "text": "Serve &amp; enjoy."},
        "Wash up.",
    ])
    assert [(s.text, s.group) for s in steps] == [("Stir well.", "Sauce"), ("Serve & enjoy.", None), ("Wash up.", None)]


def test_cleanDecodesEntitiesAndDropsTags():
    assert schemaOrg.clean("Mac &amp; Cheese") == "Mac & Cheese"
    assert schemaOrg.clean("<p>Gluttony&#039;s  <b>test</b></p>") == "Gluttony's test"
    assert schemaOrg.clean(None) == ""


def test_keywordsAndJoinedLists():
    assert schemaOrg.keywordsOf("made-up, test dinner") == ["made-up", "test dinner"]
    assert schemaOrg.keywordsOf([" a ", "b", ""]) == ["a", "b"]
    assert schemaOrg.keywordsOf(None) == []
    assert schemaOrg.joined(["Cocktail", "Sour"]) == "Cocktail, Sour"
    assert schemaOrg.joined("Dinner") == "Dinner"
    assert schemaOrg.joined([]) is None


def test_nutritionOfReadsTheSitesPerServingValues():
    assert schemaOrg.nutritionOf({"@type": "NutritionInformation", "calories": "1,250 kcal", "proteinContent": "32 g",
                                  "carbohydrateContent": "6.5g", "fatContent": "28 g", "saturatedFatContent": "7 g",
                                  "fiberContent": "1 g", "sugarContent": "2 g", "sodiumContent": "640 mg"}) == {
        "calories": 1250.0, "proteinG": 32.0, "carbsG": 6.5, "fatG": 28.0, "satFatG": 7.0, "fibreG": 1.0,
        "sugarG": 2.0, "sodiumMg": 640.0}


def test_saltBecomesSodiumAndGramsOfSodiumBecomeMilligrams():
    assert schemaOrg.nutritionOf({"calories": "300", "saltContent": "1.2 g"})["sodiumMg"] == 471.6
    assert schemaOrg.nutritionOf({"calories": "300", "sodiumContent": "0.45 g"})["sodiumMg"] == 450.0


def test_noCaloriesMeansNoNutrition():
    assert schemaOrg.nutritionOf({"proteinContent": "10 g"}) is None
    assert schemaOrg.nutritionOf(None) is None
    assert schemaOrg.nutritionOf("400 kcal") is None


def _page(image, og=""):
    import json
    ld = json.dumps({"@type": "Recipe", "name": "Made-up", "image": image})
    return f'<html><head><script type="application/ld+json">{ld}</script>{og}</head></html>'


def _best(html):
    return schemaOrg.bestImage(html, schemaOrg.recipeJsonLd(html))


def test_bestImageTakesTheWidestImageObject():
    html = _page([{"@type": "ImageObject", "url": "https://x.test/a.jpg?resize=768,713", "width": 768, "height": 713},
                  {"@type": "ImageObject", "url": "https://x.test/a.jpg?resize=900,836", "width": 900, "height": 836}])
    assert _best(html) == "https://x.test/a.jpg?resize=900,836"


def test_bestImageReadsSizeHintsInTheAddress():
    html = _page(["https://x.test/a-500x500.jpg", "https://x.test/a-1200x900.jpg", "https://x.test/a.jpg?resize=480%2C270"])
    assert _best(html) == "https://x.test/a-1200x900.jpg"


def test_bestImageUsesTheOgImageAndItsStatedWidthForTheSameAddress():
    og = ('<meta property="og:image" content="https://x.test/plain.jpg">'
          '<meta property="og:image:width" content="1200">')
    html = _page(["https://x.test/plain.jpg", "https://x.test/plain.jpg?fit=225%2C225"], og)
    assert _best(html) == "https://x.test/plain.jpg"


def test_bestImageFindsALargerOgImageThanTheSchemaOne():
    og = '<meta property="og:image" content="https://x.test/cocktail/AbC/lifestyle/0/1024x.webp">'
    html = _page({"@type": "ImageObject", "url": "https://x.test/cocktail/AbC/square/0/512x512.webp", "width": 512}, og)
    assert _best(html) == "https://x.test/cocktail/AbC/lifestyle/0/1024x.webp"


def test_bestImageKeepsTheFirstWhenNoSizeIsKnown():
    assert _best(_page(["https://x.test/one.jpg", "https://x.test/two.jpg"])) == "https://x.test/one.jpg"


def test_bestImageWithNoImageIsNone():
    assert _best(_page(None)) is None
