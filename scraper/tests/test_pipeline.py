import pytest

import adminApi
import config
import images
import pipeline
import progress
import publish
import rulesData
import store


def quiet(*args):
    pass


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


# ---------- the recipe sites ----------

import json

import adaptSites
import fdc
import fdcMatch
import gate
import matching
import nutrition
import pagecache
from models import IngredientLine, Recipe, Step
from sources import sites

A_URL = "https://www.site-a.test/made-up-toast/"
A_SMALL = "https://www.site-a.test/made-up-small-toast/"
A_MISSING = "https://www.site-a.test/made-up-left-the-sitemap/"
B_URL = "https://www.site-b.test/made-up-soup/"
SITE_LIST = [{"site": "sitea", "name": "Site A", "kind": "food"},
             {"site": "siteb", "name": "Site B", "kind": "food", "measures": {"cup": 250}}]


def siteRecipe(site, url, width=1200):
    return Recipe(source=site, sourceId=pagecache.sourceIdFor(url), kind="food", title="Made-up toast",
                  ingredients=[IngredientLine(line="2 slices bread", name="bread", quantity=2, unit="slice")],
                  steps=[Step("Toast the bread.")], sourceUrl=url, imagePath="made-up.jpg", imageWidth=width,
                  totalMinutes=10, servings=2,
                  nutrition={"calories": 200, "proteinG": 6, "carbsG": 30, "fatG": 4, "satFatG": 1, "fibreG": 2,
                             "sugarG": 3, "sodiumMg": 300})


@pytest.fixture
def newCatalog(monkeypatch):
    """Two made-up sites; site a has a complete listing, site b was blocked."""
    world = {"crawls": [], "reads": 0, "listing": [(A_URL, None), (A_SMALL, None)]}
    realLoad = rulesData.load

    def load(folder=None):
        rules = realLoad(folder)
        rules["basics"] = [{"name": "made-up toast", "urls": [A_SMALL, A_URL]}]
        return rules
    monkeypatch.setattr(rulesData, "load", load)
    monkeypatch.setattr(sites, "loadSites", lambda rules: [dict(s) for s in SITE_LIST])

    def crawl(siteList, pages, log=print, priority=frozenset(), now=None, only=None, stopRequested=None):
        world["crawls"].append({"pages": pages, "priority": priority, "only": only, "stop": stopRequested})
        pagecache.saveListing("sitea", world["listing"])
        listed = len(world["listing"])
        result = {"sitea": {"site": "sitea", "ok": True, "stopReason": None, "listed": listed, "planned": 2, "due": 2,
                            "fetched": 2, "notRecipe": 0, "gone": 0, "errors": 0, "complete": True, "goneUrls": []},
                  "siteb": {"site": "siteb", "ok": False, "stopReason": "blocked (403)", "listed": 7, "planned": 0,
                            "due": 0, "fetched": 0, "notRecipe": 0, "gone": 0, "errors": 0, "complete": False,
                            "goneUrls": []}}
        return {k: v for k, v in result.items() if only in (None, k)}
    monkeypatch.setattr(sites, "crawl", crawl)

    def adaptCached(siteList, rules):
        world["reads"] += 1
        return [siteRecipe("sitea", A_URL), siteRecipe("sitea", A_SMALL, width=400),
                siteRecipe("siteb", B_URL)], []
    monkeypatch.setattr(adaptSites, "adaptCached", adaptCached)
    monkeypatch.setattr(images, "ensureImages", lambda recipes, allowDownload, log=print, onProgress=None:
                        {"made": 0, "failed": 0, "pictureStops": {"siteb": "blocked (403)"}})
    monkeypatch.setattr(fdc, "loadFoods", lambda path=None: {})
    return world


def test_aStopBeforePublishingPublishesNothing(newCatalog, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("published after a stop")
    monkeypatch.setattr(publish, "publish", refuse)
    result = pipeline.runPass("full", log=quiet, stopRequested=lambda: True)
    assert result["outcome"] == "stopped"


def test_aFailureEndsThePassWithItsReason(newCatalog, monkeypatch):
    monkeypatch.setattr(config, "PUBLISH", "on")
    def fail(*args, **kwargs):
        raise adminApi.AdminError("POST /ingredients/seed failed after 3 attempts")
    monkeypatch.setattr(adminApi, "post", fail)
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "failed" and "ingredients/seed" in result["error"]
    assert progress.read()["state"] == "idle"


def test_aPassSaysItIsTheNewCatalog(newCatalog):
    result = pipeline.runPass("full", log=quiet, site="sitea")
    assert (result["catalog"], result["site"]) == ("new", "sitea")
    assert pipeline.runPass("retag", log=quiet)["catalog"] == "new"


def test_aNewFullPassRunsNutritionBeforeTheGateForEveryRecipe(newCatalog, monkeypatch):
    calls = []
    realChoose, realApply = nutrition.choose, gate.apply
    monkeypatch.setattr(nutrition, "choose", lambda recipe, *a, **k: calls.append(("choose", recipe.sourceUrl))
                        or realChoose(recipe, *a, **k))
    monkeypatch.setattr(gate, "apply", lambda recipe, units: calls.append(("gate", recipe.sourceUrl))
                        or realApply(recipe, units))
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "ok", result["error"]
    urls = [url for kind, url in calls if kind == "choose"]
    assert sorted(urls) == sorted([A_URL, A_SMALL, B_URL])
    assert calls == [step for url in urls for step in (("choose", url), ("gate", url))]
    crawl = newCatalog["crawls"][0]
    assert crawl["pages"] is None and crawl["only"] is None and crawl["stop"] is not None
    assert {A_URL, A_SMALL} <= set(crawl["priority"])


def test_aNewFullPassTagsTheBasicOnlyOnARecipeThatPassedTheGate(newCatalog, monkeypatch):
    payloads = {}
    real = publish.payloadFor
    monkeypatch.setattr(publish, "payloadFor", lambda recipe: payloads.setdefault(recipe.sourceUrl, real(recipe)))
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "ok", result["error"]

    def basic(url):
        return {"type": "occasion", "tag": "basic", "origin": "rule"} in payloads[url]["tags"]
    assert payloads[A_SMALL]["hiddenReason"] == "small-photo" and not basic(A_SMALL)    # candidate 1 failed the gate
    assert "hiddenReason" not in payloads[A_URL] and basic(A_URL)
    assert not basic(B_URL)
    assert result["publish"]["dry"] is True and result["publish"]["changed"] == 3
    assert result["pairings"]["dry"] is True and result["pairings"]["recipes"] == 2   # the hidden one takes no part


def test_aNewFullPassWritesSiteHealthTheFdcQueueAndTheReport(newCatalog):
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "ok", result["error"]
    stored = json.loads(config.SITES_FILE.read_text(encoding="utf-8"))
    assert stored["mode"] == "pass" and [row["site"] for row in stored["sites"]] == ["sitea", "siteb"]
    a, b = stored["sites"]
    assert a["recipes"] == 2 and a["shown"] == 1 and a["listingComplete"] is True and a["lastPassAt"]
    assert b["pictureStop"] == "blocked (403)" and b["alarm"]["red"] is True
    assert result["sites"] == stored["sites"]
    queue = json.loads(config.FDC_QUEUE_FILE.read_text(encoding="utf-8"))
    assert "queue" in queue and queue["generatedAt"].endswith("+00:00")
    assert result["recipes"] == 3 and isinstance(result["calibration"], dict)
    assert len(config.NORMALISED_FILE.read_text(encoding="utf-8").splitlines()) == 3
    assert json.loads(config.LAST_REPORT_FILE.read_text(encoding="utf-8"))["outcome"] == "ok"
    assert progress.read()["state"] == "idle"


def test_aNewFullPassRemovesWhatLeftACompleteListingAndKeepsItsCount(newCatalog):
    missing = f"sitea:{pagecache.sourceIdFor(A_MISSING)}"
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {missing: "made-up-hash"}})
    store.writeJson(config.STATE_FILE, {"lastFullAt": 5.0})
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "ok", result["error"]
    assert result["publish"]["wouldRemove"] == [missing]
    state = store.readJson(config.STATE_FILE)
    assert state["siteCounts"] == {"sitea": 2} and state["lastFullAt"] == 5.0     # site b: listing incomplete


def test_aShrunkListingIsGuardedAndKeepsTheLastCount(newCatalog):
    missing = f"sitea:{pagecache.sourceIdFor(A_MISSING)}"
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {missing: "made-up-hash"}})
    store.writeJson(config.STATE_FILE, {"siteCounts": {"sitea": 100}})
    result = pipeline.runPass("full", log=quiet)
    assert result["publish"]["wouldRemoveCount"] == 0 and result["publish"]["guarded"] == ["sitea"]
    assert store.readJson(config.STATE_FILE)["siteCounts"] == {"sitea": 100}


def test_aListingShrunkTwiceIsStillGuardedOnTheSecondPass(newCatalog):
    missing = f"sitea:{pagecache.sourceIdFor(A_MISSING)}"
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {missing: "made-up-hash"}})
    store.writeJson(config.STATE_FILE, {"siteCounts": {"sitea": 100}})
    for _ in range(2):
        result = pipeline.runPass("full", log=quiet)
        assert result["publish"]["wouldRemoveCount"] == 0 and result["publish"]["guarded"] == ["sitea"]
    assert store.readJson(config.STATE_FILE)["siteCounts"] == {"sitea": 100}


def test_anEmptyListingNeverBecomesTheBaseline(newCatalog):
    missing = f"sitea:{pagecache.sourceIdFor(A_MISSING)}"
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {missing: "made-up-hash"}})
    store.writeJson(config.STATE_FILE, {"siteCounts": {"sitea": 100}})
    newCatalog["listing"] = []
    first = pipeline.runPass("full", log=quiet)
    assert first["publish"]["wouldRemoveCount"] == 0 and first["publish"]["guarded"] == ["sitea"]
    assert store.readJson(config.STATE_FILE)["siteCounts"] == {"sitea": 100}
    newCatalog["listing"] = [(A_URL, None), (A_SMALL, None)]                # then a small listing: still held back
    second = pipeline.runPass("full", log=quiet)
    assert second["publish"]["wouldRemoveCount"] == 0 and second["publish"]["guarded"] == ["sitea"]
    assert store.readJson(config.STATE_FILE)["siteCounts"] == {"sitea": 100}


def test_aNewRetagCrawlsNothingRemovesNothingAndKeepsTheCrawlFields(newCatalog, monkeypatch):
    pipeline.runPass("full", log=quiet)
    before = json.loads(config.SITES_FILE.read_text(encoding="utf-8"))["sites"]
    newCatalog["crawls"].clear()
    missing = f"sitea:{pagecache.sourceIdFor(A_MISSING)}"
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {missing: "made-up-hash"}})
    seen = {}
    real = publish.publish

    def recording(recipes, log=print, removals=None):
        seen["removals"] = removals
        return real(recipes, log, removals=removals)
    monkeypatch.setattr(publish, "publish", recording)
    result = pipeline.runPass("retag", log=quiet)
    assert result["outcome"] == "ok", result["error"]
    assert newCatalog["crawls"] == [] and newCatalog["reads"] == 2
    assert seen["removals"] == ([], [], []) and result["publish"]["wouldRemoveCount"] == 0
    assert result["sources"] == {}
    after = json.loads(config.SITES_FILE.read_text(encoding="utf-8"))["sites"]
    assert [row["lastPassAt"] for row in after] == [row["lastPassAt"] for row in before]
    assert [row["listed"] for row in after] == [2, 7]


def test_aPassOfOneSiteCrawlsOnlyThatSite(newCatalog):
    pipeline.runPass("full", log=quiet)
    before = {row["site"]: row for row in json.loads(config.SITES_FILE.read_text(encoding="utf-8"))["sites"]}
    newCatalog["crawls"].clear()
    other = f"siteb:{pagecache.sourceIdFor('https://www.site-b.test/made-up-gone/')}"
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {other: "made-up-hash"}})
    result = pipeline.runPass("full", log=quiet, site="sitea")
    assert result["outcome"] == "ok", result["error"]
    assert newCatalog["crawls"][0]["only"] == "sitea" and list(result["sources"]) == ["sitea"]
    after = {row["site"]: row for row in json.loads(config.SITES_FILE.read_text(encoding="utf-8"))["sites"]}
    assert (after["siteb"]["listed"], after["siteb"]["lastPassAt"], after["siteb"]["alarm"]) == \
        (before["siteb"]["listed"], before["siteb"]["lastPassAt"], before["siteb"]["alarm"])
    assert result["publish"]["wouldRemoveCount"] == 0


def test_aStopDuringTheCrawlEndsThePassBeforeReading(newCatalog, monkeypatch):
    stop = {"now": False}
    realCrawl = sites.crawl

    def crawl(*args, **kwargs):
        stop["now"] = True
        return realCrawl(*args, **kwargs)
    monkeypatch.setattr(sites, "crawl", crawl)
    result = pipeline.runPass("full", log=quiet, stopRequested=lambda: stop["now"])
    assert result["outcome"] == "stopped" and newCatalog["reads"] == 0


def fdcWorld(monkeypatch, mappings):
    monkeypatch.setattr(config, "PUBLISH", "on")
    posted = []
    monkeypatch.setattr(adminApi, "post", lambda path, payload, timeout=120: posted.append((path, payload)) or {})
    monkeypatch.setattr(pipeline, "loadTable", lambda rules, log=print: matching.IngredientTable.fromSeed(
        rules["ingredients"], set(rules["prepWords"]), set(rules["modifierWords"])))
    foods = {1: {"id": 1, "description": "Made-up bread", "dataType": "foundation_food"}}
    monkeypatch.setattr(fdc, "loadFoods", lambda path=None: foods)
    monkeypatch.setattr(fdcMatch, "resolveTable", lambda table, foods, rules, picks: {})
    seen = {}
    monkeypatch.setattr(fdcMatch, "syncList", lambda table, resolved, foodsGiven:
                        seen.setdefault("foods", foodsGiven) and list(mappings))
    monkeypatch.setattr(publish, "publish", lambda *a, **k: {"dry": False, "changed": 0, "guarded": []})
    monkeypatch.setattr(publish, "publishedState", lambda dry: {})
    return posted, seen, foods


def test_withPublishOnTheFdcMappingsArePostedInChunks(newCatalog, monkeypatch):
    mappings = [{"ingredientId": n, "fdcId": 1, "from": "rule"} for n in range(5001)]
    posted, seen, foods = fdcWorld(monkeypatch, mappings)
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "ok", result["error"]
    fdcPosts = [payload for path, payload in posted if path == "/ingredients/fdc"]
    assert [len(p["mappings"]) for p in fdcPosts] == [5000, 1] and fdcPosts[0]["mappings"][0] == mappings[0]
    assert seen["foods"] is foods


def test_withPublishOnAnEmptySyncListPostsNothing(newCatalog, monkeypatch):
    posted, _, _ = fdcWorld(monkeypatch, [])
    assert pipeline.runPass("full", log=quiet)["outcome"] == "ok"
    assert [path for path, _ in posted if path == "/ingredients/fdc"] == []


def test_aDryNewPassPostsNoMappings(newCatalog, monkeypatch):
    monkeypatch.setattr(fdcMatch, "syncList", lambda *a: (_ for _ in ()).throw(AssertionError("synced when dry")))
    assert pipeline.runPass("full", log=quiet)["outcome"] == "ok"


def removalWorld(newCatalog, monkeypatch, publishOn):
    """Site a's three pages are cached and published; A_MISSING has left a complete listing. The read is real
    over the cache (one recipe per cached page), so a page left in the cache would be read and sent again."""
    for url in (A_URL, A_SMALL, A_MISSING):
        pagecache.save("sitea", url, "<html>made-up</html>", None)
    missing = f"sitea:{pagecache.sourceIdFor(A_MISSING)}"
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {f"sitea:{pagecache.sourceIdFor(u)}": "made-up-hash"
                                                        for u in (A_URL, A_SMALL, A_MISSING)}})
    monkeypatch.setattr(adaptSites, "adaptCached", lambda siteList, rules: (
        [siteRecipe("sitea", meta["url"]) for meta, _ in pagecache.pages("sitea")], []))
    monkeypatch.setattr(pipeline, "loadTable", lambda rules, log=print: matching.IngredientTable.fromSeed(
        rules["ingredients"], set(rules["prepWords"]), set(rules["modifierWords"])))
    posts = []
    if publishOn:
        monkeypatch.setattr(config, "PUBLISH", "on")
        monkeypatch.setattr(adminApi, "configured", lambda: True)
        monkeypatch.setattr(adminApi, "rsync", lambda src, dest: None)

        def post(path, payload, timeout=120):
            posts.append((path, payload))
            if path == "/recipes/batch":
                return {"stored": [r["key"] for r in payload["recipes"]], "failed": []}
            if path == "/recipes/removed":
                return {"removed": len(payload["keys"])}
            return {}
        monkeypatch.setattr(adminApi, "post", post)
    return missing, posts


def sentKeys(posts, path):
    if path == "/recipes/batch":
        return [r["key"] for p, payload in posts if p == path for r in payload["recipes"]]
    return [k for p, payload in posts if p == path for k in payload["keys"]]


def test_aRemovedSitePageIsDroppedFromTheCacheAndNeverSentAgain(newCatalog, monkeypatch):
    missing, posts = removalWorld(newCatalog, monkeypatch, publishOn=True)
    first = pipeline.runPass("full", log=quiet)
    assert first["outcome"] == "ok", first["error"]
    assert sentKeys(posts, "/recipes/removed") == [missing]
    assert missing not in sentKeys(posts, "/recipes/batch")          # never re-posted in the pass that removes it
    assert pagecache.meta("sitea", A_MISSING) is None and pagecache.load("sitea", A_MISSING) is None
    assert pagecache.meta("sitea", A_URL) is not None
    assert missing not in store.readJson(config.PUBLISHED_FILE)["recipes"]
    for mode in ("retag", "full"):
        posts.clear()
        result = pipeline.runPass(mode, log=quiet)
        assert result["outcome"] == "ok", result["error"]
        assert missing not in sentKeys(posts, "/recipes/batch") + sentKeys(posts, "/recipes/removed")
        assert missing not in store.readJson(config.PUBLISHED_FILE)["recipes"]


def test_aDryPassDropsNothingFromTheCache(newCatalog, monkeypatch):
    missing, _ = removalWorld(newCatalog, monkeypatch, publishOn=False)
    result = pipeline.runPass("full", log=quiet)
    assert result["outcome"] == "ok", result["error"]
    assert result["publish"]["wouldRemove"] == [missing]
    assert pagecache.load("sitea", A_MISSING) is not None and pagecache.meta("sitea", A_MISSING) is not None


def test_theRetiredCatalogsRecipesOnPlutusAreNeitherRemovedNorSent(newCatalog, monkeypatch):
    """After the switch plutus still holds the old catalog's retired rows: no pass touches them."""
    missing, posts = removalWorld(newCatalog, monkeypatch, publishOn=True)
    retired = ["mealdb:7", "cocktaildb:9", "wikibooks:Cookbook:Made-up Soup"]
    published = store.readJson(config.PUBLISHED_FILE)["recipes"]
    store.writeJson(config.PUBLISHED_FILE, {"recipes": dict(published, **{key: "old-hash" for key in retired})})
    for mode in ("full", "retag"):
        posts.clear()
        result = pipeline.runPass(mode, log=quiet)
        assert result["outcome"] == "ok", result["error"]
        touched = sentKeys(posts, "/recipes/batch") + sentKeys(posts, "/recipes/removed")
        assert not set(retired) & set(touched)
    assert all(key in store.readJson(config.PUBLISHED_FILE)["recipes"] for key in retired)
