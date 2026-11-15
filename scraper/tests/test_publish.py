import hashlib
import importlib
import sys

import pytest

import adminApi
import config
import pagecache
import publish
import store
from models import IngredientLine, Recipe, Step
from sources import schemaSite


def recipe(sourceId="1", source="mealdb", title="Toast"):
    r = Recipe(source=source, sourceId=sourceId, kind="food", title=title,
               ingredients=[IngredientLine(line="1 slice bread", name="bread", quantity=1.0, unit="slice",
                                           ingredientId=1)],
               steps=[Step(text="Toast it.")], licence="TheMealDB", credit="Recipe data and imagery: TheMealDB")
    r.dishKey = "toast"
    r.facts = {"complete": True, "contains": ["gluten"], "diets": ["vegetarian", "vegan", "dairy-free"]}
    return r


class FakePlutus:
    def __init__(self, monkeypatch, stored=None, failOnBatch=None, state=None):
        self.posts, self.rsyncs = [], []
        self.stored, self.failOnBatch, self.state = stored, failOnBatch, state or []
        monkeypatch.setattr(config, "PUBLISH", "on")
        monkeypatch.setattr(adminApi, "configured", lambda: True)
        monkeypatch.setattr(adminApi, "post", self.post)
        monkeypatch.setattr(adminApi, "get", self.get)
        monkeypatch.setattr(adminApi, "rsync", lambda src, dest: self.rsyncs.append(dest))

    def post(self, path, payload, timeout=120):
        self.posts.append((path, payload))
        if path == "/recipes/batch":
            batchNumber = sum(1 for p, _ in self.posts if p == "/recipes/batch")
            if self.failOnBatch == batchNumber:
                raise adminApi.AdminError("POST /recipes/batch failed after 3 attempts")
            keys = [r["key"] for r in payload["recipes"]]
            stored = [k for k in keys if self.stored is None or k in self.stored]
            return {"status": "ok", "stored": stored,
                    "failed": [{"key": k, "message": "nope"} for k in keys if k not in stored]}
        if path == "/recipes/removed":
            return {"status": "ok", "removed": len(payload["keys"])}
        raise AssertionError(path)

    def get(self, path, timeout=60):
        assert path == "/state"
        return {"status": "ok", "recipes": self.state}


OK = {"mealdb": {"ok": True, "ids": ["1", "2"]}}


def test_thePayloadFollowsTheContract():
    payload = publish.payloadFor(recipe())
    assert payload["key"] == "mealdb:1" and payload["searchText"] == "Toast bread"
    assert payload["ingredients"][0] == {"line": "1 slice bread", "quantity": 1.0, "quantityMax": None, "unit": "slice",
                                         "ingredientId": 1, "unknownName": None, "note": None, "optional": False,
                                         "group": None}
    assert len(payload["contentHash"]) == 40
    assert publish.payloadFor(recipe())["contentHash"] == payload["contentHash"]
    assert publish.payloadFor(recipe(title="Toast!"))["contentHash"] != payload["contentHash"]


def test_removalsComeOnlyFromACompleteFetch():
    published = ["mealdb:1", "mealdb:9", "wikibooks:Cookbook:Gone"]
    keys, notes, guarded = publish.removalsFor(published, {"mealdb": {"ok": True, "ids": ["1"]},
                                                           "wikibooks": {"ok": False, "ids": []}}, {}, 0.05)
    assert keys == ["mealdb:9"] and guarded == []
    assert notes == ["wikibooks: fetch failed, nothing removed"]


def test_aSuddenDropRemovesNothing():
    keys, notes, guarded = publish.removalsFor(["mealdb:9"], {"mealdb": {"ok": True, "ids": [str(n) for n in range(90)]}},
                                               {"mealdb": 100}, 0.05)
    assert keys == [] and guarded == ["mealdb"] and "more than 5% fewer" in notes[0]


def test_aDryPublishSendsNothing(monkeypatch):
    sent = []
    monkeypatch.setattr(adminApi, "post", lambda *a, **k: sent.append(a))
    summary = publish.publish([recipe()], OK, {}, log=lambda *a: None)
    assert summary["dry"] is True and summary["changed"] == 1 and sent == []
    assert summary["perSource"] == {"mealdb": {"new": 1, "changed": 0}}
    assert not config.PUBLISHED_FILE.exists()


def test_publishingSendsPicturesThenBatchesAndRemembersWhatWasStored(monkeypatch):
    plutus = FakePlutus(monkeypatch, stored={"mealdb:1"})
    monkeypatch.setattr(config, "BATCH_SIZE", 1)
    (config.IMAGE_DIR / "images").mkdir(parents=True)
    (config.IMAGE_DIR / "thumbs").mkdir(parents=True)
    summary = publish.publish([recipe("1"), recipe("2")], OK, {}, log=lambda *a: None)
    assert plutus.rsyncs == ["/pool/appFiles/gluttony/images", "/pool/appFiles/gluttony/thumbs"]
    assert [p for p, _ in plutus.posts] == ["/recipes/batch", "/recipes/batch"]
    assert summary["stored"] == 1 and summary["failed"] == [{"key": "mealdb:2", "message": "nope"}]
    assert list(store.readJson(config.PUBLISHED_FILE)["recipes"]) == ["mealdb:1"]


def test_anUnchangedRecipeIsNotSentAgain(monkeypatch):
    plutus = FakePlutus(monkeypatch)
    publish.publish([recipe()], OK, {}, log=lambda *a: None)
    plutus.posts.clear()
    summary = publish.publish([recipe()], OK, {}, log=lambda *a: None)
    assert summary["changed"] == 0 and plutus.posts == []


def test_removalsAreSentAndForgotten(monkeypatch):
    plutus = FakePlutus(monkeypatch)
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {"mealdb:1": "x", "mealdb:7": "y"}})
    summary = publish.publish([recipe("1")], {"mealdb": {"ok": True, "ids": ["1"]}}, {}, log=lambda *a: None)
    assert ("/recipes/removed", {"keys": ["mealdb:7"]}) in plutus.posts and summary["removed"] == 1
    assert list(store.readJson(config.PUBLISHED_FILE)["recipes"]) == ["mealdb:1"]


def test_aLostStateFileIsRebuiltFromPlutus(monkeypatch):
    first = publish.payloadFor(recipe())
    plutus = FakePlutus(monkeypatch, state=[{"key": "mealdb:1", "hash": first["contentHash"]}])
    summary = publish.publish([recipe()], {}, {}, log=lambda *a: None)
    assert summary["changed"] == 0 and plutus.posts == []


def test_aFailureMidwayKeepsWhatWasAlreadyStored(monkeypatch):
    FakePlutus(monkeypatch, failOnBatch=2)
    monkeypatch.setattr(config, "BATCH_SIZE", 1)
    with pytest.raises(adminApi.AdminError):
        publish.publish([recipe("1"), recipe("2")], OK, {}, log=lambda *a: None)
    assert list(store.readJson(config.PUBLISHED_FILE)["recipes"]) == ["mealdb:1"]


def test_anEmptyFetchRemovesNothing():
    keys, notes, guarded = publish.removalsFor(["mealdb:1", "mealdb:2"], {"mealdb": {"ok": True, "ids": []}}, {}, 0.05)
    assert keys == [] and guarded == ["mealdb"]
    assert notes == ["mealdb: fetch returned no records, nothing removed"]


def test_publishingWithoutSettingsFailsFirst(monkeypatch):
    plutus = FakePlutus(monkeypatch)
    monkeypatch.setattr(adminApi, "configured", lambda: False)
    with pytest.raises(adminApi.AdminError, match="ADMIN_TOKEN and ADMIN_HOST"):
        publish.publish([recipe()], OK, {}, log=lambda *a: None)
    assert plutus.rsyncs == [] and plutus.posts == []


# --- the new catalog: payload fields and site removals ---

NUTRITION = {"calories": 420.0, "proteinG": 12.5, "carbsG": 50.0, "fatG": 18.0, "satFatG": 6.0, "fibreG": 4.0,
             "sugarG": 9.0, "sodiumMg": 610.0}


def siteRecipe(url="https://example.test/recipes/soup", nutrition=NUTRITION, flagged=False):
    r = recipe(sourceId=schemaSite.sourceIdFor(url), source="budgetbytes", title="Soup")
    r.description = "A warm soup."
    r.hiddenReason = "small-photo"
    r.imageWidth = 640
    r.nutrition = dict(nutrition) if nutrition is not None else None
    r.nutritionFrom = "source"
    r.nutritionFlagged = flagged
    return r


def test_aSiteRecipeCarriesDescriptionHiddenReasonWidthAndNutrition():
    payload = publish.payloadFor(siteRecipe())
    assert payload["description"] == "A warm soup." and payload["hiddenReason"] == "small-photo"
    assert payload["imageWidth"] == 640
    assert payload["nutrition"] == dict(NUTRITION, **{"from": "source", "flagged": False})
    assert publish.payloadFor(siteRecipe(flagged=True))["contentHash"] != payload["contentHash"]


def test_nutritionWithoutCaloriesIsLeftOutAndMissingNutrientsAreNone():
    assert "nutrition" not in publish.payloadFor(siteRecipe(nutrition=None))
    assert "nutrition" not in publish.payloadFor(siteRecipe(nutrition={"proteinG": 3.0}))
    partial = publish.payloadFor(siteRecipe(nutrition={"calories": 100.0, "fatG": 2.0}))["nutrition"]
    assert partial == {"calories": 100.0, "proteinG": None, "carbsG": None, "fatG": 2.0, "satFatG": None,
                       "fibreG": None, "sugarG": None, "sodiumMg": None, "from": "source", "flagged": False}


def test_aNutrientOutsideWhatPlutusStoresIsLeftOut():
    wild = publish.payloadFor(siteRecipe(nutrition=dict(NUTRITION, sodiumMg=250000.0, fatG=-1.0)))["nutrition"]
    assert wild["sodiumMg"] is None and wild["fatG"] is None and wild["proteinG"] == 12.5
    edges = publish.payloadFor(siteRecipe(nutrition=dict(NUTRITION, sodiumMg=100000.0, sugarG=0.0)))["nutrition"]
    assert edges["sodiumMg"] == 100000.0 and edges["sugarG"] == 0.0


def test_caloriesOutsideWhatPlutusStoresSendNoNutrition():
    assert "nutrition" not in publish.payloadFor(siteRecipe(nutrition=dict(NUTRITION, calories=100001.0)))
    assert "nutrition" not in publish.payloadFor(siteRecipe(nutrition=dict(NUTRITION, calories=-5.0)))


def test_anOldSourceRecipesPayloadAndHashAreUnchanged():
    r = recipe()
    r.imageWidth = 1200          # images.ensureImages records a width for old-source pictures too
    r.description, r.hiddenReason = "Made-up.", "small-photo"
    r.nutrition, r.nutritionFrom = dict(NUTRITION), "source"
    payload = publish.payloadFor(r)
    for name in ("description", "hiddenReason", "imageWidth", "nutrition"):
        assert name not in payload
    assert payload["contentHash"] == "fbe0b73d4aae52a5a7c16c48162a248bc035e3ab"     # the hash before this change


def keyFor(site, url):
    return f"{site}:{schemaSite.sourceIdFor(url)}"


URLS = [f"https://example.test/recipes/{n}" for n in range(20)]


def test_aCompleteListingMissingAPublishedPageRemovesIt():
    pagecache.saveListing("budgetbytes", [(u, None) for u in URLS[:19]])
    published = [keyFor("budgetbytes", u) for u in URLS]
    keys, notes, guarded = publish.siteRemovals(
        published, {"budgetbytes": {"ok": True, "complete": True, "listed": 19, "goneUrls": []}},
        {"budgetbytes": 20}, 0.05)
    assert keys == [keyFor("budgetbytes", URLS[19])] and notes == [] and guarded == []


def test_anIncompleteListingRemovesOnlyGonePages():
    pagecache.saveListing("budgetbytes", [(u, None) for u in URLS[:5]])
    published = [keyFor("budgetbytes", u) for u in URLS]
    keys, notes, guarded = publish.siteRemovals(
        published, {"budgetbytes": {"ok": True, "complete": False, "listed": 5, "goneUrls": [URLS[2], URLS[7],
                                                                                           "https://example.test/x"]}},
        {"budgetbytes": 20}, 0.05)
    assert keys == sorted([keyFor("budgetbytes", URLS[2]), keyFor("budgetbytes", URLS[7])])
    assert guarded == []


def test_aShrunkenListingRemovesNothingAndSaysSo():
    pagecache.saveListing("budgetbytes", [(u, None) for u in URLS[:18]])
    published = [keyFor("budgetbytes", u) for u in URLS]
    keys, notes, guarded = publish.siteRemovals(
        published, {"budgetbytes": {"ok": True, "complete": True, "listed": 18, "goneUrls": []}},
        {"budgetbytes": 20}, 0.05)
    assert keys == [] and guarded == ["budgetbytes"]
    assert notes and "budgetbytes" in notes[0] and "more than 5% fewer" in notes[0]


def test_anEmptyCompleteListingRemovesNothing():
    published = [keyFor("budgetbytes", u) for u in URLS]
    keys, notes, guarded = publish.siteRemovals(
        published, {"budgetbytes": {"ok": True, "complete": True, "listed": 0, "goneUrls": []}}, {}, 0.05)
    assert keys == [] and guarded == ["budgetbytes"] and notes


def test_siteRemovalsLeaveOtherSitesAndOldSourcesAlone():
    pagecache.saveListing("budgetbytes", [(URLS[0], None)])
    pagecache.saveListing("difford", [])
    published = [keyFor("budgetbytes", URLS[0]), keyFor("budgetbytes", URLS[1]), keyFor("difford", URLS[1]),
                 keyFor("pinchofyum", URLS[1]), "mealdb:1", "wikibooks:Cookbook:Soup", "cocktaildb:9"]
    keys, notes, guarded = publish.siteRemovals(
        published, {"budgetbytes": {"ok": True, "complete": True, "listed": 1, "goneUrls": []}}, {}, 0.05)
    assert keys == [keyFor("budgetbytes", URLS[1])]


def test_publishUsesGivenRemovals(monkeypatch):
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {"difford:x": "h", "mealdb:7": "y"}})
    fetched = {"mealdb": {"ok": True, "ids": ["1"]}}      # removalsFor alone would remove mealdb:7
    assert publish.removalsFor(["mealdb:7"], fetched, {}, 0.05)[0] == ["mealdb:7"]
    summary = publish.publish([], fetched, {}, log=lambda *a: None, removals=(["difford:x"], [], []))
    assert summary["dry"] is True and summary["wouldRemove"] == ["difford:x"] and summary["wouldRemoveCount"] == 1
    assert "mealdb:7" not in summary["wouldRemove"]


def test_siteRemovalsNeverActOnAnOldSourceEvenIfAskedTo():
    published = ["mealdb:1", "cocktaildb:2", "wikibooks:Cookbook:Soup"]
    crawled = {name: {"ok": True, "complete": True, "listed": 0, "goneUrls": ["https://example.test/a"]}
               for name in ("mealdb", "cocktaildb", "wikibooks")}
    keys, notes, guarded = publish.siteRemovals(published, crawled, {}, 0.05)
    assert keys == [] and notes == [] and guarded == []


def test_importingPublishDoesNotNeedRecipeScrapers(monkeypatch):
    """The old-catalog pass imports publish; the VM may not have recipe-scrapers installed."""
    monkeypatch.setitem(sys.modules, "recipe_scrapers", None)      # any import of it now raises ImportError
    for name in ("publish", "sources.schemaSite"):
        monkeypatch.delitem(sys.modules, name, raising=False)       # restored after the test
    monkeypatch.delattr(sys.modules["sources"], "schemaSite", raising=False)   # else "from sources import" finds it
    fresh = importlib.import_module("publish")
    assert fresh.siteRemovals and "sources.schemaSite" not in sys.modules
    with pytest.raises(ImportError):
        importlib.import_module("sources.schemaSite")              # the block is real
    monkeypatch.delitem(sys.modules, "sources.schemaSite", raising=False)


def test_imagesAndPublishShareOneListOfOldSources():
    import images
    assert publish.OLD_SOURCES is config.OLD_SOURCES and images.OLD_SOURCES is config.OLD_SOURCES
    assert config.OLD_SOURCES == ("mealdb", "cocktaildb", "wikibooks")


def test_siteSourceIdsAreTheSameEverywhere():
    url = "https://example.test/recipes/soup"
    assert schemaSite.sourceIdFor(url) == pagecache.sourceIdFor(url) == hashlib.sha1(url.encode()).hexdigest()[:20]


def test_aKeyBeingRemovedIsNeverAlsoSent(monkeypatch):
    plutus = FakePlutus(monkeypatch)
    r = siteRecipe()
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {r.key: "old-hash"}})
    summary = publish.publish([r], {}, {}, log=lambda *a: None, removals=([r.key], [], []))
    assert [p for p, _ in plutus.posts] == ["/recipes/removed"] and summary["changed"] == 0


def test_aPostedSiteRemovalDropsThePageFromTheCacheButAnOldSourceIsLeftAlone(monkeypatch):
    FakePlutus(monkeypatch)
    url = "https://example.test/recipes/gone"
    pagecache.save("budgetbytes", url, "<html>made-up</html>", None)
    key = keyFor("budgetbytes", url)
    store.writeJson(config.PUBLISHED_FILE, {"recipes": {key: "h", "mealdb:7": "y"}})
    publish.publish([], {}, {}, log=lambda *a: None, removals=([key, "mealdb:7"], [], []))
    assert pagecache.meta("budgetbytes", url) is None and pagecache.load("budgetbytes", url) is None


def test_aFailedRemovalPostKeepsThePageCached(monkeypatch):
    plutus = FakePlutus(monkeypatch)
    url = "https://example.test/recipes/gone"
    pagecache.save("budgetbytes", url, "<html>made-up</html>", None)

    def failing(path, payload, timeout=120):
        raise adminApi.AdminError("POST /recipes/removed failed after 3 attempts")
    monkeypatch.setattr(adminApi, "post", failing)
    with pytest.raises(adminApi.AdminError):
        publish.publish([], {}, {}, log=lambda *a: None, removals=([keyFor("budgetbytes", url)], [], []))
    assert pagecache.load("budgetbytes", url) is not None
