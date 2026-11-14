import gzip
from urllib.robotparser import RobotFileParser

import pytest

import net
from sources import sites

HOST = "www.example-recipes.test"
SITE = {"site": "testsite", "name": "Test Site", "host": HOST,
        "sitemaps": [f"https://{HOST}/sitemap_index.xml"],
        "recipeUrl": r"^https://www\.example-recipes\.test/[a-z0-9-]+/$",
        "parser": "schema", "kind": "food", "enabled": True}
QUIET = lambda *args: None  # noqa: E731


def urlset(*entries):
    rows = "".join(f"<url><loc>{url}</loc>" + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "") + "</url>"
                   for url, lastmod in entries)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>')


def sitemapIndex(*locs):
    rows = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</sitemapindex>')


def fakeCrawl(monkeypatch, answers):
    """net.crawl answering from url -> text, bytes or an exception to raise; any other url is a 404."""
    asked = []
    def crawl(url, *, binary=False, timeout=20, retries=2):
        asked.append(url)
        answer = answers.get(url)
        if answer is None:
            raise net.HttpError(f"GET {url} -> 404", status=404)
        if isinstance(answer, BaseException):     # BaseException: Task 4 also raises KeyboardInterrupt
            raise answer
        data = answer.encode("utf-8") if isinstance(answer, str) else answer
        return data if binary else data.decode("utf-8")
    monkeypatch.setattr(net, "crawl", crawl)
    return asked


def robotsFrom(*lines):
    robots = RobotFileParser()
    robots.parse(list(lines))
    return robots


def test_robotsRulesAreObeyed(monkeypatch):
    fakeCrawl(monkeypatch, {f"https://{HOST}/robots.txt": "User-agent: *\nDisallow: /private/\n"})
    robots = sites.robotsFor(SITE)
    assert robots.can_fetch(sites.AGENT, f"https://{HOST}/made-up-stew/")
    assert not robots.can_fetch(sites.AGENT, f"https://{HOST}/private/made-up-stew/")


def test_aMissingRobotsFileAllowsEverything(monkeypatch):
    fakeCrawl(monkeypatch, {})
    assert sites.robotsFor(SITE).can_fetch(sites.AGENT, f"https://{HOST}/made-up-stew/")


@pytest.mark.parametrize("status, reason", [(403, "blocked (403)"), (429, "rate limited (429)")])
def test_aRefusedRobotsFileStopsTheSite(monkeypatch, status, reason):
    fakeCrawl(monkeypatch, {f"https://{HOST}/robots.txt": net.HttpError("refused", status=status)})
    with pytest.raises(sites.SiteStopped) as stop:
        sites.robotsFor(SITE)
    assert stop.value.reason == reason


def test_anUnreachableRobotsFileStopsTheSite(monkeypatch):
    fakeCrawl(monkeypatch, {f"https://{HOST}/robots.txt": net.HttpError("down", status=503)})
    with pytest.raises(sites.SiteStopped, match="robots.txt unreachable"):
        sites.robotsFor(SITE)


def test_indexesAreFollowedAndOnlyRecipePagesKeptNewestFirst(monkeypatch):
    fakeCrawl(monkeypatch, {
        f"https://{HOST}/sitemap_index.xml": sitemapIndex(f"https://{HOST}/post-sitemap.xml",
                                                          f"https://{HOST}/page-sitemap.xml"),
        f"https://{HOST}/post-sitemap.xml": urlset((f"https://{HOST}/made-up-stew/", "2026-10-01"),
                                                   (f"https://{HOST}/made-up-soup/", "2026-11-02T08:00:00+00:00"),
                                                   (f"https://{HOST}/made-up-salad/", None),
                                                   (f"https://{HOST}/tag/soup/", "2026-11-03")),
        f"https://{HOST}/page-sitemap.xml": urlset((f"https://{HOST}/about/team/", "2026-01-01")),
    })
    assert sites.sitemapEntries(SITE, robotsFrom(), log=QUIET) == [
        (f"https://{HOST}/made-up-soup/", "2026-11-02T08:00:00+00:00"),
        (f"https://{HOST}/made-up-stew/", "2026-10-01T00:00:00+00:00"),
        (f"https://{HOST}/made-up-salad/", None),
    ]


def test_aPageListedTwiceKeepsItsNewestLastmod(monkeypatch):
    fakeCrawl(monkeypatch, {
        f"https://{HOST}/sitemap_index.xml": sitemapIndex(f"https://{HOST}/a.xml", f"https://{HOST}/b.xml"),
        f"https://{HOST}/a.xml": urlset((f"https://{HOST}/made-up-stew/", "2026-11-05")),
        f"https://{HOST}/b.xml": urlset((f"https://{HOST}/made-up-stew/", "2026-10-01")),
    })
    assert sites.sitemapEntries(SITE, robotsFrom(), log=QUIET) == [
        (f"https://{HOST}/made-up-stew/", "2026-11-05T00:00:00+00:00")]


def test_aDisallowedSitemapIsNotAsked(monkeypatch):
    asked = fakeCrawl(monkeypatch, {
        f"https://{HOST}/sitemap_index.xml": sitemapIndex(f"https://{HOST}/post-sitemap.xml",
                                                          f"https://{HOST}/private-sitemap.xml"),
        f"https://{HOST}/post-sitemap.xml": urlset((f"https://{HOST}/made-up-stew/", None)),
        f"https://{HOST}/private-sitemap.xml": urlset((f"https://{HOST}/made-up-secret/", None)),
    })
    entries = sites.sitemapEntries(SITE, robotsFrom("User-agent: *", "Disallow: /private-sitemap.xml"), log=QUIET)
    assert f"https://{HOST}/private-sitemap.xml" not in asked
    assert entries == [(f"https://{HOST}/made-up-stew/", None)]


def test_aGzippedSitemapIsRead(monkeypatch):
    fakeCrawl(monkeypatch, {f"https://{HOST}/sitemap_index.xml":
                            gzip.compress(urlset((f"https://{HOST}/made-up-stew/", None)).encode("utf-8"))})
    assert sites.sitemapEntries(SITE, robotsFrom(), log=QUIET) == [(f"https://{HOST}/made-up-stew/", None)]


def test_aCorruptGzippedSitemapIsSkippedAndTheRestRead(monkeypatch):
    fakeCrawl(monkeypatch, {
        f"https://{HOST}/sitemap_index.xml": sitemapIndex(f"https://{HOST}/bad.xml", f"https://{HOST}/good.xml"),
        f"https://{HOST}/bad.xml": b"\x1f\x8b\x08\x00corrupt-not-really-gzip",
        f"https://{HOST}/good.xml": urlset((f"https://{HOST}/made-up-stew/", None)),
    })
    assert sites.sitemapEntries(SITE, robotsFrom(), log=QUIET) == [(f"https://{HOST}/made-up-stew/", None)]


def test_aSitemapOnAnotherHostIsNotAsked(monkeypatch):
    asked = fakeCrawl(monkeypatch, {
        f"https://{HOST}/sitemap_index.xml": sitemapIndex("https://other.example.test/sitemap.xml",
                                                          f"https://{HOST}/post-sitemap.xml"),
        "https://other.example.test/sitemap.xml": urlset((f"https://{HOST}/made-up-other/", None)),
        f"https://{HOST}/post-sitemap.xml": urlset((f"https://{HOST}/made-up-stew/", None)),
    })
    entries = sites.sitemapEntries(SITE, robotsFrom(), log=QUIET)
    assert "https://other.example.test/sitemap.xml" not in asked
    assert entries == [(f"https://{HOST}/made-up-stew/", None)]


def test_robotsThatDisallowEveryRecipePageStopTheSite(monkeypatch):
    fakeCrawl(monkeypatch, {
        f"https://{HOST}/sitemap_index.xml": sitemapIndex(f"https://{HOST}/post-sitemap.xml"),
        f"https://{HOST}/post-sitemap.xml": urlset((f"https://{HOST}/made-up-stew/", None)),
    })
    robots = robotsFrom("User-agent: *", "Allow: /sitemap_index.xml", "Allow: /post-sitemap.xml", "Disallow: /")
    with pytest.raises(sites.SiteStopped, match="robots.txt disallows the recipe pages"):
        sites.sitemapEntries(SITE, robots, log=QUIET)


def test_sitemapsWithoutRecipePagesStopTheSite(monkeypatch):
    fakeCrawl(monkeypatch, {f"https://{HOST}/sitemap_index.xml": urlset((f"https://{HOST}/about/team/", None))})
    with pytest.raises(sites.SiteStopped, match="no recipe pages"):
        sites.sitemapEntries(SITE, robotsFrom(), log=QUIET)


def test_a429OnASitemapStopsTheSiteWithItsRetryAfter(monkeypatch):
    fakeCrawl(monkeypatch, {f"https://{HOST}/sitemap_index.xml":
                            net.HttpError("slow down", status=429, retryAfter=600.0)})
    with pytest.raises(sites.SiteStopped) as stop:
        sites.sitemapEntries(SITE, robotsFrom(), log=QUIET)
    assert (stop.value.reason, stop.value.retryAfter) == ("rate limited (429)", 600.0)


@pytest.mark.parametrize("lastmod, cached, recheck, due", [
    (None, None, False, True),                                                  # never fetched
    ("2026-11-02", {"lastmod": "2026-11-01T00:00:00+00:00"}, False, True),     # changed since
    ("2026-11-01", {"lastmod": "2026-11-01T00:00:00+00:00"}, False, False),    # unchanged
    ("2026-11-01T00:00:00+00:00", {"lastmod": None}, False, True),             # the site began giving lastmod
    (None, {"lastmod": None}, False, False),                                   # no lastmod: kept
    (None, {"lastmod": None}, True, True),                                     # ... until the fourth-pass recheck
])
def test_isDue(lastmod, cached, recheck, due):
    assert sites.isDue(lastmod, cached, recheck) is due


import re

import rulesData


def test_loadSitesKeepsTheEnabledEntries():
    rules = {"sites": [dict(SITE), dict(SITE, site="off", enabled=False)]}
    assert [site["site"] for site in sites.loadSites(rules)] == ["testsite"]


@pytest.mark.parametrize("change, message", [
    ({"parser": "html"}, "parser"), ({"kind": "snack"}, "kind"), ({"recipeUrl": "("}, "recipeUrl"),
])
def test_aMalformedSiteEntryIsRefused(change, message):
    with pytest.raises(ValueError, match=message):
        sites.loadSites({"sites": [dict(SITE, **change)]})


def test_aSiteEntryMissingAFieldIsRefused():
    entry = dict(SITE)
    del entry["host"]
    with pytest.raises(ValueError, match="host"):
        sites.loadSites({"sites": [entry]})


def test_theSitesFileNamesTheFiveSitesWithDiscoveredValues():
    entries = rulesData.load()["sites"]
    assert [e["site"] for e in entries] == ["bbcgoodfood", "budgetbytes", "recipetineats", "pinchofyum", "difford"]
    for entry in entries:
        assert set(entry) == set(sites.FIELDS), entry["site"]
        # Fails while a value the discovery step fills in is still missing.
        assert entry["sitemaps"] and all(url.startswith("https://") for url in entry["sitemaps"]), entry["site"]
        pattern = re.compile(entry["recipeUrl"])
        assert entry["recipeUrl"].startswith("^https://"), entry["site"]
        assert not pattern.match(f"https://{entry['host']}/"), entry["site"]
    kinds = {e["site"]: (e["parser"], e["kind"], e["name"]) for e in entries}
    assert kinds["difford"] == ("difford", "drink", "Difford's Guide")
    assert kinds["recipetineats"] == ("schema", "food", "RecipeTin Eats")
    assert len(sites.loadSites(rulesData.load())) == sum(1 for e in entries if e["enabled"])
