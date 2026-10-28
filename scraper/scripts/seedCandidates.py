"""
Helps grow rules/ingredients.json from the last pass's data/normalised.jsonl:
how many ingredient lines and recipes the table covers, the unknown names that
block the most recipes, and an allergen audit of the seed. Run by hand while
curating; the scraper never runs it.

    .venv/Scripts/python.exe scripts/seedCandidates.py [--limit 300] [--audit] [--cocktail-ingredients]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import report  # noqa: E402
import rulesData  # noqa: E402
from models import Recipe  # noqa: E402

# (item, words that suggest it, words that look like it but aren't). Matched on the name and each alias.
AUDIT = [
    ("dairy", r"\b(milk|cheese|butter|cream|yogh?urt|ghee|whey|custard|paneer|ricotta|mascarpone|brie|feta|cheddar|"
              r"parmesan|mozzarella|buttermilk|kefir|quark)\b",
     r"\b(coconut|almond|oat|soy|soya|rice|cashew|peanut|cocoa|nut|seed|apple) (milk|cream|butter)\b|\bbutternut\b|"
     r"\bbutter bean|\bcream of tartar\b|\bice cream\b"),
    ("gluten", r"\b(flour|bread|pasta|noodle|couscous|bulgur|semolina|barley|rye|beer|ale|lager|soy sauce|seitan|"
               r"cracker|biscuit|tortilla|pita|spaghetti|macaroni|crouton|breadcrumb|panko|wheat|malt)\b",
     r"\b(rice|corn|gluten free|almond|coconut|chickpea|gram|buckwheat|tapioca|potato|cassava) "
     r"(flour|noodle|pasta|bread|tortilla)\b|\bcornflour\b|\bcorn tortilla\b"),
    ("egg", r"\b(egg|mayonnaise|mayo|meringue|aioli)\b", r"\beggplant\b"),
    ("tree-nut", r"\b(almond|walnut|pecan|cashew|pistachio|hazelnut|macadamia|brazil nut|pine nut|praline|marzipan|"
                 r"amaretto|frangelico|nutella)\b", None),
    ("peanut", r"\bpeanut", None),
    ("shellfish", r"\b(shrimp|prawn|crab|lobster|crayfish|scallop|mussel|clam|oyster)\b", r"\boyster mushroom\b"),
    ("fish", r"\b(fish|anchov|salmon|tuna|cod|haddock|sardine|mackerel|trout|tilapia|halibut|worcestershire)",
     r"\bfish sauce free\b"),
    ("sesame", r"\b(sesame|tahini|halva)", None),
    ("soy", r"\b(soy|soya|tofu|tempeh|miso|edamame|tamari)\b", None),
    ("meat", r"\b(beef|pork|bacon|ham|lamb|mutton|veal|venison|sausage|salami|chorizo|prosciutto|pancetta|gelatin|"
             r"gelatine|lard|suet)\b", r"\b(vegetarian|vegan|plant based) "),
    ("poultry", r"\b(chicken|turkey|duck|goose|quail)\b", None),
    ("alcohol", r"\b(vodka|gin|rum|tequila|whisk(e)?y|bourbon|brandy|cognac|wine|beer|liqueur|vermouth|schnapps|sake|"
                r"sherry|champagne|prosecco|cider|bitters|kahlua|baileys|amaretto|mezcal|absinthe|grappa|ouzo)\b",
     r"\b(wine|cider|sherry|rice wine) vinegar\b|\b(rum|brandy) extract\b|\bnon alcoholic\b"),
    ("honey", r"\bhoney\b", r"\bhoneydew\b"),
]


def _contains(entry, byName):
    items, seen = set(), set()
    while entry and entry["name"] not in seen:
        seen.add(entry["name"])
        items |= set(entry.get("contains", []))
        entry = byName.get(entry.get("parent"))
    return items


def audit(seed):
    byName = {e["name"]: e for e in seed}
    findings = []
    for entry in seed:
        has = _contains(entry, byName)
        for item, suggests, except_ in AUDIT:
            if item in has:
                continue
            for text in [entry["name"], *entry.get("aliases", [])]:
                lower = text.lower()
                if re.search(suggests, lower) and not (except_ and re.search(except_, lower)):
                    findings.append((entry["name"], item, text))
                    break
    return findings


def coverage(recipes):
    lines = sum(len(r.ingredients) for r in recipes)
    matched = sum(1 for r in recipes for line in r.ingredients if line.ingredientId)
    complete = sum(1 for r in recipes if r.facts and r.facts["complete"])
    return {"lines": lines, "matched": matched, "recipes": len(recipes), "complete": complete}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--cocktail-ingredients", action="store_true")
    args = parser.parse_args(argv)
    rules = rulesData.load()
    if args.audit:
        accepted = {(a["name"], a["item"]) for a in rules["auditAccepted"]}
        for name, item, text in audit(rules["ingredients"]):
            mark = "accepted" if (name, item) in accepted else "REVIEW"
            print(f"{mark:9} {name!r} may contain {item} (from {text!r})")
        return 0
    if args.cocktail_ingredients:
        from sources import thedb
        for record in thedb.cocktailIngredients():
            print(json.dumps({k: record.get(k) for k in ("strIngredient", "strType", "strAlcohol", "strABV")}))
        return 0
    recipes = [Recipe.fromDict(json.loads(line)) for line in
               config.NORMALISED_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    c = coverage(recipes)
    print(f"lines matched {c['matched']}/{c['lines']} ({c['matched'] / max(c['lines'], 1):.1%}); "
          f"recipes complete {c['complete']}/{c['recipes']} ({c['complete'] / max(c['recipes'], 1):.1%})")
    for row in report.unknownIngredients(recipes, args.limit):
        print(f"{row['recipes']:5}  {row['name']:40}  {row['example']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
