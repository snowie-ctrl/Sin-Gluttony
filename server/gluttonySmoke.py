"""
The real-MySQL smoke test, run on plutus against a scratch database before
gluttonyDB exists (the route tests only ever meet a fake connection):

    cd /database/API && /database/venv/bin/python -m util.gluttonySmoke --database gluttony_smoke

Every connection is switched to the scratch database, and pictures go to a
temporary folder, so nothing touches gluttonyDB or /pool. Prints PASS or FAIL
per step and stops at the first failure.
"""
import argparse
import re
import secrets
import sys
import tempfile
from pathlib import Path

import flask

from . import DBUtils, gluttonyAdminRoutes as admin, gluttonyRoutes as read, gluttonyUserRoutes as user


class SmokeFailed(Exception):
    pass


def scratchConnections(database, connect):
    """Wraps connect so every connection switches to `database`. Only a name containing "smoke" is accepted, so
    gluttonyDB, pageturnerDB and every other real database are refused."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", database or "") or "smoke" not in database.lower():
        raise ValueError("the smoke test only runs on a scratch database whose name contains smoke, never gluttonyDB")

    def switched(name):
        try:
            conn = connect(name)
            cur = conn.cursor()
            cur.execute(f"USE `{database}`")
            cur.close()
        except Exception as e:
            print(f"smoke: could not open the scratch database: {type(e).__name__}: {e}", file=sys.stderr)
            raise
        return conn
    return switched


def check(condition, message):
    if not condition:
        raise SmokeFailed(message)


def call(client, method, path, body=None, expect=200):
    answer = client.open(path, method=method, json=body)
    # The body is only read on failure, and leniently: a picture is not text.
    if answer.status_code != expect:
        text = answer.get_data()[:200].decode("utf-8", "replace")
        raise SmokeFailed(f"{method} {path} gave {answer.status_code}: {text}")
    return answer.get_json(silent=True) if answer.mimetype == "application/json" else answer


def payload(ingredientIds, sourceId="smoke-1", title="Smoke Cheese Toast"):
    return {"key": f"mealdb:{sourceId}", "source": "mealdb", "sourceId": sourceId, "kind": "food", "title": title,
            "dishKey": "smoke cheese toast", "course": "main", "cuisine": "British", "servings": 2,
            "servingsFrom": "source", "prepMinutes": None, "cookMinutes": None, "totalMinutes": 10, "timeFrom": "rule",
            "difficulty": 1, "difficultyFrom": "rule", "alcohol": None, "glass": None,
            "imagePath": "0123456789abcdef0123.jpg", "imageCredit": "smoke", "videoUrl": None,
            "sourceUrl": None, "licence": "smoke", "credit": "smoke test", "searchText": f"{title} bread cheddar",
            "ingredients": [
                {"line": "2 slices bread", "quantity": 2, "quantityMax": None, "unit": "slice",
                 "ingredientId": ingredientIds["bread"], "unknownName": None, "note": None, "optional": False, "group": None},
                {"line": "50 g cheddar", "quantity": 50, "quantityMax": None, "unit": "g",
                 "ingredientId": ingredientIds["cheddar"], "unknownName": None, "note": None, "optional": False, "group": None},
                {"line": "1 smoke berry", "quantity": 1, "quantityMax": None, "unit": None, "ingredientId": None,
                 "unknownName": "smoke berry", "note": None, "optional": True, "group": None}],
            "steps": [{"text": "Toast.", "group": None}, {"text": "Melt.", "group": None}],
            "tags": [{"type": "flavour", "tag": "savoury", "origin": "rule"}],
            "facts": {"complete": False, "contains": [], "diets": []}, "contentHash": "b" * 40}


def steps(media):
    A, R = "/api/gluttony-admin", "/api/gluttony"

    def seed(client, state):
        answer = call(client, "POST", f"{A}/ingredients/seed", {"ingredients": [
            {"name": "smoke bread", "parent": None, "category": "grain", "contains": ["gluten"], "aliases": ["smoke bread"]},
            {"name": "smoke cheese", "parent": None, "category": "dairy", "contains": ["dairy"], "aliases": ["smoke cheese"]},
            {"name": "smoke cheddar", "parent": "smoke cheese", "category": None, "contains": [], "aliases": ["smoke cheddar"]}]})
        check(answer["updated"] == 0 and answer["kept"] == 0, "the scratch database is not empty: drop and recreate it")
        check(answer["added"] == 3, f"seed added {answer}")
        table = call(client, "GET", f"{A}/ingredients")
        byName = {i["name"]: i for i in table["ingredients"]}
        check(byName["smoke cheddar"]["parentId"] == byName["smoke cheese"]["id"], "cheddar is not under cheese")
        state["ids"] = {"bread": byName["smoke bread"]["id"], "cheddar": byName["smoke cheddar"]["id"],
                        "cheese": byName["smoke cheese"]["id"]}
        return "3 ingredients, cheddar under cheese"

    def store(client, state):
        answer = call(client, "POST", f"{A}/recipes/batch", {"recipes": [payload(state["ids"])]})
        check(answer["stored"] == ["mealdb:smoke-1"], f"batch: {answer}")
        again = call(client, "POST", f"{A}/recipes/batch", {"recipes": [payload(state["ids"], title="Smoke Toast")]})
        check(again["stored"] == ["mealdb:smoke-1"], f"resend: {again}")
        shown = call(client, "GET", f"{A}/state")["recipes"]
        check(len(shown) == 1, f"a resend made {len(shown)} rows")
        return "stored, resent, still one row"

    def unknown(client, state):
        rows = call(client, "GET", f"{A}/ingredients/unknown")["unknown"]
        check(rows and rows[0]["name"] == "smoke berry", f"unknown: {rows}")
        call(client, "POST", f"{A}/ingredients/map", {"alias": "smoke berry", "create": {
            "name": "smoke berry", "category": "fruit", "contains": []}})
        return "listed and mapped"

    def account(client, state):
        # The owner inserts keys by hand; the smoke test does the same on the scratch database.
        key = "smoke-key-" + secrets.token_hex(8)
        conn = DBUtils.initConnection("gluttony")
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO LoginKeys (KeyValue) VALUES (%s)", (key,))
            conn.commit()
            cur.close()
        finally:
            conn.close()
        fingerprint = "smoke-device-" + secrets.token_hex(8)
        made = call(client, "POST", f"{R}/auth", {"username": "smoke-user", "password": "smoke-password",
                                                  "fingerprint": fingerprint, "key": key})
        check(made.get("status") == "ok" and made.get("token"), f"sign-up: {made}")
        call(client, "POST", f"{R}/auth", {"username": "smoke-other", "password": "smoke-password",
                                           "fingerprint": fingerprint, "key": key}, expect=403)
        again = call(client, "POST", f"{R}/device/identify", {"fingerprint": fingerprint})
        check(again.get("UID") == made["UID"], f"identify: {again}")
        client.environ_base["HTTP_X_SESSION_TOKEN"] = again["token"]
        state["fingerprint"] = fingerprint
        return "signed up with a key, the key is spent, the device signs itself in"

    def browse(client, state):
        found = call(client, "GET", f"{R}/recipes?q=smoke%20toast")["data"]
        check(found["total"] == 1, f"search found {found['total']}")
        state["recipeId"] = found["recipes"][0]["id"]
        check(call(client, "GET", f"{R}/recipes?avoid=dairy")["data"]["total"] == 0,
              "an incomplete recipe passed an allergen filter")
        check(call(client, "GET", f"{R}/recipes?include={state['ids']['cheese']}")["data"]["total"] == 1,
              "include did not find cheddar under cheese")
        detail = call(client, "GET", f"{R}/recipes/{state['recipeId']}")["data"]
        check(len(detail["ingredients"]) == 3 and detail["title"] == "Smoke Toast", f"detail: {detail}")
        call(client, "GET", f"{R}/filters")
        (media / "images").mkdir(parents=True, exist_ok=True)
        (media / "images" / "0123456789abcdef0123.jpg").write_bytes(b"\xff\xd8smoke")
        picture = call(client, "GET", f"{R}/images/{state['recipeId']}")
        check(picture.data == b"\xff\xd8smoke", "the picture did not come back")
        return "search, allergen safety, include, detail, filters, picture"

    def diet(client, state):
        call(client, "POST", f"{R}/me/diet", {"diets": ["vegetarian"], "avoid": []})
        check(call(client, "GET", f"{R}/me/diet")["data"] == {"diets": ["vegetarian"], "avoid": []}, "not kept")
        check(call(client, "GET", f"{R}/recipes?q=smoke%20toast")["data"]["total"] == 0,
              "the profile let an incomplete recipe through")
        check(call(client, "GET", f"{R}/recipes?q=smoke%20toast&profile=off")["data"]["total"] == 1,
              "profile=off still filtered")
        call(client, "POST", f"{R}/me/diet", {"diets": [], "avoid": []})
        return "kept, applied with the safety rule, switched off for one search"

    def home(client, state):
        data = call(client, "GET", f"{R}/home?tz=America/Chicago")["data"]
        check(data["pick"] and data["pick"]["id"] == state["recipeId"], f"home: {data}")
        again = call(client, "GET", f"{R}/home?tz=America/Chicago")["data"]
        check(again["pick"]["id"] == data["pick"]["id"], "the pick changed within the day")
        picked = call(client, "GET", f"{R}/random?q=smoke%20toast")["data"]["recipe"]
        check(picked and picked["id"] == state["recipeId"], f"random: {picked}")
        return "today's pick holds, Go on, then finds the recipe"

    def remove(client, state):
        check(call(client, "POST", f"{A}/recipes/removed", {"keys": ["mealdb:smoke-1"]})["removed"] == 1, "not removed")
        check(call(client, "GET", f"{R}/recipes?q=smoke%20toast")["data"]["total"] == 0, "a removed recipe is shown")
        call(client, "GET", f"{R}/recipes/{state['recipeId']}", expect=404)
        return "removed and hidden"

    def signout(client, state):
        call(client, "POST", f"{R}/auth/logout", {"fingerprint": state["fingerprint"]})
        call(client, "GET", f"{R}/recipes", expect=401)
        check(call(client, "POST", f"{R}/device/identify", {"fingerprint": state["fingerprint"]})["status"] == "new",
              "the device still signs itself in")
        return "signed out, the session ends, the device is forgotten"

    return [("seed", seed), ("store", store), ("unknown", unknown), ("account", account), ("browse", browse),
            ("diet", diet), ("home", home), ("remove", remove), ("signout", signout)]


def runSteps(client, media):
    state = {}
    for name, step in steps(media):
        try:
            print(f"PASS  {name}: {step(client, state)}")
        except SmokeFailed as failure:
            print(f"FAIL  {name}: {failure}")
            return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gluttony routes against a scratch database")
    parser.add_argument("--database", required=True)
    args = parser.parse_args(argv)
    try:
        DBUtils.initConnection = scratchConnections(args.database, DBUtils.initConnection)
    except ValueError as e:
        print(e)
        return 2
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        token = secrets.token_urlsafe(24)
        config = folder / "gluttonyAdminConfig.json"
        config.write_text('{"token": "%s"}' % token)
        admin.CONFIG_FILE = config
        admin._tokenCache.update({"mtime": None, "token": None})
        read.MEDIA_ROOT = folder / "media"
        app = flask.Flask("gluttony-smoke")
        app.register_blueprint(admin.gluttonyAdminBP, url_prefix="/api/gluttony-admin")
        app.register_blueprint(read.gluttonyBP, url_prefix="/api/gluttony")
        app.register_blueprint(user.gluttonyUserBP, url_prefix="/api/gluttony")
        client = app.test_client()
        client.environ_base["HTTP_X_ADMIN_TOKEN"] = token
        return runSteps(client, read.MEDIA_ROOT)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
