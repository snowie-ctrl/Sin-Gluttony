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
    assert chosen == [{"name": "scrambled eggs", "url": "https://www.recipetineats.com/scrambled-eggs/"},
                      {"name": "toast", "url": None}]


def test_frenchToastIsNotToast():
    listings = {"bbcgoodfood": [("https://www.bbcgoodfood.com/recipes/french-toast", None)]}
    toast = [basic for basic in findBasics.BASICS if basic[0] == "toast"]
    assert findBasics.chooseBasics(listings, toast) == [{"name": "toast", "url": None}]


def test_thereAreAboutFiftyBasics():
    assert 45 <= len(findBasics.BASICS) <= 60
    assert len({name for name, _ in findBasics.BASICS}) == len(findBasics.BASICS)
