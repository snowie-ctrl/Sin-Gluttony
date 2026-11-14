"""
Lists the ingredients the dry-run recipes use most that have no FDC food yet,
with the rules' best guesses, to help curate rules/fdcMap.json. It reads the
page cache in data/raw/ and the foods cache in data/fdc/, prints ingredient
names, counts and FDC descriptions only, and writes nothing. Run by hand.

    python scripts/fdcCoverage.py                 # the 200 most used unmapped names
    python scripts/fdcCoverage.py --limit 50 --all   # mapped ones too, with their food
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adaptSites  # noqa: E402
import fdc  # noqa: E402
import fdcMatch  # noqa: E402
import matching  # noqa: E402
import rulesData  # noqa: E402
import tagging  # noqa: E402
from sources import sites  # noqa: E402


def ingredientCounts(rules):
    """How many non-optional lines name each matched ingredient, over every cached recipe."""
    recipes, _ = adaptSites.adaptCached(sites.loadSites(rules), rules)
    table = matching.IngredientTable.fromSeed(rules["ingredients"], set(rules["prepWords"]),
                                              set(rules["modifierWords"]))
    counts = Counter()
    for recipe in recipes:
        tagging.tagRecipe(recipe, table, rules)
        for line in recipe.ingredients:
            if line.ingredientId is not None and not line.optional:
                counts[table.rows[line.ingredientId]["name"]] += 1
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--candidates", type=int, default=3)
    parser.add_argument("--all", action="store_true", help="list mapped names too")
    args = parser.parse_args()
    rules = rulesData.load()
    foods = fdc.loadFoods()
    if not foods:
        sys.exit("no FDC foods: run `python fdc.py import` first")
    counts = ingredientCounts(rules)
    mapping = fdcMatch.mappingFor(list(counts), foods, rules, fdcMatch.loadPicks())
    total = sum(counts.values())
    mappedLines = sum(n for name, n in counts.items() if name in mapping)
    print(f"{len(mapping)} of {len(counts)} names mapped, covering {mappedLines} of {total} lines")
    shown = 0
    for name, n in counts.most_common():
        if shown >= args.limit:
            break
        if name in mapping and not args.all:
            continue
        shown += 1
        if name in mapping:
            print(f"{n:6}  {name}  ->  {mapping[name]} {foods[mapping[name]]['description']}")
            continue
        print(f"{n:6}  {name}")
        for c in fdcMatch.candidates(name, foods, limit=args.candidates):
            print(f"          {c['score']:6}  {c['fdcId']}  {c['description']}")


if __name__ == "__main__":
    main()
