import pytest

import adminApi
import config
import images
import pipeline
import progress
import publish
import rulesData
import store
from sources import thedb, wikibooks

MEAL = {"idMeal": "1", "strMeal": "Cheese Toast", "strCategory": "Breakfast", "strArea": "British",
        "strInstructions": "Toast the bread. Melt the cheese.", "strIngredient1": "Bread", "strMeasure1": "2 slices",
        "strIngredient2": "Cheddar", "strMeasure2": "50g", "strIngredient3": "Yuzu", "strMeasure3": "1"}
DRINK = {"idDrink": "2", "strDrink": "Gin Fizz", "strCategory": "Ordinary Drink", "strAlcoholic": "Alcoholic",
         "strGlass": "Highball glass", "strInstructions": "Shake and strain.", "strIngredient1": "Gin",
         "strMeasure1": "2 oz", "strIngredient2": "Soda water", "strMeasure2": "Top up"}
PAGE = "{{recipe summary|Difficulty=2|Time=20 minutes}}\n== Ingredients ==\n* 2 eggs\n== Procedure ==\n# Fry the eggs.\n"


@pytest.fixture
def sources(monkeypatch):
    calls = []
    def allRecords(db):
        calls.append(db.source)
        return {"1": MEAL} if db.source == "mealdb" else {"2": DRINK}
    def fetch(previous=None, log=print):
        calls.append("wikibooks")
        store.writeJson(store.rawPath("wikibooks", "Cookbook:Fried Eggs"),
                        {"source": "wikibooks", "sourceId": "Cookbook:Fried Eggs", "wikitext": PAGE})
        store.writeJson(store.rawPath("wikibooks", "Cookbook:Eggs"),
                        {"source": "wikibooks", "sourceId": "Cookbook:Eggs", "wikitext": "{{cookdp}} Eggs."})
        return {"source": "wikibooks", "ok": True, "ids": ["Cookbook:Eggs", "Cookbook:Fried Eggs"], "error": None,
                "dumpDate": "20261001"}
    monkeypatch.setattr(thedb, "allRecords", allRecords)
    monkeypatch.setattr(wikibooks, "fetch", fetch)
    monkeypatch.setattr(images, "ensureImages", lambda recipes, allowDownload, log=print, onProgress=None:
                        {"made": 0, "failed": 0})
    return calls


def quiet(*args):
    pass


def test_aDryFullPassReadsEverySourceAndReports(sources):
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "ok" and result["recipes"] == 3
    assert result["sources"] == {"mealdb": {"ok": True, "records": 1, "error": None},
                                 "cocktaildb": {"ok": True, "records": 1, "error": None},
                                 "wikibooks": {"ok": True, "records": 2, "error": None}}
    assert result["skippedByReason"] == {"topic page": 1}
    assert result["unknownIngredients"][0]["name"] == "yuzu"
    assert result["publish"]["dry"] is True and result["publish"]["changed"] == 3
    assert result["calibration"]["difficulty"]["n"] == 1
    assert len(config.NORMALISED_FILE.read_text(encoding="utf-8").splitlines()) == 3
    assert store.readJson(config.STATE_FILE)["counts"] == {"mealdb": 1, "cocktaildb": 1, "wikibooks": 2}
    assert progress.read() == {"state": "idle", "updatedAt": progress.read()["updatedAt"]}
    assert config.LAST_REPORT_FILE.exists()


def test_aRetagFetchesNothingAndRemovesNothing(sources, monkeypatch):
    pipeline.runPass("full", log=quiet)
    sources.clear()
    seen = {}
    real = publish.publish

    def recording(recipes, fetchResults, lastCounts, log=print):
        seen["fetchResults"] = fetchResults
        return real(recipes, fetchResults, lastCounts, log)
    monkeypatch.setattr(publish, "publish", recording)
    result = pipeline.runPass("retag", log=quiet)
    assert result["outcome"] == "ok" and result["recipes"] == 3
    assert sources == [] and seen["fetchResults"] == {}


def test_aStopBeforePublishingPublishesNothing(sources, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("published after a stop")
    monkeypatch.setattr(publish, "publish", refuse)
    result = pipeline.runPass("full", log=quiet, stopRequested=lambda: True)
    assert result["outcome"] == "stopped"


def test_aFailureEndsThePassWithItsReason(sources, monkeypatch):
    monkeypatch.setattr(config, "PUBLISH", "on")
    def fail(*args, **kwargs):
        raise adminApi.AdminError("POST /ingredients/seed failed after 3 attempts")
    monkeypatch.setattr(adminApi, "post", fail)
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "failed" and "ingredients/seed" in result["error"]
    assert progress.read()["state"] == "idle"


def test_loadTableSeedsPlutusThenReadsItsTable(monkeypatch):
    monkeypatch.setattr(config, "PUBLISH", "on")
    asked = []
    monkeypatch.setattr(adminApi, "post", lambda path, payload, timeout=120: asked.append(path) or {"added": 1})
    monkeypatch.setattr(adminApi, "get", lambda path, timeout=60: asked.append(path) or {
        "ingredients": [{"id": 7, "name": "yuzu", "parentId": None, "category": "citrus", "contains": []}],
        "aliases": [{"alias": "yuzu", "ingredientId": 7}]})
    rules = rulesData.load()
    table = pipeline.loadTable(rules, log=quiet)
    assert asked == ["/ingredients/seed", "/ingredients"] and table.match("Yuzu")[0] == 7
    # the modifier words from rules/modifierWords.json reach the live table too
    modifier = sorted(rules["modifierWords"])[0]
    assert table.match(f"{modifier} yuzu")[0] == 7


def test_loadTableGivesTheDrySeedTableTheModifierWords():
    rules = rulesData.load()
    modifier = sorted(rules["modifierWords"])[0]
    table = pipeline.loadTable(rules, log=quiet)
    plain = table.match("salt")
    assert plain is not None and table.match(f"{modifier} salt")[0] == plain[0]
