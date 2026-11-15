"""
The catalog switch (new-catalog spec §5 step 3), run once on plutus by the owner after the new catalog is
published (server/README.md, "The catalog switch"):

    cd /database/API && /database/venv/bin/python -m util.gluttonySwitch --list     # dry run: reports, writes nothing
    cd /database/API && /database/venv/bin/python -m util.gluttonySwitch --apply    # the switch, in one transaction
    ... --apply --without drink     # also when no drink site recipe is shown: the old drinks are retired unmoved

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
    """DishKey and Kind folded for matching: case and accents ignored (close to MySQL's utf8mb4_0900_ai_ci) and
    surrounding spaces ignored. Matching runs in Python only; MySQL is never asked to compare them."""
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


# ---- the database ----

class Refused(Exception):
    pass


def _in(values):
    return ", ".join(["%s"] * len(values))


OLD_IN = f"r.Source IN ({_in(rules.OLD_SOURCES)})"


def _all(cur, sql, params):
    cur.execute(sql, tuple(params))
    return cur.fetchall()


def readState(cur):
    """Everything the switch decides from, read in one transaction. The old recipes and every row that references
    one are locked FOR UPDATE, and the shown site recipes FOR SHARE, so nothing changes under the plan."""
    retired = _all(cur, f"SELECT RecipeID, Source, DishKey, Kind, RemovedAt FROM Recipes "
                        f"WHERE Source IN ({_in(rules.OLD_SOURCES)}) FOR UPDATE", rules.OLD_SOURCES)
    candidates = _all(cur, "SELECT r.RecipeID, r.DishKey, r.Kind, r.PrepMinutes, r.CookMinutes, r.ImageWidth, "
                           "n.NutritionFrom FROM Recipes r LEFT JOIN RecipeNutrition n ON n.RecipeID = r.RecipeID "
                           f"WHERE r.Source IN ({_in(rules.SITE_SOURCES)}) AND {rules.SHOWN} FOR SHARE",
                      rules.SITE_SOURCES)
    refs = {
        "ListItems": _all(cur, "SELECT t.ListID, t.RecipeID, t.OrderIndex FROM ListItems t "
                               f"JOIN Recipes r ON r.RecipeID = t.RecipeID WHERE {OLD_IN} FOR UPDATE",
                          rules.OLD_SOURCES),
        "Devoured": _all(cur, "SELECT t.DevouredID, t.RecipeID FROM Devoured t "
                              f"JOIN Recipes r ON r.RecipeID = t.RecipeID WHERE {OLD_IN} FOR UPDATE",
                         rules.OLD_SOURCES),
        "Ratings": _all(cur, "SELECT t.UserID, t.RecipeID, t.Stars FROM Ratings t "
                             f"JOIN Recipes r ON r.RecipeID = t.RecipeID WHERE {OLD_IN} FOR UPDATE",
                        rules.OLD_SOURCES),
        "Notes": _all(cur, "SELECT t.UserID, t.RecipeID, t.Text FROM Notes t "
                           f"JOIN Recipes r ON r.RecipeID = t.RecipeID WHERE {OLD_IN} FOR UPDATE",
                      rules.OLD_SOURCES),
    }
    targets, several = chooseTargets(retired, candidates)
    used = sorted({targets[r["RecipeID"]] for rows in refs.values() for r in rows if r["RecipeID"] in targets})
    existing = {"ListItems": [], "Ratings": [], "Notes": []}
    if used:
        existing = {
            "ListItems": _all(cur, f"SELECT ListID, RecipeID FROM ListItems WHERE RecipeID IN ({_in(used)}) "
                                   "FOR UPDATE", used),
            "Ratings": _all(cur, f"SELECT UserID, RecipeID, Stars FROM Ratings WHERE RecipeID IN ({_in(used)}) "
                                 "FOR UPDATE", used),
            "Notes": _all(cur, f"SELECT UserID, RecipeID, Text FROM Notes WHERE RecipeID IN ({_in(used)}) "
                               "FOR UPDATE", used),
        }
    return {"retired": retired, "candidates": candidates, "refs": refs, "targets": targets, "several": several,
            "existing": existing}


def kindCounts(retired, candidates, referenced, targets):
    """{Kind: shown site recipes, old recipes, kept old recipes, kept ones with a match}, kinds sorted."""
    byId = {r["RecipeID"]: r for r in retired}
    kinds = sorted({r["Kind"] for r in retired} | {r["Kind"] for r in candidates})
    result = {}
    for kind in kinds:
        kept = [rid for rid in referenced if byId[rid]["Kind"] == kind]
        result[kind] = {"shown": sum(c["Kind"] == kind for c in candidates),
                        "old": sum(r["Kind"] == kind for r in retired),
                        "referenced": len(kept),
                        "matched": sum(rid in targets for rid in kept)}
    return result


def switch(apply, now, without=()):
    """The report; with apply, the moves and the retirement are committed together, otherwise rolled back. With
    apply it refuses while a kind that has old recipes has no shown site recipe, unless named in without."""
    conn = DBUtils.initConnection("gluttony")
    try:
        conn.autocommit = False
        cur = conn.cursor(dictionary=True)
        state = readState(cur)
        writes, report = planMoves(state["targets"], state["refs"], state["existing"], now)
        referenced = sorted({r["RecipeID"] for rows in state["refs"].values() for r in rows})
        byId = {r["RecipeID"]: r for r in state["retired"]}
        report.update({
            "retired": len(state["retired"]),
            "newlyRetired": sum(r["RemovedAt"] is None for r in state["retired"]),
            "shown": len(state["candidates"]),
            "referenced": len(referenced),
            "matched": sum(rid in state["targets"] for rid in referenced),
            "several": sum(rid in state["several"] for rid in referenced),
            "kinds": kindCounts(state["retired"], state["candidates"], referenced, state["targets"]),
            "mapping": [(byId[rid], state["targets"].get(rid)) for rid in referenced],
            "applied": False,
        })
        if not apply:
            conn.rollback()
            return report
        if not state["candidates"]:
            raise Refused("no site recipe is shown: publish the new catalog first")
        bare = [k for k, c in report["kinds"].items() if c["old"] and not c["shown"] and k not in without]
        if bare:
            names = " and ".join(bare)
            flags = " ".join(f"--without {k}" for k in bare)
            raise Refused(f"no {names} site recipe is shown: publish them first, or pass {flags} to retire the "
                          f"old {names} recipes anyway")
        for sql, params in writes:
            cur.execute(sql, params)
        cur.execute(f"UPDATE Recipes SET RemovedAt = NOW() WHERE Source IN ({_in(rules.OLD_SOURCES)}) "
                    "AND RemovedAt IS NULL", rules.OLD_SOURCES)
        conn.commit()
        report["applied"] = True
        return report
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---- the report ----

def reportLines(report, listing):
    lines = ["switch: applied" if report["applied"]
             else "switch: dry run, nothing was written (run again with --apply to switch)"]
    did = "retired by this run" if report["applied"] else "would be retired by --apply"
    lines.append(f"old recipes: {report['retired']} ({report['newlyRetired']} {did}, the rest already removed)")
    lines.append(f"shown site recipes: {report['shown']}")
    for kind, c in report["kinds"].items():
        lines.append(f"{kind}: {c['shown']} shown site recipes; {c['old']} old recipes, {c['referenced']} kept, "
                     f"{c['matched']} with a match")
    lines.append(f"old recipes people kept: {report['referenced']}, {report['matched']} with a match "
                 f"({report['several']} chosen among several)")
    for table in TABLES:
        counts = report[table]
        line = (f"{table}: {counts['moved']} moved ({counts['merged']} merged with one already there), "
                f"{counts['notMoved']} not moved")
        if counts.get("tooLong"):
            line += f" ({counts['tooLong']} too long to join, left in place)"
        lines.append(line)
    if listing:
        for row, target in report["mapping"]:
            lines.append(f"  #{row['RecipeID']} {row['Source']} {row['DishKey']} ({row['Kind']}) -> "
                         + (f"#{target}" if target is not None else "no match"))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Retire the old catalog and move what people kept (spec §5)")
    parser.add_argument("--apply", action="store_true", help="switch for real; without it nothing is written")
    parser.add_argument("--list", action="store_true", help="also list each kept old recipe and where it goes")
    parser.add_argument("--without", action="append", default=[], metavar="KIND",
                        help="with --apply, retire this kind's old recipes although no site recipe of that kind "
                             "is shown (repeatable, e.g. --without drink)")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)     # DATETIME(3)
    try:
        report = switch(args.apply, now, tuple(args.without))
    except Refused as e:
        print(f"switch: refused, nothing was changed: {e}")
        return 1
    except Exception as e:
        print(f"switch: failed, nothing was changed: {type(e).__name__}: {e}")
        return 1
    print("\n".join(reportLines(report, args.list)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
