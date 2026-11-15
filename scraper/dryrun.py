"""
The PC dry run: crawl the sites in rules/sites.json (the first `pages`
recipe pages of each, the basics first), read every cached page, make the
pictures, tag, estimate nutrition from USDA foods, run the gate, and write
reports/dryrun-<date>/ for the owner, with the FDC mapping queue. Nothing is
published: publish.py is never called and nothing is sent to plutus, whatever
PUBLISH says. The ingredient table is the repo's seed, or with serverTable
plutus's own table, read with one GET and no seed load (M4's full trial:
`--pages 0 --server-table`). pages=None means every listed page.
"""
import time
from datetime import date, datetime, timezone
from itertools import zip_longest

import adaptSites
import adminApi
import basics
import config
import dryrunReport
import fdc
import fdcMatch
import gate
import images
import linking
import matching
import nutrition
import nutritionReport
import rulesData
import siteHealth
import store
import tagging
from sources import sites


def roundRobin(recipes):
    """One recipe per site in turn, so picture downloads from different hosts overlap their waits."""
    bySite = {}
    for recipe in recipes:
        bySite.setdefault(recipe.source, []).append(recipe)
    return [r for row in zip_longest(*bySite.values()) for r in row if r is not None]


def run(pages=200, log=print, today=None, crawl=True, serverTable=False):
    startedAt = time.time()
    rules = rulesData.load()
    siteList = sites.loadSites(rules)
    basicUrls = basics.priorityUrls(rules)
    crawled = sites.crawl(siteList, pages, log=log, priority=basicUrls) if crawl else {}
    recipes, skipped = adaptSites.adaptCached(siteList, rules)
    log(f"read {len(recipes)} recipes; {len(skipped)} cached pages gave none")
    recipes = roundRobin(recipes)
    pictures = images.ensureImages(recipes, allowDownload=crawl, log=log) or {}
    prep, modifiers = set(rules["prepWords"]), set(rules["modifierWords"])
    if serverTable:
        table = matching.IngredientTable.fromServer(adminApi.get("/ingredients"), prep, modifiers)
        log(f"ingredient table: plutus's, {len(table.rows)} rows (read only)")
    else:
        table = matching.IngredientTable.fromSeed(rules["ingredients"], prep, modifiers)
    foods = fdc.loadFoods()
    mapping = fdcMatch.mappingForTable(table, foods, rules, fdcMatch.loadPicks())
    log(f"FDC: {len(foods)} foods, {len(mapping)} ingredients mapped")
    if not foods:
        log("warning: no FDC foods found, so no recipe gets an estimate; import the USDA files first")
    measures = {site["site"]: site.get("measures") for site in siteList}
    for recipe in recipes:
        tagging.tagRecipe(recipe, table, rules)
        recipe.dishKey = linking.dishKey(recipe.title, set(rules["fillerWords"]))
        nutrition.choose(recipe, table, mapping, foods, rules, measures.get(recipe.source))
        gate.apply(recipe, rules["unitMap"])
    basics.applyTags(recipes, rules)
    queue = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "queue": nutritionReport.fdcQueue(recipes, foods)}
    store.writeJson(config.FDC_QUEUE_FILE, queue)
    calibration = nutritionReport.calibrate(recipes)
    siteState = store.readJson(config.SITE_STATE_FILE, {}) or {}
    health = siteHealth.summarise(siteList, crawled, recipes, skipped, siteState, startedAt,
                                  pictures.get("pictureStops", {}), calibration, previous=siteHealth.previousRows())
    store.writeJson(config.SITE_STATE_FILE, siteState)
    siteHealth.write(health, "dryrun")
    today = today or date.today()
    folder = config.REPORT_DIR / f"dryrun-{today.isoformat()}"
    summary = dryrunReport.write(folder, siteList, crawled, recipes, skipped, rules, today, siteState,
                                    calibration=calibration, queue=queue["queue"],
                                    unknown=nutritionReport.unknownQueue(recipes))
    store.writeJson(folder / "fdc-queue.json", queue)
    log(f"dry run: {summary['listed']} of {summary['pages']} pages would be listed; report in {folder}")
    return folder
