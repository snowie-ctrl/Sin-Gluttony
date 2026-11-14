"""
The PC dry run: crawl the sites in rules/sites.json (the first `pages`
recipe pages of each, the basics first), read every cached page, make the
pictures, tag, estimate nutrition from USDA foods, run the gate, and write
reports/dryrun-<date>/ for the owner, with the FDC mapping queue. Nothing is published: publish.py is never called and plutus is never
asked, whatever PUBLISH says; the ingredient table is the repo's seed.
"""
from datetime import date, datetime, timezone
from itertools import zip_longest

import adaptSites
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
    basicUrls = basics.priorityUrls(rules)
    crawled = sites.crawl(siteList, pages, log=log, priority=basicUrls) if crawl else {}
    recipes, skipped = adaptSites.adaptCached(siteList, rules)
    log(f"read {len(recipes)} recipes; {len(skipped)} cached pages gave none")
    recipes = roundRobin(recipes)
    images.ensureImages(recipes, allowDownload=crawl, log=log)
    table = matching.IngredientTable.fromSeed(rules["ingredients"], set(rules["prepWords"]),
                                              set(rules["modifierWords"]))
    foods = fdc.loadFoods()
    mapping = fdcMatch.mappingFor([row["name"] for row in table.rows.values()], foods, rules, fdcMatch.loadPicks())
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
    today = today or date.today()
    folder = config.REPORT_DIR / f"dryrun-{today.isoformat()}"
    summary = dryrunReport.write(folder, siteList, crawled, recipes, skipped, rules, today,
                                    store.readJson(config.SITE_STATE_FILE, {}),
                                    calibration=nutritionReport.calibrate(recipes), queue=queue["queue"],
                                    unknown=nutritionReport.unknownQueue(recipes))
    store.writeJson(folder / "fdc-queue.json", queue)
    log(f"dry run: {summary['listed']} of {summary['pages']} pages would be listed; report in {folder}")
    return folder
