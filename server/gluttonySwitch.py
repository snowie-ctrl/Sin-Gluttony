"""
The catalog switch (new-catalog spec §5 step 3), run once on plutus by the owner after the new catalog is
published (server/README.md, "The catalog switch"):

    cd /database/API && /database/venv/bin/python -m util.gluttonySwitch --list     # dry run: reports, writes nothing
    cd /database/API && /database/venv/bin/python -m util.gluttonySwitch --apply    # the switch, in one transaction

Every TheMealDB, TheCocktailDB and Wikibooks recipe gets RemovedAt. None is deleted: the user tables cascade on
delete. What people kept on one (list entries, Devoured marks, stars, notes) moves to the shown site recipe with the
same DishKey and Kind; with several, the one with the most facts, then the lowest RecipeID. A clash (the person
already has the new recipe) keeps the higher rating, joins the notes with a blank line, keeps every Devoured date and
one list entry. Moved stars and notes take the moment of the move as UpdatedAt, which /sync/batch compares. A
reference with no match stays on the retired recipe, which the app no longer shows; the backup taken before the
switch undoes everything.

It is safe to run again: a recipe already retired keeps its first RemovedAt, and a reference still on a retired
recipe moves once a match has been published.
"""
import argparse
import sys
import unicodedata
from datetime import datetime, timezone

from . import DBUtils, gluttonyRules as rules

TABLES = ("ListItems", "Devoured", "Ratings", "Notes")
NOTE_LIMIT = 2000        # Notes.Text is VARCHAR(2000); a longer join would abort the whole transaction


# ---- which new recipe ----

def matchKey(dishKey, kind):
    """DishKey and Kind as MySQL's utf8mb4_0900_ai_ci compares them: case and accents ignored."""
    folded = unicodedata.normalize("NFKD", dishKey or "").casefold()
    return "".join(c for c in folded if not unicodedata.combining(c)).strip(), kind


def factOrder(candidate):
    """Sort key, best first: nutrition from the page, then prep and cook given, then the wider picture, then the
    lowest RecipeID."""
    given = (candidate["PrepMinutes"] is not None) + (candidate["CookMinutes"] is not None)
    return (candidate["NutritionFrom"] != "source", -given, -(candidate["ImageWidth"] or 0), candidate["RecipeID"])


def chooseTargets(retired, candidates):
    """({retired RecipeID: new RecipeID}, {retired RecipeIDs that had several candidates})."""
    byKey = {}
    for row in candidates:
        key = matchKey(row["DishKey"], row["Kind"])
        if key[0]:
            byKey.setdefault(key, []).append(row)
    targets, several = {}, set()
    for row in retired:
        key = matchKey(row["DishKey"], row["Kind"])
        found = byKey.get(key) if key[0] else None
        if found:
            targets[row["RecipeID"]] = min(found, key=factOrder)["RecipeID"]
            if len(found) > 1:
                several.add(row["RecipeID"])
    return targets, several


# ---- moving what people kept ----

def _grouped(rows, targets, owner):
    """{(owner, target): [moved rows, by old RecipeID]} for the rows that have a target."""
    groups = {}
    for row in sorted(rows, key=lambda r: r["RecipeID"]):
        if row["RecipeID"] in targets:
            groups.setdefault((row[owner], targets[row["RecipeID"]]), []).append(row)
    return groups


def _counts(rows, targets):
    moved = sum(r["RecipeID"] in targets for r in rows)
    return {"moved": moved, "merged": 0, "notMoved": len(rows) - moved}


def _listItems(rows, held, targets, writes):
    counts = _counts(rows, targets)
    held = {(r["ListID"], r["RecipeID"]) for r in held}
    for (listId, target), group in _grouped(rows, targets, "ListID").items():
        clash = (listId, target) in held or len(group) > 1
        counts["merged"] += len(group) if clash else 0
        drop = group
        if (listId, target) not in held:
            top = min(group, key=lambda r: (r["OrderIndex"], r["RecipeID"]))
            writes.append(("UPDATE ListItems SET RecipeID = %s WHERE ListID = %s AND RecipeID = %s",
                           (target, listId, top["RecipeID"])))
            drop = [r for r in group if r is not top]
        for row in drop:
            writes.append(("DELETE FROM ListItems WHERE ListID = %s AND RecipeID = %s", (listId, row["RecipeID"])))
    return counts


def _devoured(rows, targets, writes):
    for row in sorted(rows, key=lambda r: r["DevouredID"]):
        if row["RecipeID"] in targets:
            writes.append(("UPDATE Devoured SET RecipeID = %s WHERE DevouredID = %s",
                           (targets[row["RecipeID"]], row["DevouredID"])))
    return _counts(rows, targets)


def _joinedNote(texts):
    kept = []
    for text in texts:
        if text.strip() and text.strip() not in (k.strip() for k in kept):
            kept.append(text.strip())
    return "\n\n".join(kept)


def _perPerson(table, column, rows, held, targets, now, writes, merge):
    """Ratings or Notes: per (person, new recipe), the moved rows and the one already there become one row."""
    counts = _counts(rows, targets)
    held = {(r["UserID"], r["RecipeID"]): r[column] for r in held}
    if table == "Notes":
        counts["tooLong"] = 0
    for (uid, target), group in _grouped(rows, targets, "UserID").items():
        values = ([held[(uid, target)]] if (uid, target) in held else []) + [r[column] for r in group]
        value = merge(values)
        if table == "Notes" and len(value) > NOTE_LIMIT:
            counts["moved"] -= len(group)
            counts["notMoved"] += len(group)
            counts["tooLong"] += len(group)
            continue
        if len(values) > 1:
            counts["merged"] += len(group)
        for row in group:
            writes.append((f"DELETE FROM {table} WHERE UserID = %s AND RecipeID = %s", (uid, row["RecipeID"])))
        writes.append((f"INSERT INTO {table} (UserID, RecipeID, {column}, UpdatedAt) VALUES (%s, %s, %s, %s) "
                       f"ON DUPLICATE KEY UPDATE {column} = VALUES({column}), UpdatedAt = VALUES(UpdatedAt)",
                       (uid, target, value, now)))
    return counts


def _higherStars(values):
    stars = [v for v in values if v is not None]
    return max(stars) if stars else None


def planMoves(targets, refs, existing, now):
    """(writes, report): every statement that moves what people kept, in order, and per table how many references
    moved (merged: of those, how many met another row for the same person or list) and how many did not."""
    writes = []
    report = {
        "ListItems": _listItems(refs["ListItems"], existing["ListItems"], targets, writes),
        "Devoured": _devoured(refs["Devoured"], targets, writes),
        "Ratings": _perPerson("Ratings", "Stars", refs["Ratings"], existing["Ratings"], targets, now, writes,
                              _higherStars),
        "Notes": _perPerson("Notes", "Text", refs["Notes"], existing["Notes"], targets, now, writes, _joinedNote),
    }
    return writes, report
