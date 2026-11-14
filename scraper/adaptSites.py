"""
A cached recipe-site page into Gluttony's recipe shape, by the parser its
entry in rules/sites.json names: "schema" (recipe-scrapers) or "difford".
Like pipeline.normaliseAll for the part 1 sources: one bad page never stops
the rest, and every page that gives no recipe is recorded with its reason.
"""
import pagecache
from models import Skipped
from sources import difford, schemaSite


def adaptPage(site, url, html, rules):
    if site["parser"] == "difford":
        return difford.extractDifford(html, url, site, rules["unitMap"], rules)
    return schemaSite.extractSchema(html, url, site, rules["unitMap"])


def adaptCached(siteList, rules):
    """(recipes, skipped) from every cached page of the given sites."""
    recipes, skipped = [], []
    for site in siteList:
        for meta, html in pagecache.pages(site["site"]):
            url = meta["url"]
            try:
                recipes.append(adaptPage(site, url, html, rules))
            except Skipped as s:
                skipped.append({"site": site["site"], "url": url, "reason": s.reason, "detail": None})
            except Exception as e:      # one bad page never stops the pass
                skipped.append({"site": site["site"], "url": url, "reason": "could not be read",
                                "detail": f"{type(e).__name__}: {e}"[:200]})
    return recipes, skipped
