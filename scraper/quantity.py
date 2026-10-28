"""
Reads the amount at the front of an ingredient line: "1 1/2 cups flour,
sifted" becomes 1.5, cup, "flour" and the note "sifted". Sources write amounts
every way people do (fractions, ½, ranges, "200g", "to taste"); the app only
needs a clean name to match and an amount to show.
"""
import re

from models import IngredientLine

FRACTIONS = {"½": 1 / 2, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 1 / 4, "¾": 3 / 4, "⅕": 1 / 5,
             "⅛": 1 / 8, "⅜": 3 / 8, "⅝": 5 / 8, "⅞": 7 / 8}
_FR = "".join(FRACTIONS)
NUMBER = rf"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?\s?[{_FR}]?|[{_FR}])"
_AMOUNT = re.compile(rf"^\s*({NUMBER})(?:\s*(?:-|–|—|to)\s*({NUMBER}))?(?![\d/])\s*", re.IGNORECASE)
_OPTIONAL = re.compile(r"\(\s*optional\s*\)|,?\s*\boptional\b", re.IGNORECASE)
_TO_TASTE = re.compile(r",?\s*\b(to taste|as needed|as required)\b", re.IGNORECASE)
_BRACKETS = re.compile(r"\(([^)]*)\)")
_DANGLING = re.compile(r"\s+(?:or|and)$", re.IGNORECASE)    # "salt or to taste" once "to taste" is a note
_FOR_USE = re.compile(r"^(\S.*?)\s+(for\s+\S.*)$", re.IGNORECASE)


_THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+")


def toNumber(text):
    """1, 1.5, 1,5, 1,000, 1/2, 1 1/2, ½, 1½ and 1 ½ as a float (3 decimals); None when it can't be a number."""
    total = 0.0
    for part in text.strip().split():
        if _THOUSANDS.fullmatch(part):
            part = part.replace(",", "")          # "1,000" is a thousand, not one and a bit
        else:
            part = part.replace(",", ".")
        if part in FRACTIONS:
            total += FRACTIONS[part]
        elif part[-1] in FRACTIONS:
            total += float(part[:-1]) + FRACTIONS[part[-1]]
        elif "/" in part:
            top, bottom = part.split("/", 1)
            if float(bottom) == 0:
                return None
            total += float(top) / float(bottom)
        else:
            total += float(part)
    return round(total, 3)


def unitMap(units):
    """{"tablespoons": "tbsp", "tbsp": "tbsp", ...} from rules/units.json's {canonical: [aliases]}."""
    return {alias.lower(): canonical for canonical, aliases in units.items() for alias in [canonical, *aliases]}


def _takeUnit(text, units):
    words = text.split()
    for size in (2, 1):
        if len(words) >= size:
            candidate = " ".join(words[:size]).lower().rstrip(".")
            if candidate in units:
                rest = words[size:]
                if rest and rest[0].lower() == "of":
                    rest = rest[1:]
                return units[candidate], " ".join(rest)
    return None, text


def parseAmount(text, units):
    """(quantity, quantityMax, unit, the rest of the text)."""
    match = _AMOUNT.match(text)
    if not match:
        unit, rest = _takeUnit(text, units)          # "pinch of salt" has a unit and no number
        return None, None, unit, rest
    qty = toNumber(match.group(1))
    qtyMax = toNumber(match.group(2)) if match.group(2) else None
    unit, rest = _takeUnit(text[match.end():], units)
    return qty, qtyMax, unit, rest


def parseLine(text, units):
    """A free-text ingredient line (Wikibooks) as an IngredientLine."""
    original = " ".join(text.split())
    work = original
    optional = bool(_OPTIONAL.search(work))
    work = _OPTIONAL.sub("", work)
    notes = []
    taste = _TO_TASTE.search(work)
    if taste:
        notes.append(taste.group(1).lower())
        work = _TO_TASTE.sub("", work)
    # Brackets first: "1 (14 oz) can tomatoes" must still find "can" after the amount.
    notes += [inner.strip() for inner in _BRACKETS.findall(work) if inner.strip()]
    work = _BRACKETS.sub(" ", work)
    qty, qtyMax, unit, work = parseAmount(work, units)
    if "," in work:
        work, after = work.split(",", 1)
        if after.strip():
            notes.append(after.strip())
    name = _DANGLING.sub("", " ".join(work.split()).strip(" -–:;."))
    use = _FOR_USE.match(name)
    if use:                                          # "oil for deep frying": the use is a note
        name = use.group(1)
        notes.append(use.group(2))
    return IngredientLine(line=original, name=name, quantity=qty, quantityMax=qtyMax, unit=unit,
                          note="; ".join(notes) or None, optional=optional)


def parseMeasure(measure, units):
    """TheMealDB/TheCocktailDB keep the measure apart from the ingredient: (quantity, quantityMax, unit, note)."""
    text = " ".join((measure or "").split())
    if not text:
        return None, None, None, None
    qty, qtyMax, unit, rest = parseAmount(text, units)
    return qty, qtyMax, unit, (rest.strip() or None)
