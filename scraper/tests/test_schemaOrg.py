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
