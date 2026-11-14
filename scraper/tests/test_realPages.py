"""
Regression over the real pages a dry run cached in data/raw/. That folder is
git-ignored, so these tests are skipped on a fresh checkout. They only read:
the pages stay on this machine and nothing from them is written anywhere.
"""
from pathlib import Path

import pytest

import adaptSites
import config
import gate
import pagecache
import rulesData
from models import Skipped
from sources import sites

REAL_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
RULES = rulesData.load()
SITES = sites.loadSites(RULES)
MIN_PAGES = 10
_READ = {}      # each site's cached pages are parsed once for all the tests below


def readAll(site, monkeypatch):
    if site["site"] not in _READ:
        monkeypatch.setattr(config, "RAW_DIR", REAL_RAW)
        _READ[site["site"]] = readSite(site)
    pages, read, failures, recipes = _READ[site["site"]]
    if pages < MIN_PAGES:
        pytest.skip(f"fewer than {MIN_PAGES} cached pages of {site['site']} (data/raw is local only)")
    return pages, read, failures, recipes


def readSite(site):
    pages = read = 0
    failures, recipes = [], []
    for meta, html in pagecache.pages(site["site"]):
        pages += 1
        try:
            recipes.append(adaptSites.adaptPage(site, meta["url"], html, RULES))
            read += 1
        except Skipped:
            pass
        except Exception as e:
            failures.append(f"{meta['url']}: {type(e).__name__}: {e}")
    return pages, read, failures, recipes


@pytest.mark.parametrize("site", SITES, ids=lambda s: s["site"])
def test_cachedPagesStillBecomeRecipes(site, monkeypatch):
    pages, read, failures, _ = readAll(site, monkeypatch)
    assert not failures
    assert read / pages >= 0.9


@pytest.mark.parametrize("site", SITES, ids=lambda s: s["site"])
def test_almostEveryIngredientLineParses(site, monkeypatch):
    _, _, _, recipes = readAll(site, monkeypatch)
    lines = [line for recipe in recipes for line in recipe.ingredients]
    parsed = sum(1 for line in lines if gate.lineParsed(line, RULES["unitMap"]))
    assert lines and parsed / len(lines) >= 0.95


def test_diffordsDrinksHaveTheirGlass(monkeypatch):
    site = next((s for s in SITES if s["parser"] == "difford"), None)
    if site is None:
        pytest.skip("Difford's is not enabled")
    _, _, _, recipes = readAll(site, monkeypatch)
    assert recipes and sum(1 for r in recipes if r.glass) / len(recipes) >= 0.8
