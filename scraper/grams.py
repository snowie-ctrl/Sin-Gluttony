"""
Grams for one ingredient line. Weights convert directly, pack sizes come from
the note, volumes go through an FDC portion of the same unit (or a density),
named units and counts go through FDC portions, and vague units have a fixed
guess. No rule fits: the line has no grams and the reason says why.
"""
import re

import quantity

_CONTAINERS = ("can", "jar", "package", "bottle")
_NAMED = ("clove", "slice", "stick", "head", "stalk", "sheet", "piece", "wedge")
_SIZES = ("extra large", "small", "medium", "large")        # "extra large" first: "large" is inside it
_PORTION_WORDS = {"cup": ("cup",), "tbsp": ("tbsp", "tablespoon"), "tsp": ("tsp", "teaspoon"),
                  "fl oz": ("fl oz",)}
_VOLUME_WORDS = ("cup", "tbsp", "tablespoon", "tsp", "teaspoon", "fl oz", "ml", "l", "pint", "quart", "gallon")
_NOT_A_COUNT = ("oz", "lb", "ounce", "pound", "serving")      # amount-1 portions that are not one piece
_NOTE_WEIGHT = re.compile(r"(\d+(?:\.\d+)?)\s*(g|kg|oz|lb|ml)\b")
_NUMBER = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
_COUNT_WEIGHT = re.compile(rf"({_NUMBER})(?:\s*(?:-|–|to)\s*({_NUMBER}))?\s*(kg|lbs|lb|oz|g)\b")
_EACH = re.compile(r"\W{0,3}each\b")
_SECOND_WEIGHT = re.compile(rf"\s*[/(]?\s*{_NUMBER}\s*(?:kg|lbs|lb|oz|g)\b\)?")
_EACH_BEFORE = re.compile(r"\beach\b[^\d]{0,15}$")
_MULTIPLIER = re.compile(r"[x\u00d7]\s*$")
_WEIGHT_UNITS = {"lbs": "lb"}


def _statedWeight(line, weights):
    """
    Grams a count's note states: "200g each" (or "each about 200g") times the count, any other weight
    ("~1.2kg") once. A second weight in another unit ("200g/7oz each") is skipped; a multiplier before
    the weight ("2 x 150g") makes it unreadable.
    """
    note = (line.note or "").lower()
    found = _COUNT_WEIGHT.search(note)
    if not found or _MULTIPLIER.search(note[:found.start()]):
        return None
    low = quantity.toNumber(found.group(1))
    high = quantity.toNumber(found.group(2)) if found.group(2) else None
    if low is None or (found.group(2) and high is None):
        return None
    number = low if high is None else (low + high) / 2
    grams = number * weights[_WEIGHT_UNITS.get(found.group(3), found.group(3))]
    end = found.end()
    second = _SECOND_WEIGHT.match(note, end)
    if second:
        end = second.end()
    each = _EACH.match(note, end) or _EACH_BEFORE.search(note[:found.start()])
    return grams * amountOf(line) if each else grams


def amountOf(line):
    """The midpoint of a range, otherwise the quantity; a unit with no number ("pinch of salt") is 1."""
    if line.quantity is None:
        return 1.0 if line.unit else None
    if line.quantityMax is not None:
        return (line.quantity + line.quantityMax) / 2
    return line.quantity


def _isNotACount(portion, weightUnits):
    unit = portion["unit"]
    return any(unit == word or unit.startswith((word + " ", word + ",")) for word in _VOLUME_WORDS + _NOT_A_COUNT + tuple(weightUnits))


def _portionStarting(food, words):
    """A portion named exactly by the word (or "word (...)") wins over a modified one like "cup, sifted"."""
    portions = (food or {}).get("portions", [])
    for portion in portions:
        if any(portion["unit"] == word or portion["unit"].startswith(word + " (") for word in words):
            return portion
    for portion in portions:
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
        stated = _statedWeight(line, densities["weight"])
        if stated is not None:
            return _round(stated)
        size = _sizeIn(line.note)
        chosen = _portionStarting(food, (size,)) if size else None
        for word in ("medium", "large", "whole"):
            if chosen:
                break
            chosen = _portionStarting(food, (word,))
        if not chosen:
            chosen = next((p for p in (food or {}).get("portions", [])
                           if p["amount"] == 1 and not _isNotACount(p, densities["weight"])), None)
        if chosen and chosen["amount"]:
            return _round(amount * chosen["grams"] / chosen["amount"])

    return None, "no-gram-rule"
