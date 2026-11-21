"""
Counts the glossary's candidate terms (rules/glossarySeed.json: cooking techniques and British/American kitchen
words) across the shown recipes' steps and ingredient lines, the most used first, to choose which terms
app/assets/glossary.json writes up (spec 2026-11-19 part 3, 3.1). It reads data/normalised.jsonl, which the last
pass wrote from the page cache, and prints seed terms and numbers only: no recipe text leaves the cache. Run by
hand; the scraper never runs it.

    .venv/bin/python scripts/glossaryCandidates.py [--normalised data/normalised.jsonl] [--min 1]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import glossary  # noqa: E402
from models import Recipe  # noqa: E402


def readRecipes(path):
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            if line.strip():
                yield Recipe.fromDict(json.loads(line))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--normalised", default=str(config.NORMALISED_FILE))
    parser.add_argument("--seed", default=str(config.RULES_DIR / "glossarySeed.json"))
    parser.add_argument("--min", type=int, default=1, help="leave out terms in fewer shown recipes")
    args = parser.parse_args(argv)
    seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    terms = glossary.seedTerms(seed)
    entries = glossary.loadEntries() or []
    shown = 0
    found = {}
    for recipe in readRecipes(args.normalised):
        if recipe.hiddenReason is None:
            shown += 1
        for term, row in glossary.counts([recipe], terms).items():
            total = found.setdefault(term, {"recipes": 0, "uses": 0})
            total["recipes"] += row["recipes"]
            total["uses"] += row["uses"]
    kinds = {t["term"]: t for t in terms}
    print(f"shown recipes: {shown}; seed terms: {len(terms)}; terms that appear: {len(found)}")
    print("recipes | uses | kind | status | term")
    for term, row in sorted(found.items(), key=lambda item: (-item[1]["recipes"], item[0])):
        if row["recipes"] < args.min:
            continue
        status = "entry" if glossary.covered(kinds[term], entries) else "new"
        print(f"{row['recipes']:6} | {row['uses']:6} | {kinds[term]['kind']:9} | {status:5} | {term}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
