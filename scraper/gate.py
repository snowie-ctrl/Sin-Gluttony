"""
The completeness gate: a recipe is listed only with a picture at least 800 px
wide, a total time, servings, every ingredient line parsed, and per-serving
nutrition. The first check that fails, in that order, is its HiddenReason. It
is checked again every pass, so better rules bring recipes in without a
re-crawl.

Check 5 passes on per-serving nutrition, which is the site's own or, when the
site gave none, the complete estimate from USDA data that nutrition.choose
stored in recipe.nutrition.

The gate never touches facts: a recipe whose ingredients are not all known is
still never listed under a diet or as free of an allergen (facts.py).
"""
import re

MIN_WIDTH = 800
REASONS = ("no-photo", "small-photo", "no-time", "no-servings", "unparsed-line", "no-nutrition")
_LETTER = re.compile(r"[^\W\d_]")
_LEFTOVER = re.compile(r"^(?:[x×]\s|[x×/⁄]\s*\d|⁄)", re.IGNORECASE)    # "x 400g cans", "/7oz", "⁄2 cup"


def _measureInName(units):
    """A number followed by a unit inside the name: an amount the parser did not take ("g/7oz", "flour 200g")."""
    words = "|".join(sorted((re.escape(unit) for unit in units), key=len, reverse=True))
    return re.compile(rf"\d\s*(?:{words})\b", re.IGNORECASE)


def lineParsed(line, units):
    """Parsed: a name was found and no amount is left inside it. "Salt, to taste" and "Lemon wedge" count."""
    name = (line.name or "").strip()
    if not _LETTER.search(name.replace("½", "")):
        return False
    return not _LEFTOVER.match(name) and not _measureInName(units).search(name)


def hasNutrition(recipe):
    return bool(recipe.nutrition) and recipe.nutrition.get("calories") is not None


def check(recipe, units):
    """The first failing check's reason, or None when the recipe may be listed."""
    if not recipe.imagePath:
        return "no-photo"
    if not recipe.imageWidth or recipe.imageWidth < MIN_WIDTH:
        return "small-photo"        # a width never measured cannot show 800 px either
    if not recipe.totalMinutes:
        return "no-time"
    if not recipe.servings:
        return "no-servings"
    if not recipe.ingredients or not all(lineParsed(line, units) for line in recipe.ingredients):
        return "unparsed-line"
    if not hasNutrition(recipe):    # the site's own or a chosen estimate
        return "no-nutrition"
    return None


def apply(recipe, units):
    recipe.hiddenReason = check(recipe, units)
    return recipe.hiddenReason
