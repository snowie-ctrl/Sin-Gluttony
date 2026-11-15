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

Each row says when its site was last crawled (lastPassAt). A site this pass
did not crawl (a re-tag, or a full pass of another one site) keeps what its
last crawl found, from the previous run/sites.json: the counts, stop,
listing, extraction, alarm and lastPassAt. What the gate and this pass's
pictures decide (cached, recipes, shown, hidden, skipped, calibration,
pictureStop) is worked out afresh.
"""
from datetime import datetime, timezone

import config
import gate
import pagecache
import store

JUDGE_PAGES = 10        # fewer fetched pages than this is too few to judge
LOW_RATE = 0.5          # under this share of fetched pages giving a recipe is red
MAX_FALL = 0.20         # a fall of more than this from the last judged rate is red
# what a site's crawl decides: carried over from the previous sites.json for a site not crawled this pass
# (pictureStop is not one: every pass with pictures runs the images stage for every site)
CRAWL_FIELDS = ("listed", "due", "fetched", "notRecipe", "gone", "errors", "stopReason",
                "listingComplete", "extraction", "alarm", "lastPassAt")


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


def previousRows():
    """{site: row} from the last run/sites.json, or {} when there is none."""
    saved = store.readJson(config.SITES_FILE, {}) or {}
    rows = saved.get("sites") if isinstance(saved, dict) else None
    return {row["site"]: row for row in rows or [] if isinstance(row, dict) and row.get("site")}


def summarise(siteList, crawled, recipes, skipped, siteState, startedAt, pictureStops, calibration, previous=None):
    """
    One row per enabled site; siteState[site]["lastRate"] is updated for every site whose pass was judged.
    previous ({site: row}, previousRows()) is given when sites not in crawled should keep their last crawl's
    fields; a site with no previous row then has lastPassAt None. Without it, every row is worked out as is.
    """
    passAt = datetime.fromtimestamp(startedAt, timezone.utc).isoformat(timespec="seconds")
    rows = []
    for site in siteList:
        name = site["site"]
        wasCrawled = name in (crawled or {})
        carry = previous is not None and not wasCrawled
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
        if rate is not None and pages >= JUDGE_PAGES and not carry:
            state["lastRate"] = rate
        row = {
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
            "lastPassAt": passAt if wasCrawled else None,
        }
        if carry:
            row.update({field: value for field, value in (previous.get(name) or {}).items()
                        if field in CRAWL_FIELDS})
            if name not in previous:        # never crawled: nothing found yet, so nothing to alarm about
                row.update(stopReason=None, listingComplete=False,
                           extraction={"pages": 0, "recipes": 0, "rate": None}, alarm={"red": False, "why": None})
        rows.append(row)
    return rows


def write(rows, mode, at=None):
    """run/sites.json: {generatedAt, mode ("pass" | "dryrun"), sites}."""
    at = at or datetime.now(timezone.utc)
    store.writeJson(config.SITES_FILE, {"generatedAt": at.isoformat(timespec="seconds"), "mode": mode,
                                        "sites": rows})
