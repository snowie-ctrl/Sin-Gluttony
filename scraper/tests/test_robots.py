import pytest

import robots

AGENT = "GluttonyPersonalCrawler"
SITE = "https://www.example-recipes.test"


def rules(text):
    return robots.Rules.parse(text)


def allows(text, path, agent=AGENT):
    return rules(text).allows(agent, SITE + path)


def test_ourGroupIsUsedWhenOneNamesUs():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: GluttonyPersonalCrawler\nDisallow: /private/\n"
    assert allows(text, "/made-up-stew/")
    assert not allows(text, "/private/made-up-stew/")


def test_aTokenThatIsAPrefixOfOurNameMatchesCaseIgnored():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: gluttony\nAllow: /\n"
    assert allows(text, "/made-up-stew/")


def test_theMostSpecificTokenPicksTheGroupEvenListedSecond():
    text = ("User-agent: glut\nUser-agent: GluttonyPersonalCrawler\nDisallow: /made-up-a/\n\n"
            "User-agent: gluttonypersonal\nDisallow: /made-up-b/\n")
    assert not allows(text, "/made-up-a/x")
    assert allows(text, "/made-up-b/x")


def test_anotherCrawlersGroupIsNotOurs():
    text = "User-agent: OtherBot\nDisallow: /\n\nUser-agent: *\nDisallow: /private/\n"
    assert allows(text, "/made-up-stew/")
    assert not allows(text, "/private/x")


def test_consecutiveUserAgentLinesShareOneGroup():
    text = "User-agent: OtherBot\nUser-agent: GluttonyPersonalCrawler\nDisallow: /made-up-secret/\n"
    assert not allows(text, "/made-up-secret/a")
    assert allows(text, "/made-up-stew/")


def test_noGroupForUsAllowsEverything():
    assert allows("User-agent: OtherBot\nDisallow: /\n", "/made-up-stew/")
    assert allows("", "/made-up-stew/")


def test_theLongestMatchWins():
    text = "User-agent: *\nAllow: /recipes/\nDisallow: /\n"
    assert allows(text, "/recipes/made-up-stew/")
    assert not allows(text, "/about/")
    text = "User-agent: *\nAllow: /\nDisallow: /recipes/drafts/\n"
    assert not allows(text, "/recipes/drafts/made-up")


def test_allowWinsATie():
    assert allows("User-agent: *\nDisallow: /made-up\nAllow: /made-up\n", "/made-up-stew/")


def test_aStarMatchesAnyRunAndTheQueryIsPartOfThePath():
    text = "User-agent: *\nDisallow: /*?print=\n"
    assert not allows(text, "/soup/?print=1")
    assert allows(text, "/soup/")


def test_aDollarAnchorsTheEnd():
    text = "User-agent: *\nDisallow: /*.pdf$\n"
    assert not allows(text, "/a.pdf")
    assert allows(text, "/a.pdf?x=1")
    assert allows(text, "/a.pdfx")


def test_anEmptyDisallowAllowsAll():
    assert allows("User-agent: *\nDisallow:\n", "/made-up-stew/")


def test_percentEncodingIsComparedAfterUnquotingUnreservedCharacters():
    text = "User-agent: *\nDisallow: /made-up%2Dsecret/\nDisallow: /%7Euser/\n"
    assert not allows(text, "/made-up-secret/a")
    assert not allows(text, "/~user/a")
    assert not allows("User-agent: *\nDisallow: /made-up-secret/\n", "/made%2Dup-secret/a")
    # an escaped reserved character stays escaped: %2F is not a slash
    assert allows("User-agent: *\nDisallow: /a/b\n", "/a%2Fb")


def test_commentsAndUnknownLinesAreIgnored():
    text = "# made-up robots\nUser-agent: * # everyone\nDisallow: /private/ # keep out\nHost: example\n"
    assert not allows(text, "/private/x")
    assert allows(text, "/made-up-stew/")


def test_theRobotsFileItselfIsAlwaysAllowed():
    assert allows("User-agent: *\nDisallow: /\n", "/robots.txt")


def test_crawlDelayComesFromOurGroup():
    assert rules("User-agent: GluttonyPersonalCrawler\nCrawl-delay: 10\n").crawlDelay(AGENT) == 10.0
    assert rules("User-agent: *\nCrawl-delay: 2.5\n").crawlDelay(AGENT) == 2.5
    assert rules("User-agent: OtherBot\nCrawl-delay: 30\n").crawlDelay(AGENT) is None
    assert rules("User-agent: *\nCrawl-delay: soon\n").crawlDelay(AGENT) is None


def test_sitemapLinesAreKeptWhereverTheyStand():
    text = "Sitemap: https://www.example-recipes.test/a.xml\nUser-agent: *\nDisallow:\nSitemap: https://www.example-recipes.test/b.xml\n"
    assert rules(text).sitemaps == ["https://www.example-recipes.test/a.xml", "https://www.example-recipes.test/b.xml"]
