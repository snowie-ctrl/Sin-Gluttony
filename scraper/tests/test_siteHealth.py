import json
from datetime import datetime, timezone

import config
import gate
import pagecache
import siteHealth
from models import Recipe

STARTED = 1_000_000.0
SITES = [{"site": "madeupblocked", "name": "Made-up Blocked", "kind": "food"},
         {"site": "madeuphealthy", "name": "Made-up Healthy", "kind": "drink"}]


def recipe(site, n, hidden=None):
    return Recipe(source=site, sourceId=str(n), kind="food", title=f"made-up {n}", ingredients=[], steps=[],
                  sourceUrl=f"https://{site}.test/r{n}/", hiddenReason=hidden)


# ---------- the alarm (Ruling S5) ----------

def test_aStoppedSiteIsRedWithItsStopReason():
    assert siteHealth.alarm(None, 0, None, "blocked (403)") == (True, "blocked (403)")
    assert siteHealth.alarm(0.95, 40, 0.95, "429")[0] is True


def test_fewerThanTenPagesIsTooFewToJudge():
    assert siteHealth.alarm(0.0, 9, 0.99, None) == (False, None)
    assert siteHealth.alarm(None, 0, None, None) == (False, None)


def test_exactlyTenPagesIsJudged():
    assert siteHealth.alarm(0.4, 10, None, None) == (True, "only 40% of fetched pages gave a recipe")


def test_underHalfIsRed():
    assert siteHealth.alarm(0.45, 20, 0.5, None) == (True, "only 45% of fetched pages gave a recipe")
    assert siteHealth.alarm(0.5, 20, None, None) == (False, None)


def test_aFallOfMoreThanTwentyPointsIsRed():
    assert siteHealth.alarm(0.69, 20, 0.9, None) == (True, "extraction fell from 90% to 69%")


def test_aFallOfExactlyTwentyPointsIsNotRed():
    assert siteHealth.alarm(0.7, 20, 0.9, None) == (False, None)
    assert siteHealth.alarm(0.6, 20, 0.8, None) == (False, None)


def test_aHealthySiteWithNoHistoryIsGreen():
    assert siteHealth.alarm(0.92, 12, None, None) == (False, None)


# ---------- summarise over two made-up sites ----------

def twoSites():
    crawled = {
        "madeupblocked": {"site": "madeupblocked", "ok": False, "stopReason": "blocked (403)", "listed": 0,
                          "planned": 0, "due": 0, "fetched": 0, "notRecipe": 0, "gone": 0, "errors": 0,
                          "complete": False, "goneUrls": []},
        "madeuphealthy": {"site": "madeuphealthy", "ok": True, "stopReason": None, "listed": 300, "planned": 20,
                          "due": 14, "fetched": 12, "notRecipe": 1, "gone": 1, "errors": 0, "complete": True,
                          "goneUrls": []},
    }
    recipes = [recipe("madeuphealthy", n) for n in range(10)] + [recipe("madeuphealthy", 10, "small-photo")]
    old = recipe("madeuphealthy", 99)                     # cached on an earlier pass
    recipes.append(old)
    for r in recipes:
        pagecache.save("madeuphealthy", r.sourceUrl, "<html>made up</html>", None,
                       fetchedAt=STARTED - 50 if r is old else STARTED + 5)
    damaged = "https://madeuphealthy.test/broken/"
    pagecache.save("madeuphealthy", damaged, "<html>made up</html>", None, fetchedAt=STARTED + 6)
    skipped = [{"site": "madeuphealthy", "url": damaged, "reason": "could not be read", "detail": "made up"}]
    siteState = {"madeupblocked": {"lastStop": "blocked (403)", "lastRate": 0.9}, "madeuphealthy": {}}
    calibration = {"madeuphealthy": {"n": 3, "median": 1.0, "p25": 0.9, "p75": 1.1, "within20": 1.0,
                                     "within35": 1.0, "pieceYields": 0}}
    return crawled, recipes, skipped, siteState, calibration


def test_summariseGivesOneRowPerSiteWithTheContractKeys():
    crawled, recipes, skipped, siteState, calibration = twoSites()
    rows = siteHealth.summarise(SITES, crawled, recipes, skipped, siteState, STARTED,
                                {"madeuphealthy": "429"}, calibration)
    assert [row["site"] for row in rows] == ["madeupblocked", "madeuphealthy"]
    keys = {"site", "name", "kind", "listed", "due", "fetched", "notRecipe", "gone", "errors", "stopReason",
            "pictureStop", "listingComplete", "cached", "recipes", "shown", "hidden", "skipped", "extraction",
            "calibration", "alarm", "lastPassAt"}
    assert all(set(row) == keys for row in rows)


def test_aBlockedSiteIsRedAndKeepsItsLastRate():
    crawled, recipes, skipped, siteState, calibration = twoSites()
    blocked = siteHealth.summarise(SITES, crawled, recipes, skipped, siteState, STARTED, {}, calibration)[0]
    assert blocked["alarm"] == {"red": True, "why": "blocked (403)"}
    assert blocked["stopReason"] == "blocked (403)" and blocked["listingComplete"] is False
    assert (blocked["cached"], blocked["recipes"], blocked["shown"]) == (0, 0, 0)
    assert blocked["extraction"] == {"pages": 0, "recipes": 0, "rate": None}
    assert blocked["hidden"] == {reason: 0 for reason in gate.REASONS} and blocked["skipped"] == {}
    assert blocked["calibration"] is None and blocked["pictureStop"] is None
    assert siteState["madeupblocked"]["lastRate"] == 0.9


def test_aHealthySiteCountsItsPagesAndIsJudged():
    crawled, recipes, skipped, siteState, calibration = twoSites()
    healthy = siteHealth.summarise(SITES, crawled, recipes, skipped, siteState, STARTED,
                                   {"madeuphealthy": "429"}, calibration)[1]
    assert (healthy["name"], healthy["kind"]) == ("Made-up Healthy", "drink")
    assert (healthy["listed"], healthy["due"], healthy["fetched"], healthy["notRecipe"], healthy["gone"],
            healthy["errors"]) == (300, 14, 12, 1, 1, 0)
    assert healthy["listingComplete"] is True and healthy["stopReason"] is None
    assert healthy["pictureStop"] == "429"
    assert (healthy["cached"], healthy["recipes"], healthy["shown"]) == (13, 12, 11)
    assert healthy["hidden"] == {**{reason: 0 for reason in gate.REASONS}, "small-photo": 1}
    assert list(healthy["hidden"]) == list(gate.REASONS)
    assert healthy["skipped"] == {"could not be read": 1}
    assert healthy["extraction"] == {"pages": 12, "recipes": 11, "rate": 11 / 12}
    assert healthy["calibration"] == calibration["madeuphealthy"]
    assert healthy["alarm"] == {"red": False, "why": None}
    assert siteState["madeuphealthy"]["lastRate"] == 11 / 12


def test_aPassTooSmallToJudgeLeavesLastRateAlone():
    siteState = {"madeuphealthy": {"lastRate": 0.8}}
    recipes = [recipe("madeuphealthy", n) for n in range(3)]
    for r in recipes:
        pagecache.save("madeuphealthy", r.sourceUrl, "<html>made up</html>", None, fetchedAt=STARTED + 1)
    row = siteHealth.summarise(SITES[1:], {}, recipes, [], siteState, STARTED, {}, {})[0]
    assert row["extraction"] == {"pages": 3, "recipes": 3, "rate": 1.0}
    assert row["alarm"] == {"red": False, "why": None} and row["fetched"] == 0 and row["listed"] == 0
    assert siteState["madeuphealthy"]["lastRate"] == 0.8


def test_aDropAgainstTheLastJudgedRateIsRed():
    siteState = {}
    recipes = [recipe("madeuphealthy", n) for n in range(6)]
    skipped = []
    for n, r in enumerate(recipes):
        pagecache.save("madeuphealthy", r.sourceUrl, "<html>made up</html>", None, fetchedAt=STARTED + 1)
    for n in range(4):
        url = f"https://madeuphealthy.test/topic{n}/"
        pagecache.save("madeuphealthy", url, "<html>made up</html>", None, fetchedAt=STARTED + 1)
        skipped.append({"site": "madeuphealthy", "url": url, "reason": "no recipe", "detail": None})
    siteState["madeuphealthy"] = {"lastRate": 0.85}
    row = siteHealth.summarise(SITES[1:], {}, recipes, skipped, siteState, STARTED, {}, {})[0]
    assert row["alarm"] == {"red": True, "why": "extraction fell from 85% to 60%"}
    assert siteState["madeuphealthy"]["lastRate"] == 0.6


def test_writeStoresTheRowsWithModeAndTime():
    rows = [{"site": "madeuphealthy"}]
    at = datetime(2026, 11, 14, 3, 0, tzinfo=timezone.utc)
    siteHealth.write(rows, "dryrun", at=at)
    stored = json.loads(config.SITES_FILE.read_text(encoding="utf-8"))
    assert stored == {"generatedAt": "2026-11-14T03:00:00+00:00", "mode": "dryrun", "sites": rows}
    assert config.SITES_FILE.parent == config.RUN_DIR and str(config.RUN_DIR).startswith(str(config.BASE_DIR)) is False
    siteHealth.write(rows, "pass")
    assert json.loads(config.SITES_FILE.read_text(encoding="utf-8"))["mode"] == "pass"


# ---------- lastPassAt, and a site not crawled this pass (controller ruling) ----------

CARRIED = ("listed", "due", "fetched", "notRecipe", "gone", "errors", "stopReason", "pictureStop", "listingComplete",
           "extraction", "alarm", "lastPassAt")


def test_aCrawledSiteGetsThePassStartAsLastPassAt():
    crawled, recipes, skipped, siteState, calibration = twoSites()
    rows = siteHealth.summarise(SITES, crawled, recipes, skipped, siteState, STARTED, {}, calibration)
    assert all(row["lastPassAt"] == "1970-01-12T13:46:40+00:00" for row in rows)


def test_aSiteNeverCrawledHasNoLastPassAt():
    rows = siteHealth.summarise(SITES, {}, [], [], {}, STARTED, {}, {}, previous={})
    assert [row["lastPassAt"] for row in rows] == [None, None]
    assert rows[1]["listed"] == 0 and rows[1]["alarm"] == {"red": False, "why": None}


def test_aSiteNotCrawledCarriesItsCrawlFieldsAndRecomputesItsGateFields():
    crawled, recipes, skipped, siteState, calibration = twoSites()
    before = {row["site"]: row for row in
              siteHealth.summarise(SITES, crawled, recipes, skipped, siteState, STARTED, {"madeuphealthy": "429"},
                                   calibration)}
    siteState["madeuphealthy"]["lastRate"] = 0.5
    recipes[0].hiddenReason = "no-time"             # a re-gate changes what is shown
    later = STARTED + 7 * 86400
    rows = siteHealth.summarise(SITES, {"madeupblocked": crawled["madeupblocked"]}, recipes, skipped, siteState,
                                later, {}, {}, previous=before)
    healthy = rows[1]
    for field in CARRIED:
        assert healthy[field] == before["madeuphealthy"][field], field
    assert healthy["lastPassAt"] == "1970-01-12T13:46:40+00:00"
    assert (healthy["recipes"], healthy["shown"]) == (12, 10)
    assert healthy["hidden"]["no-time"] == 1 and healthy["calibration"] is None
    assert siteState["madeuphealthy"]["lastRate"] == 0.5       # not judged: it was not crawled
    assert rows[0]["lastPassAt"] == "1970-01-19T13:46:40+00:00"


def test_previousRowsReadsTheLastSitesFile():
    assert siteHealth.previousRows() == {}
    siteHealth.write([{"site": "madeuphealthy", "listed": 3}], "pass")
    assert siteHealth.previousRows() == {"madeuphealthy": {"site": "madeuphealthy", "listed": 3}}
    config.SITES_FILE.write_text("not json", encoding="utf-8")
    assert siteHealth.previousRows() == {}
