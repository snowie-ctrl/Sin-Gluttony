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
_PRICE = re.compile(r",?\s*\$\s*\d+(?:[.,]\d+)?\s*\*?")                   # Budget Bytes' "($0.32)", "(with juices, $2.12*)"
_GLUED_SLASH = re.compile(r"(?<=[^\W\d_])/(?=\s*\d)")                  # "200g/7oz" -> "200g / 7oz"
_ALT = re.compile(rf"^/\s*({NUMBER}(?:\s*(?:-|–|—|to)\s*{NUMBER})?)\s*", re.IGNORECASE)              # "/ 7oz": the same amount in other units
_PLUS = re.compile(rf"^(?:\+|plus)\s*({NUMBER})\s*", re.IGNORECASE)    # "+ 2 tbsp": a second amount added on
_TIMES = re.compile(rf"^[x×]\s*({NUMBER})\s*", re.IGNORECASE)          # "x 400g": packs of a size
_SIZED_PACK = re.compile(rf"^({NUMBER})\s*-?\s*", re.IGNORECASE)      # "15-ounce can", "15oz. can", "14.5 oz. cans"
_ABBREVIATION = re.compile(r"\b(tsp|tbsp|tbs|oz|lbs?)\.(?=[^\W\d_])", re.IGNORECASE)   # "tsp.salt"
_PART_OF = re.compile(rf"^((?:finely\s+grated\s+)?(?:zest\s+and\s+juice|juice\s+and\s+zest|zest|juice))\s+of\s+"
                      rf"(?=(?:{NUMBER}|an?\s))", re.IGNORECASE)
_LEAD = re.compile(rf"^(heaping|heaped|scant|rounded|level|about|approx\.?|approximately|around)\s+(?={NUMBER})",
                   re.IGNORECASE)                                            # "heaping 1/2 cup", "about 2 cups"
_EXTRA = re.compile(r"^(.*?)\s+((?:plus|\+|approx\.?|approximately|about|around)\s+\d.*)$", re.IGNORECASE)
_TOP_UP =re.compile(r"^top(?:\s+up)?\s+with\s+", re.IGNORECASE)
_ARTICLE = re.compile(r"^an?\s+", re.IGNORECASE)
_SIZE = re.compile(r"^(small|medium|large|big|generous|good)\s+", re.IGNORECASE)


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


def _pack(rest, units):
    """'x 400g cans tomatoes' -> ('400g', 'can', 'tomatoes'): N packs of a size; the size becomes a note.
    '15-ounce can beans' and '14.5 oz. cans tomatoes' read the same way, but only with a container after the size."""
    times = _TIMES.match(rest)
    sized = None if times else _SIZED_PACK.match(rest)
    start = times or sized
    if not start:
        return None
    sizeUnit, after = _takeUnit(rest[start.end():], units)
    if sizeUnit is None:
        return None
    size = rest[start.start(1): len(rest) - len(after)].strip()
    alternative, after = _alternative(after, units)         # "3 x 400g / 14oz cans": the size in both measures
    if alternative:
        size = f"{size} / {alternative}"
    packUnit, name = _takeUnit(after, units)
    if sized and packUnit is None:
        return None
    return size, packUnit, name


def _alternative(rest, units):
    """'/ 7oz plain flour' -> ('7oz', 'plain flour'): the second measure a site gives, kept as a note."""
    alt = _ALT.match(rest) or _PLUS.match(rest)
    if not alt:
        return None, rest
    unit, after = _takeUnit(rest[alt.end():], units)
    if unit is None:
        return None, rest
    return rest[: len(rest) - len(after)].lstrip("/ ").strip(), after


def _article(work, units):
    """'a pinch of salt' -> '1 pinch of salt': an article before a unit is one of it."""
    article = _ARTICLE.match(work)
    if not article:
        return work
    rest = work[article.end():]
    size = _SIZE.match(rest)
    unit, _ = _takeUnit(rest[size.end():] if size else rest, units)
    return f"1 {rest}" if unit else work


def _sized(work, units):
    """'small bunch mint' -> ('bunch', 'mint', 'small'); anything else unchanged."""
    size = _SIZE.match(work)
    if size:
        unit, rest = _takeUnit(work[size.end():], units)
        if unit:
            return unit, rest, size.group(1).lower()
    return None, work, None


def parseLine(text, units):
    """A free-text ingredient line (Wikibooks, the recipe sites) as an IngredientLine."""
    original = " ".join(text.split())
    work = _PRICE.sub(" ", original.replace("⁄", "/"))      # the fraction slash some recipe cards use
    work = _ABBREVIATION.sub(r"\1. ", work)
    optional = bool(_OPTIONAL.search(work))
    work = _OPTIONAL.sub("", work)
    notes = []
    taste = _TO_TASTE.search(work)
    if taste:
        notes.append(taste.group(1).lower())
        work = _TO_TASTE.sub("", work)
    # Brackets first: "1 (14 oz) can tomatoes" must still find "can" after the amount.
    notes += [inner.strip() for inner in _BRACKETS.findall(work) if inner.strip()]
    work = " ".join(_BRACKETS.sub(" ", work).split())
    part = _PART_OF.match(work)
    if part:                                         # "juice of 1 lemon": a lemon, used for its juice
        notes.append(part.group(1).lower())
        work = work[part.end():]
        work = _ARTICLE.sub("1 ", work, count=1)     # "juice of a lemon": one lemon
    topUp = _TOP_UP.match(work)
    if topUp:                                        # "top up with soda water"
        notes.append("to top up")
        work = work[topUp.end():]
    lead = _LEAD.match(work)
    if lead:
        notes.append(lead.group(1).lower())
        work = work[lead.end():]
    work = _article(_GLUED_SLASH.sub(" / ", work), units)
    qty, qtyMax, unit, work = parseAmount(work, units)
    if unit is None and qty is not None:
        packed = _pack(work, units)
        if packed:
            size, unit, work = packed
            notes.append(size)
    if unit is not None:
        alternative, work = _alternative(work, units)
        if alternative:
            notes.append(alternative)
    else:
        unit, work, size = _sized(work, units)
        if size:
            notes.append(size)
    if "," in work:
        work, after = work.split(",", 1)
        if after.strip():
            notes.append(after.strip())
    extra = _EXTRA.match(" ".join(work.split()))
    if extra and qty is not None:                    # "butter plus 1 tbsp melted", "chicken approx 1.2kg"
        work = extra.group(1)
        notes.append(extra.group(2))
    name = _DANGLING.sub("", " ".join(work.split()).strip(" -–:;."))
    use =_FOR_USE.match(name)
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
