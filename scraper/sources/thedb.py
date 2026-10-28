"""
TheMealDB and TheCocktailDB share one API shape, so one fetcher serves both.
Only the official API with the free key is used; the sites ask not to be
scraped. The first-letter search returns full records. The category and area
(or alcohol and glass) filters only return ids; they are asked as well to
catch anything the letter search missed, should the free key cap it.
Filtering by each of the several hundred ingredients would add about 600 calls
a pass, so it is left out.
"""
import time
from dataclasses import dataclass

import config
import net
import store


@dataclass(frozen=True)
class TheDb:
    source: str
    baseSetting: str      # the config name holding the API base, read when it runs
    listKey: str          # "meals" or "drinks"
    idField: str
    filters: tuple        # (list.php / filter.php letter, the field list.php names each value by)


MEALDB = TheDb("mealdb", "MEALDB_BASE", "meals", "idMeal", (("c", "strCategory"), ("a", "strArea")))
COCKTAILDB = TheDb("cocktaildb", "COCKTAILDB_BASE", "drinks", "idDrink",
                   (("c", "strCategory"), ("a", "strAlcoholic"), ("g", "strGlass")))
LETTERS = "abcdefghijklmnopqrstuvwxyz0123456789"


def _rows(data, key):
    rows = (data or {}).get(key)
    return rows if isinstance(rows, list) else []      # "None Found" and null both mean nothing


def _get(db, endpoint, params):
    return net.getJson(f"{getattr(config, db.baseSetting)}/{endpoint}", params=params)


def allRecords(db):
    records = {}
    for letter in LETTERS:
        for row in _rows(_get(db, "search.php", {"f": letter}), db.listKey):
            records[str(row[db.idField])] = row
    seen = set(records)
    for letter, field in db.filters:
        values = [row.get(field) for row in _rows(_get(db, "list.php", {letter: "list"}), db.listKey)]
        for value in values:
            if not value:
                continue
            for row in _rows(_get(db, "filter.php", {letter: value}), db.listKey):
                seen.add(str(row[db.idField]))
    for missing in sorted(seen - set(records)):
        for row in _rows(_get(db, "lookup.php", {"i": missing}), db.listKey):
            records[str(row[db.idField])] = row
    return records


def fetchSource(db, previous=None, log=print):
    """
    Fetch every record and save each as a raw file. On failure the previous
    pass's ids are kept, so its recipes stay as they are and nothing is
    removed (ok is False).
    """
    try:
        records = allRecords(db)
    except net.HttpError as e:
        log(f"{db.source}: fetch failed, keeping last pass's records ({e})")
        return {"source": db.source, "ok": False, "ids": list((previous or {}).get("ids", [])), "error": str(e)}
    now = time.time()
    for sourceId, record in records.items():
        store.writeJson(store.rawPath(db.source, sourceId),
                        {"source": db.source, "sourceId": sourceId, "fetchedAt": now, "record": record})
    log(f"{db.source}: {len(records)} records")
    return {"source": db.source, "ok": True, "ids": sorted(records), "error": None}


def cocktailIngredients():
    """TheCocktailDB's ingredient records (type, alcohol, ABV), for growing the seed table by hand. Cached 30 days."""
    names = [row.get("strIngredient1") for row in _rows(_get(COCKTAILDB, "list.php", {"i": "list"}), "drinks")]
    records = []
    for name in names:
        if name:
            data = net.getJson(f"{config.COCKTAILDB_BASE}/search.php", params={"i": name}, cacheHours=24 * 30)
            records += _rows(data, "ingredients")
    return records
