"""
Wikibooks Cookbook pages into the one recipe shape. A page is wikitext: a
{{recipe summary}} box (servings, time, difficulty 1-5, cuisine, image), an
Ingredients section of bullets and a Procedure section of numbered steps.
Text is cleaned to plain words: links become their words, {{convert}} its
amount, and every other template, tag and entity goes.
"""
import html
import re
from urllib.parse import quote

import mwparserfromhell as mwp

import config
import quantity
from models import Recipe, Skipped, Step
from sources import wikiImages

_INGREDIENTS = re.compile(r"ingredient", re.IGNORECASE)
_STEPS = re.compile(r"procedure|method|directions|preparation|instructions|steps", re.IGNORECASE)
_DRINK = re.compile(r"(beverage|drink|cocktail|smoothie|punch|tea|coffee) recipes", re.IGNORECASE)
_CATEGORY = re.compile(r"\[\[\s*category\s*:\s*([^\]|]+)", re.IGNORECASE)
_SUB_HEADING = re.compile(r"^(={3,})\s*(.*?)\s*\1$")
_LIST_LINE = re.compile(r"^([*#]+)\s*(.*)$")
_SUMMARY = {"recipe summary", "recipesummary", "recipe_summary"}
_TOPIC = {"cookdp"}


def _unprefix(text):
    # A link with no display text renders as its target, "Cookbook:Salt".
    return re.sub(r"\bCookbook:", "", text)


def clean(wikitext):
    code = mwp.parse(re.sub(r"<br\s*/?>", " ", wikitext, flags=re.IGNORECASE))
    for tag in code.filter_tags(recursive=True):
        if str(tag.tag).lower() == "ref":
            try:
                code.remove(tag)
            except ValueError:
                pass
    for template in code.filter_templates(recursive=False):
        name = str(template.name).strip().lower()
        if name in ("convert", "cvt") and template.params:
            code.replace(template, " ".join(str(p.value).strip() for p in template.params[:2]))
        else:
            code.remove(template)
    text = html.unescape(code.strip_code(normalize=True, collapse=True))
    return " ".join(_unprefix(text).split())


def _firstInt(text):
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None


def _items(section):
    """(marker, text, group) for each list line of a section; sub-headings and ; lines become groups."""
    group = None
    items = []
    for raw in str(section).splitlines()[1:]:       # the first line is the section's own heading
        line = raw.strip()
        if not line:
            continue
        heading = _SUB_HEADING.match(line)
        if heading:
            group = clean(heading.group(2)) or None
            continue
        if line.startswith(";"):
            group = clean(line.lstrip(";")) or None
            continue
        listed = _LIST_LINE.match(line)
        if listed:
            text = clean(listed.group(2))
            if text:
                items.append((listed.group(1)[0], text, group))
    return items


def adaptPage(raw, units):
    title = raw["sourceId"]
    text = raw["wikitext"]
    code = mwp.parse(text)
    templates = code.filter_templates()
    if {str(t.name).strip().lower() for t in templates} & _TOPIC:
        raise Skipped("topic page")
    summary = next((t for t in templates if str(t.name).strip().lower() in _SUMMARY), None)

    def field(name):
        if summary is None or not summary.has(name):
            return None
        return clean(str(summary.get(name).value)) or None

    ingredients, steps = [], []
    for section in code.get_sections(levels=[2]):
        headings = section.filter_headings(recursive=False)
        if not headings:
            continue
        heading = headings[0].title.strip_code().strip()
        if _INGREDIENTS.search(heading) and not ingredients:
            for _, line, group in _items(section):
                item = quantity.parseLine(line, units)
                item.group = group
                ingredients.append(item)
        elif _STEPS.search(heading) and not steps:
            items = _items(section)
            numbered = [item for item in items if item[0] == "#"]
            steps = [Step(text=t, group=g) for _, t, g in (numbered or items)]
    if not ingredients:
        raise Skipped("no ingredients")
    if not steps:
        raise Skipped("no steps")

    categories = [c.strip() for c in _CATEGORY.findall(text)]
    if field("Category"):
        categories.append(field("Category"))
    name = field("Name") or title.split(":", 1)[-1].replace("_", " ")
    servings = _firstInt(field("Servings") or field("Yield"))
    servings = servings if servings is not None and 1 <= servings <= 100 else None
    rating = _firstInt(field("Difficulty"))
    imageField = str(summary.get("Image").value) if summary is not None and summary.has("Image") else None
    return Recipe(
        source="wikibooks", sourceId=title, kind="drink" if any(_DRINK.search(c) for c in categories) else "food",
        title=name, ingredients=ingredients, steps=steps,
        sourceUrl=config.WIKIBOOKS_PAGE_BASE + quote(title.replace(" ", "_"), safe=":"),
        licence="CC BY-SA 4.0",
        credit=f'From the Wikibooks Cookbook page "{name}" by its contributors, CC BY-SA 4.0',
        servings=servings, servingsFrom="source" if servings else None,
        hints={"categories": categories, "timeText": field("Time"),
               "difficultyRating": rating if rating and 1 <= rating <= 5 else None,
               "cuisineText": field("Cuisine") or field("Origin"),
               "imageFile": wikiImages.fileName(imageField)})
