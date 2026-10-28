import bz2

import config
import net
import store
from sources import wikibooks

XML = """<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <page><title>Cookbook:Grilled Cheese</title><ns>102</ns><id>1</id>
    <revision><id>111</id><timestamp>2026-09-01T00:00:00Z</timestamp>
      <text>{{recipe summary|Difficulty=1}}
== Ingredients ==
* 2 slices bread</text></revision></page>
  <page><title>Cookbook:Toastie</title><ns>102</ns><id>2</id><redirect title="Cookbook:Grilled Cheese" />
    <revision><id>222</id><timestamp>2026-09-01T00:00:00Z</timestamp><text>#REDIRECT [[Cookbook:Grilled Cheese]]</text></revision></page>
  <page><title>Cookbook:Cheese</title><ns>102</ns><id>3</id>
    <revision><id>333</id><timestamp>2026-09-01T00:00:00Z</timestamp><text>{{cookdp}} Cheese is made from milk.</text></revision></page>
  <page><title>Physics Study Guide</title><ns>0</ns><id>4</id>
    <revision><id>444</id><timestamp>2026-09-01T00:00:00Z</timestamp><text>[[Category:Recipes]] not really</text></revision></page>
</mediawiki>"""


NO_RECIPES = """<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <page><title>Physics Study Guide</title><ns>0</ns><id>4</id>
    <revision><id>444</id><timestamp>2026-09-01T00:00:00Z</timestamp><text>[[Category:Recipes]] not really</text></revision></page>
  <page><title>Cookbook:Cheese</title><ns>102</ns><id>3</id>
    <revision><id>333</id><timestamp>2026-09-01T00:00:00Z</timestamp><text>{{cookdp}} Cheese is made from milk.</text></revision></page>
</mediawiki>"""


def writeDump(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bz2.compress(XML.encode("utf-8")))


def test_extractPagesKeepsOnlyCookbookRecipePages(tmp_path):
    dump = tmp_path / "dump.xml.bz2"
    writeDump(dump)
    pages = list(wikibooks.extractPages(dump))
    assert [(t, r) for t, r, _, _ in pages] == [("Cookbook:Grilled Cheese", "111")]
    assert "2 slices bread" in pages[0][3]


def test_aNewDumpIsDownloadedReadAndDeleted(monkeypatch):
    monkeypatch.setattr(net, "getText", lambda url, **kw: "<link>http://dumps.wikimedia.org/enwikibooks/20261001</link>")
    monkeypatch.setattr(net, "downloadLarge", lambda url, dest, **kw: writeDump(dest))
    result = wikibooks.fetch({"dumpDate": "20260920", "ids": ["Cookbook:Old"]}, log=lambda *a: None)
    assert result == {"source": "wikibooks", "ok": True, "ids": ["Cookbook:Grilled Cheese"], "error": None,
                      "dumpDate": "20261001"}
    assert store.readJson(store.rawPath("wikibooks", "Cookbook:Grilled Cheese"))["revision"] == "111"
    assert not (config.DATA_DIR / "wikibooks-dump.xml.bz2").exists()


def test_theSameDumpIsNotDownloadedAgain(monkeypatch):
    monkeypatch.setattr(net, "getText", lambda url, **kw: "/enwikibooks/20261001/")
    def refuse(*a, **kw):
        raise AssertionError("downloaded an unchanged dump")
    monkeypatch.setattr(net, "downloadLarge", refuse)
    previous = {"source": "wikibooks", "ok": True, "ids": ["Cookbook:A"], "error": None, "dumpDate": "20261001"}
    assert wikibooks.fetch(previous, log=lambda *a: None) == previous


def test_anUnreachableFeedKeepsLastPassIdsAndIsNotOk(monkeypatch):
    def fail(url, **kw):
        raise net.HttpError("GET feed failed")
    monkeypatch.setattr(net, "getText", fail)
    result = wikibooks.fetch({"dumpDate": "20260920", "ids": ["Cookbook:A"]}, log=lambda *a: None)
    assert result["ok"] is False and result["ids"] == ["Cookbook:A"] and result["dumpDate"] == "20260920"


def test_aBrokenDumpIsNotOkAndRemovesNothing(monkeypatch):
    monkeypatch.setattr(net, "getText", lambda url, **kw: "/enwikibooks/20261001/")
    def brokenDownload(url, dest, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"not bz2")
    monkeypatch.setattr(net, "downloadLarge", brokenDownload)
    result = wikibooks.fetch({"dumpDate": "20260920", "ids": ["Cookbook:A"]}, log=lambda *a: None)
    assert result["ok"] is False and result["ids"] == ["Cookbook:A"]
    assert result["error"].startswith("OSError")
    assert not (config.DATA_DIR / "wikibooks-dump.xml.bz2").exists()


def test_aDumpWithNoRecipePagesIsNotOk(monkeypatch):
    monkeypatch.setattr(net, "getText", lambda url, **kw: "/enwikibooks/20261001/")
    def noRecipesDownload(url, dest, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bz2.compress(NO_RECIPES.encode("utf-8")))
    monkeypatch.setattr(net, "downloadLarge", noRecipesDownload)
    result = wikibooks.fetch({"dumpDate": "20260920", "ids": ["Cookbook:A"]}, log=lambda *a: None)
    assert result["ok"] is False and result["ids"] == ["Cookbook:A"] and result["dumpDate"] == "20260920"
    assert result["error"] == "the dump held no recipe pages"
    assert not (config.DATA_DIR / "wikibooks-dump.xml.bz2").exists()
