"""Publishing pairings (spec 2026-11-19 part 3, 2.3): chunks to /pairings, unchanged sets not sent, an emptied set
cleared, refused items reported, only recipes plutus holds. Every recipe here is made up."""
import adminApi
import config
import publish
import rulesData
import store
from test_pairing import made

RULES = rulesData.load(config.RULES_DIR)


def catalog():
    """One cuisine: a main whose description names two sides, a dessert and a drink."""
    return [made(1, "main", "Curry", cuisine="Indian", description="Serve with naan and rice."),
            made(2, "side", "Naan", cuisine="Indian"), made(3, "side", "Rice", cuisine="Indian"),
            made(4, "dessert", "Kulfi", cuisine="Indian"), made(5, "cocktail", "Fizz", cuisine="Indian")]


class FakePlutus:
    def __init__(self, monkeypatch, refuse=(), held=None):
        self.posts = []
        self.refuse = set(refuse)
        monkeypatch.setattr(config, "PUBLISH", "on")
        monkeypatch.setattr(adminApi, "configured", lambda: True)
        monkeypatch.setattr(adminApi, "post", self.post)
        held = held if held is not None else {f"madeup:{n}": "h" for n in range(1, 6)}
        store.writeJson(config.PUBLISHED_FILE, {"recipes": held})

    def post(self, path, payload, timeout=120):
        assert path == "/pairings"
        self.posts.append(payload)
        keys = [item["key"] for item in payload["items"]]
        return {"status": "ok", "stored": [k for k in keys if k not in self.refuse],
                "failed": [{"key": k, "message": "unknown recipe"} for k in keys if k in self.refuse]}

    def sent(self):
        return {item["key"]: item["pairings"] for payload in self.posts for item in payload["items"]}


def quiet(*args):
    pass


def test_aDryPassCountsButSendsNothing(monkeypatch):
    sent = []
    monkeypatch.setattr(adminApi, "post", lambda *a, **k: sent.append(a))
    summary = publish.publishPairings(catalog(), RULES, log=quiet)
    assert sent == [] and summary["dry"] is True
    assert summary["perSlot"] == {"side": 1, "dessert": 1, "drink": 2, "goes-on": 2}
    assert summary["wouldSend"] == 4 and summary["recipes"] == 5
    assert summary["none"] == 1                         # the cocktail's snack slot found nothing


def test_setsGoInChunksAndTheirHashesAreKept(monkeypatch):
    plutus = FakePlutus(monkeypatch)
    monkeypatch.setattr(config, "PAIRING_BATCH", 2)
    summary = publish.publishPairings(catalog(), RULES, log=quiet)
    assert [len(p["items"]) for p in plutus.posts] == [2, 2]
    curry = plutus.sent()["madeup:1"]
    assert sorted((p["slot"], p["key"]) for p in curry) == [
        ("dessert", "madeup:4"), ("drink", "madeup:5"), ("side", "madeup:2"), ("side", "madeup:3")]
    naan = next(p for p in curry if p["key"] == "madeup:2")
    assert naan["why"] == "the recipe says to serve it with naan; same cuisine" and naan["slot"] == "side"
    assert summary["sent"] == 4 and summary["stored"] == 4 and summary["failed"] == []
    saved = store.readJson(config.PUBLISHED_FILE)
    assert set(saved["pairings"]) == {"madeup:1", "madeup:2", "madeup:3", "madeup:4"}
    assert saved["recipes"]["madeup:1"] == "h"         # the recipe hashes are kept as they were


def test_anUnchangedSetIsNotSentAgain(monkeypatch):
    plutus = FakePlutus(monkeypatch)
    publish.publishPairings(catalog(), RULES, log=quiet)
    plutus.posts.clear()
    summary = publish.publishPairings(catalog(), RULES, log=quiet)
    assert plutus.posts == [] and summary["sent"] == 0


def test_aSetThatEmptiedIsSentEmptySoPlutusClearsIt(monkeypatch):
    plutus = FakePlutus(monkeypatch)
    publish.publishPairings(catalog(), RULES, log=quiet)
    plutus.posts.clear()
    changed = catalog()
    changed[0].description, changed[0].cuisine = "A curry.", None
    publish.publishPairings(changed, RULES, log=quiet)
    assert plutus.sent() == {"madeup:1": [], "madeup:2": [], "madeup:3": []}
    plutus.posts.clear()
    publish.publishPairings(changed, RULES, log=quiet)
    assert plutus.posts == []                           # sent once; an empty set is remembered like any other


def test_refusedItemsAreReportedAndSentAgainNextTime(monkeypatch):
    plutus = FakePlutus(monkeypatch, refuse={"madeup:1"})
    summary = publish.publishPairings(catalog(), RULES, log=quiet)
    assert summary["failed"] == [{"key": "madeup:1", "message": "unknown recipe"}] and summary["stored"] == 3
    assert "madeup:1" not in store.readJson(config.PUBLISHED_FILE)["pairings"]
    plutus.refuse.clear()
    plutus.posts.clear()
    publish.publishPairings(catalog(), RULES, log=quiet)
    assert list(plutus.sent()) == ["madeup:1"]


def test_onlyShownRecipesPlutusHoldsAndThisPassKeepsTakePart(monkeypatch):
    plutus = FakePlutus(monkeypatch, held={"madeup:1": "h", "madeup:2": "h", "madeup:3": "h"})
    recipes = catalog() + [made(6, "side", "Naan bread", hidden="no-photo")]
    recipes[2].description = None
    publish.publishPairings(recipes, RULES, log=quiet, removing={"madeup:3"})
    sent = plutus.sent()
    assert [p["key"] for p in sent["madeup:1"]] == ["madeup:2"]       # not held, removed or hidden: never paired
    assert set(sent) == {"madeup:1", "madeup:2"}


def test_savingRecipeHashesKeepsThePairingHashes(monkeypatch):
    FakePlutus(monkeypatch)
    publish.publishPairings(catalog(), RULES, log=quiet)
    publish._save({"madeup:1": "new"})
    saved = store.readJson(config.PUBLISHED_FILE)
    assert saved["recipes"] == {"madeup:1": "new"} and len(saved["pairings"]) == 4


def test_theHashFollowsTheSet():
    one = [{"slot": "side", "key": "a:1", "rank": 1, "why": "same cuisine"}]
    assert publish.pairingsHash(one) == publish.pairingsHash([dict(one[0])])
    assert publish.pairingsHash(one) != publish.pairingsHash([dict(one[0], why="both Mediterranean")])
    assert publish.pairingsHash([]) != publish.pairingsHash(one)
