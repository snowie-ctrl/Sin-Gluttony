"""
What the sources don't say, worked out by rules (rules only: no paid service
reads the recipes). Values a source stated are marked "source"; values a rule
worked out are marked "rule", so the app can say "about 30 min".
"""
import re

import facts
import quantity
from matching import plainText

_MINUTES = {"minute": 1, "minutes": 1, "min": 1, "mins": 1, "hour": 60, "hours": 60, "hr": 60, "hrs": 60, "h": 60,
            "day": 1440, "days": 1440}
_DURATION = re.compile(rf"({quantity.NUMBER})(?:\s*(?:-|–|to)\s*({quantity.NUMBER}))?\s*"
                       r"(minutes?|mins?|hours?|hrs?|h|days?)\b", re.IGNORECASE)
_LABEL = re.compile(r"\b(prep(?:aration)?|cook(?:ing)?|bak(?:e|ing)|total|rest(?:ing)?|chill(?:ing)?)"
                    r"(?:\s*time)?\s*[:\-]", re.IGNORECASE)
_HOLIDAY = re.compile(r"\b(?:christmas|thanksgiving|easter|halloween|holiday|festive|hanukkah|diwali|eid|new year)\b",
                      re.IGNORECASE)
_SAVOURY_COURSES = {"main", "side", "starter", "sauce", "bread", "snack"}
_FOOD_COURSES = {"breakfast", "starter", "main", "side", "dessert", "snack", "bread", "sauce"}
_DRINK_COURSES = {"cocktail", "mocktail", "shot", "coffee/tea", "shake", "punch"}
_MAX_MINUTES = 10080                # a week: a longer time is a parsing slip or not a cooking time, so unknown
# A clause about how long food keeps or how far ahead it can be made ("refrigerate
# for up to 3 days", "it keeps well for 5 days", "use within 5 days", "make the
# sauce 2 days in advance") is not cooking time.
_DAYS = rf"(?:{quantity.NUMBER})\s*(?:days?|weeks?|months?)"
_STORAGE = re.compile(r"\b(?:keeps|will\s+keep|can\s+be\s+kept|stor(?:e|ed|es|ing|age)\b(?!-)|leftovers?"
                      r"|shelf\s+life|will\s+last|lasts|in\s+advance|ahead\s+of\s+time|make[-\s]ahead"
                      rf"|can\s+be\s+(?:prepared|made)|(?:up\s+to|within|no\s+more\s+than)\s+{_DAYS})", re.IGNORECASE)
_CLAUSE_END = re.compile(r"(?<=[.!?;,])\s+|[()]")


def durations(text):
    """Every duration in a text, in minutes. A range counts its upper end: a "quick" filter must not over-promise."""
    found = []
    for match in _DURATION.finditer(text or ""):
        amount = quantity.toNumber(match.group(2) or match.group(1))
        if amount is not None:
            found.append(round(amount * _MINUTES[match.group(3).lower()]))
    return found


def parseTimeText(text):
    """(prep, cook, total) from a Wikibooks Time field, or None when it names no duration."""
    labels = list(_LABEL.finditer(text or ""))
    if not labels:
        total = sum(durations(text))
        return (None, None, total) if total else None
    parts = {}
    for n, label in enumerate(labels):
        end = labels[n + 1].start() if n + 1 < len(labels) else len(text)
        kind = label.group(1).lower()[:3]
        parts[kind] = parts.get(kind, 0) + sum(durations(text[label.end():end]))
    prep = parts.get("pre") or None
    cook = (parts.get("coo", 0) + parts.get("bak", 0)) or None
    total = parts.get("tot") or sum(parts.values()) or None
    return (prep, cook, total) if total else None


def cookingText(text):
    """A step without its clauses about storing the food or making it ahead."""
    return " ".join(c for c in _CLAUSE_END.split(text or "") if not _STORAGE.search(c))


def timeFromSteps(steps):
    """Each step's longest duration, summed: "bake 25 minutes, check after 20" is 25, not 45."""
    total = sum(max(durations(cookingText(step.text)), default=0) for step in steps)
    return total or None


def withinAWeek(minutes):
    return minutes if minutes is not None and minutes <= _MAX_MINUTES else None


def applyTime(recipe, rules):
    stated = parseTimeText(recipe.hints.get("timeText")) if recipe.hints.get("timeText") else None
    if stated and withinAWeek(stated[2]):
        recipe.prepMinutes, recipe.cookMinutes = withinAWeek(stated[0]), withinAWeek(stated[1])
        recipe.totalMinutes, recipe.timeFrom = stated[2], "source"
        return
    guessed = timeFromSteps(recipe.steps)
    if guessed is None and recipe.kind == "drink":
        guessed = rules["difficulty"]["drinkMinutes"]
    if withinAWeek(guessed):
        recipe.totalMinutes, recipe.timeFrom = guessed, "rule"


def difficultyFromRating(rating):
    return {1: 1, 2: 1, 3: 2, 4: 3, 5: 3}[rating]


def difficultyScore(recipe, rules):
    text = " ".join(step.text.lower() for step in recipe.steps)
    hits = sum(1 for word in rules["techniques"] if re.search(rf"\b{re.escape(word)}", text))
    limits = rules["difficulty"]
    score = len(recipe.steps) + len(recipe.ingredients) / 2 + limits["techniqueWeight"] * hits
    return 1 if score <= limits["easyMax"] else 2 if score <= limits["mediumMax"] else 3


def applyDifficulty(recipe, rules):
    rating = recipe.hints.get("difficultyRating")
    if rating:
        recipe.difficulty, recipe.difficultyFrom = difficultyFromRating(rating), "source"
    else:
        recipe.difficulty, recipe.difficultyFrom = difficultyScore(recipe, rules), "rule"


def _hintTexts(recipe):
    return [t for t in [recipe.hints.get("category"), *recipe.hints.get("tags", []),
                        *recipe.hints.get("categories", [])] if t]


def applyCuisine(recipe, rules):
    candidates = [recipe.hints.get("area"), recipe.hints.get("cuisineText"), *recipe.hints.get("categories", [])]
    for candidate in candidates:
        padded = f" {plainText(candidate)} "
        for cuisine, words in rules["cuisines"].items():
            if any(f" {plainText(word)} " in padded for word in words):
                recipe.cuisine = cuisine
                return


def applyCourse(recipe, rules):
    maps = rules["courses"]
    if recipe.source == "wikibooks":
        mapped = [maps["wikibooks"].get(c.lower()) for c in recipe.hints.get("categories", [])]
    else:
        mapped = [maps.get(recipe.source, {}).get((recipe.hints.get("category") or "").lower())]
    fits = _DRINK_COURSES if recipe.kind == "drink" else _FOOD_COURSES
    # A course that does not fit the kind is a mis-categorised page: skip it, take the first that fits.
    course = next((c for c in mapped if c in fits), None)
    if recipe.kind == "drink":
        if recipe.alcohol is None and recipe.facts:
            if "alcohol" in recipe.facts["contains"]:
                recipe.alcohol = "alcoholic"
            elif recipe.facts["complete"]:
                recipe.alcohol = "non-alcoholic"
        if course in (None, "cocktail"):
            course = "mocktail" if recipe.alcohol == "non-alcoholic" else "cocktail"
    recipe.course = course


def applyFlavour(recipe, table, rules):
    found = {}
    categories = [table.categoriesOf(line.ingredientId) if line.ingredientId else set() for line in recipe.ingredients]
    sugar = sum(1 for c in categories if "sugar" in c)
    if any("chilli" in c for c in categories):
        found["spicy"] = "rule"
    if recipe.course == "dessert" or (categories and sugar / len(categories) >= rules["flavours"]["sweetShare"]):
        found["sweet"] = "rule"
    if sum(1 for c in categories if "citrus" in c) >= 2 or "sour" in plainText(recipe.title).split():
        found["sour"] = "rule"
    if any("bitter" in c for c in categories):
        found["bitter"] = "rule"
    if recipe.kind == "food" and recipe.course in _SAVOURY_COURSES and "sweet" not in found:
        found["savoury"] = "rule"
    for text in _hintTexts(recipe):
        words = set(plainText(text).split())
        for flavour, sourceWords in rules["flavours"]["sourceWords"].items():
            if words & set(sourceWords):
                found[flavour] = "source"
    recipe.tags += [{"type": "flavour", "tag": tag, "origin": origin} for tag, origin in sorted(found.items())]


def applyOccasion(recipe):
    found = {}
    texts = [t.lower() for t in _hintTexts(recipe)]
    if (recipe.kind == "food" and recipe.course == "main" and recipe.totalMinutes and recipe.totalMinutes <= 45
            and recipe.difficulty and recipe.difficulty <= 2):
        found["weeknight"] = "rule"
    if recipe.course in ("starter", "punch") or (recipe.servings and recipe.servings >= 8):
        found["party"] = "rule"
    if any("party" in t for t in texts):
        found["party"] = "source"
    if any(_HOLIDAY.search(t) for t in texts):
        found["holiday"] = "source"
    if recipe.course == "breakfast":
        found["brunch"] = "rule"
    if any("brunch" in t for t in texts):
        found["brunch"] = "source"
    recipe.tags += [{"type": "occasion", "tag": tag, "origin": origin} for tag, origin in sorted(found.items())]


def applySourceTags(recipe):
    seen = set()
    for tag in recipe.hints.get("tags", []):
        tag = tag.strip()[:40].strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            recipe.tags.append({"type": "source", "tag": tag, "origin": "source"})


def tagRecipe(recipe, table, rules):
    recipe.tags = []
    facts.applyMatching(recipe, table)
    facts.applyFacts(recipe, table)
    applyTime(recipe, rules)
    applyDifficulty(recipe, rules)
    applyCuisine(recipe, rules)
    applyCourse(recipe, rules)
    applyFlavour(recipe, table, rules)
    applyOccasion(recipe)
    applySourceTags(recipe)
    return recipe
