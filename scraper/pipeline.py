"""
One pass of the scraper over the recipe sites in rules/sites.json: crawl (full
passes only) -> read the cached pages -> pictures -> tag, nutrition, gate,
basics -> site health -> publish with site removals, then the pairings. A re-tag runs everything
after the crawl over the pages already cached on the VM, with no new downloads
and no removals, so a rule change can be applied in minutes. A stop is
honoured between stages, never once publishing has started.

The old catalog (TheMealDB, TheCocktailDB, Wikibooks) was retired at the
catalog switch; main.py refuses CATALOG=old before a pass can start.
"""
import time
import traceback
from datetime import datetime, timezone

import adaptSites
import adminApi
import basics
import config
import dryrun
import fdc
import fdcMatch
import gate
import glossary
import images as images_            # runPass has an `images` switch, so the module needs another name
import linking
import matching
import nutrition
import nutritionReport
import progress
import publish
import report as reports
import rulesData
import siteHealth
import store
import tagging
from sources import sites

FDC_CHUNK = 5000        # FDC mappings sent to plutus per request


class Stopped(Exception):
    pass


def loadTable(rules, log=print):
    """plutus's live table (after loading the seed into it) when publishing; the repo's seed otherwise."""
    prep = set(rules["prepWords"])
    modifiers = set(rules["modifierWords"])
    if config.PUBLISH == "on":
        answer = adminApi.post("/ingredients/seed", {"ingredients": matching.seedPayload(rules["ingredients"], prep)})
        log(f"ingredient seed: {answer.get('added', 0)} added, {answer.get('updated', 0)} updated, "
            f"{answer.get('kept', 0)} kept as the owner's")
        return matching.IngredientTable.fromServer(adminApi.get("/ingredients"), prep, modifiers)
    return matching.IngredientTable.fromSeed(rules["ingredients"], prep, modifiers)


def runSitesPass(mode, log=print, stopRequested=None, images=True, site=None, result=None, stage=None):
    """
    The recipe sites in rules/sites.json. crawl (full passes only; `site` limits it to one site)
    -> read the cached pages -> pictures -> tag, FDC mappings, nutrition, the gate, then the basics -> site
    health -> publish with the site removals. A re-tag crawls nothing, so it removes nothing. Fills and
    returns `result`; raises Stopped when the owner stops the pass before publishing.
    """
    stopRequested = stopRequested or (lambda: False)
    result = {"mode": mode} if result is None else result
    started = result.setdefault("startedAt", time.time())
    stage = stage or (lambda name, detail="": progress.stage(mode, name, detail, started))

    def checkStop():
        if stopRequested():
            raise Stopped()

    rules = rulesData.load()
    siteList = sites.loadSites(rules)
    crawled = {}
    result["sources"] = {}      # a re-tag crawls nothing; report readers still find the key
    if mode == "full":
        stage("crawl", site or "")
        # the crawl looks for the stop before every request and saves the site state however it ends
        crawled = sites.crawl(siteList, None, log, priority=basics.priorityUrls(rules), only=site,
                              stopRequested=stopRequested)
        result["sources"] = {name: {"ok": r.get("ok", False), "records": r.get("listed", 0),
                                    "error": r.get("stopReason")} for name, r in crawled.items()}
        result["crawl"] = {name: {k: v for k, v in r.items() if k != "goneUrls"} for name, r in crawled.items()}
    checkStop()

    stage("read")
    recipes, skipped = adaptSites.adaptCached(siteList, rules)
    recipes = dryrun.roundRobin(recipes)
    result["recipes"] = len(recipes)
    result.update(reports.summariseSkipped(skipped))
    checkStop()

    pictureStops = {}
    if images:
        stage("images")
        pictures = images_.ensureImages(recipes, allowDownload=(mode == "full"), log=log,
                                        onProgress=lambda done: stage("images", f"{done} of {len(recipes)}")) or {}
        result["images"] = pictures
        pictureStops = pictures.get("pictureStops", {})
    checkStop()

    stage("tag")
    table = loadTable(rules, log)
    foods = fdc.loadFoods()
    resolved = fdcMatch.resolveTable(table, foods, rules, fdcMatch.loadPicks())
    mapping = {table.rows[i]["name"]: fdcId for i, (fdcId, _) in resolved.items() if fdcId is not None}
    log(f"FDC: {len(foods)} foods, {len(mapping)} ingredients mapped")
    if not foods:
        log("warning: no FDC foods found, so no recipe gets an estimate; import the USDA files first")
    if config.PUBLISH == "on":
        sync = fdcMatch.syncList(table, resolved, foods)       # [] with no foods: nothing is cleared on plutus
        for start in range(0, len(sync), FDC_CHUNK):
            adminApi.post("/ingredients/fdc", {"mappings": sync[start:start + FDC_CHUNK]})
        result["fdcSynced"] = len(sync)
    measures = {entry["site"]: entry.get("measures") for entry in siteList}
    fillers = set(rules["fillerWords"])
    for recipe in recipes:
        tagging.tagRecipe(recipe, table, rules)
        recipe.dishKey = linking.dishKey(recipe.title, fillers)
        nutrition.choose(recipe, table, mapping, foods, rules, measures.get(recipe.source))   # before the gate
        gate.apply(recipe, rules["unitMap"])
    basics.applyTags(recipes, rules)                                                          # after the gate
    store.writeLines(config.NORMALISED_FILE, (r.toDict() for r in recipes))
    result["unknownIngredients"] = reports.unknownIngredients(recipes)
    # The seed words the shown recipes use that the app's glossary has no entry for yet (spec 2026-11-19 part 3,
    # 3.1 upkeep). Secondary, like the pairings: a failure is reported and never fails the pass.
    try:
        result["glossaryGaps"] = glossary.reportGaps(recipes, rules)
    except Exception as e:
        result["glossaryGaps"] = {"error": f"{type(e).__name__}: {e}"}
    result["calibration"] = nutritionReport.calibrate(recipes)
    store.writeJson(config.FDC_QUEUE_FILE, {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                            "queue": nutritionReport.fdcQueue(recipes, foods)})

    siteState = store.readJson(config.SITE_STATE_FILE, {}) or {}
    rows = siteHealth.summarise(siteList, crawled, recipes, skipped, siteState, started, pictureStops,
                                result["calibration"], previous=siteHealth.previousRows())
    store.writeJson(config.SITE_STATE_FILE, siteState)
    siteHealth.write(rows, "pass")
    result["sites"] = rows
    checkStop()

    stage("publish")
    state = store.readJson(config.STATE_FILE, {}) or {}
    siteCounts = state.get("siteCounts", {})
    publishedKeys = list(publish.publishedState(config.PUBLISH != "on"))
    removals = publish.siteRemovals(publishedKeys, crawled, siteCounts, config.REMOVAL_GUARD)
    summary = result["publish"] = publish.publish(recipes, log, removals=removals)
    # After the recipes, so every key a set names is one plutus holds; the report gives pairings per slot and how
    # many recipes found none. Pairings are secondary: a failure here is reported, never the pass's failure, since
    # the recipes and removals are already sent (and the removal guard's baseline below must still move on).
    try:
        result["pairings"] = publish.publishPairings(recipes, rules, log, removing=removals[0])
    except Exception as e:
        result["pairings"] = {"error": f"{type(e).__name__}: {e}"}
        log(f"pairings failed, recipes kept: {result['pairings']['error']}")
    if mode == "full":
        # The baseline the next pass's guard compares against: a complete, non-empty listing the guard let through.
        # A guarded or empty listing never becomes it, so a shrink stays held back pass after pass.
        guarded = set(summary.get("guarded", []))
        for name, crawlResult in crawled.items():
            if crawlResult.get("complete") and crawlResult.get("listed", 0) > 0 and name not in guarded:
                siteCounts[name] = crawlResult["listed"]
        state["siteCounts"] = siteCounts
        store.writeJson(config.STATE_FILE, state)
    return result


def runPass(mode, log=print, stopRequested=None, images=True, site=None):
    """One pass over the recipe sites; site limits a full pass to that one recipe site."""
    started = time.time()
    result = {"mode": mode, "startedAt": started, "outcome": "ok", "error": None, "catalog": "new"}
    if site:
        result["site"] = site

    def stage(name, detail=""):
        progress.stage(mode, name, detail, started)

    try:
        runSitesPass(mode, log, stopRequested, images, site, result=result, stage=stage)
    except Stopped:
        result["outcome"] = "stopped"
    except Exception as e:
        result["outcome"] = "failed"
        result["error"] = f"{type(e).__name__}: {e}"
        log(traceback.format_exc())
    result["endedAt"] = time.time()
    reports.write(result)
    progress.idle()
    log(f"pass {mode}: {result['outcome']}" + (f" ({result['error']})" if result["error"] else ""))
    return result
