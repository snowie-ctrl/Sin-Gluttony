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
    note = (line.note or "").lower()
    noQuantity = line.quantity is None
    if line.optional or line.group == "Garnish":
        return True
    if noQuantity and any(text in note for text in _NO_QUANTITY_NOTES):
        return True
    return noQuantity and any(text in note for text in densities.get("skipNotes", []))


def _blocker(line, reason, name=None):
    return {"line": line.line, "reason": reason, "ingredient": name}


def _drinkMl(line, category, densities, measures):
    """(ml, None) for a drink line, or (None, reason); a line in grams goes back through the category's density."""
    density = category["mlDensity"]
    grams, reason = gramsOf(line, {"portions": [], "mlDensity": density}, densities, measures)
    return (grams / density, None) if grams is not None else (None, reason)


def estimate(recipe, table, mapping, foods, rules, measures=None):
    """(per-serving dict, None), or (None, {"line", "reason", "ingredient"}) for the first failing line."""
    densities = rules["densities"]
    drinks = rules["drinkNutrition"]
    totals = dict.fromkeys(FIELDS, 0.0)
    for line in recipe.ingredients:
        if _skipped(line, densities):
            continue
        if line.ingredientId is None:
            return None, _blocker(line, "unknown-ingredient")
        name = table.rows[line.ingredientId]["name"]
        categoryName = drinks["ingredients"].get(name)
        if categoryName:
            category = drinks["categories"][categoryName]
            ml, reason = _drinkMl(line, category, densities, measures)
            if ml is None:
                return None, _blocker(line, reason, name)
            for field in FIELDS:
                totals[field] += (category.get(field) or 0) * ml / 100
            continue
        fdcId = mapping.get(name)
        food = foods.get(fdcId) if fdcId is not None else None
        if food is None:
            return None, _blocker(line, "no-fdc", name)
        grams, reason = gramsOf(line, food, densities, measures, name)
        if grams is None:
            return None, _blocker(line, reason, name)
        for field in FIELDS:
            totals[field] += (food["per100g"].get(field) or 0) * grams / 100
    if not recipe.servings or recipe.servings < 1:
        return None, {"line": None, "reason": "no-servings", "ingredient": None}
    return {field: round(total / recipe.servings, 1) for field, total in totals.items()}, None


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
