"""
The meal sites (and any later schema.org site): recipe-scrapers reads the
page's schema.org Recipe and the site's recipe card, and this turns its answer
into Gluttony's recipe shape. A field the page lacks stays None: the gate, not
the extractor, decides what that costs the recipe.
"""
import hashlib
import re
from urllib.parse import urljoin

from recipe_scrapers import scrape_html

import quantity
from models import Recipe, Skipped, Step
from sources import schemaOrg

LICENCE = "personal use"
_HEADING = re.compile(r"^[^\d½¼¾⅓⅔]{1,50}:$")    # "For the dressing:" written as an ingredient line


def _safe(read):
    """recipe-scrapers raises for a field a page lacks: that is None here."""
    try:
        value = read()
    except Exception:   # its exception types vary by field and version; a missing field is never fatal
        return None
    return None if value in ("", [], {}) else value


def sourceIdFor(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def linesFrom(texts, units, group=None):
    """Ingredient lines; a line that is only a heading ("For the dressing:") heads the lines after it."""
    lines = []
    for text in texts:
        text = schemaOrg.clean(text)
        if not text:
            continue
        if _HEADING.match(text):
            group = text.rstrip(":").strip()
            continue
        line = quantity.parseLine(text, units)
        line.group = group
        lines.append(line)
    return lines


def ingredientLines(scraper, units):
    """The lines with the recipe card's group headings when the site groups them, else the plain list."""
    groups = [g for g in (_safe(scraper.ingredient_groups) or []) if getattr(g, "ingredients", None)]
    if len(groups) > 1 or (groups and groups[0].purpose):
        lines = []
        for g in groups:
            lines += linesFrom(g.ingredients, units, schemaOrg.clean(g.purpose) or None)
        return lines
    return linesFrom(_safe(scraper.ingredients) or [], units)


def _minutes(read):
    return schemaOrg.isoMinutes(_safe(read))


def extractSchema(html, url, site, units):
    try:
        scraper = scrape_html(html, org_url=url, supported_only=False)
    except Exception as e:      # no schema at all, or a page recipe-scrapers cannot open
        raise Skipped("no recipe on the page") from e
    title = schemaOrg.clean(_safe(scraper.title))
    if not title:
        raise Skipped("no title")
    ingredients = ingredientLines(scraper, units)
    if not ingredients:
        raise Skipped("no ingredients")
    steps = [Step(text=schemaOrg.clean(t)) for t in (_safe(scraper.instructions_list) or []) if schemaOrg.clean(t)]
    if not steps:
        raise Skipped("no steps")
    prep, cook = _minutes(scraper.prep_time), _minutes(scraper.cook_time)
    total = _minutes(scraper.total_time) or (prep + cook if prep and cook else None)
    servings, pieces = schemaOrg.yieldOf(_safe(scraper.yields))
    image = schemaOrg.bestImage(html, schemaOrg.recipeJsonLd(html)) or schemaOrg.imageOf(_safe(scraper.image))
    return Recipe(
        source=site["site"], sourceId=sourceIdFor(url), kind=site["kind"], title=title,
        ingredients=ingredients, steps=steps, sourceUrl=url, licence=LICENCE, credit=site["name"],
        imageUrl=urljoin(url, image) if image else None, imageCredit=site["name"],
        servings=servings, servingsFrom=("yield" if pieces else "source") if servings else None,
        prepMinutes=prep, cookMinutes=cook, totalMinutes=total, timeFrom="source" if total else None,
        description=schemaOrg.clean(_safe(scraper.description)) or None,
        nutrition=schemaOrg.nutritionOf(_safe(scraper.nutrients)),
        hints={"category": schemaOrg.joined(_safe(scraper.category)),
               "cuisineText": schemaOrg.joined(_safe(scraper.cuisine)),
               "tags": schemaOrg.keywordsOf(_safe(scraper.keywords))})
