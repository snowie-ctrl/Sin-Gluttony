import gzip
import hashlib

import config
import pagecache

URL = "https://www.example-recipes.test/made-up-stew/"
PAGE = "<html><body>Made-up Stew ½ cup</body></html>"


def test_aPageIsKeptGzippedBesideItsUrlAndLastmod():
    pagecache.save("testsite", URL, PAGE, "2026-11-01T00:00:00+00:00", fetchedAt=1000.0)
    name = hashlib.sha1(URL.encode("utf-8")).hexdigest()
    stored = config.RAW_DIR / "testsite" / f"{name}.html.gz"
    assert gzip.decompress(stored.read_bytes()).decode("utf-8") == PAGE
    assert pagecache.meta("testsite", URL) == {"url": URL, "fetchedAt": 1000.0, "lastmod": "2026-11-01T00:00:00+00:00"}
    assert pagecache.load("testsite", URL) == PAGE
    assert not list((config.RAW_DIR / "testsite").glob("*.tmp"))


def test_anUncachedPageIsNone():
    assert pagecache.meta("testsite", URL) is None
    assert pagecache.load("testsite", URL) is None


def test_pagesListsEveryCachedPageInUrlOrder():
    pagecache.save("testsite", "https://www.example-recipes.test/b/", "<b>", None)
    pagecache.save("testsite", "https://www.example-recipes.test/a/", "<a>", None)
    pagecache.saveListing("testsite", [("https://www.example-recipes.test/a/", None)])
    assert [(meta["url"], html) for meta, html in pagecache.pages("testsite")] == [
        ("https://www.example-recipes.test/a/", "<a>"), ("https://www.example-recipes.test/b/", "<b>")]


def test_aBrokenCachedPageIsSkipped():
    pagecache.save("testsite", URL, PAGE, None)
    name = hashlib.sha1(URL.encode("utf-8")).hexdigest()
    (config.RAW_DIR / "testsite" / f"{name}.html.gz").write_bytes(b"half a page")
    assert pagecache.load("testsite", URL) is None
    assert list(pagecache.pages("testsite")) == []


def test_theListingRoundTrips():
    entries = [("https://www.example-recipes.test/a/", "2026-11-01T00:00:00+00:00"),
               ("https://www.example-recipes.test/b/", None)]
    pagecache.saveListing("testsite", entries)
    assert pagecache.listing("testsite") == entries
    assert pagecache.listing("othersite") == []


def test_dropForgetsThePageAndItsSidecarSoItIsDueAgain():
    other = "https://www.example-recipes.test/made-up-other/"
    pagecache.save("testsite", URL, PAGE, None)
    pagecache.save("testsite", other, "<p>", None)
    assert pagecache.urlsBySourceId("testsite") == {pagecache.sourceIdFor(URL): URL,
                                                    pagecache.sourceIdFor(other): other}
    pagecache.drop("testsite", URL)
    pagecache.drop("testsite", "https://www.example-recipes.test/never-cached/")     # nothing there: no error
    assert pagecache.meta("testsite", URL) is None and pagecache.load("testsite", URL) is None
    assert [meta["url"] for meta, _ in pagecache.pages("testsite")] == [other]
    assert pagecache.urlsBySourceId("testsite") == {pagecache.sourceIdFor(other): other}
