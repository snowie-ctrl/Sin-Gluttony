import json
from datetime import date

import pytest

import dryrunReport
import rulesData
from models import IngredientLine, Recipe, Step

RULES = rulesData.load()
UNITS = RULES["unitMap"]
SITE = {"site": "testsite", "name": "Test Site", "kind": "food"}
DRINKS = {"site": "testdrinks", "name": "Test Drinks", "kind": "drink"}


def made(source="testsite", url="https://x.test/a/", hidden=None, lines=("salt",), **fields):
    return Recipe(source=source, sourceId=url[-3:], kind="food", title=f"Made-up {url}",
                  ingredients=[IngredientLine(line=l, name=l) for l in lines], steps=[Step(text="Cook.")],
                  sourceUrl=url, hiddenReason=hidden, **fields)


@pytest.mark.parametrize("text, pattern", [
    ("2 x 400g cans chopped tomatoes", "N x NU U w"),
    ("200g/7oz plain flour", "NU / NU w"),
    ("1 ½ tsp salt", "N N U w"),
    ("Juice of 1 lemon", "juice of N w"),
    ("1 Tbsp olive oil ($0.32)", "N U w ( $ N )"),
])
def test_linePatternGroupsLinesByShape(text, pattern):
    assert dryrunReport.linePattern(text, UNITS) == pattern


def test_siteSummaryCountsPagesRecipesAndGateReasons():
    recipes = [made(url="https://x.test/a/"), made(url="https://x.test/b/", hidden="no-time"),
               made(url="https://x.test/c/", hidden="no-nutrition", nutrition=None),
               made(source="other", url="https://y.test/a/")]
    skipped = [{"site": "testsite", "url": "https://x.test/d/", "reason": "no steps", "detail": None}]
    s = dryrunReport.siteSummary(SITE, {"fetched": 4}, recipes, skipped)
    assert (s["pages"], s["recipes"], s["notRead"], s["listed"], s["passRate"]) == (4, 3, 1, 1, 0.25)
    assert s["gate"]["no-time"] == 1 and s["gate"]["no-nutrition"] == 1 and s["gate"]["no-photo"] == 0
    assert s["notReadByReason"] == {"no steps": 1} and s["crawl"] == {"fetched": 4}
    assert "drinks" not in s


def test_aDrinkSiteReportsGlassGarnishAndMethod():
    drink = made(source="testdrinks", glass="Coupe glass", hints={"method": "shaken"})
    drink.ingredients.append(IngredientLine(line="Lime wedge", name="Lime wedge", optional=True, group="Garnish"))
    s = dryrunReport.siteSummary(DRINKS, None, [drink], [])
    assert s["drinks"] == {"withGlass": 1, "withGarnish": 1, "withMethod": 1}


def test_samplesPutListedRecipesFirstAndStopAtTen():
    recipes = [made(url=f"https://x.test/{n:02d}/", hidden="no-time" if n % 2 else None) for n in range(14)]
    chosen = dryrunReport.samples(recipes, "testsite")
    assert len(chosen) == 10 and [c["hiddenReason"] for c in chosen[:7]] == [None] * 7


def test_unparsedLinesAreGroupedByShape():
    recipes = [made(lines=("x 400g cans tomatoes", "x 200g cans beans", "salt"))]
    for recipe in recipes:
        recipe.ingredients[0].line = "2 x 400g cans tomatoes"
        recipe.ingredients[1].line = "1 x 200g cans beans"
    groups = dryrunReport.unparsedGroups(recipes, UNITS)
    assert groups == [{"pattern": "N x NU U w", "count": 2, "sites": {"testsite": 2},
                       "examples": ["2 x 400g cans tomatoes", "1 x 200g cans beans"]}]


def test_basicsAreFoundOrMissing():
    rules = {"basics": [{"name": "scrambled eggs", "url": "https://x.test/a/"},
                        {"name": "porridge", "url": "https://x.test/b/"},
                        {"name": "omelette", "url": "https://x.test/c/"},
                        {"name": "pancakes", "url": "https://x.test/d/"},
                        {"name": "toast", "url": None}]}
    recipes = [made(url="https://x.test/a/"), made(url="https://x.test/b/", hidden="small-photo")]
    skipped = [{"site": "testsite", "url": "https://x.test/c/", "reason": "no steps", "detail": None}]
    assert [b["status"] for b in dryrunReport.basicsStatus(rules, recipes, skipped)] == [
        "listed", "hidden: small-photo", "not read: no steps", "not fetched", "missing: no site has it"]


def test_aBasicTheCrawlerFetchedAndRejectedIsNotARecipePage():
    rules = {"basics": [{"name": "chicken", "url": "https://x.test/e/"}, {"name": "rice", "url": "https://x.test/f/"}]}
    state = {"testsite": {"notRecipe": {"https://x.test/e/": "2023-11-07T00:00:00+00:00"}}}
    assert [b["status"] for b in dryrunReport.basicsStatus(rules, [], [], state)] == ["not a recipe page", "not fetched"]


def test_theReportShowsAllCrawlCountersAndSaysCountsCoverEveryCachedPage():
    crawl = {"due": 9, "fetched": 4, "notRecipe": 3, "gone": 1, "errors": 1, "listed": 50}
    summary = dryrunReport.siteSummary(SITE, crawl, [made()], [])
    text = dryrunReport.renderMarkdown({"date": "2026-11-14", "pages": 1, "recipes": 1, "listed": 1, "passRate": 1.0,
                                        "sites": [summary], "reasons": {r: 0 for r in dryrunReport._ORDER},
                                        "unparsedLines": 0, "basics": []}, [])
    assert "9 due, 4 fetched, 3 notRecipe, 1 gone, 1 errors, 50 listed" in text
    assert "every cached page, not only this run's" in text


def test_writeLeavesTheOwnersReport(tmp_path):
    recipes = [made(url="https://x.test/a/")]
    summary = dryrunReport.write(tmp_path / "report", [SITE], {"testsite": {"listed": 9, "fetched": 1}}, recipes, [],
                                 {"unitMap": UNITS, "basics": [{"name": "toast", "url": None}]}, date(2026, 11, 14))
    assert summary["listed"] == 1 and summary["passRate"] == 1.0
    text = (tmp_path / "report" / "summary.md").read_text(encoding="utf-8")
    assert "# Dry run 2026-11-14" in text and "| Test Site |" in text and "No site provides: toast." in text
    assert json.loads((tmp_path / "report" / "samples" / "testsite.json").read_text(encoding="utf-8"))[0]["title"]
    assert (tmp_path / "report" / "unparsed.json").exists() and (tmp_path / "report" / "skipped.json").exists()


def test_theReportHasANutritionSectionWithCalibrationAndTheQueue(tmp_path):
    recipes = [made(url="https://x.test/a/", nutritionFrom="source", nutrition={"calories": 100},
                    estimate={"calories": 100}),
               made(url="https://x.test/b/", hidden="no-nutrition", nutritionFlagged=False,
                    estimateBlocker={"line": "x", "reason": "no-fdc", "ingredient": "saffron"},
                    hints={"blockers": [{"reason": "no-fdc", "ingredient": "saffron"},
                                        {"reason": "no-fdc", "ingredient": "mace"},
                                        {"reason": "unknown-ingredient", "ingredient": "sumac"}]})]
    calibration = {"testsite": {"n": 1, "median": 1.0, "p25": 1.0, "p75": 1.0, "within20": 1.0, "within35": 1.0}}
    queue = [{"ingredient": "saffron", "unlocks": 1, "blocks": 1,
              "candidates": [{"fdcId": 1, "description": "Spices, saffron", "dataType": "sr_legacy_food", "score": 100}]}]
    summary = dryrunReport.write(tmp_path / "report", [SITE], {}, recipes, [],
                                 {"unitMap": UNITS, "basics": []}, date(2026, 11, 14),
                                 calibration=calibration, queue=queue,
                                 unknown=[{"name": "sumac", "blocks": 1, "unlocks": 0}])
    assert summary["nutrition"] == {"source": 1, "estimate": 0, "flagged": 0, "blockers": {"no-fdc": 1},
                                    "hiddenBlockers": {"no-fdc": 1, "unknown-ingredient": 1}}
    assert summary["sites"][0]["nutrition"]["blockers"] == {"no-fdc": 1}
    text = (tmp_path / "report" / "summary.md").read_text(encoding="utf-8")
    assert "## Nutrition" in text and "| Test Site | 1 | 0 | 0 | 1 | 1 | 1.00 | 1.00-1.00 | 100% |" in text
    assert "| saffron | 1 | 1 | Spices, saffron |" in text and "| no-fdc | 1 | 1 |" in text
    assert "| unknown-ingredient | 1 | 0 |" in text and "Hidden recipes (no-nutrition) counts every blocker" in text
    assert "Unknown ingredients blocking hidden recipes" in text and "| sumac | 0 | 1 |" in text
    assert "ingredient mapping page" in text and "unlocks is exact" in text
    assert json.loads((tmp_path / "report" / "unknown-queue.json").read_text(encoding="utf-8")) == [
        {"name": "sumac", "blocks": 1, "unlocks": 0}]
    assert "milestone 2's estimate brings" not in text


def test_theReportCountsBasicsThatFellBackToALaterCandidate():
    rules = {"basics": [{"name": "eggs", "url": "https://x.test/a/", "urls": ["https://x.test/a/", "https://x.test/b/"]},
                        {"name": "rice", "url": "https://x.test/c/", "urls": ["https://x.test/c/"]}]}
    rows = dryrunReport.basicsStatus(rules, [made(url="https://x.test/a/", hidden="small-photo"),
                                             made(url="https://x.test/b/"), made(url="https://x.test/c/")], [])
    assert [(r["url"], r["status"]) for r in rows] == [("https://x.test/b/", "listed via candidate 2"),
                                                       ("https://x.test/c/", "listed")]
    text = dryrunReport.renderMarkdown({"date": "2026-11-14", "pages": 0, "recipes": 0, "listed": 0, "passRate": None,
                                        "sites": [], "reasons": {r: 0 for r in dryrunReport._ORDER},
                                        "unparsedLines": 0, "basics": rows, "basicsFellBack": 1}, [])
    assert "1 basics fell back to a later candidate" in text
    assert "listed via candidate 2" in text
