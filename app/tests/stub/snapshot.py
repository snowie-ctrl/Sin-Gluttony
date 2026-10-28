"""Takes the stub's recipe snapshot from the LAN read API. Run it once, in milestone 1, while that API still needs
no session:

    server\\.venv\\Scripts\\python.exe app\\tests\\stub\\snapshot.py --base <LAN read API base>

The base is plutus's LAN address and API port followed by /api/gluttony (the scraper VM's ADMIN_HOST and
ADMIN_PORT); ask the owner, and never write it into a committed file. It writes app/tests/stub/snapshot/ (git
ignores it): recipes.json, and the pictures as images/<id>.jpg and thumbs/<id>.jpg.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FOOD = ("breakfast", "starter", "main", "side", "dessert", "snack", "bread", "sauce")
DRINK = ("cocktail", "mocktail", "shot", "coffee/tea", "shake", "punch")
FEATURES = ("mealdb", "cocktaildb", "wikibooks", "guessedTime", "noServings", "unknownIngredient", "range",
            "groupHeading", "noPicture", "incomplete", "complete", "versions", "temperature", "longTime")
HERE = Path(__file__).resolve().parent


def features(r):
    """What a recipe shows off, so the snapshot has at least two of each: every source, guessed values, missing
    servings, unknown ingredients, ranges, group headings, missing pictures, temperatures, very long times."""
    found = {r["source"], "complete" if r["facts"]["complete"] else "incomplete"}
    if r.get("timeFrom") == "rule":
        found.add("guessedTime")
    if not r.get("servings"):
        found.add("noServings")
    if any(i["ingredientId"] is None for i in r["ingredients"]):
        found.add("unknownIngredient")
    if any(i["quantityMax"] is not None for i in r["ingredients"]):
        found.add("range")
    if any(i["group"] for i in r["ingredients"]) or any(s["group"] for s in r["steps"]):
        found.add("groupHeading")
    if not r.get("hasImage"):
        found.add("noPicture")
    if r.get("versions"):
        found.add("versions")
    if any(re.search(r"\d\s*(°|º|degrees)", s["text"]) for s in r["steps"]):
        found.add("temperature")
    if (r.get("totalMinutes") or 0) >= 1440:
        found.add("longTime")
    return found


def choose(details, limit):
    """Up to `limit` recipes: first two of every feature the candidates have, then the rest taken in turn by
    course, so every filter has something to find."""
    chosen, seen = [], set()

    def take(r):
        if r["id"] not in seen and len(chosen) < limit:
            seen.add(r["id"])
            chosen.append(r)

    for feature in FEATURES:
        for r in [d for d in details if feature in features(d)][:2]:
            take(r)
    byCourse = {}
    for d in details:
        byCourse.setdefault(str(d["course"]), []).append(d)
    queues = [list(rows) for _, rows in sorted(byCourse.items())]
    while len(chosen) < limit and any(queues):
        for rows in queues:
            if rows:
                take(rows.pop(0))
    return chosen


def candidateIds(listed, limit):
    """Up to `limit` distinct ids, taken in turn from each course's list. Cutting the joined lists instead would
    drop whole courses (the drinks come last), and then the filters for them would have nothing to find."""
    ids = []
    for rank in range(max(map(len, listed), default=0)):
        for rows in listed:
            if rank < len(rows) and rows[rank] not in ids:
                ids.append(rows[rank])
    return ids[:limit]


def fetch(base, path, raw=False):
    with urllib.request.urlopen(base + path, timeout=30) as reply:
        data = reply.read()
    # plutus is the owner's own server, serving other apps too: a short pause between calls.
    time.sleep(0.05)
    return data if raw else json.loads(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Snapshot recipes for the Gluttony stub")
    parser.add_argument("--base", required=True, help="the LAN read API, ending in /api/gluttony")
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--out", default=str(HERE / "snapshot"))
    args = parser.parse_args(argv)
    base = args.base.rstrip("/")

    listed = []
    for kind, courses in (("food", FOOD), ("drink", DRINK)):
        for course in courses:
            page = fetch(base, f"/recipes?kind={kind}&course={urllib.parse.quote(course)}&pageSize=60")
            listed.append([t["id"] for t in page["data"]["recipes"]])
    details = []
    for rid in candidateIds(listed, args.count * 2):
        try:
            details.append(fetch(base, f"/recipes/{rid}")["data"])
        except urllib.error.HTTPError:
            continue
    chosen = choose(details, args.count)

    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "thumbs").mkdir(exist_ok=True)
    kept = {r["id"] for r in chosen}
    for r in chosen:
        # Seconds? links only to recipes the stub can open.
        r["versions"] = [v for v in r["versions"] if v["id"] in kept]
        if r["hasImage"]:
            try:
                for folder in ("thumbs", "images"):
                    (out / folder / f"{r['id']}.jpg").write_bytes(fetch(base, f"/{folder}/{r['id']}", raw=True))
            except urllib.error.HTTPError:
                r["hasImage"] = False
    taken = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (out / "recipes.json").write_text(json.dumps({"takenAt": taken, "recipes": chosen}, ensure_ascii=False),
                                      encoding="utf-8")
    print(f"{len(chosen)} recipes ({sum(r['hasImage'] for r in chosen)} with pictures) into {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
