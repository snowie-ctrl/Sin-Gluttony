"""
Milestone 1's PC dry run: crawl the sites in rules/sites.json (the first
`pages` recipe pages of each, the basics first), read every cached page, make
the pictures, tag, run the gate, and write reports/dryrun-<date>/ for the
owner. Nothing is published: publish.py is never called and plutus is never
asked, whatever PUBLISH says; the ingredient table is the repo's seed.
"""
from datetime import date
from itertools import zip_longest

import adaptSites
import config
import dryrunReport
import gate
import images
import linking
import matching
import rulesData
import store
import tagging
from sources import sites


def roundRobin(recipes):
    """One recipe per site in turn, so picture downloads from different hosts overlap their waits."""
    bySite = {}
    for recipe in recipes:
        bySite.setdefault(recipe.source, []).append(recipe)
    return [r for row in zip_longest(*bySite.values()) for r in row if r is not None]


def run(pages=200, log=print, today=None, crawl=True):
    rules = rulesData.load()
    siteList = sites.loadSites(rules)
    basicUrls = frozenset(b["url"] for b in rules.get("basics", []) if b.get("url"))
    crawled = sites.crawl(siteList, pages, log=log, priority=basicUrls) if crawl else {}
    recipes, skipped = adaptSites.adaptCached(siteList, rules)
    log(f"read {len(recipes)} recipes; {len(skipped)} cached pages gave none")
    recipes = roundRobin(recipes)
    images.ensureImages(recipes, allowDownload=crawl, log=log)
    table = matching.IngredientTable.fromSeed(rules["ingredients"], set(rules["prepWords"]),
                                              set(rules["modifierWords"]))
    for recipe in recipes:
        tagging.tagRecipe(recipe, table, rules)
        recipe.dishKey = linking.dishKey(recipe.title, set(rules["fillerWords"]))
        gate.apply(recipe, rules["unitMap"])
    today = today or date.today()
    folder = config.REPORT_DIR / f"dryrun-{today.isoformat()}"
    summary = dryrunReport.write(folder, siteList, crawled, recipes, skipped, rules, today,
                                    store.readJson(config.SITE_STATE_FILE, {}))
    log(f"dry run: {summary['listed']} of {summary['pages']} pages would be listed; report in {folder}")
    return folder
