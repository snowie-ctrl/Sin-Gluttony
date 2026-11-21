"""
The glossary's words in the scraper (spec 2026-11-19 part 3, milestone 3). The terms themselves live in the
app (app/assets/glossary.json); the candidates they are chosen from in rules/glossarySeed.json. marks() finds
them the way the app's qml/logic/glossary.mjs does: whole words, case-insensitive, the longest form first, the
first occurrence of a term per text, and never a stop-list word. counts() and gaps() give the candidate script
and the reports how many shown recipes use each seed term; only terms and numbers come out, never recipe text.
"""
import json

import config

# Everyday words that are never marked, whatever the glossary says. The same list as STOP in glossary.mjs (a
# test keeps them equal).
STOP = frozenset([
    "add", "bake", "baked", "bakes", "baking", "boil", "boiled", "boiling", "chop", "chopped", "chopping",
    "cook", "cooked", "cooking", "cooks", "cut", "fry", "fried", "frying", "heat", "heated", "heating", "melt",
    "melted", "mix", "mixed", "mixes", "mixing", "pour", "poured", "serve", "served", "slice", "sliced", "stir",
    "stirred", "stirring", "stirs", "wash", "washed",
])


def _isWordChar(ch):
    return ch.isalnum()


def _lower(text):
    """Lowercase one character at a time, so every index still points at the same character."""
    return "".join((c.lower() if len(c.lower()) == 1 else c) for c in text)


def marks(text, entries, stop=STOP):
    """[(start, end, term)] in text order: whole-word matches of each entry's forms, the longest first where
    they overlap, then only each term's first."""
    lower = _lower(text or "")
    found = []
    for entry in entries or []:
        for form in entry.get("forms", []):
            if not form or form in stop or entry["term"] in stop:
                continue
            start = lower.find(form)
            while start >= 0:
                end = start + len(form)
                if (start == 0 or not _isWordChar(lower[start - 1])) and (end == len(lower) or not _isWordChar(lower[end])):
                    found.append((start, end, entry["term"]))
                start = lower.find(form, start + 1)
    kept = []
    for start, end, term in sorted(found, key=lambda f: (-(f[1] - f[0]), f[0])):
        if all(end <= s or start >= e for s, e, _ in kept):
            kept.append((start, end, term))
    first = {}
    for span in sorted(kept):
        first.setdefault(span[2], span)
    return sorted(first.values())


def seedTerms(seed):
    """The seed file's {"technique": ["fold|folds|…"], "word": [...]} as [{term, forms, kind}]."""
    return [{"term": item.split("|")[0], "forms": item.split("|"), "kind": kind}
            for kind in ("technique", "word") for item in seed.get(kind, [])]


def _texts(recipe):
    return [step.text for step in recipe.steps] + [line.line for line in recipe.ingredients]


def counts(recipes, terms):
    """term -> {"recipes", "uses"} over the shown recipes' steps and ingredient lines; terms never seen are left out."""
    out = {}
    for recipe in recipes:
        if recipe.hiddenReason is not None:
            continue
        uses = {}
        for text in _texts(recipe):
            for _, _, term in marks(text, terms):
                uses[term] = uses.get(term, 0) + 1
        for term, n in uses.items():
            row = out.setdefault(term, {"recipes": 0, "uses": 0})
            row["recipes"] += 1
            row["uses"] += n
    return out


def covered(term, entries):
    """True when some glossary entry has one of the seed term's forms."""
    forms = {form for entry in entries for form in entry.get("forms", [])} | {entry["term"] for entry in entries}
    return bool(set(term["forms"]) & forms)


def gaps(recipes, seed, entries, minRecipes=3):
    """Seed terms in at least minRecipes shown recipes that no glossary entry covers, the most used first."""
    terms = [t for t in seedTerms(seed) if not covered(t, entries)]
    found = counts(recipes, terms)
    rows = [{"term": term, "recipes": row["recipes"]} for term, row in found.items() if row["recipes"] >= minRecipes]
    return sorted(rows, key=lambda r: (-r["recipes"], r["term"]))


def loadEntries(path=None):
    """The app's glossary entries, or None when the file is missing or not a list (the reports say so)."""
    path = path or config.GLOSSARY_FILE
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return entries if isinstance(entries, list) else None


def reportGaps(recipes, rules):
    """The reports' glossary gaps: a list, or None when the app's glossary is not beside the scraper."""
    entries = loadEntries()
    if entries is None:
        return None
    return gaps(recipes, rules.get("glossarySeed", {}), entries)
