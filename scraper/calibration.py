"""
How good the time and difficulty rules are. Wikibooks recipes that state a
time and a difficulty are the reference: the rules are applied as if nothing
had been stated, and each run reports how often they agree. A time agrees
within 10 minutes or a quarter of the stated total, whichever is larger.
"""
from tagging import difficultyFromRating, difficultyScore, parseTimeText, timeFromSteps, withinAWeek


def calibrate(recipes, rules):
    difficulty = {"n": 0, "agree": 0}
    time = {"n": 0, "agree": 0}
    for recipe in recipes:
        if recipe.source != "wikibooks":
            continue
        rating = recipe.hints.get("difficultyRating")
        if rating:
            difficulty["n"] += 1
            difficulty["agree"] += difficultyScore(recipe, rules) == difficultyFromRating(rating)
        stated = parseTimeText(recipe.hints.get("timeText")) if recipe.hints.get("timeText") else None
        if stated and withinAWeek(stated[2]):
            guessed = timeFromSteps(recipe.steps)
            time["n"] += 1
            time["agree"] += bool(guessed) and abs(guessed - stated[2]) <= max(10, 0.25 * stated[2])
    for counts in (difficulty, time):
        counts["rate"] = round(counts["agree"] / counts["n"], 3) if counts["n"] else None
    return {"difficulty": difficulty, "time": time}
