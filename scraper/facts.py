"""
What a recipe contains and which diets it meets. The safety rule lives here:
a recipe with any unknown ingredient, optional ones included (a reader may add
them), is not complete, and an incomplete recipe meets no diet. It is better
to leave a vegan dish out of the vegan filter than to call a dish with an
unknown sauce nut-free.
"""
CONTAINS_ITEMS = ("meat", "poultry", "fish", "shellfish", "dairy", "egg", "gluten", "tree-nut", "peanut", "soy",
                  "sesame", "alcohol", "honey")
DIETS = ("vegetarian", "vegan", "gluten-free", "dairy-free")
_FLESH = {"meat", "poultry", "fish", "shellfish"}


def dietsFor(contains):
    diets = []
    if not contains & _FLESH:
        diets.append("vegetarian")
    if not contains & (_FLESH | {"dairy", "egg", "honey"}):
        diets.append("vegan")
    if "gluten" not in contains:
        diets.append("gluten-free")
    if "dairy" not in contains:
        diets.append("dairy-free")
    return diets


def applyMatching(recipe, table):
    for line in recipe.ingredients:
        ids, key = table.matchOptions(line.name or line.line)
        line.ingredientId = ids[0] if ids else None
        line.alternativeIds = ids[1:]
        line.unknownName = None if ids else (key or None)


def applyFacts(recipe, table):
    """A line with options contains what any option contains, so it fits a diet only when every option does."""
    complete = bool(recipe.ingredients) and all(line.ingredientId for line in recipe.ingredients)
    contains = set()
    for line in recipe.ingredients:
        for ingredientId in ([line.ingredientId, *line.alternativeIds] if line.ingredientId else []):
            contains |= table.containsOf(ingredientId)
    recipe.facts = {"complete": complete,
                    "contains": sorted(contains) if complete else [],
                    "diets": dietsFor(contains) if complete else []}
