"""Stand-in for Gluttony's app API (docs/api.md), for screenshot runs and trying the app without plutus or
anyone's account. It listens on 127.0.0.1:5079; tests/stub/grab.ps1 starts it.

It serves the recipes in snapshot/ (taken by snapshot.py from the LAN read API; never committed) or, without one,
the four in fixture/recipes.json. Filters, the profile and the safety rule follow the server's rules, except that
include and exclude match only the ingredient itself, not its children.

Sign in as stub / stub-password (UID 7, token "stub"). Sign up with the key "stub-key" (any other key is 403
invalid_key); the username "taken" is 409. Signing out makes /device/identify say "new" until the next /auth.

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
from datetime import datetime, timezone
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
    recipes = json.loads((folder / "recipes.json").read_text(encoding="utf-8"))["recipes"]
    diets, _, avoid = (os.environ.get("STUB_DIET") or "").partition(";")
    state.clear()
    state.update({
        "folder": folder,
        "recipes": {r["id"]: r for r in recipes},
        "readers": {UID: {"username": "stub", "password": "stub-password",
                          "diets": [d for d in diets.split(",") if d], "avoid": [a for a in avoid.split(",") if a]}},
        "tokens": {TOKEN: UID},
        "deviceUid": None if os.environ.get("STUB_NEW_DEVICE") else UID,
        "otherDevice": True,
        "nextUid": 100,
    })


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
            state["readers"][rid] = {"username": username, "password": password, "diets": [], "avoid": []}
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
    return ok({"total": len(rows), "page": f["page"], "pageSize": f["pageSize"],
               "recipes": [tile(r) for r in rows[start:start + f["pageSize"]]]})


@app.route(API + "/recipes/<int:rid>")
def recipe(rid):
    r = state["recipes"].get(rid)
    return ok(r) if r else fail("error", 404, "no such recipe")


@app.route(API + "/random")
def randomRecipe():
    f, rows, problem = found(request.args)
    if problem:
        return fail("error", 400, problem)
    return ok({"recipe": tile(random.choice(rows)) if rows else None})


def counts(values):
    tally = {}
    for value in values:
        if value is not None:
            tally[value] = tally.get(value, 0) + 1
    return [{"value": v, "count": n} for v, n in sorted(tally.items(), key=lambda kv: (-kv[1], str(kv[0])))]


@app.route(API + "/filters")
def filters():
    shown = list(state["recipes"].values())
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
    tz = request.args.get("tz") or ""
    try:
        zone = ZoneInfo(tz) if tz else timezone.utc
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = timezone.utc
    day = datetime.now(timezone.utc).astimezone(zone).date().isoformat()
    f = {"kind": "food", "course": list(HOME_COURSES)}
    if (request.args.get("profile") or "on") == "on":
        f = withProfile(f, uid())
    rows = [r for r in state["recipes"].values() if r["hasImage"] and matches(r, f)]
    rows = sorted(rows, key=lambda r: shuffleKey(r["id"], uid(), day))[:9]
    tiles = [tile(r) for r in rows]
    return ok({"date": day, "pick": tiles[0] if tiles else None, "picks": tiles[1:]})


def picture(rid, folder):
    if os.environ.get("STUB_SLOW"):
        time.sleep(int(os.environ["STUB_SLOW"]) / 1000)
    target = state["folder"] / folder / f"{rid}.jpg"
    if os.environ.get("STUB_PICTURES_FAIL") or not target.is_file():
        return fail("error", 404, "no picture")
    return send_file(target, mimetype="image/jpeg")


@app.route(API + "/images/<int:rid>")
def image(rid):
    return picture(rid, "images")


@app.route(API + "/thumbs/<int:rid>")
def thumb(rid):
    return picture(rid, "thumbs")


reset()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, threaded=True)
