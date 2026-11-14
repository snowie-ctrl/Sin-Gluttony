"""
Grams for one ingredient line. Weights convert directly, pack sizes come from
the note, volumes go through an FDC portion of the same unit (or a density),
named units and counts go through FDC portions, and vague units have a fixed
guess. No rule fits: the line has no grams and the reason says why.
"""
import re

_CONTAINERS = ("can", "jar", "package", "bottle")
_NAMED = ("clove", "slice", "stick", "head", "stalk", "sheet", "piece", "wedge")
_SIZES = ("extra large", "small", "medium", "large")        # "extra large" first: "large" is inside it
_PORTION_WORDS = {"cup": ("cup",), "tbsp": ("tbsp", "tablespoon"), "tsp": ("tsp", "teaspoon"),
                  "fl oz": ("fl oz",)}
_VOLUME_WORDS = ("cup", "tbsp", "tablespoon", "tsp", "teaspoon", "fl oz", "ml", "l", "pint", "quart", "gallon")
_NOTE_WEIGHT = re.compile(r"(\d+(?:\.\d+)?)\s*(g|kg|oz|lb|ml)\b")


def amountOf(line):
    """The midpoint of a range, otherwise the quantity; a unit with no number ("pinch of salt") is 1."""
    if line.quantity is None:
        return 1.0 if line.unit else None
    if line.quantityMax is not None:
        return (line.quantity + line.quantityMax) / 2
    return line.quantity


def _isVolumePortion(portion):
    unit = portion["unit"]
    return any(unit == word or unit.startswith((word + " ", word + ",")) for word in _VOLUME_WORDS)


def _portionStarting(food, words):
    for portion in (food or {}).get("portions", []):
        if any(portion["unit"].startswith(word) for word in words):
            return portion
    return None


def _sizeIn(note):
    text = (note or "").lower()
    for size in _SIZES:
        if re.search(r"\b" + size + r"\b", text):
            return size
    return None


def _density(name, mlDensity):
    key = (name or "").lower()
    best = max((k for k in mlDensity if k != "default" and k in key), key=len, default="default")
    return mlDensity[best]


def _round(value):
    return round(value, 1), None


def gramsOf(line, food, densities, measures=None, ingredientName=None):
    """(grams, None), or (None, "no-amount" | "no-gram-rule")."""
    amount = amountOf(line)
    if amount is None:
        return None, "no-amount"
    unit = line.unit

    if unit in densities["weight"]:
        return _round(amount * densities["weight"][unit])

    if unit in _CONTAINERS:
        found = _NOTE_WEIGHT.search(line.note or "")
        if found:
            kind = found.group(2)
            return _round(amount * float(found.group(1)) * densities["weight"].get(kind, 1))  # ml read as grams

    if unit in densities["volumeMl"]:
        perUnit = (measures or {}).get(unit, densities["volumeMl"][unit])
        ml = amount * perUnit
        portion = _portionStarting(food, _PORTION_WORDS[unit]) if unit in _PORTION_WORDS else None
        if portion and portion["amount"]:
            return _round(ml * portion["grams"] / (portion["amount"] * densities["volumeMl"][unit]))
        if food and "mlDensity" in food:
            return _round(ml * food["mlDensity"])
        return _round(ml * _density(ingredientName or line.name, densities["mlDensity"]))

    if unit in _NAMED:
        portion = _portionStarting(food, (unit,))
        if portion and portion["amount"]:
            return _round(amount * portion["grams"] / portion["amount"])

    if unit in densities["vagueGrams"]:
        return _round(amount * densities["vagueGrams"][unit])

    if not unit:
        size = _sizeIn(line.note)
        chosen = _portionStarting(food, (size,)) if size else None
        for word in ("medium", "large", "whole"):
            if chosen:
                break
            chosen = _portionStarting(food, (word,))
        if not chosen:
            chosen = next((p for p in (food or {}).get("portions", [])
                           if p["amount"] == 1 and not _isVolumePortion(p)), None)
        if chosen and chosen["amount"]:
            return _round(amount * chosen["grams"] / chosen["amount"])

    return None, "no-gram-rule"
