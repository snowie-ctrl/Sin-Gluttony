"""
Difford's Guide cocktails. The page's schema.org Recipe gives the title,
description, time, yield, ingredients, steps and picture; the glass and the
garnish are read from the page's own text ("Serve in a Coupe glass",
"Garnish: ..."); the method (shaken, stirred, built, blended, thrown) comes
from the steps by the keyword rules in rules/drinkMethods.json. Difford's
gives no nutrition: milestone 2 estimates it.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from models import Recipe, Skipped
from sources import schemaOrg, schemaSite

_SERVE_IN = re.compile(r"^serve\s+in\s+(?:an?\s+)?", re.IGNORECASE)
# The real pages put "Glass" as a heading whose next block is only a photo caption ("Photographed in a ... Coupe"),
# and name the glass in the method's first step, upper-cased and sometimes with a size: "Select and pre-chill a
# HIGHBALL (MAX 10OZ/300ML) GLASS."
_PRE_CHILL = re.compile(r"^select\s+and\s+pre-?chill\s+(?:an?\s+)?([^.]+)", re.IGNORECASE)
# the method also has "Prepare garnish of lemon zest twist.": the garnish alone, where the "Garnish" heading is
# followed by a sentence ("Garnish with lime wedge on rim", "EXPRESS lemon zest twist over the cocktail ...")
_PREPARE_GARNISH = re.compile(r"^prepare\s+garnish\s+of\s+([^.]+)", re.IGNORECASE)
# a bare "Glass" with no colon is just a word on the page; only "Garnish" may take the next block as its value
_LABEL = re.compile(r"^(glass\s*:|garnish\s*:|garnish(?=$))\s*(.*)$", re.IGNORECASE)


class _Blocks(HTMLParser):
    """The page's visible text, one entry per block element; scripts and styles are left out."""
    BLOCK = {"p", "div", "section", "article", "header", "footer", "li", "ul", "ol", "dt", "dd", "td", "th", "tr",
             "h1", "h2", "h3", "h4", "h5", "h6", "br"}
    HIDDEN = {"script", "style", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self._parts, self._hidden = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self._hidden += 1
        elif tag in self.BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.HIDDEN:
            self._hidden = max(0, self._hidden - 1)
        elif tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self._hidden:
            self._parts.append(data)

    def _flush(self):
        text = " ".join("".join(self._parts).split())
        if text:
            self.blocks.append(text)
        self._parts = []

    def close(self):
        super().close()
        self._flush()


def textBlocks(html):
    parser = _Blocks()
    parser.feed(html)
    parser.close()
    return parser.blocks


def _value(text):
    text = _SERVE_IN.sub("", text or "").strip().rstrip(".").strip()
    return text if 0 < len(text) <= 80 else None


def _bare(block):
    """The block without bracketed sizes: 'HIGHBALL (MAX 10OZ/300ML) GLASS.' -> 'HIGHBALL GLASS.'."""
    return " ".join(re.sub(r"\([^)]*\)", " ", block).split())


def _preChilled(block):
    """'Select and pre-chill a HIGHBALL (MAX 10OZ/300ML) GLASS.' -> 'Highball glass'. None for any other block,
    and for a pre-chill step that names no glass ("Select and pre-chill the shaker")."""
    match = _PRE_CHILL.match(_bare(block))
    value = match.group(1).strip() if match else ""
    if not value or len(value) > 40 or "glass" not in value.lower():
        return None
    return value[0].upper() + value[1:].lower() if value.isupper() else value


def _garnishFrom(value):
    """The fallback garnish sentence reduced to the garnish: 'Garnish with lime wedge on rim' -> 'lime wedge on rim';
    'Serve naked, without garnish' is no garnish at all."""
    if not value or re.search(r"\b(?:without|no)\s+garnish\b|\bnaked\b", value, re.IGNORECASE):
        return None
    with_ = re.match(r"^garnish\b.*?\bwith\s+(.+)$", value, re.IGNORECASE)
    return with_.group(1).strip() if with_ else value


def _preparedGarnish(block):
    match = _PREPARE_GARNISH.match(block)
    return _value(match.group(1)) if match else None


def glassAndGarnish(html):
    """(glass, garnish) from "Serve in a Coupe glass" and "Garnish:" / "Glass:" labels, the value beside or after.
    Without those, the glass is the one the first method step pre-chills."""
    glass = garnish = None
    blocks = textBlocks(html)
    preChilled = next(filter(None, map(_preChilled, blocks)), None)
    prepared = next(filter(None, map(_preparedGarnish, blocks)), None)
    for n, block in enumerate(blocks):
        if _SERVE_IN.match(block):
            value = _value(block)
            glass = glass or (value if value and "glass" in value.lower() else None)
            continue
        label = _LABEL.match(block)
        if not label:
            continue
        value = _value(label.group(2) or (blocks[n + 1] if n + 1 < len(blocks) else ""))
        if label.group(1).lower().startswith("glass"):
            glass = glass or value
        else:
            garnish = garnish or _garnishFrom(value)
    return glass or preChilled, prepared or garnish


def methodFor(steps, methods):
    text = " ".join(step.text.lower() for step in steps)
    for method in methods["order"]:
        if any(re.search(rf"\b{re.escape(word)}", text) for word in methods["words"][method]):
            return method
    return None


def extractDifford(html, url, site, units, rules):
    data = schemaOrg.recipeJsonLd(html)
    if data is None:
        raise Skipped("no recipe on the page")
    title = schemaOrg.clean(data.get("name"))
    if not title:
        raise Skipped("no title")
    ingredients = schemaSite.linesFrom(data.get("recipeIngredient") or [], units)
    if not ingredients:
        raise Skipped("no ingredients")
    steps = schemaOrg.stepsOf(data.get("recipeInstructions"))
    if not steps:
        raise Skipped("no steps")
    glass, garnish = glassAndGarnish(html)
    for line in schemaSite.linesFrom([garnish] if garnish else [], units, "Garnish"):
        line.optional = True        # spec §2.4: the garnish is marked optional (facts still count it)
        ingredients.append(line)
    methods = rules["drinkMethods"]
    method = methodFor(steps, methods)
    total = schemaOrg.isoMinutes(data.get("totalTime"))
    timeFrom = "source" if total else None
    if not total and method in methods["minutes"]:
        total, timeFrom = methods["minutes"][method], "rule"
    servings, pieces = schemaOrg.yieldOf(data.get("recipeYield"))
    servingsFrom = ("yield" if pieces else "source") if servings else "rule"
    image = schemaOrg.bestImage(html, data)
    return Recipe(
        source=site["site"], sourceId=schemaSite.sourceIdFor(url), kind=site["kind"], title=title,
        ingredients=ingredients, steps=steps, sourceUrl=url, licence=schemaSite.LICENCE, credit=site["name"],
        imageUrl=urljoin(url, image) if image else None, imageCredit=site["name"],
        servings=servings or 1, servingsFrom=servingsFrom, totalMinutes=total, timeFrom=timeFrom, glass=glass,
        description=schemaOrg.clean(data.get("description")) or None,
        nutrition=schemaOrg.nutritionOf(data.get("nutrition")),
        hints={"method": method, "category": schemaOrg.joined(data.get("recipeCategory")),
               "tags": schemaOrg.keywordsOf(data.get("keywords"))})
