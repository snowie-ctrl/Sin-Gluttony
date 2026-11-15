"""
Finds the USDA FDC food for one of our ingredient names, by rules alone.

An FDC description is comma parts, the first naming the food ("Onions, raw").
A food whose first part is the ingredient scores highest; one whose words
merely include the ingredient's scores lower. Raw and plain forms win over
cooked, canned or frozen ones unless the name asks for them, and Foundation
foods win over SR Legacy. `settle` gives an id only when one food is clearly
best; anything less sure waits for the owner.

A name's food comes from, in order (R2): the owner's pick in run/fdc-picks.json
(a None pick means no FDC food fits), the curated rules/fdcMap.json, then a
settled rule match. A pick or override naming a food the cache lacks is ignored.
"""
import threading
from functools import lru_cache

import config
import store
from matching import plainText, singular

PENALISED = ("cooked", "boiled", "canned", "frozen", "prepared", "fried", "baked", "dehydrated", "infant", "babyfood")
# Drinks and fats are never "raw" in FDC; for them, a description with nothing cooked earns the raw bonus.
DRINKS_AND_FATS = {"oil", "butter", "lard", "shortening", "margarine", "ghee", "fat", "beverage", "alcoholic",
                   "juice", "milk", "wine", "beer", "liqueur", "spirit", "water", "drink"}

_picksLock = threading.Lock()    # the control server is threaded; one pick at a time reads, changes and writes the file


def _words(text):
    return [singular(w) for w in plainText(text).split()]


@lru_cache(maxsize=None)
def _parsed(description):
    """-> (head words, rest words, number of comma parts)."""
    parts = [_words(part) for part in description.split(",")]
    parts = [p for p in parts if p] or [[]]
    return parts[0], [w for p in parts[1:] for w in p], len(parts)


def _score(nameWords, food):
    head, rest, partCount = _parsed(food["description"])
    allWords = head + rest
    if head == nameWords:
        score = 100
    elif sorted(head) == sorted(nameWords):
        score = 90
    elif nameWords and set(nameWords) <= set(allWords):
        score = 60 + 10 * sum(w in nameWords for w in allWords) / len(allWords)
    else:
        return 0
    penalised = [w for w in PENALISED if w in allWords and w not in nameWords]
    if "raw" in rest or (not penalised and DRINKS_AND_FATS & set(allWords)):
        score += 8
    score -= 10 * len(penalised)
    if food["dataType"] == "foundation_food":
        score += 5
    score -= max(0, partCount - 2)
    return round(score, 2)


def candidates(name, foods, limit=5):
    """The best FDC foods for name, best first: [{"fdcId", "description", "dataType", "score"}]."""
    nameWords = _words(name)
    found = []
    for food in foods.values():
        score = _score(nameWords, food)
        if score:
            found.append({"fdcId": food["id"], "description": food["description"],
                          "dataType": food["dataType"], "score": score})
    found.sort(key=lambda c: (-c["score"], len(c["description"]), c["fdcId"]))
    return found[:limit]


def settle(name, foods):
    """An fdcId only when the rules are sure: the top food has the name as its head and leads by 8 points."""
    top = candidates(name, foods, limit=2)
    if not top or top[0]["score"] < 100:
        return None
    if len(top) > 1 and top[0]["score"] - top[1]["score"] < 8:
        return None
    return top[0]["fdcId"]


def mappingFor(names, foods, rules, picks):
    """{name: fdcId} for every name with a food: owner pick, then curated override, then a settled match."""
    overrides = rules.get("fdcMap", {})
    mapping = {}
    for name in names:
        if name in picks and picks[name] is None:
            continue
        chosen = picks.get(name)
        if chosen not in foods:
            chosen = (overrides.get(name) or {}).get("fdcId")
        if chosen not in foods:
            chosen = settle(name, foods)
        if chosen is not None:
            mapping[name] = chosen
    return mapping


def resolveTable(table, foods, rules, picks):
    """{ingredientId: (fdcId, from)} for every row; from is owner, curated, rule or None.

    Order: the owner's file pick (None means no food fits), the row's own owner choice from the
    database (its id may be None), the curated override, then a settled match. A pick or owner id
    naming a food the cache lacks falls through for the estimate; syncList still keeps the owner row.
    """
    overrides = rules.get("fdcMap", {})
    resolved = {}
    for ingredientId, row in table.rows.items():
        name = row["name"]
        if name in picks and (picks[name] is None or picks[name] in foods):
            resolved[ingredientId] = (picks[name], "owner")
            continue
        if row.get("fdcFrom") == "owner" and (row.get("fdcId") is None or row["fdcId"] in foods):
            resolved[ingredientId] = (row["fdcId"], "owner")
            continue
        curated = (overrides.get(name) or {}).get("fdcId")
        if curated in foods:
            resolved[ingredientId] = (curated, "curated")
            continue
        settled = settle(name, foods)
        resolved[ingredientId] = (settled, "rule") if settled is not None else (None, None)
    return resolved


def mappingForTable(table, foods, rules, picks):
    """{name: fdcId} for every row with a food, in the shape nutrition.choose takes."""
    resolved = resolveTable(table, foods, rules, picks)
    return {table.rows[i]["name"]: fdcId for i, (fdcId, _) in resolved.items() if fdcId is not None}


def syncList(table, resolved, foods):
    """The mappings to send the server: only rows whose stored (fdcId, fdcFrom) differ.

    Safe against a thin cache: with no foods nothing is sent, and a stored id the cache merely
    lacks is never cleared or replaced by a curated or rule choice; such a row changes only when
    its stored food is present in foods (or it has no id yet). The owner's own choice (a pick, or
    "no food fits") is always sent, whatever the cache holds. A row stored as owner is never
    listed unless the resolved choice is the owner's too. So a file pick naming a food the cache
    lacks is used for nothing but the estimate (resolveTable falls through to curated/rule): if
    the row is stored as owner it is left alone; if it is not owner yet, the fallthrough id is
    written as curated/rule.
    """
    if not foods:
        return []
    out = []
    for ingredientId, (fdcId, source) in resolved.items():
        row = table.rows[ingredientId]
        if (row.get("fdcId"), row.get("fdcFrom")) == (fdcId, source):
            continue
        if row.get("fdcFrom") == "owner" and source != "owner":
            continue
        if source != "owner" and row.get("fdcId") is not None and row["fdcId"] not in foods:
            continue
        out.append({"ingredientId": ingredientId, "fdcId": fdcId, "from": source})
    return out


def loadPicks():
    return store.readJson(config.FDC_PICKS_FILE, {}) or {}


def savePick(name, fdcId):
    """Records the owner's choice for name; None means no FDC food fits it."""
    with _picksLock:
        picks = loadPicks()
        picks[name] = fdcId
        store.writeJson(config.FDC_PICKS_FILE, picks)
