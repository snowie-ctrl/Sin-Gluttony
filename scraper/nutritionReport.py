"""
What the nutrition estimate says about itself, for the dry run's report: how
close the estimate comes to the sites' own numbers (calibration), and which
ingredients still need an FDC food or a place in the ingredient table, ranked
by how many recipes each would bring back (the two queues). It holds only
ingredient names, counts and FDC candidates, never recipe text.
"""
from statistics import median

import fdcMatch


def _quantile(values, fraction):
    """Linear-interpolated quantile of a sorted list."""
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def _row(ratios):
    if not ratios:
        return {"n": 0, "median": None, "p25": None, "p75": None, "within20": None, "within35": None}
    ratios = sorted(ratios)
    n = len(ratios)
    return {"n": n, "median": round(median(ratios), 3), "p25": round(_quantile(ratios, 0.25), 3),
            "p75": round(_quantile(ratios, 0.75), 3),
            "within20": round(sum(1 for x in ratios if abs(x - 1) <= 0.2) / n, 3),
            "within35": round(sum(1 for x in ratios if abs(x - 1) <= 0.35) / n, 3)}


def calibrate(recipes):
    """
    {site: {n, median, p25, p75, within20, within35, pieceYields}} of estimate calories over the site's own.
    Recipes whose servings came from a piece count are left out (their per-serving basis differs from the
    site's) and counted in pieceYields.
    """
    ratios = {}
    pieces = {}
    for recipe in recipes:
        ratios.setdefault(recipe.source, [])
        pieces.setdefault(recipe.source, 0)
        if recipe.nutritionFrom != "source" or not recipe.estimate:
            continue
        if recipe.servingsFrom == "yield":
            pieces[recipe.source] += 1
            continue
        own = (recipe.nutrition or {}).get("calories")
        if own and own > 0 and recipe.estimate.get("calories") is not None:
            ratios[recipe.source].append(recipe.estimate["calories"] / own)
    return {site: {**_row(values), "pieceYields": pieces[site]} for site, values in ratios.items()}


def _hiddenBlockers(recipes):
    """The blockers of each recipe hidden for no-nutrition that has some."""
    return [r.hints["blockers"] for r in recipes if r.hiddenReason == "no-nutrition" and r.hints.get("blockers")]


def fdcQueue(recipes, foods, limit=200):
    """
    Ingredients with no FDC food that block recipes hidden for no-nutrition, most unlocking first.
    blocks counts the recipes with the ingredient among their blockers; unlocks counts those where it is
    the only blocker, so mapping it completes the estimate.
    """
    counts = {}
    for blockers in _hiddenBlockers(recipes):
        names = {b["ingredient"] for b in blockers if b["reason"] == "no-fdc"}
        for name in names:
            entry = counts.setdefault(name, {"unlocks": 0, "blocks": 0})
            entry["blocks"] += 1
            if all(b["reason"] == "no-fdc" and b["ingredient"] == name for b in blockers):
                entry["unlocks"] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1]["unlocks"], -kv[1]["blocks"], kv[0]))[:limit]
    return [{"ingredient": name, "unlocks": c["unlocks"], "blocks": c["blocks"],
             "candidates": fdcMatch.candidates(name, foods, 5)} for name, c in ranked]


def unknownQueue(recipes, limit=50):
    """
    [{name, blocks, unlocks}]: ingredient names the table does not know that block recipes hidden for
    no-nutrition. unlocks counts the recipes where that name is the only blocker of any kind.
    """
    counts = {}
    for blockers in _hiddenBlockers(recipes):
        names = {b["ingredient"] for b in blockers if b["reason"] == "unknown-ingredient"}
        for name in names:
            entry = counts.setdefault(name, {"blocks": 0, "unlocks": 0})
            entry["blocks"] += 1
            if all(b["reason"] == "unknown-ingredient" and b["ingredient"] == name for b in blockers):
                entry["unlocks"] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1]["unlocks"], -kv[1]["blocks"], kv[0]))[:limit]
    return [{"name": name, "blocks": c["blocks"], "unlocks": c["unlocks"]} for name, c in ranked]
