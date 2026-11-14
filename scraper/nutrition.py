"""
Per-serving nutrition for a recipe. The estimate adds up every required line
from USDA foods (or a typical drink category per 100 ml), then divides by the
servings. One line that cannot be converted means no estimate at all, with the
first such line named. The site's own nutrition wins; an estimate is used only
when the site gave none, and is flagged when its calories look out of range.
"""
import gate
from grams import gramsOf

FIELDS = ("calories", "proteinG", "carbsG", "fatG", "satFatG", "fibreG", "sugarG", "sodiumMg")
_NO_QUANTITY_NOTES = ("to taste", "as needed", "to top up")
_ABSURD = 3         # an estimate over this many times the range's top counts as no estimate


def _skipped(line, densities):
    """Optional, Garnish, "to taste" and cooking-medium lines; a skip note wins even over an amount."""
    note = (line.note or "").lower()
    if line.optional or line.group == "Garnish":
        return True
    if line.quantity is None and any(text in note for text in _NO_QUANTITY_NOTES):
        return True
    return any(text in note for text in densities.get("skipNotes", []))


def _blocker(line, reason, name=None):
    return {"line": line.line, "reason": reason, "ingredient": name}


def _drinkMl(line, category, densities, measures):
    """(ml, None) for a drink line, or (None, reason); a line in grams goes back through the category's density."""
    density = category["mlDensity"]
    grams, reason = gramsOf(line, {"portions": [], "mlDensity": density}, densities, measures)
    return (grams / density, None) if grams is not None else (None, reason)


def estimate(recipe, table, mapping, foods, rules, measures=None):
    """
    (per-serving dict, None), or (None, {"line", "reason", "ingredient"}) for the first failing line.
    Every line is still read after a failure: recipe.hints["blockers"] lists each failing required line as
    {"reason", "ingredient"} (deduplicated, in line order, plus no-servings), and recipe.hints["noFdc"] the
    sorted names that have no FDC food, so the queues know what one more mapping would unlock.
    """
    densities = rules["densities"]
    drinks = rules["drinkNutrition"]
    totals = dict.fromkeys(FIELDS, 0.0)
    failures = []
    for line in recipe.ingredients:
        if _skipped(line, densities):
            continue
        if line.ingredientId is None:
            failures.append((_blocker(line, "unknown-ingredient"), line.unknownName or line.name))
            continue
        name = table.rows[line.ingredientId]["name"]
        categoryName = drinks["ingredients"].get(name)
        if categoryName:
            category = drinks["categories"][categoryName]
            ml, reason = _drinkMl(line, category, densities, measures)
            if ml is None:
                failures.append((_blocker(line, reason, name), name))
                continue
            for field in FIELDS:
                totals[field] += (category.get(field) or 0) * ml / 100
            continue
        fdcId = mapping.get(name)
        food = foods.get(fdcId) if fdcId is not None else None
        if food is None:
            failures.append((_blocker(line, "no-fdc", name), name))
            continue
        grams, reason = gramsOf(line, food, densities, measures, name)
        if grams is None:
            failures.append((_blocker(line, reason, name), name))
            continue
        for field in FIELDS:
            totals[field] += (food["per100g"].get(field) or 0) * grams / 100
    noServings = not recipe.servings or recipe.servings < 1
    named = [(blocker["reason"], hint) for blocker, hint in failures]     # hint: the ingredient's name
    blockers = []
    for reason, ingredient in named + ([("no-servings", None)] if noServings else []):
        entry = {"reason": reason, "ingredient": ingredient}
        if entry not in blockers:
            blockers.append(entry)
    _record(recipe, "blockers", blockers)
    _record(recipe, "noFdc", sorted({hint for reason, hint in named if reason == "no-fdc"}))
    if failures:
        return None, failures[0][0]
    if noServings:
        return None, {"line": None, "reason": "no-servings", "ingredient": None}
    return {field: round(total / recipe.servings, 1) for field, total in totals.items()}, None


def _record(recipe, key, values):
    if values:
        recipe.hints[key] = values
    else:
        recipe.hints.pop(key, None)


def rangeOf(recipe, rules):
    """(low, high) calories per serving: piece counts first, then the course, then the kind."""
    ranges = rules["nutritionRanges"]
    if recipe.servingsFrom == "yield":
        return tuple(ranges["piece"])
    if recipe.course in ranges:
        return tuple(ranges[recipe.course])
    return tuple(ranges[recipe.kind])


def choose(recipe, table, mapping, foods, rules, measures=None):
    """Fill estimate and estimateBlocker, then pick the nutrition the recipe shows."""
    if recipe.nutritionFrom == "estimate":      # a repeat pass starts again from what the site gave
        recipe.nutrition = None
    recipe.estimate, recipe.estimateBlocker = estimate(recipe, table, mapping, foods, rules, measures)
    low, high = rangeOf(recipe, rules)
    if gate.hasNutrition(recipe):
        recipe.nutritionFrom = "source"
    elif recipe.estimate and recipe.estimate["calories"] <= _ABSURD * high:
        recipe.nutritionFrom = "estimate"
        recipe.nutrition = dict(recipe.estimate)
    else:
        recipe.nutritionFrom = None
    calories = recipe.nutrition["calories"] if gate.hasNutrition(recipe) else None
    recipe.nutritionFlagged = calories is not None and not low <= calories <= high
