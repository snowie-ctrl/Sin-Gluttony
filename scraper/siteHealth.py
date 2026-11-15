"""
How each recipe site fared on a pass, for the owner's Sites page: what was
listed and fetched, how many recipes were read, shown and hidden (and why),
which cached pages gave none, the nutrition calibration, and the breakage
alarm. The rows go to run/sites.json, which the control API serves.

The alarm (Ruling S5): a site the pass stopped is red with its stop reason.
Otherwise the extraction rate is recipes read over the pages fetched this
pass; under 10 such pages is too few to judge. Red when the rate is under
50%, or more than 20 points below the last judged rate (lastRate in
run/site-state.json, updated here whenever a pass is judged).
"""
from datetime import datetime, timezone

import config
import gate
import pagecache
import store

JUDGE_PAGES = 10        # fewer fetched pages than this is too few to judge
LOW_RATE = 0.5          # under this share of fetched pages giving a recipe is red
MAX_FALL = 0.20         # a fall of more than this from the last judged rate is red


def _percent(rate):
    return f"{round(rate * 100)}%"


def alarm(rate, pages, lastRate, stopReason):
    """(red, why) for one site's pass."""
    if stopReason:
        return True, stopReason
    if rate is None or pages < JUDGE_PAGES:
        return False, None
    if rate < LOW_RATE:
        return True, f"only {_percent(rate)} of fetched pages gave a recipe"
    if lastRate is not None and round(lastRate - rate, 9) > MAX_FALL:     # rounded: 0.9 - 0.7 is not over 0.2
        return True, f"extraction fell from {_percent(lastRate)} to {_percent(rate)}"
    return False, None


def _fetchedThisPass(site, url, startedAt):
    info = pagecache.meta(site, url) if url else None
    return isinstance(info, dict) and (info.get("fetchedAt") or 0) >= startedAt


def summarise(siteList, crawled, recipes, skipped, siteState, startedAt, pictureStops, calibration):
    """One row per enabled site; siteState[site]["lastRate"] is updated for every site whose pass was judged."""
    rows = []
    for site in siteList:
        name = site["site"]
        result = (crawled or {}).get(name) or {}
        own = [r for r in recipes if r.source == name]
        damaged = [s for s in skipped if s.get("site") == name]
        hidden = {reason: 0 for reason in gate.REASONS}
        for r in own:
            if r.hiddenReason is not None:
                hidden[r.hiddenReason] = hidden.get(r.hiddenReason, 0) + 1
        skippedCounts = {}
        for s in damaged:
            skippedCounts[s["reason"]] = skippedCounts.get(s["reason"], 0) + 1
        readNow = sum(1 for r in own if _fetchedThisPass(name, r.sourceUrl, startedAt))
        pages = readNow + sum(1 for s in damaged if _fetchedThisPass(name, s.get("url"), startedAt))
        rate = readNow / pages if pages else None
        state = siteState.setdefault(name, {})
        stopReason = result.get("stopReason")
        red, why = alarm(rate, pages, state.get("lastRate"), stopReason)
        if rate is not None and pages >= JUDGE_PAGES:
            state["lastRate"] = rate
        rows.append({
            "site": name, "name": site.get("name", name), "kind": site.get("kind"),
            "listed": result.get("listed", 0), "due": result.get("due", 0), "fetched": result.get("fetched", 0),
            "notRecipe": result.get("notRecipe", 0), "gone": result.get("gone", 0),
            "errors": result.get("errors", 0), "stopReason": stopReason,
            "pictureStop": (pictureStops or {}).get(name),
            "listingComplete": bool(result.get("complete", False)),
            "cached": len(own) + len(damaged), "recipes": len(own),
            "shown": sum(1 for r in own if r.hiddenReason is None),
            "hidden": hidden, "skipped": skippedCounts,
            "extraction": {"pages": pages, "recipes": readNow, "rate": rate},
            "calibration": (calibration or {}).get(name),
            "alarm": {"red": red, "why": why},
        })
    return rows


def write(rows, mode, at=None):
    """run/sites.json: {generatedAt, mode ("pass" | "dryrun"), sites}."""
    at = at or datetime.now(timezone.utc)
    store.writeJson(config.SITES_FILE, {"generatedAt": at.isoformat(timespec="seconds"), "mode": mode,
                                        "sites": rows})
