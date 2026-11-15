import pytest

import net


def test_testsCannotReachTheNetwork():
    with pytest.raises(RuntimeError, match="must not touch the network"):
        net.getJson("https://api.example.test/made-up/search", params={"f": "a"})


from datetime import datetime, timezone


class FakeResponse:
    def __init__(self, status, body=b"", headers=None):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else body.encode("utf-8")
        self.headers = {"Content-Type": "text/html; charset=utf-8"} if headers is None else headers
        contentType = self.headers.get("Content-Type", "")
        self.encoding = contentType.split("charset=", 1)[1] if "charset=" in contentType else None

    @property
    def text(self):
        # requests decodes a text/* body without a charset as ISO-8859-1; so does this fake.
        return self.content.decode(self.encoding or "ISO-8859-1", errors="replace")


def fakeSession(monkeypatch, answers):
    calls = []
    def request(method, url, **kwargs):
        calls.append({"method": method, "url": url, "headers": kwargs.get("headers"),
                      "allowRedirects": kwargs.get("allow_redirects", True)})
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(net._session, "request", request)
    return calls


@pytest.fixture(autouse=True)
def freshHosts(monkeypatch):
    monkeypatch.setattr(net, "_crawlHosts", set())
    monkeypatch.setattr(net, "_lastCall", {})
    monkeypatch.setattr(net, "MIN_INTERVAL", dict(net.MIN_INTERVAL))


def test_crawlNamesTheCrawlerAndReturnsThePage(monkeypatch):
    calls = fakeSession(monkeypatch, [FakeResponse(200, "<html>Made-up page</html>")])
    assert net.crawl("https://www.example-recipes.test/made-up-stew/") == "<html>Made-up page</html>"
    assert calls[0]["headers"] == {"User-Agent": net.CRAWLER_AGENT}
    assert net.CRAWLER_AGENT == "GluttonyPersonalCrawler/1.0 (+https://github.com/snowie-ctrl/Sin-Gluttony)"


def test_crawlCanReturnBytes(monkeypatch):
    fakeSession(monkeypatch, [FakeResponse(200, b"\x1f\x8bgzipped")])
    assert net.crawl("https://www.example-recipes.test/sitemap.xml.gz", binary=True) == b"\x1f\x8bgzipped"


def test_aPageWithoutACharsetIsReadAsUtf8(monkeypatch):
    fakeSession(monkeypatch, [FakeResponse(200, "½ cup made-up flour".encode("utf-8"), {"Content-Type": "text/html"})])
    assert net.crawl("https://www.example-recipes.test/made-up-cake/") == "½ cup made-up flour"


@pytest.mark.parametrize("status", [403, 404, 410])
def test_aClientErrorRaisesAtOnceWithItsStatus(monkeypatch, status):
    calls = fakeSession(monkeypatch, [FakeResponse(status)])
    with pytest.raises(net.HttpError) as error:
        net.crawl("https://www.example-recipes.test/made-up-stew/")
    assert error.value.status == status and len(calls) == 1


def test_a429IsHandedBackNotSleptOn(monkeypatch):
    sleeps = []
    monkeypatch.setattr(net.time, "sleep", sleeps.append)
    calls = fakeSession(monkeypatch, [FakeResponse(429, headers={"Retry-After": "120"})])
    with pytest.raises(net.HttpError) as error:
        net.crawl("https://www.example-recipes.test/made-up-stew/")
    assert (error.value.status, error.value.retryAfter) == (429, 120.0)
    assert len(calls) == 1 and sleeps == []


def test_aServerErrorIsTriedAgainThenReported(monkeypatch):
    calls = fakeSession(monkeypatch, [FakeResponse(503), FakeResponse(503)])
    with pytest.raises(net.HttpError) as error:
        net.crawl("https://www.example-recipes.test/made-up-stew/")
    assert error.value.status == 503 and len(calls) == 2


def test_aSiteHostIsAskedAtMostOnceEveryFiveSeconds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(net.time, "sleep", sleeps.append)
    fakeSession(monkeypatch, [FakeResponse(200, "a"), FakeResponse(200, "b")])
    net.crawl("https://www.example-recipes.test/one/")
    net.crawl("https://www.example-recipes.test/two/")
    assert len(sleeps) == 1 and 4.5 <= sleeps[0] <= 5.3


def test_retryAfterReadsSecondsAndDates():
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    assert net.retryAfterSeconds("30") == 30.0
    assert net.retryAfterSeconds("Sat, 14 Nov 2026 12:02:00 GMT", now) == 120.0
    assert net.retryAfterSeconds("Sat, 14 Nov 2026 11:00:00 GMT", now) == 0.0
    assert net.retryAfterSeconds(None) is None
    assert net.retryAfterSeconds("soon") is None


def test_requestErrorsCarryTheStatus(monkeypatch):
    fakeSession(monkeypatch, [FakeResponse(404)])
    with pytest.raises(net.HttpError) as error:
        net.getText("https://api.example.test/made-up/lookup")
    assert error.value.status == 404


def test_picturesFromACrawledHostGetTheCrawlersNameAndPace(monkeypatch, tmp_path):
    fakeSession(monkeypatch, [FakeResponse(200, "page")])
    seen = []
    def get(url, **kwargs):
        seen.append((url, kwargs.get("headers")))
        return FakeResponse(200, b"picture")
    monkeypatch.setattr(net._session, "get", get)
    net.crawl("https://www.example-recipes.test/made-up-stew/")
    assert net.download("https://www.example-recipes.test/made-up.jpg", tmp_path / "a")
    assert net.download("https://images.example-cdn.test/made-up.jpg", tmp_path / "b")
    assert seen[0][1] == {"User-Agent": net.CRAWLER_AGENT}
    assert seen[1][1] is None
    assert net._interval("www.example-recipes.test") == 5.0
    assert net._interval("images.example-cdn.test") == net.DEFAULT_INTERVAL


STEW = "https://www.example-recipes.test/made-up-stew/"


def moved(location, status=301):
    return FakeResponse(status, headers={"Location": location})


def throttled(monkeypatch):
    hosts = []
    monkeypatch.setattr(net, "_throttle", hosts.append)
    return hosts


def test_aRedirectOffHostIsRefusedWithoutAskingTheOtherHost(monkeypatch):
    throttled(monkeypatch)
    calls = fakeSession(monkeypatch, [moved("https://elsewhere.example.test/made-up/"), FakeResponse(200, "other")])
    with pytest.raises(net.HttpError, match="redirected off host") as error:
        net.crawl(STEW)
    assert error.value.status is None
    assert [c["url"] for c in calls] == [STEW] and calls[0]["allowRedirects"] is False


def test_aRelativeRedirectOnTheSameHostIsFollowedEachHopThrottledAndItsUrlHandedBack(monkeypatch):
    hosts = throttled(monkeypatch)
    calls = fakeSession(monkeypatch, [moved("/made-up-new/", 308),
                                      moved("https://WWW.Example-Recipes.test/made-up-newer/", 302),
                                      FakeResponse(200, "<html>Made-up</html>")])
    final = []
    assert net.crawl(STEW, finalUrl=final) == "<html>Made-up</html>"
    assert [c["url"] for c in calls] == [STEW, "https://www.example-recipes.test/made-up-new/",
                                         "https://WWW.Example-Recipes.test/made-up-newer/"]
    assert all(c["allowRedirects"] is False for c in calls)
    assert len(hosts) == 3
    assert final == ["https://WWW.Example-Recipes.test/made-up-newer/"]


def test_aRedirectIntoADisallowedPathIsNeverRequested(monkeypatch):
    throttled(monkeypatch)
    calls = fakeSession(monkeypatch, [moved("/private/made-up-stew/"), FakeResponse(200, "secret")])
    with pytest.raises(net.HttpError, match="robots.txt disallows the redirect target") as error:
        net.crawl(STEW, mayFetch=lambda url: "/private/" not in url)
    assert error.value.status is None and len(calls) == 1


def test_moreThanFiveRedirectsAreRefused(monkeypatch):
    throttled(monkeypatch)
    calls = fakeSession(monkeypatch, [moved(f"/made-up-{n}/") for n in range(7)])
    with pytest.raises(net.HttpError, match="too many redirects"):
        net.crawl(STEW)
    assert len(calls) == 6         # the page and five hops; the sixth redirect is not followed


def test_downloadReportsARefusalOnlyWhenAsked(monkeypatch, tmp_path):
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    answers = [FakeResponse(403), FakeResponse(403), FakeResponse(429, headers={"Retry-After": "60"}),
               FakeResponse(404)]
    monkeypatch.setattr(net._session, "get", lambda url, **kw: answers.pop(0))
    url = "https://images.example-cdn.test/made-up.jpg"
    assert net.download(url, tmp_path / "a") is False
    with pytest.raises(net.HttpError) as error:
        net.download(url, tmp_path / "b", refusals=True)
    assert error.value.status == 403
    with pytest.raises(net.HttpError) as error:
        net.download(url, tmp_path / "c", refusals=True)
    assert (error.value.status, error.value.retryAfter) == (429, 60.0)
    assert net.download(url, tmp_path / "d", refusals=True) is False


def test_theSitemapCapIsFiftyMegabytes():
    assert net.MAX_SITEMAP_BYTES == 50 * 1024 * 1024
