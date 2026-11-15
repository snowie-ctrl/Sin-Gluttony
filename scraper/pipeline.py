"""
One pass of the scraper: fetch (full passes only) -> normalise -> pictures ->
tag -> link -> publish. A re-tag runs everything after fetch over the raw
copies already on the VM, with no new downloads and no removals, so a rule
change can be applied in minutes. A stop is honoured between stages, never
once publishing has started.

CATALOG picks the body: "old" is the pass above over TheMealDB, TheCocktailDB
and Wikibooks; "new" is runSitesPass over the recipe sites (crawl -> read ->
pictures -> tag, nutrition, gate, basics -> site health -> publish with site
removals). The recipe-site modules that need recipe-scrapers are imported
only inside runSitesPass, so an old-catalog VM never needs it.
"""
import time
import traceback
from datetime import datetime, timezone

import adaptTheDb
import adaptWikibooks
import adminApi
import basics
import calibration
import config
import fdc
import fdcMatch
import gate
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
from models import Skipped
from sources import sites, thedb, wikibooks

FDC_CHUNK = 5000        # FDC mappings sent to plutus per request
ADAPTERS = {"mealdb": adaptTheDb.adaptMeal, "cocktaildb": adaptTheDb.adaptDrink, "wikibooks": adaptWikibooks.adaptPage}


class Stopped(Exception):
    pass


def normaliseAll(fetchResults, units):
    recipes, skipped = [], []
    for source, result in sorted(fetchResults.items()):
        adapt = ADAPTERS[source]
        for sourceId in result.get("ids", []):
            key = f"{source}:{sourceId}"
            raw = store.readJson(store.rawPath(source, sourceId))
            if raw is None:
                skipped.append({"key": key, "title": sourceId, "reason": "raw record missing", "detail": None})
                continue
            try:
                recipes.append(adapt(raw, units))
            except Skipped as s:
                skipped.append({"key": key, "title": sourceId, "reason": s.reason, "detail": None})
            except Exception as e:      # one bad record never stops the pass
                skipped.append({"key": key, "title": sourceId, "reason": "could not be read",
                                "detail": f"{type(e).__name__}: {e}"[:200]})
    return recipes, skipped


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


def _fetch(previous, log, stage):
    results = {}
    for db, label in ((thedb.MEALDB, "TheMealDB"), (thedb.COCKTAILDB, "TheCocktailDB")):
        stage("fetch", label)
        results[db.source] = thedb.fetchSource(db, previous.get(db.source), log)
    stage("fetch", "Wikibooks")
    results["wikibooks"] = wikibooks.fetch(previous.get("wikibooks"), log)
    store.writeJson(config.FETCH_FILE, results)
    return results




def _runOldPass(mode, log, stage, checkStop, images, result):
    """CATALOG=old: TheMealDB, TheCocktailDB and Wikibooks, as before the recipe sites."""
    rules = rulesData.load()
    previous = store.readJson(config.FETCH_FILE, {}) or {}
    fetched = _fetch(previous, log, stage) if mode == "full" else previous
    result["sources"] = {s: {"ok": r.get("ok", False), "records": len(r.get("ids", [])), "error": r.get("error")}
                         for s, r in fetched.items()}
    checkStop()

    stage("normalise")
    recipes, skipped = normaliseAll(fetched, rules["unitMap"])
    result["recipes"] = len(recipes)
    result.update(reports.summariseSkipped(skipped))
    checkStop()

    if images:
        stage("images")
        result["images"] = images_.ensureImages(recipes, allowDownload=(mode == "full"), log=log,
                                                onProgress=lambda done: stage("images", f"{done} of {len(recipes)}"))
    checkStop()

    stage("tag")
    table = loadTable(rules, log)
    for recipe in recipes:
        tagging.tagRecipe(recipe, table, rules)
        recipe.dishKey = linking.dishKey(recipe.title, set(rules["fillerWords"]))
    store.writeLines(config.NORMALISED_FILE, (r.toDict() for r in recipes))
    result["unknownIngredients"] = reports.unknownIngredients(recipes)
    result["calibration"] = calibration.calibrate(recipes, rules)
    checkStop()

    stage("publish")
    state = store.readJson(config.STATE_FILE, {}) or {}
    summary = publish.publish(recipes, fetched if mode == "full" else {}, state.get("counts", {}), log)
    result["publish"] = summary
    if mode == "full":
        counts = state.get("counts", {})
        for source, fetchedSource in fetched.items():
            if fetchedSource.get("ok") and source not in summary["guarded"]:
                counts[source] = len(fetchedSource.get("ids", []))
        state["counts"] = counts
        store.writeJson(config.STATE_FILE, state)


def runSitesPass(mode, log=print, stopRequested=None, images=True, site=None, result=None, stage=None):
    """
    CATALOG=new: the recipe sites in rules/sites.json. crawl (full passes only; `site` limits it to one site)
    -> read the cached pages -> pictures -> tag, FDC mappings, nutrition, the gate, then the basics -> site
    health -> publish with the site removals. A re-tag crawls nothing, so it removes nothing. Fills and
    returns `result`; raises Stopped when the owner stops the pass before publishing.
    """
    import adaptSites   # here, not at the top: only the recipe sites need recipe-scrapers (CATALOG=old never does)
    import dryrun

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
    summary = result["publish"] = publish.publish(recipes, {}, {}, log, removals=removals)
    if mode == "full":
        # The baseline the next pass's guard compares against: a complete, non-empty listing the guard let through.
        # A guarded or empty listing never becomes it, so a shrink stays held back pass after pass (as the old pass).
        guarded = set(summary.get("guarded", []))
        for name, crawlResult in crawled.items():
            if crawlResult.get("complete") and crawlResult.get("listed", 0) > 0 and name not in guarded:
                siteCounts[name] = crawlResult["listed"]
        state["siteCounts"] = siteCounts
        store.writeJson(config.STATE_FILE, state)
    return result


def runPass(mode, log=print, stopRequested=None, images=True, site=None):
    """One pass: the old catalog or the recipe sites, by config.CATALOG. site (one recipe site) is for CATALOG=new."""
    stopRequested = stopRequested or (lambda: False)
    started = time.time()
    result = {"mode": mode, "startedAt": started, "outcome": "ok", "error": None}
    if config.CATALOG == "new":
        result["catalog"] = "new"
        if site:
            result["site"] = site

    def stage(name, detail=""):
        progress.stage(mode, name, detail, started)

    def checkStop():
        if stopRequested():
            raise Stopped()

    try:
        if config.CATALOG == "new":
            runSitesPass(mode, log, stopRequested, images, site, result=result, stage=stage)
        else:
            _runOldPass(mode, log, stage, checkStop, images, result)
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
