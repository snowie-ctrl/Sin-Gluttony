"""
The dry run's report, for the owner to read before any full crawl. In
reports/dryrun-<date>/:

  summary.md            pass rate per site and per gate reason, crawl stops, nutrition and its calibration, basics found or missing
  summary.json          the same, as data
  samples/<site>.json   ten recipes per site, listed ones first
  unparsed.json         the ingredient lines the gate calls unparsed, grouped by their shape
  skipped.json          pages that gave no recipe, with the reason
  unknown-queue.json    unknown ingredient names blocking hidden recipes

It holds the sites' recipe text, so it stays in reports/, which git ignores.
"""
import re
import time

import basics
import gate
import quantity
import store

SAMPLES = 10
EXAMPLES = 5
PATTERN_LENGTH = 8
SHOWN_PATTERNS = 20
SHOWN_QUEUE = 20
SHOWN_UNKNOWN = 20
_KEEP = {"x", "of", "or", "and", "to", "a", "an", "top", "juice", "zest"}
_TOKEN = re.compile(r"\d+(?:[.,/⁄]\d+)*[^\W\d_]*|[^\W\d_]+|[^\w\s]")
_NUMBER_WORD = re.compile(r"(\d+(?:[.,/⁄]\d+)*)([^\W\d_]*)")
_FRACTION = re.compile(f"[{''.join(quantity.FRACTIONS)}]")
_ORDER = ("listed", *gate.REASONS)


def linePattern(text, units):
    """
    The shape of an ingredient line, so lines that fail the same way group
    together: N a number, U a unit, NU a number glued to a unit, w words.
    "2 x 400g cans tomatoes" -> "N x NU U w"; "200g/7oz flour" -> "NU / NU w".
    """
    symbols = []
    for token in _TOKEN.findall(_FRACTION.sub(" 1 ", text)):
        number = _NUMBER_WORD.fullmatch(token)
        if number:
            unit = number.group(2).lower()
            symbol = "N" + ("" if not unit else "U" if unit in units else "w")
        elif token.lower() in units:
            symbol = "U"
        elif token.lower() in _KEEP:
            symbol = token.lower()
        elif re.fullmatch(r"[^\W\d_]+", token):
            symbol = "w"
        else:
            symbol = token
        if not (symbol == "w" and symbols and symbols[-1] == "w"):
            symbols.append(symbol)
    return " ".join(symbols[:PATTERN_LENGTH])


def _share(part, whole):
    return round(part / whole, 3) if whole else None


def nutritionSummary(recipes):
    """How many recipes show the site's nutrition, an estimate, a flagged value, and why estimates failed."""
    blockers = {}
    hidden = {}
    for recipe in recipes:
        if recipe.estimateBlocker:
            reason = recipe.estimateBlocker["reason"]
            blockers[reason] = blockers.get(reason, 0) + 1
        if recipe.hiddenReason == "no-nutrition":
            for reason in {b["reason"] for b in recipe.hints.get("blockers") or []}:
                hidden[reason] = hidden.get(reason, 0) + 1
    return {"source": sum(1 for r in recipes if r.nutritionFrom == "source"),
            "estimate": sum(1 for r in recipes if r.nutritionFrom == "estimate"),
            "flagged": sum(1 for r in recipes if r.nutritionFlagged), "blockers": blockers,
            "hiddenBlockers": hidden}


def siteSummary(site, crawl, recipes, skipped):
    mine = [r for r in recipes if r.source == site["site"]]
    lost = [s for s in skipped if s["site"] == site["site"]]
    counts = {reason: 0 for reason in _ORDER}
    for recipe in mine:
        counts[recipe.hiddenReason or "listed"] += 1
    lostBy = {}
    for entry in lost:
        lostBy[entry["reason"]] = lostBy.get(entry["reason"], 0) + 1
    pages = len(mine) + len(lost)
    summary = {"site": site["site"], "name": site["name"], "crawl": crawl, "pages": pages, "recipes": len(mine),
               "notRead": len(lost), "notReadByReason": lostBy, "listed": counts["listed"],
               "passRate": _share(counts["listed"], pages), "gate": counts,
               "siteNutrition": sum(1 for r in mine if gate.hasNutrition(r)),
               "nutrition": nutritionSummary(mine),
               "kinds": {"drinks": sum(1 for r in mine if r.kind == "drink"),
                         "drinksShown": sum(1 for r in mine if r.kind == "drink" and r.hiddenReason is None),
                         "noCourse": sum(1 for r in mine if r.course is None),
                         "noCourseShown": sum(1 for r in mine if r.course is None and r.hiddenReason is None)}}
    if site["kind"] == "drink":
        summary["drinks"] = {"withGlass": sum(1 for r in mine if r.glass),
                             "withGarnish": sum(1 for r in mine if any(l.group == "Garnish" for l in r.ingredients)),
                             "withMethod": sum(1 for r in mine if r.hints.get("method"))}
    return summary


def samples(recipes, siteName, count=SAMPLES):
    mine = sorted((r for r in recipes if r.source == siteName),
                  key=lambda r: (r.hiddenReason is not None, r.sourceUrl or ""))
    return [r.toDict() for r in mine[:count]]


def unparsedGroups(recipes, units):
    groups = {}
    for recipe in recipes:
        for line in recipe.ingredients:
            if gate.lineParsed(line, units):
                continue
            key = linePattern(line.line, units)
            group = groups.setdefault(key, {"pattern": key, "count": 0, "sites": {}, "examples": []})
            group["count"] += 1
            group["sites"][recipe.source] = group["sites"].get(recipe.source, 0) + 1
            if len(group["examples"]) < EXAMPLES:
                group["examples"].append(line.line)
    return sorted(groups.values(), key=lambda g: (-g["count"], g["pattern"]))


def basicsStatus(rules, recipes, skipped, siteState=None):
    return basics.resolve(rules, recipes, skipped, siteState)


def _pct(value):
    return "-" if value is None else f"{value:.0%}"


def _cell(text):
    return str(text).replace("|", "/")


def _ratio(value):
    return "-" if value is None else f"{value:.2f}"


def _blockerTable(summary):
    """Blocker counts two ways: every blocker of the hidden recipes, and the first blocker of all recipes."""
    nutrition = summary.get("nutrition") or {}
    hidden = nutrition.get("hiddenBlockers") or {}
    first = nutrition.get("blockers") or {}
    reasons = sorted(set(hidden) | set(first), key=lambda r: (-hidden.get(r, 0), -first.get(r, 0), r))
    if not reasons:
        return ["", "No recipe is blocked from an estimate."]
    out = ["", "Why recipes have no estimate. Hidden recipes (no-nutrition) counts every blocker of each recipe; "
           "all recipes counts only each recipe's first blocker.", "",
           "| Blocker | Hidden recipes (every blocker) | All recipes (first blocker) |", "|---|---|---|"]
    return out + [f"| {r} | {hidden.get(r, 0)} | {first.get(r, 0)} |" for r in reasons]


def _nutritionSection(summary, queue, unknown=None):
    out = ["", "## Nutrition", "",
           "Calibration is the estimate's calories over the site's own, for recipes that have both; "
           "recipes whose servings are a piece count are left out. "
           "no-nutrition is what the gate still hides.", "",
           "| Site | Site nutrition | Estimated | Flagged | no-nutrition | Calibration n | Median | p25-p75 | Within 20% |",
           "|---|---|---|---|---|---|---|---|---|"]
    calibration = summary.get("calibration") or {}
    for s in summary["sites"]:
        n = s.get("nutrition") or {"source": 0, "estimate": 0, "flagged": 0}
        c = calibration.get(s["site"]) or {"n": 0, "median": None, "p25": None, "p75": None, "within20": None}
        out.append(f"| {s['name']} | {n['source']} | {n['estimate']} | {n['flagged']} | {s['gate']['no-nutrition']} | "
                   f"{c['n']} | {_ratio(c['median'])} | {_ratio(c['p25'])}-{_ratio(c['p75'])} | {_pct(c['within20'])} |")
    out += _blockerTable(summary)
    if queue:
        out += ["", f"### FDC mapping queue (top {min(len(queue), SHOWN_QUEUE)})", "",
                "Blocks counts the hidden recipes with this ingredient among their blockers; unlocks is exact: "
                "the hidden recipes whose only blockers are this ingredient, so mapping it completes their estimate.", "",
                "| Ingredient | Unlocks | Blocks | Best candidate |", "|---|---|---|---|"]
        for row in queue[:SHOWN_QUEUE]:
            best = row["candidates"][0]["description"] if row["candidates"] else "-"
            out.append(f"| {_cell(row['ingredient'])} | {row['unlocks']} | {row['blocks']} | {_cell(best)} |")
    if unknown:
        out += ["", f"### Unknown ingredients blocking hidden recipes (top {min(len(unknown), SHOWN_UNKNOWN)})", "",
                "These names are not in the ingredient table. They are mapped on Surrogate's existing ingredient "
                "mapping page. Unlocks counts the hidden recipes where the name is the only blocker.", "",
                "| Name | Unlocks | Blocks |", "|---|---|---|"]
        out += [f"| {_cell(row['name'])} | {row['unlocks']} | {row['blocks']} |" for row in unknown[:SHOWN_UNKNOWN]]
    return out


def renderMarkdown(summary, groups, queue=None, unknown=None):
    out = [f"# Dry run {summary['date']}", "",
           f"{summary['recipes']} recipes from {summary['pages']} cached pages; {summary['listed']} would be listed "
           f"({_pct(summary['passRate'])}). These counts cover every cached page, not only this run's. Nutrition estimates from USDA foods are included: `no-nutrition` "
           "counts the recipes with neither the site's own nutrition nor a complete estimate.", "",
           "## Sites", "",
           "| Site | Pages | Not read | " + " | ".join(_ORDER) + " | Pass rate | Site nutrition | Crawl |",
           "|" + "---|" * (len(_ORDER) + 6)]
    for s in summary["sites"]:
        crawl = s["crawl"]
        if not crawl:
            state = "not crawled this run"
        elif crawl.get("stopReason"):
            state = f"stopped: {crawl['stopReason']}"
        else:
            state = (f"{crawl.get('due', 0)} due, {crawl.get('fetched', 0)} fetched, {crawl.get('notRecipe', 0)} "
                     f"notRecipe, {crawl.get('gone', 0)} gone, {crawl.get('errors', 0)} errors, "
                     f"{crawl.get('listed', 0)} listed")
        out.append(f"| {s['name']} | {s['pages']} | {s['notRead']} | "
                   + " | ".join(str(s["gate"][r]) for r in _ORDER)
                   + f" | {_pct(s['passRate'])} | {s['siteNutrition']} | {_cell(state)} |")
    out += ["", "## Gate reasons, all sites", "", "| Reason | Recipes |", "|---|---|"]
    out += [f"| {r} | {summary['reasons'][r]} |" for r in _ORDER]
    out += ["", "## Kinds and courses", "",
            "Drinks are pages whose site category says so (or every page of a drink site); a recipe with no course "
            "has no category word in rules/siteCourses.json.", ""]
    out += [f"- {s['name']}: {s['kinds']['drinks']} drinks ({s['kinds']['drinksShown']} shown); "
            f"{s['kinds']['noCourse']} recipes with no course ({s['kinds']['noCourseShown']} shown)"
            for s in summary["sites"]]
    drinks = [s for s in summary["sites"] if "drinks" in s]
    if drinks:
        out += ["", "## Drinks", ""]
        out += [f"- {s['name']}: glass {s['drinks']['withGlass']}, garnish {s['drinks']['withGarnish']}, "
                f"method {s['drinks']['withMethod']} of {s['recipes']}" for s in drinks]
    out += _nutritionSection(summary, queue, unknown)
    out += ["", "## Unparsed ingredient lines by shape", "",
            f"{summary['unparsedLines']} lines in all. N a number, U a unit, NU both glued, w words.", "",
            "| Shape | Lines | Example |", "|---|---|---|"]
    out += [f"| `{g['pattern']}` | {g['count']} | {_cell(g['examples'][0])} |" for g in groups[:SHOWN_PATTERNS]]
    out += ["", "## Basics", "", "| Basic | Status | Chosen URL |", "|---|---|---|"]
    out += [f"| {b['name']} | {b['status']} | {b['url'] or '-'} |" for b in summary["basics"]]
    missing = [b["name"] for b in summary["basics"] if not b["url"]]
    out += ["", f"{summary.get('basicsFellBack', 0)} basics fell back to a later candidate."]
    out += ["", "No site provides: " + (", ".join(missing) if missing else "none") + "."]
    return "\n".join(out) + "\n"


def write(folder, siteList, crawled, recipes, skipped, rules, today, siteState=None, calibration=None, queue=None, unknown=None):
    units = rules["unitMap"]
    perSite = [siteSummary(site, crawled.get(site["site"]), recipes, skipped) for site in siteList]
    reasons = {reason: sum(s["gate"][reason] for s in perSite) for reason in _ORDER}
    groups = unparsedGroups(recipes, units)
    pages = sum(s["pages"] for s in perSite)
    summary = {"date": today.isoformat(), "generatedAt": time.time(), "pages": pages, "recipes": len(recipes),
               "listed": reasons["listed"], "passRate": _share(reasons["listed"], pages), "sites": perSite,
               "reasons": reasons, "unparsedLines": sum(g["count"] for g in groups),
               "basics": basicsStatus(rules, recipes, skipped, siteState),
               "nutrition": nutritionSummary(recipes), "calibration": calibration or {}}
    summary["basicsFellBack"] = sum(1 for b in summary["basics"] if (b["candidate"] or 1) > 1)
    store.writeJson(folder / "summary.json", summary)
    store.writeJson(folder / "unparsed.json", groups)
    store.writeJson(folder / "skipped.json", skipped)
    store.writeJson(folder / "unknown-queue.json", unknown or [])
    for site in siteList:
        store.writeJson(folder / "samples" / f"{site['site']}.json", samples(recipes, site["site"]))
    (folder / "summary.md").write_text(renderMarkdown(summary, groups, queue, unknown), encoding="utf-8")
    return summary
