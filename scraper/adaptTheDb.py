"""
TheMealDB and TheCocktailDB records into the one recipe shape. Their
ingredients sit in numbered slots (20 for meals, 15 for drinks) with the
measure kept apart; empty slots are "", whitespace or null.
"""
import re

import quantity
from models import IngredientLine, Recipe, Skipped, Step

_STEP_LABEL = re.compile(r"^\s*(?:step\s*)?\d+[.):]?\s*$", re.IGNORECASE)
_LEADING_NUMBER = re.compile(r"^\s*(?:step\s*)?\d+[.):]\s+", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_ALCOHOL = {"alcoholic": "alcoholic", "non alcoholic": "non-alcoholic", "non-alcoholic": "non-alcoholic",
            "optional alcohol": "optional"}


def splitSteps(text):
    """Steps from a block of instructions: by line, without "STEP 1" labels; one paragraph splits into sentences."""
    lines = [line.strip() for line in re.split(r"[\r\n]+", text or "")]
    lines = [_LEADING_NUMBER.sub("", line) for line in lines if line and not _STEP_LABEL.match(line)]
    if len(lines) == 1:
        lines = [s.strip() for s in _SENTENCE.split(lines[0]) if s.strip()]
    return [Step(text=line) for line in lines if line]


def _ingredients(record, slots, units):
    lines = []
    for n in range(1, slots + 1):
        name = " ".join((record.get(f"strIngredient{n}") or "").split())
        if not name:
            continue
        measure = " ".join((record.get(f"strMeasure{n}") or "").split())
        qty, qtyMax, unit, note = quantity.parseMeasure(measure, units)
        lines.append(IngredientLine(line=f"{measure} {name}".strip(), name=name, quantity=qty,
                                    quantityMax=qtyMax, unit=unit, note=note))
    return lines


def _tags(record):
    return [tag.strip() for tag in (record.get("strTags") or "").split(",") if tag.strip()]


def _checked(recipe):
    if not recipe.ingredients:
        raise Skipped("no ingredients")
    if not recipe.steps:
        raise Skipped("no steps")
    return recipe


def adaptMeal(raw, units):
    record = raw["record"]
    sourceId = str(record["idMeal"])
    return _checked(Recipe(
        source="mealdb", sourceId=sourceId, kind="food", title=" ".join(record["strMeal"].split()),
        ingredients=_ingredients(record, 20, units), steps=splitSteps(record.get("strInstructions")),
        sourceUrl=f"https://www.themealdb.com/meal/{sourceId}", licence="TheMealDB",
        credit="Recipe data and imagery: TheMealDB",
        imageUrl=record.get("strMealThumb") or None, imageCredit="TheMealDB",
        videoUrl=record.get("strYoutube") or None,
        hints={"category": record.get("strCategory"), "area": record.get("strArea"), "tags": _tags(record)}))


def adaptDrink(raw, units):
    record = raw["record"]
    sourceId = str(record["idDrink"])
    return _checked(Recipe(
        source="cocktaildb", sourceId=sourceId, kind="drink", title=" ".join(record["strDrink"].split()),
        ingredients=_ingredients(record, 15, units), steps=splitSteps(record.get("strInstructions")),
        sourceUrl=f"https://www.thecocktaildb.com/drink/{sourceId}", licence="TheCocktailDB",
        credit="Recipe data and imagery: TheCocktailDB",
        imageUrl=record.get("strDrinkThumb") or None, imageCredit="TheCocktailDB",
        videoUrl=record.get("strVideo") or None,
        alcohol=_ALCOHOL.get((record.get("strAlcoholic") or "").strip().lower()),
        glass=(record.get("strGlass") or "").strip() or None,
        hints={"category": record.get("strCategory"), "tags": _tags(record), "iba": record.get("strIBA")}))
