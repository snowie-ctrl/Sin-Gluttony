"""
One pass of the scraper: fetch (full passes only) -> normalise -> pictures ->
tag -> link -> publish. A re-tag runs everything after fetch over the raw
copies already on the VM, with no new downloads and no removals, so a rule
change can be applied in minutes. A stop is honoured between stages, never
once publishing has started.
"""
import time
import traceback

import adaptTheDb
import adaptWikibooks
import adminApi
import calibration
import config
import images as images_            # runPass has an `images` switch, so the module needs another name
import linking
import matching
import progress
import publish
import report as reports
import rulesData
import store
import tagging
from models import Skipped
from sources import thedb, wikibooks

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


def runPass(mode, log=print, stopRequested=None, images=True):
    stopRequested = stopRequested or (lambda: False)
    started = time.time()
    result = {"mode": mode, "startedAt": started, "outcome": "ok", "error": None}

    def stage(name, detail=""):
        progress.stage(mode, name, detail, started)

    def checkStop():
        if stopRequested():
            raise Stopped()

    try:
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
