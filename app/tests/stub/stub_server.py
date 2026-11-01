"""Stand-in for Gluttony's app API (docs/api.md), for screenshot runs and trying the app without plutus or
anyone's account. It listens on 127.0.0.1:5079; tests/stub/grab.ps1 starts it.

It serves the recipes in snapshot/ (taken by snapshot.py from the LAN read API; never committed) or, without one,
the four in fixture/recipes.json. Filters, the profile and the safety rule follow the server's rules, except that
include and exclude match only the ingredient itself, not its children.

Sign in as stub / stub-password (UID 7, token "stub"). Sign up with the key "stub-key" (any other key is 403
invalid_key); the username "taken" is 409. Signing out makes /device/identify say "new" until the next /auth.

Every reader starts with an empty Cravings list. Lists, items, Devoured marks, stars and notes follow docs/api.md and
refuse what the server refuses, in its words; they last until the stub stops.

What the app did offline arrives with /sync/batch: marks once per clientId, the newest star or note wins (/rating and
/note remember when they changed). /saved/manifest gives every recipe the snapshot's takenAt as its updatedAt, and the reader's mine as /recipes/<id> gives it.

STUB_KEPT=1              the stub reader starts with two Cravings, a list "Weeknights", a mark three days ago, four
                         stars and a note, on the first recipes of the snapshot (or the fixture).
STUB_REMOVED=<id,..>     those recipes are removed by their source: hidden from browsing and Home's picks, and open
                         only for a reader who keeps them (there they stay in lists and Again?, marked removed).
STUB_NEW_DEVICE=1        /device/identify says "new", so the sign-in form shows.
STUB_DIET=<d,..>;<a,..>  the stub reader's saved profile at start, e.g. "vegetarian;peanut,sesame".
STUB_HOME_DOWN=1         /home answers 500 "home is down".
STUB_PICTURES_FAIL=1     every picture is 404, to see the placeholders.
STUB_SLOW=<ms>           pictures answer that late, to see loading states.
STUB_SNAPSHOT=<dir>      serve that folder instead of snapshot/.
"""
import hashlib
import json
import os
import random
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, request, send_file

API = "/api/gluttony"
TOKEN = "stub"
UID = 7
PORT = 5079
PUBLIC = {"/ping", "/auth", "/device/identify"}
HERE = Path(__file__).resolve().parent
DIETS = ("vegetarian", "vegan", "gluten-free", "dairy-free")
CONTAINS = ("meat", "poultry", "fish", "shellfish", "dairy", "egg", "gluten", "tree-nut", "peanut", "soy",
            "sesame", "alcohol", "honey")
ALCOHOL = ("alcoholic", "non-alcoholic", "optional")
WORD_LISTS = {"course": None, "cuisine": None, "flavour": None, "occasion": None, "diet": DIETS,
              "avoid": CONTAINS, "alcohol": ALCOHOL}
HOME_COURSES = ("main", "breakfast")
THIS_DEVICE, OTHER_DEVICE = "f00dfeedf00dfeed", "0a1b2c3d4e5f6071"

app = Flask(__name__)
lock = threading.Lock()
state = {}


def snapshotFolder():
    folder = Path(os.environ.get("STUB_SNAPSHOT") or HERE / "snapshot")
    return folder if (folder / "recipes.json").is_file() else HERE / "fixture"


def reset():
    folder = snapshotFolder()
    snapshot = json.loads((folder / "recipes.json").read_text(encoding="utf-8"))
    recipes = snapshot["recipes"]
    diets, _, avoid = (os.environ.get("STUB_DIET") or "").partition(";")
    state.clear()
    state.update({
        "folder": folder,
        "recipes": {r["id"]: r for r in recipes},
        "readers": {},
        "tokens": {TOKEN: UID},
        "deviceUid": None if os.environ.get("STUB_NEW_DEVICE") else UID,
        "otherDevice": True,
        "nextUid": 100,
        "nextListId": 1,
        "nextMarkId": 1,
        "takenAt": str(snapshot.get("takenAt") or "2026-10-27T00:00:00")[:19],
        "removed": {int(v) for v in (os.environ.get("STUB_REMOVED") or "").split(",") if v.strip().isdigit()},
    })
    reader = newReader("stub", "stub-password")
    reader["diets"] = [d for d in diets.split(",") if d]
    reader["avoid"] = [a for a in avoid.split(",") if a]
    state["readers"][UID] = reader
    if os.environ.get("STUB_KEPT"):
        seedKept(reader)


def nextId(counter):
    value = state[counter]
    state[counter] += 1
    return value


def nowStamp():
    """Now in UTC, as the app writes its queued moments, so the two compare as text."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def newReader(username, password):
    """A reader as sign-up leaves one: no diet, and an empty Cravings list (always the first list)."""
    return {"username": username, "password": password, "diets": [], "avoid": [],
            "lists": [{"id": nextId("nextListId"), "title": "Cravings", "kind": "cravings", "items": []}],
            "devoured": [], "ratings": {}, "notes": {}, "changedAt": {}}


def seedKept(reader):
    first = sorted(state["recipes"])[:4]
    if len(first) < 4:
        return
    reader["lists"][0]["items"] = [first[0], first[3]]
    reader["lists"].append({"id": nextId("nextListId"), "title": "Weeknights", "kind": "custom", "items": [first[1]]})
    day = (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat()
    reader["devoured"].append({"id": nextId("nextMarkId"), "rid": first[0], "on": day,
                               "clientId": "00000000-0000-4000-8000-000000000001"})
    reader["ratings"][first[0]] = 4
    reader["notes"][first[0]] = "Less salt, more wine."


def ok(data=None, status="ok", **extra):
    answer = {"status": status}
    if data is not None:
        answer["data"] = data
    answer.update(extra)
    return jsonify(answer), 200


def fail(status, http, message=None):
    return jsonify({"status": status, "message": message or status}), http


def uid():
    return state["tokens"].get(request.headers.get("X-Session-Token") or "")


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.before_request
def guard():
    route = request.path[len(API):] if request.path.startswith(API) else None
    if route is not None and route not in PUBLIC and uid() is None:
        return fail("error", 401, "not signed in")
    return None


# ---- Account ----

@app.route(API + "/ping")
def ping():
    return ok()


def signedIn(rid):
    token = TOKEN if rid == UID else f"stub-{rid}"
    state["tokens"][token] = rid
    state["deviceUid"] = rid
    return ok(UID=rid, username=state["readers"][rid]["username"], token=token)


@app.route(API + "/device/identify", methods=["POST"])
def identify():
    if not body().get("fingerprint"):
        return fail("error", 400, "missing fingerprint")
    with lock:
        rid = state["deviceUid"]
        return signedIn(rid) if rid else ok(status="new")


@app.route(API + "/auth", methods=["POST"])
def auth():
    data = body()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    key = str(data.get("key") or "").strip()
    if not username or not password or not data.get("fingerprint"):
        return fail("error", 400, "missing credentials")
    with lock:
        if key:
            if not 3 <= len(username) <= 32:
                return fail("error", 400, "a username is 3 to 32 characters")
            if not 8 <= len(password) <= 256:
                return fail("error", 400, "a password is 8 to 256 characters")
            if key != "stub-key":
                return fail("invalid_key", 403)
            if username == "taken" or any(r["username"] == username for r in state["readers"].values()):
                return fail("username_taken", 409)
            rid = state["nextUid"]
            state["nextUid"] += 1
            state["readers"][rid] = newReader(username, password)
            return signedIn(rid)
        for rid, reader in state["readers"].items():
            if reader["username"] == username and reader["password"] == password:
                return signedIn(rid)
    return fail("invalid_credentials", 401)


@app.route(API + "/auth/logout", methods=["POST"])
def logout():
    with lock:
        state["deviceUid"] = None
    return ok()


@app.route(API + "/user/username", methods=["POST"])
def username():
    name = str(body().get("username") or "").strip()
    if not 3 <= len(name) <= 32:
        return fail("error", 400, "a username is 3 to 32 characters")
    if name == "taken":
        return fail("username_taken", 409)
    with lock:
        state["readers"][uid()]["username"] = name
    return ok(username=name)


@app.route(API + "/user/password", methods=["POST"])
def password():
    data = body()
    reader = state["readers"][uid()]
    if data.get("current") != reader["password"]:
        return fail("invalid_credentials", 401)
    if not 8 <= len(str(data.get("password") or "")) <= 256:
        return fail("error", 400, "a password is 8 to 256 characters")
    reader["password"] = data["password"]
    return ok()


@app.route(API + "/devices")
def devices():
    rows = [{"id": THIS_DEVICE, "label": THIS_DEVICE[:8], "current": True, "lastSignIn": "2026-10-27T08:00:00Z"}]
    if state["otherDevice"]:
        rows.append({"id": OTHER_DEVICE, "label": OTHER_DEVICE[:8], "current": False, "lastSignIn": None})
    return ok(rows)


@app.route(API + "/devices/remove", methods=["POST"])
def devicesRemove():
    wanted = body().get("id")
    if wanted == THIS_DEVICE:
        return fail("error", 400, "this is the device you are using: sign out instead")
    if wanted == OTHER_DEVICE:
        state["otherDevice"] = False
    return ok()


# ---- Diet profile ----

@app.route(API + "/me/diet", methods=["GET"])
def getDiet():
    reader = state["readers"][uid()]
    return ok({"diets": reader["diets"], "avoid": reader["avoid"]})


@app.route(API + "/me/diet", methods=["POST"])
def setDiet():
    data = body()
    for name, word, allowed in (("diets", "diet", DIETS), ("avoid", "avoid", CONTAINS)):
        values = data.get(name, [])
        if not isinstance(values, list):
            return fail("error", 400, f"{name} must be a list of words")
        bad = [v for v in values if v not in allowed]
        if bad:
            return fail("error", 400, f"unknown {word}: {bad[0]}")
    reader = state["readers"][uid()]
    reader["diets"] = [d for d in DIETS if d in data.get("diets", [])]
    reader["avoid"] = [a for a in CONTAINS if a in data.get("avoid", [])]
    return ok({"diets": reader["diets"], "avoid": reader["avoid"]})


# ---- Catalog ----

def many(args, name):
    return [v.strip() for raw in args.getlist(name) for v in raw.split(",") if v.strip()]


def parse(args):
    f = {}
    kind = args.get("kind")
    if kind:
        if kind not in ("food", "drink"):
            return None, "kind must be one of food, drink"
        f["kind"] = kind
    for name, allowed in WORD_LISTS.items():
        values = many(args, name)
        bad = [v for v in values if allowed and v not in allowed]
        if bad:
            return None, f"unknown {name}: {bad[0]}"
        if values:
            f[name] = values
    # The limits and words of server/gluttonyRules.py parseFilters, so the app meets the server's refusals here too.
    cuisines = f.get("cuisine", [])
    if any(len(c) > 40 for c in cuisines) or len(cuisines) > 10:
        return None, "cuisine takes up to 10 names of at most 40 characters"
    difficulties = many(args, "difficulty")
    if any(d not in ("1", "2", "3") for d in difficulties):
        return None, "difficulty must be 1, 2 or 3"
    if difficulties:
        f["difficulty"] = [int(d) for d in difficulties]
    pageSize = args.get("pageSize")
    if pageSize not in (None, "") and (not re.fullmatch(r"[0-9]{1,9}", pageSize) or not 1 <= int(pageSize) <= 60):
        return None, "pageSize must be a whole number from 1 to 60"
    f["pageSize"] = int(pageSize or 24)
    try:
        for name in ("include", "exclude"):
            values = [int(v) for v in many(args, name)]
            if values:
                f[name] = values
        if args.get("maxMinutes"):
            f["maxMinutes"] = int(args["maxMinutes"])
        f["page"] = max(1, int(args.get("page") or 1))
    except ValueError:
        return None, "a number filter is not a whole number"
    f["q"] = (args.get("q") or "").strip()
    if len(f["q"]) > 100:
        return None, "q must be at most 100 characters"
    sort = args.get("sort") or ("relevance" if f["q"] else "shuffle")
    if sort not in ("relevance", "quickest", "shuffle"):
        return None, "sort must be one of relevance, quickest, shuffle"
    f["sort"] = "shuffle" if sort == "relevance" and not f["q"] else sort
    profile = args.get("profile") or "on"
    if profile not in ("on", "off"):
        return None, "profile must be on or off"
    f["profile"] = profile == "on"
    return f, None


def withProfile(f, rid):
    reader = state["readers"][rid]
    merged = dict(f)
    for key, saved in (("diet", reader["diets"]), ("avoid", reader["avoid"])):
        values = list(f.get(key, [])) + [v for v in saved if v not in f.get(key, [])]
        if values:
            merged[key] = values
    return merged


def words(q):
    return [w for w in re.findall(r"[^\W_]+", (q or "").lower()) if len(w) >= 3]


def matches(r, f):
    # A recipe its source removed is never browsed, picked or offered (it still opens for its saver).
    if r["id"] in state["removed"]:
        return False
    if "kind" in f and r["kind"] != f["kind"]:
        return False
    for key in ("course", "cuisine", "alcohol"):
        if key in f and r[key] not in f[key]:
            return False
    if "difficulty" in f and r["difficulty"] not in f["difficulty"]:
        return False
    if "maxMinutes" in f and (r["totalMinutes"] is None or r["totalMinutes"] > f["maxMinutes"]):
        return False
    for tagType in ("flavour", "occasion"):
        if tagType in f and not set(f[tagType]) & set(r["tags"].get(tagType, [])):
            return False
    # The safety rule: only a recipe whose every ingredient is known can meet a diet or avoid an allergen.
    if ("diet" in f or "avoid" in f) and not r["facts"]["complete"]:
        return False
    if not set(f.get("diet", [])) <= set(r["facts"]["diets"]):
        return False
    if set(f.get("avoid", [])) & set(r["facts"]["contains"]):
        return False
    held = {i["ingredientId"] for i in r["ingredients"] if i["ingredientId"]}
    if any(i not in held for i in f.get("include", [])) or held & set(f.get("exclude", [])):
        return False
    if f.get("q"):
        text = (r["title"] + " " + " ".join(i["line"] for i in r["ingredients"])).lower()
        found = words(f["q"])
        if found and not all(w in text for w in found):
            return False
        if not found and f["q"].lower() not in r["title"].lower():
            return False
    return True


def shuffleKey(rid, *parts):
    return hashlib.sha1(":".join([str(rid), *map(str, parts)]).encode()).hexdigest()


def ordered(rows, f):
    today = datetime.now(timezone.utc).date().isoformat()
    if f["sort"] == "quickest":
        return sorted(rows, key=lambda r: (r["totalMinutes"] is None, r["totalMinutes"] or 0, r["title"]))
    if f["sort"] == "relevance":
        found = words(f["q"])
        return sorted(rows, key=lambda r: (not all(w in r["title"].lower() for w in found), shuffleKey(r["id"], today)))
    return sorted(rows, key=lambda r: shuffleKey(r["id"], today))


def tile(r):
    return {key: r[key] for key in ("id", "kind", "title", "course", "cuisine", "totalMinutes", "timeFrom",
                                    "difficulty", "hasImage", "source")}


def found(args):
    f, problem = parse(args)
    if problem:
        return None, None, problem
    if f["profile"]:
        f = withProfile(f, uid())
    return f, [r for r in state["recipes"].values() if matches(r, f)], None


@app.route(API + "/recipes")
def recipes():
    f, rows, problem = found(request.args)
    if problem:
        return fail("error", 400, problem)
    rows = ordered(rows, f)
    start = (f["page"] - 1) * f["pageSize"]
    reader = state["readers"][uid()]
    return ok({"total": len(rows), "page": f["page"], "pageSize": f["pageSize"],
               "recipes": [flagged(tile(r), reader) for r in rows[start:start + f["pageSize"]]]})


@app.route(API + "/recipes/<int:rid>")
def recipe(rid):
    reader = state["readers"][uid()]
    r = visible(rid, reader)
    if not r:
        return fail("error", 404, "no such recipe")
    detail = dict(r)
    detail["versions"] = [flagged(dict(v), reader) for v in r.get("versions", []) if v["id"] not in state["removed"]]
    detail["removed"] = rid in state["removed"]
    detail["mine"] = mineOf(reader, rid)
    return ok(detail)


@app.route(API + "/random")
def randomRecipe():
    f, rows, problem = found(request.args)
    if problem:
        return fail("error", 400, problem)
    return ok({"recipe": flagged(tile(random.choice(rows)), state["readers"][uid()]) if rows else None})


def counts(values):
    tally = {}
    for value in values:
        if value is not None:
            tally[value] = tally.get(value, 0) + 1
    return [{"value": v, "count": n} for v, n in sorted(tally.items(), key=lambda kv: (-kv[1], str(kv[0])))]


@app.route(API + "/filters")
def filters():
    # The whole catalog's counts leave out what the source has removed, as the server's do.
    shown = [r for r in state["recipes"].values() if r["id"] not in state["removed"]]
    return ok({"kinds": counts(r["kind"] for r in shown), "courses": counts(r["course"] for r in shown),
               "cuisines": counts(r["cuisine"] for r in shown), "difficulties": counts(r["difficulty"] for r in shown),
               "flavours": counts(t for r in shown for t in r["tags"].get("flavour", [])),
               "occasions": counts(t for r in shown for t in r["tags"].get("occasion", [])),
               "diets": counts(d for r in shown for d in r["facts"]["diets"]), "avoid": list(CONTAINS)})


@app.route(API + "/ingredients")
def ingredients():
    q = (request.args.get("q") or "").strip().lower()
    if not 1 <= len(q) <= 60:
        return fail("error", 400, "q must be 1 to 60 characters")
    names = {}
    for r in state["recipes"].values():
        for i in r["ingredients"]:
            if i["ingredientId"] and i["name"] and q in i["name"].lower():
                names[i["ingredientId"]] = i["name"]
    rows = sorted(names.items(), key=lambda kv: (len(kv[1]), kv[1]))[:20]
    return ok([{"id": i, "name": n} for i, n in rows])


@app.route(API + "/home")
def home():
    if os.environ.get("STUB_HOME_DOWN"):
        return fail("error", 500, "home is down")
    profile = request.args.get("profile") or "on"
    if profile not in ("on", "off"):
        return fail("error", 400, "profile must be on or off")
    tz = request.args.get("tz") or ""
    try:
        zone = ZoneInfo(tz) if tz else timezone.utc
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = timezone.utc
    day = datetime.now(timezone.utc).astimezone(zone).date().isoformat()
    reader = state["readers"][uid()]
    f = {"kind": "food", "course": list(HOME_COURSES)}
    if profile == "on":
        f = withProfile(f, uid())
    # The server's 30-day rule: nothing made after this day is today's temptation or one of today's picks.
    cutoff = (date.fromisoformat(day) - timedelta(days=30)).isoformat()
    recent = {m["rid"] for m in reader["devoured"] if m["on"] > cutoff}
    rows = [r for r in state["recipes"].values() if r["hasImage"] and matches(r, f) and r["id"] not in recent]
    rows = sorted(rows, key=lambda r: shuffleKey(r["id"], uid(), day))[:9]
    tiles = [flagged(tile(r), reader) for r in rows]
    cravings = [savedTile(state["recipes"][rid], reader) for rid in reader["lists"][0]["items"]
                if rid in state["recipes"]][:12]
    last = {}
    for m in reader["devoured"]:
        last[m["rid"]] = max(last.get(m["rid"], ("", 0)), (m["on"], m["id"]))
    again = [savedTile(state["recipes"][rid], reader)
             for rid in sorted(last, key=lambda rid: last[rid], reverse=True) if rid in state["recipes"]][:12]
    return ok({"date": day, "pick": tiles[0] if tiles else None, "picks": tiles[1:], "cravings": cravings,
               "again": again})


def picture(rid, folder):
    if os.environ.get("STUB_SLOW"):
        time.sleep(int(os.environ["STUB_SLOW"]) / 1000)
    target = state["folder"] / folder / f"{rid}.jpg"
    if os.environ.get("STUB_PICTURES_FAIL") or not target.is_file() or not visible(rid, state["readers"][uid()]):
        return fail("error", 404, "no picture")
    return send_file(target, mimetype="image/jpeg")


@app.route(API + "/images/<int:rid>")
def image(rid):
    return picture(rid, "images")


@app.route(API + "/thumbs/<int:rid>")
def thumb(rid):
    return picture(rid, "thumbs")


# ---- What you keep (the server's gluttonyKept.py and its Lists and Yours routes) ----

CLIENT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
ON_PROBLEM = "on must be a date (YYYY-MM-DD), not after tomorrow"
STARS_PROBLEM = "stars must be a whole number from 1 to 5, or null"


def positiveId(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 2 ** 31 - 1 else None


def keptBy(reader, rid):
    """In a list (Cravings included), devoured or noted. A star alone does not keep a removed recipe."""
    return (any(rid in l["items"] for l in reader["lists"]) or any(m["rid"] == rid for m in reader["devoured"])
            or rid in reader["notes"])


def visible(rid, reader):
    r = state["recipes"].get(rid)
    if not r or (rid in state["removed"] and not keptBy(reader, rid)):
        return None
    return r


def flagged(t, reader):
    rid = t["id"]
    t.update({"craving": rid in reader["lists"][0]["items"],
              "devouredCount": sum(1 for m in reader["devoured"] if m["rid"] == rid),
              "stars": reader["ratings"].get(rid)})
    return t


def savedTile(r, reader):
    return flagged(dict(tile(r), removed=r["id"] in state["removed"]), reader)


def mineOf(reader, rid):
    marks = sorted((m for m in reader["devoured"] if m["rid"] == rid), key=lambda m: (m["on"], m["id"]), reverse=True)
    return {"craving": rid in reader["lists"][0]["items"],
            "lists": [l["id"] for l in reader["lists"] if l["kind"] == "custom" and rid in l["items"]],
            "devoured": [{"id": m["id"], "on": m["on"]} for m in marks],
            "stars": reader["ratings"].get(rid), "note": reader["notes"].get(rid)}


def ownList(reader, listId):
    return next((l for l in reader["lists"] if l["id"] == listId), None) if listId else None


def listRow(l):
    return {"id": l["id"], "title": l["title"], "kind": l["kind"], "count": len(l["items"])}


def listTitle(value):
    title = value.strip() if isinstance(value, str) else ""
    return (title, None) if 1 <= len(title) <= 60 else (None, "a list title is 1 to 60 characters")


def pageArgs(args):
    values = []
    for name, default, high in (("page", 1, 10000), ("pageSize", 24, 60)):
        raw = args.get(name)
        if raw in (None, ""):
            values.append(default)
        elif not re.fullmatch(r"[0-9]{1,9}", raw) or not 1 <= int(raw) <= high:
            return None, None, f"{name} must be a whole number from 1 to {high}"
        else:
            values.append(int(raw))
    return values[0], values[1], None


def paged(rows, page, pageSize):
    start = (page - 1) * pageSize
    return rows[start:start + pageSize]


@app.route(API + "/lists")
def lists():
    return ok([listRow(l) for l in state["readers"][uid()]["lists"]])


@app.route(API + "/lists/create", methods=["POST"])
def listsCreate():
    title, problem = listTitle(body().get("title"))
    if problem:
        return fail("error", 400, problem)
    with lock:
        reader = state["readers"][uid()]
        if len(reader["lists"]) >= 50:
            return fail("error", 400, "you can have at most 50 lists")
        made = {"id": nextId("nextListId"), "title": title, "kind": "custom", "items": []}
        reader["lists"].append(made)
    return ok(listRow(made))


@app.route(API + "/lists/rename", methods=["POST"])
def listsRename():
    data = body()
    listId = positiveId(data.get("id"))
    if not listId:
        return fail("error", 400, "id must be a list id")
    title, problem = listTitle(data.get("title"))
    if problem:
        return fail("error", 400, problem)
    row = ownList(state["readers"][uid()], listId)
    if not row:
        return fail("error", 404, "no such list")
    if row["kind"] == "cravings":
        return fail("error", 400, "Cravings can't be renamed")
    row["title"] = title
    return ok(listRow(row))


@app.route(API + "/lists/delete", methods=["POST"])
def listsDelete():
    listId = positiveId(body().get("id"))
    if not listId:
        return fail("error", 400, "id must be a list id")
    reader = state["readers"][uid()]
    row = ownList(reader, listId)
    if not row:
        return fail("error", 404, "no such list")
    if row["kind"] == "cravings":
        return fail("error", 400, "Cravings can't be deleted")
    reader["lists"].remove(row)
    return ok()


@app.route(API + "/lists/reorder", methods=["POST"])
def listsReorder():
    data = body()
    listId, after = positiveId(data.get("id")), data.get("after")
    afterId = positiveId(after)
    if not listId or (after is not None and not afterId):
        return fail("error", 400, "id must be a list id, and after a list id or null")
    if afterId == listId:
        return fail("error", 400, "a list can't go after itself")
    reader = state["readers"][uid()]
    moving = ownList(reader, listId)
    if not moving:
        return fail("error", 404, "no such list")
    if moving["kind"] == "cravings":
        return fail("error", 400, "Cravings stays first")
    anchor = ownList(reader, afterId) if afterId else None
    if afterId and not anchor:
        return fail("error", 404, "no such list")
    reader["lists"].remove(moving)
    at = 1 if anchor is None or anchor["kind"] == "cravings" else reader["lists"].index(anchor) + 1
    reader["lists"].insert(at, moving)
    return ok()


def itemIds(data):
    return positiveId(data.get("listId")), positiveId(data.get("recipeId"))


@app.route(API + "/lists/items/add", methods=["POST"])
def itemsAdd():
    listId, rid = itemIds(body())
    if not listId or not rid:
        return fail("error", 400, "listId and recipeId must be ids")
    reader = state["readers"][uid()]
    row = ownList(reader, listId)
    if not row:
        return fail("error", 404, "no such list")
    if not visible(rid, reader):
        return fail("error", 404, "no such recipe")
    if rid not in row["items"]:
        if len(row["items"]) >= 2000:
            return fail("error", 400, "a list holds at most 2000 recipes")
        row["items"].insert(0, rid)
    return ok({"listId": listId, "recipeId": rid, "count": len(row["items"])})


@app.route(API + "/lists/items/remove", methods=["POST"])
def itemsRemove():
    listId, rid = itemIds(body())
    if not listId or not rid:
        return fail("error", 400, "listId and recipeId must be ids")
    row = ownList(state["readers"][uid()], listId)
    if not row:
        return fail("error", 404, "no such list")
    if rid in row["items"]:
        row["items"].remove(rid)
    return ok({"listId": listId, "recipeId": rid, "count": len(row["items"])})


@app.route(API + "/lists/items/reorder", methods=["POST"])
def itemsReorder():
    data = body()
    listId, rid = itemIds(data)
    after = data.get("after")
    afterId = positiveId(after)
    if not listId or not rid or (after is not None and not afterId):
        return fail("error", 400, "listId and recipeId must be ids, and after a recipe id or null")
    if afterId == rid:
        return fail("error", 400, "a recipe can't go after itself")
    row = ownList(state["readers"][uid()], listId)
    if not row:
        return fail("error", 404, "no such list")
    if rid not in row["items"] or (afterId and afterId not in row["items"]):
        return fail("error", 404, "that recipe is not on this list")
    row["items"].remove(rid)
    row["items"].insert(0 if not afterId else row["items"].index(afterId) + 1, rid)
    return ok()


@app.route(API + "/lists/<int:listId>/recipes")
def listsRecipes(listId):
    page, pageSize, problem = pageArgs(request.args)
    if problem:
        return fail("error", 400, problem)
    reader = state["readers"][uid()]
    row = ownList(reader, listId)
    if not row:
        return fail("error", 404, "no such list")
    rows = [state["recipes"][rid] for rid in row["items"] if rid in state["recipes"]]
    return ok({"total": len(row["items"]), "page": page, "pageSize": pageSize, "list": listRow(row),
               "recipes": [savedTile(r, reader) for r in paged(rows, page, pageSize)]})


def madeOn(value, now=None):
    """The day, if it is a date up to tomorrow; a batch passes its one `now` (nowStamp's text) so every change in
    it is judged against the same moment."""
    if not isinstance(value, str) or not DAY.fullmatch(value):
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return None
    today = date.fromisoformat(now[:10]) if now else datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    return value if date(1900, 1, 1) <= day <= tomorrow else None


def storeMark(reader, rid, on, clientId):
    """(mark, already, problem): the mark with this clientId, stored now or found from before (as the server's
    storeMark)."""
    if not visible(rid, reader):
        return None, False, "no such recipe"
    mark = next((m for m in reader["devoured"] if m["clientId"] == clientId), None)
    if mark:
        return mark, True, None
    # A clientId is unique across every account: one held by someone else is refused, and their mark is neither
    # shown nor changed.
    if any(m["clientId"] == clientId for other in state["readers"].values() for m in other["devoured"]):
        return None, False, "that clientId is in use"
    mark = {"id": nextId("nextMarkId"), "rid": rid, "on": on, "clientId": clientId}
    reader["devoured"].append(mark)
    return mark, False, None


@app.route(API + "/devoured/add", methods=["POST"])
def devouredAdd():
    data = body()
    rid = positiveId(data.get("recipeId"))
    if not rid:
        return fail("error", 400, "recipeId must be a recipe id")
    on = madeOn(data.get("on"))
    if not on:
        return fail("error", 400, ON_PROBLEM)
    clientId = data.get("clientId")
    if not isinstance(clientId, str) or not CLIENT_ID.fullmatch(clientId):
        return fail("error", 400, "clientId must be a UUID")
    with lock:
        reader = state["readers"][uid()]
        mark, already, problem = storeMark(reader, rid, on, clientId)
        if problem:
            return fail("error", 404 if problem == "no such recipe" else 409, problem)
        count = sum(1 for m in reader["devoured"] if m["rid"] == mark["rid"])
    return ok({"id": mark["id"], "recipeId": mark["rid"], "on": mark["on"], "count": count, "already": already})


@app.route(API + "/devoured/remove", methods=["POST"])
def devouredRemove():
    markId = positiveId(body().get("id"))
    if not markId:
        return fail("error", 400, "id must be a Devoured mark's id")
    reader = state["readers"][uid()]
    mark = next((m for m in reader["devoured"] if m["id"] == markId), None)
    if not mark:
        return fail("error", 404, "no such Devoured mark")
    reader["devoured"].remove(mark)
    count = sum(1 for m in reader["devoured"] if m["rid"] == mark["rid"])
    return ok({"id": markId, "recipeId": mark["rid"], "count": count})


@app.route(API + "/devoured")
def devouredHistory():
    page, pageSize, problem = pageArgs(request.args)
    if problem:
        return fail("error", 400, problem)
    sort = request.args.get("sort") or "recent"
    if sort not in ("recent", "stars"):
        return fail("error", 400, "sort must be recent or stars")
    reader = state["readers"][uid()]
    marks = sorted(reader["devoured"], key=lambda m: (m["on"], m["id"]), reverse=True)
    if sort == "stars":
        # Stable, so marks with the same stars stay newest first; unrated last.
        marks.sort(key=lambda m: (reader["ratings"].get(m["rid"]) is None, -(reader["ratings"].get(m["rid"]) or 0)))
    rows = [dict(savedTile(state["recipes"][m["rid"]], reader), devouredId=m["id"], on=m["on"])
            for m in marks if m["rid"] in state["recipes"]]
    return ok({"total": len(marks), "page": page, "pageSize": pageSize, "recipes": paged(rows, page, pageSize)})


@app.route(API + "/rating", methods=["POST"])
def rating():
    data = body()
    rid = positiveId(data.get("recipeId"))
    if not rid:
        return fail("error", 400, "recipeId must be a recipe id")
    stars = data.get("stars")
    if "stars" not in data or (stars is not None and (not isinstance(stars, int) or isinstance(stars, bool)
                                                       or not 1 <= stars <= 5)):
        return fail("error", 400, STARS_PROBLEM)
    reader = state["readers"][uid()]
    if not visible(rid, reader):
        return fail("error", 404, "no such recipe")
    if stars is None:
        reader["ratings"].pop(rid, None)
    else:
        reader["ratings"][rid] = stars
    reader["changedAt"][f"stars:{rid}"] = nowStamp()
    return ok({"recipeId": rid, "stars": stars})


@app.route(API + "/note", methods=["POST"])
def noteRoute():
    data = body()
    rid = positiveId(data.get("recipeId"))
    if not rid:
        return fail("error", 400, "recipeId must be a recipe id")
    if not isinstance(data.get("text"), str):
        return fail("error", 400, "text must be text")
    # Python counts characters as the server and MySQL do: an emoji is one.
    text = data["text"].strip()
    if len(text) > 2000:
        return fail("error", 400, "a note is at most 2000 characters")
    reader = state["readers"][uid()]
    if not visible(rid, reader):
        return fail("error", 404, "no such recipe")
    if text:
        reader["notes"][rid] = text
    else:
        reader["notes"].pop(rid, None)
    reader["changedAt"][f"note:{rid}"] = nowStamp()
    return ok({"recipeId": rid, "note": text or None})


# ---- what the app did offline ----

AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{3})?Z")
AT_PROBLEM = "at must be a UTC time (YYYY-MM-DDTHH:MM:SS.sssZ)"


def syncAt(value, now):
    """The change's moment as the app's text with milliseconds (so it compares with nowStamp), clamped to the
    batch's one now, as the server does."""
    if not isinstance(value, str) or not AT.fullmatch(value):
        return None
    try:
        datetime.fromisoformat(value[:-1])
    except ValueError:
        return None
    full = value if "." in value else value[:-1] + ".000Z"
    return min(full, now)


def applyChange(reader, change, now):
    refused = lambda message: {"result": "refused", "message": message}
    kind = change.get("op")
    if kind not in ("devoured", "stars", "note"):
        return refused("op must be devoured, stars or note")
    rid = positiveId(change.get("recipeId"))
    if not rid:
        return refused("recipeId must be a recipe id")
    at = syncAt(change.get("at"), now)
    if not at:
        return refused(AT_PROBLEM)
    if kind == "devoured":
        on = madeOn(change.get("on"), now)
        if not on:
            return refused(ON_PROBLEM)
        clientId = change.get("clientId")
        if not isinstance(clientId, str) or not CLIENT_ID.fullmatch(clientId):
            return refused("clientId must be a UUID")
        mark, already, problem = storeMark(reader, rid, on, clientId)
        if problem:
            return refused(problem)
        count = sum(1 for m in reader["devoured"] if m["rid"] == mark["rid"])
        return {"result": "already" if already else "applied", "id": mark["id"], "recipeId": mark["rid"],
                "on": mark["on"], "count": count}
    key = f"{kind}:{rid}"
    if kind == "stars":
        stars = change.get("stars")
        if "stars" not in change or (stars is not None and (not isinstance(stars, int) or isinstance(stars, bool)
                                                             or not 1 <= stars <= 5)):
            return refused(STARS_PROBLEM)
        if not visible(rid, reader):
            return refused("no such recipe")
        if reader["changedAt"].get(key, "") >= at:
            return {"result": "already", "recipeId": rid, "stars": reader["ratings"].get(rid)}
        if stars is None:
            reader["ratings"].pop(rid, None)
        else:
            reader["ratings"][rid] = stars
        reader["changedAt"][key] = at
        return {"result": "applied", "recipeId": rid, "stars": stars}
    if not isinstance(change.get("text"), str):
        return refused("text must be text")
    text = change["text"].strip()
    if len(text) > 2000:
        return refused("a note is at most 2000 characters")
    if not visible(rid, reader):
        return refused("no such recipe")
    if reader["changedAt"].get(key, "") >= at:
        return {"result": "already", "recipeId": rid, "note": reader["notes"].get(rid)}
    if text:
        reader["notes"][rid] = text
    else:
        reader["notes"].pop(rid, None)
    reader["changedAt"][key] = at
    return {"result": "applied", "recipeId": rid, "note": text or None}


@app.route(API + "/sync/batch", methods=["POST"])
def syncBatch():
    ops = body().get("ops")
    if not isinstance(ops, list) or not 1 <= len(ops) <= 500 or not all(isinstance(op, dict) for op in ops):
        return fail("error", 400, "ops must be a list of 1 to 500 changes")
    with lock:
        reader = state["readers"][uid()]
        now = nowStamp()
        order = sorted(range(len(ops)), key=lambda i: syncAt(ops[i].get("at"), now) or "")
        results = [None] * len(ops)
        for index in order:
            results[index] = applyChange(reader, ops[index], now)
    return ok({"results": results})


@app.route(API + "/saved/manifest")
def savedManifest():
    raw = request.args.get("extra") or ""
    parts = raw.split(",") if raw else []
    if len(parts) > 200 or not all(re.fullmatch(r"[0-9]{1,9}", p) and int(p) > 0 for p in parts):
        return fail("error", 400, "extra must be up to 200 recipe ids, comma separated")
    reader = state["readers"][uid()]
    lists = [{"id": l["id"], "title": l["title"], "kind": l["kind"], "recipeIds": list(l["items"])}
             for l in reader["lists"]]
    listed = {rid for l in lists for rid in l["recipeIds"]}
    recipes = []
    for rid in sorted(listed | {int(p) for p in parts}):
        if rid not in state["recipes"] or (rid not in listed and not visible(rid, reader)):
            continue
        recipes.append({"id": rid, "updatedAt": state["takenAt"], "removed": rid in state["removed"],
                        "mine": mineOf(reader, rid)})
    return ok({"lists": lists, "recipes": recipes})


reset()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, threaded=True)
