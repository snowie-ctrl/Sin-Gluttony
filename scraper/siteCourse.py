"""
A site recipe's kind and course from the site's own category (and, for a drink, its title), by the words in
rules/siteCourses.json. It runs when a cached page is read, before tagging, so a drink found on a food site is
tagged, estimated and gated as a drink. It only ever turns food into drink, and it leaves the course as a hint
(hints["course"]) that tagging.applyCourse uses when no per-source map applies.
"""
import re


def parts(category):
    """The site's category, split on commas into lowercase parts ("Cocktails, Drink" → ["cocktails", "drink"])."""
    return [p.strip().lower() for p in (category or "").split(",") if p.strip()]


def _padded(text):
    return " " + " ".join(re.findall(r"[a-z]+", (text or "").lower())) + " "


def foodCourse(categoryParts, table):
    """The most specific course any part names, in the rules' order, or None."""
    found = {course for course, words in table["food"].items() if any(p in words for p in categoryParts)}
    return next((course for course in table["foodOrder"] if course in found), None)


def drinkCourse(title, categoryParts, table):
    """A drink's course: its category first ("Cocktails"), then whole words of its title (smoothie, latte)."""
    for course, words in table["drinkCategories"].items():
        if any(p in words for p in categoryParts):
            return course
    padded = _padded(title)
    for course, words in table["drinkTitles"].items():
        if any(f" {word} " in padded for word in words):
            return course
    return None


def classify(recipe, table):
    categoryParts = parts(recipe.hints.get("category"))
    if recipe.kind == "food" and any(p in table["drinkWords"] for p in categoryParts):
        recipe.kind = "drink"
    recipe.hints["course"] = (drinkCourse(recipe.title, categoryParts, table) if recipe.kind == "drink"
                              else foodCourse(categoryParts, table))
    return recipe
