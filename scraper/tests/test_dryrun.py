import json
from datetime import date

from PIL import Image

import config
import dryrun
import net
import pagecache
from models import Recipe
from sources import sites
from conftest import FIXTURES

SITE = {"site": "testsite", "name": "Test Site", "host": "www.example-recipes.test", "sitemaps": [],
        "recipeUrl": "^https://www\\.example-recipes\\.test/[a-z0-9-]+/$", "parser": "schema", "kind": "food",
        "enabled": True}
URL = "https://www.example-recipes.test/made-up-lemon-test-chicken/"


def fakeWorld(monkeypatch, crawled):
    monkeypatch.setattr(sites, "loadSites", lambda rules: [SITE])
    def crawl(siteList, pages, log=print, priority=frozenset(), now=None):
        crawled.append(pages)
        return {"testsite": {"ok": True, "stopReason": None, "listed": 1, "fetched": 1}}
    monkeypatch.setattr(sites, "crawl", crawl)
    def download(url, dest, timeout=30):
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1600, 1000), (200, 100, 50)).save(dest, "PNG")
        return True
    monkeypatch.setattr(net, "download", download)
    pagecache.save("testsite", URL, (FIXTURES / "sites" / "schema-wprm.html").read_text(encoding="utf-8"), None)


def test_aDryRunCrawlsGatesAndReports(monkeypatch):
    crawled = []
    fakeWorld(monkeypatch, crawled)
    folder = dryrun.run(pages=5, log=lambda *a: None, today=date(2026, 11, 14))
    assert folder == config.REPORT_DIR / "dryrun-2026-11-14" and crawled == [5]
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    site = summary["sites"][0]
    assert (site["recipes"], site["listed"], site["passRate"], site["siteNutrition"]) == (1, 1, 1.0, 1)
    sample = json.loads((folder / "samples" / "testsite.json").read_text(encoding="utf-8"))[0]
    assert sample["imageWidth"] == 1600 and sample["hiddenReason"] is None and sample["dishKey"]


def test_aDryRunWithoutFetchingAsksNobody(monkeypatch):
    crawled = []
    fakeWorld(monkeypatch, crawled)
    monkeypatch.setattr(net, "download", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no downloads")))
    folder = dryrun.run(pages=5, log=lambda *a: None, today=date(2026, 11, 14), crawl=False)
    assert crawled == []
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["sites"][0]["gate"]["no-photo"] == 1


def test_aDryRunNeverPublishes(monkeypatch):
    import adminApi
    import publish
    fakeWorld(monkeypatch, [])
    monkeypatch.setattr(publish, "publish", lambda *a, **k: (_ for _ in ()).throw(AssertionError("published")))
    monkeypatch.setattr(adminApi, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked plutus")))
    monkeypatch.setattr(config, "PUBLISH", "on")
    dryrun.run(pages=5, log=lambda *a: None, today=date(2026, 11, 14))


def test_roundRobinTakesOneRecipePerSiteInTurn():
    def r(source, n):
        return Recipe(source=source, sourceId=str(n), kind="food", title="x", ingredients=[], steps=[])
    ordered = dryrun.roundRobin([r("a", 1), r("a", 2), r("a", 3), r("b", 1)])
    assert [(x.source, x.sourceId) for x in ordered] == [("a", "1"), ("b", "1"), ("a", "2"), ("a", "3")]


def test_aDryRunWithNoFdcFoodsWarnsAndHidesRecipesWithoutSiteNutrition(monkeypatch):
    fakeWorld(monkeypatch, [])
    page = (FIXTURES / "sites" / "schema-wprm.html").read_text(encoding="utf-8")
    pagecache.save("testsite", URL, page.replace('"nutrition"', '"noNutrition"'), None)
    logged = []
    folder = dryrun.run(pages=5, log=logged.append, today=date(2026, 11, 14))
    assert any("no FDC foods" in message for message in logged)
    assert any(message.startswith("FDC: 0 foods") for message in logged)
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["nutrition"]["estimate"] == 0
    assert summary["sites"][0]["siteNutrition"] == 0 and summary["sites"][0]["gate"]["no-nutrition"] == 1
    queue = json.loads(config.FDC_QUEUE_FILE.read_text(encoding="utf-8"))
    assert queue["queue"] and all(row["candidates"] == [] for row in queue["queue"]) and queue["generatedAt"].endswith("+00:00")
    assert json.loads((folder / "fdc-queue.json").read_text(encoding="utf-8")) == queue
    assert "## Nutrition" in (folder / "summary.md").read_text(encoding="utf-8")
