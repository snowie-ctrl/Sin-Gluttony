import gzip
from urllib.parse import urlsplit

import pytest

import net
import robots as robotsTxt
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


class Redirect:
    """An answer that sends the request on to another url, as a 301 would."""
    def __init__(self, target):
        self.target = target


def fakeCrawl(monkeypatch, answers):
    """
    net.crawl answering from url -> text, bytes, a Redirect or an exception to raise; any other url is a 404.
    A redirect to another host is refused the way net.crawl refuses it; the final url goes into finalUrl.
    """
    asked = []
    def crawl(url, *, binary=False, timeout=20, retries=2, finalUrl=None):
        asked.append(url)
        answer, final = answers.get(url), url
        while isinstance(answer, Redirect):
            if urlsplit(answer.target).hostname != urlsplit(url).hostname:
                raise net.HttpError(f"GET {url} redirected off host", status=None)
            final = answer.target
            answer = answers.get(final)
        if finalUrl is not None:
            finalUrl.append(final)
        if answer is None:
            raise net.HttpError(f"GET {url} -> 404", status=404)
        if isinstance(answer, BaseException):     # BaseException: Task 4 also raises KeyboardInterrupt
            raise answer
        data = answer.encode("utf-8") if isinstance(answer, str) else answer
        return data if binary else data.decode("utf-8")
    monkeypatch.setattr(net, "crawl", crawl)
    return asked


def robotsFrom(*lines):
    return robotsTxt.Rules.parse("\n".join(lines))


def test_robotsRulesAreObeyed(monkeypatch):
    fakeCrawl(monkeypatch, {f"https://{HOST}/robots.txt": "User-agent: *\nDisallow: /private/\n"})
    robots = sites.robotsFor(SITE)
    assert robots.allows(sites.AGENT, f"https://{HOST}/made-up-stew/")
    assert not robots.allows(sites.AGENT, f"https://{HOST}/private/made-up-stew/")


def test_aMissingRobotsFileAllowsEverything(monkeypatch):
    fakeCrawl(monkeypatch, {})
    assert sites.robotsFor(SITE).allows(sites.AGENT, f"https://{HOST}/made-up-stew/")


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


def test_onlyChildSitemapsMatchingTheFilterAreFollowed(monkeypatch):
    asked = fakeCrawl(monkeypatch, {
        f"https://{HOST}/sitemap_index.xml": sitemapIndex(f"https://{HOST}/post-sitemap.xml",
                                                          f"https://{HOST}/post-sitemap2.xml",
                                                          f"https://{HOST}/page-sitemap.xml"),
        f"https://{HOST}/post-sitemap.xml": urlset((f"https://{HOST}/made-up-stew/", "2026-10-01")),
        f"https://{HOST}/post-sitemap2.xml": urlset((f"https://{HOST}/made-up-soup/", "2026-10-02")),
        f"https://{HOST}/page-sitemap.xml": urlset((f"https://{HOST}/made-up-page/", "2026-10-03")),
    })
    site = dict(SITE, sitemapFilter=r"post-sitemap\d*\.xml$")
    found = sites.sitemapEntries(site, robotsFrom(), log=QUIET)
    assert [url for url, _ in found] == [f"https://{HOST}/made-up-soup/", f"https://{HOST}/made-up-stew/"]
    assert f"https://{HOST}/page-sitemap.xml" not in asked


def test_aNewChildSitemapInTheIndexIsDiscovered(monkeypatch):
    fakeCrawl(monkeypatch, {
        f"https://{HOST}/sitemap_index.xml": sitemapIndex(f"https://{HOST}/2027-Q1-recipe.xml"),
        f"https://{HOST}/2027-Q1-recipe.xml": urlset((f"https://{HOST}/made-up-new/", "2027-01-05")),
    })
    site = dict(SITE, sitemapFilter=r"-recipe\.xml$")
    assert sites.sitemapEntries(site, robotsFrom(), log=QUIET) == [(f"https://{HOST}/made-up-new/",
                                                                    "2027-01-05T00:00:00+00:00")]


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
    ({"sitemapFilter": "("}, "sitemapFilter"), ({"parser": "html"}, "parser"), ({"kind": "snack"}, "kind"), ({"recipeUrl": "("}, "recipeUrl"),
])
def test_aMalformedSiteEntryIsRefused(change, message):
    with pytest.raises(ValueError, match=message):
        sites.loadSites({"sites": [dict(SITE, **change)]})


def test_aSiteEntryMissingAFieldIsRefused():
    entry = dict(SITE)
    del entry["host"]
    with pytest.raises(ValueError, match="host"):
        sites.loadSites({"sites": [entry]})


def test_theSitesFileNamesTheSixSitesWithDiscoveredValues():
    entries = rulesData.load()["sites"]
    assert [e["site"] for e in entries] == ["bbcgoodfood", "budgetbytes", "recipetineats", "pinchofyum", "loveandlemons", "difford"]
    for entry in entries:
        assert set(sites.FIELDS) <= set(entry) <= set(sites.FIELDS) | set(sites.OPTIONAL_FIELDS), entry["site"]
        re.compile(entry["sitemapFilter"])
        # Fails while a value the discovery step fills in is still missing.
        assert entry["sitemaps"] and all(url.startswith("https://") for url in entry["sitemaps"]), entry["site"]
        pattern = re.compile(entry["recipeUrl"])
        assert entry["recipeUrl"].startswith("^https://"), entry["site"]
        assert not pattern.match(f"https://{entry['host']}/"), entry["site"]
    kinds = {e["site"]: (e["parser"], e["kind"], e["name"]) for e in entries}
    assert kinds["difford"] == ("difford", "drink", "Difford's Guide")
    assert kinds["recipetineats"] == ("schema", "food", "RecipeTin Eats")
    assert len(sites.loadSites(rulesData.load())) == sum(1 for e in entries if e["enabled"])


def test_aSitemapOnAnotherHostThanTheEntrysIsRefused():
    with pytest.raises(ValueError, match="host"):
        sites.loadSites({"sites": [dict(SITE, sitemaps=["https://other.example.test/sitemap.xml"])]})


def test_recipeTinEatsPatternTakesRecipesAndNotTheBlogPage():
    entry = next(e for e in rulesData.load()["sites"] if e["site"] == "recipetineats")
    pattern = re.compile(entry["recipeUrl"])
    assert pattern.match("https://www.recipetineats.com/giant-hash-brown/")
    assert pattern.match("https://www.recipetineats.com/blogger-style-pasta/")
    assert not pattern.match("https://www.recipetineats.com/blog/")


import config
import pagecache
import store

A, B = "www.site-a.test", "www.site-b.test"


def siteFor(host, name):
    return dict(SITE, site=name, name=name.title(), host=host, sitemaps=[f"https://{host}/sitemap_index.xml"],
                recipeUrl=rf"^https://{re.escape(host)}/[a-z0-9-]+/$")


def recipePage(title):
    return ('<html><head><script type="application/ld+json">'
            f'{{"@context":"https://schema.org","@type":"Recipe","name":"{title}"}}'
            '</script></head><body></body></html>')


def web(host, pages, lastmods=None, robots="User-agent: *\nAllow: /\n"):
    """robots.txt, a sitemap index, one urlset and the pages of one made-up site; pages maps slug -> answer."""
    lastmods = lastmods or {}
    answers = {f"https://{host}/robots.txt": robots,
               f"https://{host}/sitemap_index.xml": sitemapIndex(f"https://{host}/post-sitemap.xml"),
               f"https://{host}/post-sitemap.xml": urlset(*[(f"https://{host}/{slug}/", lastmods.get(slug))
                                                            for slug in pages])}
    answers.update({f"https://{host}/{slug}/": answer for slug, answer in pages.items() if answer is not None})
    return answers


def pageUrls(asked):
    return [url for url in asked if "/made-up-" in url]


def test_dueRecipePagesAreFetchedAndCached(monkeypatch):
    fakeCrawl(monkeypatch, web(A, {"made-up-stew": recipePage("Made-up Stew"), "made-up-soup": recipePage("Made-up Soup")},
                               lastmods={"made-up-stew": "2026-11-01"}))
    result = sites.crawl([siteFor(A, "sitea")], pages=10, log=QUIET, now=lambda: 1000.0)["sitea"]
    assert (result["ok"], result["listed"], result["due"], result["fetched"]) == (True, 2, 2, 2)
    url = f"https://{A}/made-up-stew/"
    assert "Made-up Stew" in pagecache.load("sitea", url)
    assert pagecache.meta("sitea", url) == {"url": url, "fetchedAt": 1000.0, "lastmod": "2026-11-01T00:00:00+00:00"}
    assert pagecache.listing("sitea")[0] == (url, "2026-11-01T00:00:00+00:00")


def test_aSecondPassFetchesOnlyWhatChanged(monkeypatch):
    answers = web(A, {"made-up-stew": recipePage("Made-up Stew"), "made-up-soup": recipePage("Made-up Soup")},
                  lastmods={"made-up-stew": "2026-11-01", "made-up-soup": "2026-11-01"})
    asked = fakeCrawl(monkeypatch, answers)
    sites.crawl([siteFor(A, "sitea")], pages=10, log=QUIET)
    answers[f"https://{A}/post-sitemap.xml"] = urlset((f"https://{A}/made-up-stew/", "2026-11-09"),
                                                      (f"https://{A}/made-up-soup/", "2026-11-01"))
    asked.clear()
    result = sites.crawl([siteFor(A, "sitea")], pages=10, log=QUIET)["sitea"]
    assert result["fetched"] == 1 and pageUrls(asked) == [f"https://{A}/made-up-stew/"]


def test_pagesCapsEachSiteAndPriorityPagesComeFirst(monkeypatch):
    asked = fakeCrawl(monkeypatch, web(A, {"made-up-a": recipePage("A"), "made-up-b": recipePage("B"),
                                           "made-up-c": recipePage("C")},
                                       lastmods={"made-up-a": "2026-01-01", "made-up-b": "2026-06-01",
                                                 "made-up-c": "2026-11-01"}))
    result = sites.crawl([siteFor(A, "sitea")], pages=2, log=QUIET, priority={f"https://{A}/made-up-a/"})["sitea"]
    assert pageUrls(asked) == [f"https://{A}/made-up-a/", f"https://{A}/made-up-c/"]
    assert (result["listed"], result["planned"]) == (3, 2)


def test_theSitesTakeTurns(monkeypatch):
    answers = web(A, {"made-up-one": recipePage("1"), "made-up-two": recipePage("2")})
    answers.update(web(B, {"made-up-one": recipePage("1"), "made-up-two": recipePage("2")}))
    asked = fakeCrawl(monkeypatch, answers)
    sites.crawl([siteFor(A, "sitea"), siteFor(B, "siteb")], pages=None, log=QUIET)
    assert pageUrls(asked) == [f"https://{A}/made-up-one/", f"https://{B}/made-up-one/",
                               f"https://{A}/made-up-two/", f"https://{B}/made-up-two/"]


def test_a403StopsOnlyThatSiteForThePass(monkeypatch):
    answers = web(A, {"made-up-one": net.HttpError("no", status=403), "made-up-two": recipePage("2")})
    answers.update(web(B, {"made-up-one": recipePage("1"), "made-up-two": recipePage("2")}))
    asked = fakeCrawl(monkeypatch, answers)
    results = sites.crawl([siteFor(A, "sitea"), siteFor(B, "siteb")], pages=None, log=QUIET)
    assert (results["sitea"]["ok"], results["sitea"]["stopReason"]) == (False, "blocked (403)")
    assert f"https://{A}/made-up-two/" not in asked
    assert results["siteb"]["fetched"] == 2


def test_a429IsHonouredOnTheNextPassNotThisOne(monkeypatch):
    answers = web(A, {"made-up-one": net.HttpError("slow", status=429, retryAfter=3600.0)})
    asked = fakeCrawl(monkeypatch, answers)
    first = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET, now=lambda: 1000.0)["sitea"]
    assert first["stopReason"] == "rate limited (429)"
    assert store.readJson(config.SITE_STATE_FILE)["sitea"]["notBefore"] == 4600.0
    asked.clear()
    waiting = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET, now=lambda: 2000.0)["sitea"]
    assert waiting["stopReason"] == "waiting for the Retry-After a 429 asked for" and asked == []
    answers[f"https://{A}/made-up-one/"] = recipePage("1")
    later = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET, now=lambda: 5000.0)["sitea"]
    assert later["ok"] and later["fetched"] == 1


def test_aChallengePageStopsTheSiteAndIsNotCached(monkeypatch):
    wall = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
    fakeCrawl(monkeypatch, web(A, {"made-up-one": wall, "made-up-two": recipePage("2")}))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert result["stopReason"].startswith("walled") and result["fetched"] == 0
    assert pagecache.meta("sitea", f"https://{A}/made-up-one/") is None


def test_aPageWithoutRecipeMarkupIsSkippedNotCached(monkeypatch):
    fakeCrawl(monkeypatch, web(A, {"made-up-post": "<html><body>Made-up blog post</body></html>",
                                   "made-up-stew": recipePage("Made-up Stew")}))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert (result["ok"], result["notRecipe"], result["fetched"]) == (True, 1, 1)
    assert pagecache.meta("sitea", f"https://{A}/made-up-post/") is None


def test_tenPagesInARowWithoutRecipeMarkupStopTheSite(monkeypatch):
    asked = fakeCrawl(monkeypatch, web(A, {f"made-up-{n:02d}": "<html><body>Made-up</body></html>"
                                           for n in range(12)}))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert result["stopReason"] == "walled (10 pages in a row without recipe markup)"
    assert len(pageUrls(asked)) == 10


def test_fiveFailedRequestsInARowStopTheSite(monkeypatch):
    asked = fakeCrawl(monkeypatch, web(A, {f"made-up-{n}": net.HttpError("down", status=503) for n in range(7)}))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert result["stopReason"].startswith("unreachable") and len(pageUrls(asked)) == 5


def test_aPageGoneTwiceInARowCountsAsGone(monkeypatch):
    fakeCrawl(monkeypatch, web(A, {"made-up-gone": None, "made-up-stew": recipePage("Made-up Stew")}))
    first = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    second = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert (first["gone"], second["gone"]) == (0, 1)


def test_aSiteWithoutLastmodIsRecheckedEveryFourthPass(monkeypatch):
    fakeCrawl(monkeypatch, web(A, {"made-up-stew": recipePage("Made-up Stew")}))
    fetched = [sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]["fetched"] for _ in range(5)]
    assert fetched == [1, 0, 0, 0, 1]


def test_aCrawlDelayAboveFiveSecondsIsHonoured(monkeypatch):
    monkeypatch.setattr(net, "MIN_INTERVAL", dict(net.MIN_INTERVAL))
    fakeCrawl(monkeypatch, web(A, {"made-up-stew": recipePage("Made-up Stew")},
                               robots="User-agent: *\nCrawl-delay: 12\nAllow: /\n"))
    sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)
    assert net.MIN_INTERVAL[A] == 12.0


def test_siteStateIsSavedEvenWhenThePassBreaks(monkeypatch):
    fakeCrawl(monkeypatch, web(A, {"made-up-stew": KeyboardInterrupt()}))
    with pytest.raises(KeyboardInterrupt):
        sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)
    assert store.readJson(config.SITE_STATE_FILE)["sitea"]["passes"] == 1


def blogPost(n):
    return ('<html><head><meta property="og:type" content="article">'
            '<script type="application/ld+json">'
            f'{{"@context":"https://schema.org","@type":"BlogPosting","headline":"Made-up Post {n}"}}'
            '</script></head><body>Made-up blog post</body></html>')


BARE = "<html><body>Made-up</body></html>"


def test_ordinaryBlogPostsDoNotStopTheSiteAndCountAsNotRecipe(monkeypatch):
    pages = {f"made-up-post-{n:02d}": blogPost(n) for n in range(12)}
    pages["made-up-zz-stew"] = recipePage("Made-up Stew")
    fakeCrawl(monkeypatch, web(A, pages))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert (result["ok"], result["notRecipe"], result["fetched"]) == (True, 12, 1)
    assert pagecache.meta("sitea", f"https://{A}/made-up-post-00/") is None


def test_aPageWithOnlyAnOgTypeIsOrdinaryToo(monkeypatch):
    page = '<html><head><meta property="og:type" content="article"></head><body>Made-up</body></html>'
    fakeCrawl(monkeypatch, web(A, {f"made-up-{n:02d}": page for n in range(12)}))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert (result["ok"], result["notRecipe"]) == (True, 12)


def test_blogPostsNeitherAdvanceNorResetTheBareRun(monkeypatch):
    pages = {f"made-up-{n:02d}": (blogPost(n) if n == 4 else BARE) for n in range(12)}
    asked = fakeCrawl(monkeypatch, web(A, pages))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert result["stopReason"] == "walled (10 pages in a row without recipe markup)"
    assert len(pageUrls(asked)) == 11      # ten bare pages, with the blog post among them


def test_aBlogPostWithCloudflareAndCaptchaMarkupIsOrdinaryNotAWall(monkeypatch):
    post = ('<html><head><script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
            '<script type="application/ld+json">{"@type":"BlogPosting","headline":"Made-up Post"}</script>'
            '</head><body>Made-up post. Leave a comment: captcha. Access denied is a phrase.</body></html>')
    fakeCrawl(monkeypatch, web(A, {"made-up-post": post, "made-up-stew": recipePage("Made-up Stew")}))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert (result["ok"], result["notRecipe"], result["fetched"]) == (True, 1, 1)


def test_aBarePageTitledJustAMomentStopsTheSiteAtOnceAndNamesTheUrl(monkeypatch):
    wall = "<html><head><title>Just a moment...</title></head><body>Checking</body></html>"
    asked = fakeCrawl(monkeypatch, web(A, {"made-up-one": wall, "made-up-two": recipePage("2")}))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert result["stopReason"].startswith("walled") and f"https://{A}/made-up-one/" in result["stopReason"]
    assert len(pageUrls(asked)) == 1


def test_aKnownNonRecipePageIsNotAskedAgainUntilItsLastmodChanges(monkeypatch):
    answers = web(A, {"made-up-post": blogPost(1), "made-up-stew": recipePage("Made-up Stew")},
                  lastmods={"made-up-post": "2026-11-01", "made-up-stew": "2026-11-01"})
    asked = fakeCrawl(monkeypatch, answers)
    first = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert first["notRecipe"] == 1
    asked.clear()
    second = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert pageUrls(asked) == [] and second["notRecipe"] == 0
    answers[f"https://{A}/post-sitemap.xml"] = urlset((f"https://{A}/made-up-post/", "2026-11-09"),
                                                      (f"https://{A}/made-up-stew/", "2026-11-01"))
    third = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert pageUrls(asked) == [f"https://{A}/made-up-post/"] and third["notRecipe"] == 1


def test_knownNonRecipePagesDoNotTakeSlotsFromThePagesLimit(monkeypatch):
    answers = web(A, {"made-up-post": blogPost(1), "made-up-stew": recipePage("Made-up Stew")},
                  lastmods={"made-up-post": "2026-11-09", "made-up-stew": "2026-11-01"})
    asked = fakeCrawl(monkeypatch, answers)
    sites.crawl([siteFor(A, "sitea")], pages=1, log=QUIET)      # the newer blog post takes the one slot
    asked.clear()
    second = sites.crawl([siteFor(A, "sitea")], pages=1, log=QUIET)["sitea"]
    assert pageUrls(asked) == [f"https://{A}/made-up-stew/"] and second["fetched"] == 1


def test_aKnownNonRecipePageIsAskedAgainEveryFourthPass(monkeypatch):
    answers = web(A, {"made-up-post": blogPost(1), "made-up-stew": recipePage("Made-up Stew")},
                  lastmods={"made-up-post": "2026-11-01", "made-up-stew": "2026-11-01"})
    asked = fakeCrawl(monkeypatch, answers)
    post = f"https://{A}/made-up-post/"
    seen = []
    for _ in range(5):
        asked.clear()
        sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)
        seen.append(post in asked)
    assert seen == [True, False, False, False, True]


def test_aBasicIsNeverHeldBackByTheNonRecipeMemory(monkeypatch):
    answers = web(A, {"made-up-post": blogPost(1), "made-up-stew": recipePage("Made-up Stew")},
                  lastmods={"made-up-post": "2026-11-01", "made-up-stew": "2026-11-01"})
    asked = fakeCrawl(monkeypatch, answers)
    post = f"https://{A}/made-up-post/"
    sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)
    asked.clear()
    second = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET, priority={post})["sitea"]
    assert pageUrls(asked) == [post] and second["notRecipe"] == 1


def test_eachSiteEndsWithOneLineOfAllItsCounters(monkeypatch):
    fakeCrawl(monkeypatch, {**web(A, {"made-up-post": blogPost(1), "made-up-stew": recipePage("Made-up Stew")}),
                            **web(B, {"made-up-soup": recipePage("Made-up Soup")}, robots="User-agent: *\nDisallow: /\n")})
    lines = []
    sites.crawl([siteFor(A, "sitea"), siteFor(B, "siteb")], pages=None, log=lines.append)
    assert [l for l in lines if l.startswith("sitea: done")] == [
        "sitea: done: 2 due, 1 fetched, 1 notRecipe, 0 gone, 0 errors, not stopped"]
    assert [l for l in lines if l.startswith("siteb: done")] == [
        "siteb: done: 0 due, 0 fetched, 0 notRecipe, 0 gone, 0 errors, stopped (no recipe pages in the sitemaps)"]


def test_aPassWithAFailedChildSitemapDoesNotShrinkTheSavedListing(monkeypatch):
    site = siteFor(A, "sitea")
    answers = web(A, {"made-up-stew": None, "made-up-soup": None})
    answers[f"https://{A}/sitemap_index.xml"] = sitemapIndex(f"https://{A}/post-sitemap.xml",
                                                             f"https://{A}/more-sitemap.xml")
    answers[f"https://{A}/more-sitemap.xml"] = urlset((f"https://{A}/made-up-salad/", None))
    fakeCrawl(monkeypatch, dict(answers))
    sites.crawl([site], pages=0, log=QUIET)
    assert len(pagecache.listing("sitea")) == 3
    del answers[f"https://{A}/more-sitemap.xml"]            # a later pass cannot read one child sitemap
    messages = []
    fakeCrawl(monkeypatch, answers)
    sites.crawl([site], pages=0, log=messages.append)
    assert len(pagecache.listing("sitea")) == 3
    assert any("listing kept" in m for m in messages)
    answers[f"https://{A}/more-sitemap.xml"] = urlset()      # every sitemap read: the listing may now shrink
    fakeCrawl(monkeypatch, answers)
    sites.crawl([site], pages=0, log=QUIET)
    assert len(pagecache.listing("sitea")) == 2


def test_loveAndLemonsTakesPostPagesAndLeavesItsSectionPagesOut():
    entry = [e for e in rulesData.load()["sites"] if e["site"] == "loveandlemons"][0]
    pattern = re.compile(entry["recipeUrl"])
    assert pattern.match("https://www.loveandlemons.com/made-up-lemon-test-soup/")
    assert pattern.match("https://www.loveandlemons.com/made-up-test-recipe/")
    for url in ("https://www.loveandlemons.com/weekend/", "https://www.loveandlemons.com/instagram/",
                "https://www.loveandlemons.com/category/made-up/", "https://www.loveandlemons.com/made-up/page/2/"):
        assert not pattern.match(url), url
    assert re.search(entry["sitemapFilter"], "https://www.loveandlemons.com/post-sitemap2.xml")
    assert not re.search(entry["sitemapFilter"], "https://www.loveandlemons.com/page-sitemap.xml")


# Milestone 3: a listing is complete only when every sitemap was read; redirects and big sitemaps.

def twoChildWeb(robots="User-agent: *\nAllow: /\n"):
    """A made-up site whose index names post-sitemap (stew, soup) and more-sitemap (salad); no page answers."""
    answers = web(A, {"made-up-stew": None, "made-up-soup": None}, robots=robots)
    answers[f"https://{A}/sitemap_index.xml"] = sitemapIndex(f"https://{A}/post-sitemap.xml",
                                                             f"https://{A}/more-sitemap.xml")
    answers[f"https://{A}/more-sitemap.xml"] = urlset((f"https://{A}/made-up-salad/", None))
    return answers


def firstPassSavesThree(monkeypatch, answers):
    fakeCrawl(monkeypatch, dict(answers))
    first = sites.crawl([siteFor(A, "sitea")], pages=0, log=QUIET)["sitea"]
    assert first["complete"] is True and len(pagecache.listing("sitea")) == 3


def test_aSuccessfulPassSavesTheListingAndSaysItIsComplete(monkeypatch):
    fakeCrawl(monkeypatch, twoChildWeb())
    result = sites.crawl([siteFor(A, "sitea")], pages=0, log=QUIET)["sitea"]
    assert result["complete"] is True and result["goneUrls"] == []
    assert len(pagecache.listing("sitea")) == 3


def test_aChildSitemapDisallowedByRobotsMakesTheListingIncomplete(monkeypatch):
    answers = twoChildWeb()
    firstPassSavesThree(monkeypatch, answers)
    answers[f"https://{A}/robots.txt"] = "User-agent: *\nDisallow: /more-sitemap.xml\n"
    asked = fakeCrawl(monkeypatch, answers)
    failures = []
    sites.sitemapEntries(siteFor(A, "sitea"), robotsFrom("User-agent: *", "Disallow: /more-sitemap.xml"),
                         log=QUIET, failures=failures)
    assert failures and f"https://{A}/more-sitemap.xml" not in asked
    result = sites.crawl([siteFor(A, "sitea")], pages=0, log=QUIET)["sitea"]
    assert result["complete"] is False and len(pagecache.listing("sitea")) == 3


def test_aChildSitemapOnAnotherHostMakesTheListingIncomplete(monkeypatch):
    answers = twoChildWeb()
    firstPassSavesThree(monkeypatch, answers)
    answers[f"https://{A}/sitemap_index.xml"] = sitemapIndex(f"https://{A}/post-sitemap.xml",
                                                             "https://other.example.test/more-sitemap.xml")
    fakeCrawl(monkeypatch, answers)
    failures = []
    sites.sitemapEntries(siteFor(A, "sitea"), robotsFrom(), log=QUIET, failures=failures)
    assert failures
    result = sites.crawl([siteFor(A, "sitea")], pages=0, log=QUIET)["sitea"]
    assert result["complete"] is False and len(pagecache.listing("sitea")) == 3


def test_anIndexCutOffAtMaxSitemapsMakesTheListingIncomplete(monkeypatch):
    answers = twoChildWeb()
    firstPassSavesThree(monkeypatch, answers)
    monkeypatch.setattr(sites, "MAX_SITEMAPS", 2)       # the index and one child: the other child is never read
    fakeCrawl(monkeypatch, answers)
    failures = []
    sites.sitemapEntries(siteFor(A, "sitea"), robotsFrom(), log=QUIET, failures=failures)
    assert failures
    result = sites.crawl([siteFor(A, "sitea")], pages=0, log=QUIET)["sitea"]
    assert result["complete"] is False and len(pagecache.listing("sitea")) == 3


def test_aFailedIndexOnTheFirstEverPassSavesNoListing(monkeypatch):
    answers = twoChildWeb()
    answers[f"https://{A}/sitemap_index.xml"] = net.HttpError("down", status=503)
    fakeCrawl(monkeypatch, answers)
    result = sites.crawl([siteFor(A, "sitea")], pages=0, log=QUIET)["sitea"]
    assert result["complete"] is False and result["ok"] is False
    assert pagecache.listing("sitea") == []


def test_aStoppedSiteIsNotComplete(monkeypatch):
    answers = twoChildWeb()
    answers[f"https://{A}/robots.txt"] = net.HttpError("no", status=403)
    fakeCrawl(monkeypatch, answers)
    result = sites.crawl([siteFor(A, "sitea")], pages=0, log=QUIET)["sitea"]
    assert (result["complete"], result["goneUrls"]) == (False, [])


def test_aPageAnswering404TwoPassesInARowIsInThatPassesGoneUrls(monkeypatch):
    fakeCrawl(monkeypatch, web(A, {"made-up-gone": None, "made-up-stew": recipePage("Made-up Stew")}))
    first = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    second = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert (first["goneUrls"], second["goneUrls"]) == ([], [f"https://{A}/made-up-gone/"])


def test_anOversizedGzipSitemapIsAFailure(monkeypatch):
    monkeypatch.setattr(net, "MAX_SITEMAP_BYTES", 100)
    answers = twoChildWeb()
    answers[f"https://{A}/more-sitemap.xml"] = gzip.compress(
        urlset(*[(f"https://{A}/made-up-salad-{n}/", None) for n in range(20)]).encode("utf-8"))
    fakeCrawl(monkeypatch, answers)
    failures = []
    sites.sitemapEntries(siteFor(A, "sitea"), robotsFrom(), log=QUIET, failures=failures)
    assert any("too large" in reason for reason in failures)


def test_parseSitemapRefusesAGzipPastTheCap(monkeypatch):
    monkeypatch.setattr(net, "MAX_SITEMAP_BYTES", 100)
    with pytest.raises(sites.SitemapTooLarge):
        sites.parseSitemap(gzip.compress(urlset(*[(f"https://{A}/made-up-{n}/", None) for n in range(20)]).encode()))
    assert sites.parseSitemap(gzip.compress(b"<urlset/>")) == ("urlset", [])


def test_aPageRedirectedOffHostIsAnErrorAndNotCached(monkeypatch):
    fakeCrawl(monkeypatch, web(A, {"made-up-moved": Redirect("https://elsewhere.example.test/made-up-moved/"),
                                   "made-up-stew": recipePage("Made-up Stew")}))
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert (result["errors"], result["fetched"]) == (1, 1)
    assert pagecache.meta("sitea", f"https://{A}/made-up-moved/") is None


def test_aPageRedirectedIntoADisallowedPathIsAnErrorAndNotCached(monkeypatch):
    answers = web(A, {"made-up-moved": Redirect(f"https://{A}/private/made-up-moved/"),
                      "made-up-stew": recipePage("Made-up Stew")}, robots="User-agent: *\nDisallow: /private/\n")
    answers[f"https://{A}/private/made-up-moved/"] = recipePage("Made-up Moved")
    fakeCrawl(monkeypatch, answers)
    result = sites.crawl([siteFor(A, "sitea")], pages=None, log=QUIET)["sitea"]
    assert (result["errors"], result["fetched"]) == (1, 1)
    assert pagecache.meta("sitea", f"https://{A}/made-up-moved/") is None


def test_wildcardRobotsRulesKeepPagesOut(monkeypatch):
    answers = web(A, {"made-up-stew": recipePage("Made-up Stew")},
                  robots="User-agent: *\nDisallow: /*?print=\n")
    answers[f"https://{A}/post-sitemap.xml"] = urlset((f"https://{A}/made-up-stew/", None),
                                                      (f"https://{A}/made-up-stew/?print=1", None))
    site = dict(siteFor(A, "sitea"), recipeUrl=rf"^https://{re.escape(A)}/[a-z0-9-]+/(\?print=1)?$")
    asked = fakeCrawl(monkeypatch, answers)
    sites.crawl([site], pages=None, log=QUIET)
    assert f"https://{A}/made-up-stew/?print=1" not in asked
