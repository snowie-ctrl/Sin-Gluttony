import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import findBasics  # noqa: E402

LISTINGS = {
    "bbcgoodfood": [("https://www.bbcgoodfood.com/recipes/scrambled-eggs-with-made-up-salmon", None),
                    ("https://www.bbcgoodfood.com/recipes/perfect-scrambled-eggs", None),
                    ("https://www.bbcgoodfood.com/recipes/pancakes", None)],
    "recipetineats": [("https://www.recipetineats.com/scrambled-eggs/", None),
                      ("https://www.recipetineats.com/pancakes/", None),
                      ("https://www.recipetineats.com/made-up-potato-pancakes-with-four-extra-words/", None)],
}


def test_slugOfTakesTheLastPathPart():
    assert findBasics.slugOf("https://www.recipetineats.com/scrambled-eggs/") == "scrambled-eggs"
    assert findBasics.slugOf("https://www.bbcgoodfood.com/recipes/Pancakes") == "pancakes"


def test_theSlugWithFewestExtraWordsWins():
    assert findBasics.candidates(r"scrambled-eggs?", LISTINGS)[0][2] == "https://www.recipetineats.com/scrambled-eggs/"


def test_aTieGoesToTheEarlierSite():
    assert findBasics.candidates(r"pancakes?", LISTINGS)[0][2] == "https://www.bbcgoodfood.com/recipes/pancakes"


def test_aSlugWithTooManyExtraWordsIsNotABasic():
    found = [url for _, _, url in findBasics.candidates(r"pancakes?", LISTINGS)]
    assert "https://www.recipetineats.com/made-up-potato-pancakes-with-four-extra-words/" not in found


def test_aBasicNoSiteHasIsRecordedWithoutAUrl():
    chosen = findBasics.chooseBasics(LISTINGS, [("scrambled eggs", r"scrambled-eggs?"), ("toast", r"toast")])
    assert chosen == [{"name": "scrambled eggs", "url": "https://www.recipetineats.com/scrambled-eggs/",
                       "urls": ["https://www.recipetineats.com/scrambled-eggs/",
                                "https://www.bbcgoodfood.com/recipes/perfect-scrambled-eggs"]},
                      {"name": "toast", "url": None, "urls": []}]


def test_frenchToastIsNotToast():
    listings = {"bbcgoodfood": [("https://www.bbcgoodfood.com/recipes/french-toast", None)]}
    toast = [basic for basic in findBasics.BASICS if basic[0] == "toast"]
    assert findBasics.chooseBasics(listings, toast) == [{"name": "toast", "url": None, "urls": []}]


def test_thereAreAboutFiftyBasics():
    assert 45 <= len(findBasics.BASICS) <= 60
    assert len({name for name, _ in findBasics.BASICS}) == len(findBasics.BASICS)


def test_aWholeSlugPatternIsNotMatchedInsideAnotherDish():
    listings = {"bbcgoodfood": [("https://www.bbcgoodfood.com/recipes/avocado-toast", None),
                                ("https://www.bbcgoodfood.com/recipes/fried-egg-milanese", None)]}
    chosen = findBasics.chooseBasics(listings, [b for b in findBasics.BASICS if b[0] in ("toast", "fried eggs")])
    assert [item["url"] for item in chosen] == [None, None]


def test_aHomemadePrefixIsAllowedAndAnEarlierSiteDoesNotBeatAnEqualSlug():
    listings = {"bbcgoodfood": [("https://www.bbcgoodfood.com/recipes/vegan-banana-bread", None)],
                "budgetbytes": [("https://www.budgetbytes.com/homemade-banana-bread/", None)]}
    banana = [b for b in findBasics.BASICS if b[0] == "banana bread"]
    assert findBasics.chooseBasics(listings, banana)[0]["url"] == "https://www.budgetbytes.com/homemade-banana-bread/"


def test_chunkyAndBestEverOvenChipsAreChipsButCeriacOvenChipsAreNot():
    chips = [b for b in findBasics.BASICS if b[0] == "chips"]
    for slug in ("chunky-oven-chips", "best-ever-oven-chips", "oven-chips"):
        listings = {"bbcgoodfood": [(f"https://www.bbcgoodfood.com/recipes/{slug}", None)]}
        assert findBasics.chooseBasics(listings, chips)[0]["url"].endswith(slug)
    for slug in ("celeriac-oven-chips", "sweet-potato-chips"):
        listings = {"bbcgoodfood": [(f"https://www.bbcgoodfood.com/recipes/{slug}", None)]}
        assert findBasics.chooseBasics(listings, chips)[0]["url"] is None


def test_chooseBasicsKeepsTheBestPageOfEachSiteAndTheFirstAsUrl():
    listings = {"bbcgoodfood": [(f"https://www.bbcgoodfood.com/recipes/{slug}", None)
                                for slug in ("easy-pancakes", "pancakes", "classic-pancakes", "best-pancakes")],
                "recipetineats": [("https://www.recipetineats.com/pancakes/", None)]}
    item = findBasics.chooseBasics(listings, [("pancakes", r"pancakes?")])[0]
    assert item["urls"] == ["https://www.bbcgoodfood.com/recipes/pancakes",
                            "https://www.recipetineats.com/pancakes/"]
    assert item["url"] == item["urls"][0]


def test_noveltyVariantsAreNotTakenForTheBasic():
    listings = {"bbcgoodfood": [("https://www.bbcgoodfood.com/recipes/mac-n-cheese-bites", None),
                                ("https://www.bbcgoodfood.com/recipes/christmas-baked-salmon", None),
                                ("https://www.bbcgoodfood.com/recipes/baked-salmon-fajita-spread", None),
                                ("https://www.bbcgoodfood.com/recipes/keto-vanilla-cake", None)]}
    wanted = [b for b in findBasics.BASICS if b[0] in ("macaroni cheese", "salmon", "sponge cake")]
    assert [item["urls"] for item in findBasics.chooseBasics(listings, wanted)] == [[], [], []]
    plain = {"bbcgoodfood": [("https://www.bbcgoodfood.com/recipes/mac-and-cheese", None),
                             ("https://www.bbcgoodfood.com/recipes/baked-salmon", None),
                             ("https://www.bbcgoodfood.com/recipes/victoria-sponge-cake", None)]}
    assert all(len(item["urls"]) == 1 for item in findBasics.chooseBasics(plain, wanted))


def test_aRecipeSuffixOnAPancakeStirFryVinaigretteOrSmoothieSlugStillMakesItTheBasic():
    for name, slug in (("pancakes", "pancakes-recipe"), ("stir fry", "stir-fry-recipe"),
                       ("vinaigrette", "balsamic-vinaigrette"), ("smoothie", "best-green-smoothie-recipe")):
        basic = [b for b in findBasics.BASICS if b[0] == name]
        listings = {"loveandlemons": [(f"https://www.loveandlemons.com/{slug}/", None)]}
        assert findBasics.chooseBasics(listings, basic)[0]["url"].endswith(f"/{slug}/"), name
    pancakes = [b for b in findBasics.BASICS if b[0] == "pancakes"]
    listings = {"loveandlemons": [("https://www.loveandlemons.com/mashed-potato-pancakes/", None),
                                  ("https://www.loveandlemons.com/made-up-pancakes-recipe-ideas/", None)]}
    assert findBasics.chooseBasics(listings, pancakes)[0]["url"] is None
