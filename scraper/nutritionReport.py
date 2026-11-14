"""
What the nutrition estimate says about itself, for the dry run's report: how
close the estimate comes to the sites' own numbers (calibration), and which
ingredients still need an FDC food, ranked by how many recipes each would
bring back (the mapping queue). It holds only ingredient names, counts and
FDC candidates, never recipe text.
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
    """{site: {n, median, p25, p75, within20, within35}} of estimate calories over the site's own calories."""
    ratios = {}
    for recipe in recipes:
        ratios.setdefault(recipe.source, [])
        if recipe.nutritionFrom != "source" or not recipe.estimate:
            continue
        own = (recipe.nutrition or {}).get("calories")
        if own and own > 0 and recipe.estimate.get("calories") is not None:
            ratios[recipe.source].append(recipe.estimate["calories"] / own)
    return {site: _row(values) for site, values in ratios.items()}


def fdcQueue(recipes, foods, limit=200):
    """Ingredients that block recipes hidden for no-nutrition, most unlocking first."""
    counts = {}
    for recipe in recipes:
        blocker = recipe.estimateBlocker
        if recipe.hiddenReason != "no-nutrition" or not blocker or blocker["reason"] != "no-fdc":
            continue
        names = set(recipe.hints.get("noFdc") or [])
        names.add(blocker["ingredient"])
        for name in names:
            entry = counts.setdefault(name, {"unlocks": 0, "blocks": 0})
            entry["blocks"] += 1
            if len(names) == 1:
                entry["unlocks"] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1]["unlocks"], -kv[1]["blocks"], kv[0]))[:limit]
    return [{"ingredient": name, "unlocks": c["unlocks"], "blocks": c["blocks"],
             "candidates": fdcMatch.candidates(name, foods, 5)} for name, c in ranked]
