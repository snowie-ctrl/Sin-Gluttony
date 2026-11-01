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
import threading
import uuid
from datetime import datetime, timedelta, timezone
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


def moment(at):
    """A UTC instant as the app stamps a queued change (YYYY-MM-DDTHH:MM:SS.sssZ)."""
    return at.strftime("%Y-%m-%dT%H:%M:%S.") + f"{at.microsecond // 1000:03d}Z"


# How many devices the together step sends a batch from at the same moment.
TOGETHER = 4


def insertKey():
    """A login key on the scratch database, inserted by hand as the owner does."""
    key = "smoke-key-" + secrets.token_hex(8)
    conn = DBUtils.initConnection("gluttony")
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO LoginKeys (KeyValue) VALUES (%s)", (key,))
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return key


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
        key = insertKey()
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

    def lists(client, state):
        shown = call(client, "GET", f"{R}/lists")["data"]
        check(len(shown) == 1 and shown[0]["kind"] == "cravings", f"a new account's lists: {shown}")
        state["cravings"] = shown[0]["id"]
        # A second version of the dish, so a list has two recipes to put in order.
        second = call(client, "POST", f"{A}/recipes/batch",
                      {"recipes": [payload(state["ids"], sourceId="smoke-2", title="Smoke Melt")]})
        check(second["stored"] == ["mealdb:smoke-2"], f"second recipe: {second}")
        found = call(client, "GET", f"{R}/recipes?q=smoke%20melt")["data"]["recipes"]
        state["secondId"] = found[0]["id"]
        made = call(client, "POST", f"{R}/lists/create", {"title": "Smoke weeknights"})["data"]
        other = call(client, "POST", f"{R}/lists/create", {"title": "Smoke parties"})["data"]
        state["list"] = made["id"]
        call(client, "POST", f"{R}/lists/reorder", {"id": other["id"], "after": None})
        order = [entry["id"] for entry in call(client, "GET", f"{R}/lists")["data"]]
        check(order == [state["cravings"], other["id"], made["id"]], f"order after a move: {order}")
        renamed = call(client, "POST", f"{R}/lists/rename", {"id": made["id"], "title": "Smoke fridays"})["data"]
        check(renamed["title"] == "Smoke fridays", f"rename: {renamed}")
        call(client, "POST", f"{R}/lists/rename", {"id": state["cravings"], "title": "Wants"}, expect=400)
        for listId in (state["cravings"], made["id"]):
            call(client, "POST", f"{R}/lists/items/add", {"listId": listId, "recipeId": state["recipeId"]})
        twice = call(client, "POST", f"{R}/lists/items/add", {"listId": made["id"], "recipeId": state["recipeId"]})
        check(twice["data"]["count"] == 1, f"adding twice: {twice}")
        call(client, "POST", f"{R}/lists/items/add", {"listId": made["id"], "recipeId": state["secondId"]})
        page = call(client, "GET", f"{R}/lists/{made['id']}/recipes")["data"]
        check([t["id"] for t in page["recipes"]] == [state["secondId"], state["recipeId"]], f"newest on top: {page}")
        check(page["recipes"][1]["craving"] is True, "the craving flag is missing from a list's tile")
        call(client, "POST", f"{R}/lists/items/reorder",
             {"listId": made["id"], "recipeId": state["secondId"], "after": state["recipeId"]})
        page = call(client, "GET", f"{R}/lists/{made['id']}/recipes")["data"]
        check([t["id"] for t in page["recipes"]] == [state["recipeId"], state["secondId"]], f"after a move: {page}")
        call(client, "POST", f"{R}/lists/items/remove", {"listId": made["id"], "recipeId": state["secondId"]})
        call(client, "POST", f"{R}/lists/delete", {"id": other["id"]})
        check(len(call(client, "GET", f"{R}/lists")["data"]) == 2, "a deleted list is still there")
        return "Cravings from sign-up, lists made, moved, renamed, filled, reordered, emptied and deleted"

    def yours(client, state):
        rid = state["recipeId"]
        # The server's own today in UTC is always accepted, wherever plutus's clock is set.
        today = datetime.now(timezone.utc).date().isoformat()
        clientId = str(uuid.uuid4())
        mark = call(client, "POST", f"{R}/devoured/add", {"recipeId": rid, "on": today, "clientId": clientId})["data"]
        again = call(client, "POST", f"{R}/devoured/add", {"recipeId": rid, "on": today, "clientId": clientId})["data"]
        check(again["already"] and again["id"] == mark["id"] and again["count"] == 1, f"a resent mark: {again}")
        extra = call(client, "POST", f"{R}/devoured/add",
                     {"recipeId": rid, "on": today, "clientId": str(uuid.uuid4())})["data"]
        check(extra["count"] == 2, f"a second mark: {extra}")
        call(client, "POST", f"{R}/devoured/remove", {"id": extra["id"]})
        call(client, "POST", f"{R}/rating", {"recipeId": rid, "stars": 4})
        cakes = "\U0001F370" * 2000
        call(client, "POST", f"{R}/note", {"recipeId": rid, "text": cakes})
        call(client, "POST", f"{R}/note", {"recipeId": rid, "text": cakes + "\U0001F370"}, expect=400)
        mine = call(client, "GET", f"{R}/recipes/{rid}")["data"]["mine"]
        check(mine == {"craving": True, "lists": [state["list"]], "devoured": [{"id": mark["id"], "on": today}],
                       "stars": 4, "note": cakes}, f"mine: {str(mine)[:200]}")
        history = call(client, "GET", f"{R}/devoured?sort=stars")["data"]
        check(history["total"] == 1 and history["recipes"][0]["devouredId"] == mark["id"], f"history: {history}")
        home = call(client, "GET", f"{R}/home?tz=UTC")["data"]
        check(not home["pick"] or home["pick"]["id"] != rid, "today's temptation is a recipe devoured today")
        check([t["id"] for t in home["again"]] == [rid], f"Again?: {home['again']}")
        check(rid in [t["id"] for t in home["cravings"]], f"Cravings row: {home['cravings']}")
        state["mark"] = mark["id"]
        return "a mark stored once per clientId, stars, a 2,000-emoji note, mine, history, Home's rows"

    def sync(client, state):
        rid = state["recipeId"]
        now = datetime.now(timezone.utc)

        hourAgo = moment(now - timedelta(hours=1))
        ops = [{"op": "devoured", "recipeId": rid, "on": now.date().isoformat(), "clientId": str(uuid.uuid4()),
                "at": hourAgo},
               # Older than the 4 stars the yours step gave just now: the server keeps the 4.
               {"op": "stars", "recipeId": rid, "stars": 2, "at": hourAgo},
               # Ahead of the server's clock: counted as now, so newer than the yours step's note.
               {"op": "note", "recipeId": rid, "text": "smoke queued", "at": moment(now + timedelta(minutes=5))},
               {"op": "stars", "recipeId": 2 ** 31 - 1, "stars": 3, "at": hourAgo}]
        results = call(client, "POST", f"{R}/sync/batch", {"ops": ops})["data"]["results"]
        check([r["result"] for r in results] == ["applied", "already", "applied", "refused"], f"sync: {results}")
        check(results[1]["stars"] == 4 and results[3]["message"] == "no such recipe", f"sync answers: {results}")
        again = call(client, "POST", f"{R}/sync/batch", {"ops": ops[:1]})["data"]["results"]
        check(again[0]["result"] == "already" and again[0]["id"] == results[0]["id"], f"a resent mark: {again}")
        mine = call(client, "GET", f"{R}/recipes/{rid}")["data"]["mine"]
        check(mine["stars"] == 4 and mine["note"] == "smoke queued" and len(mine["devoured"]) == 2,
              f"mine after a sync: {str(mine)[:200]}")
        call(client, "POST", f"{R}/rating", {"recipeId": rid, "stars": None})
        cleared = call(client, "POST", f"{R}/sync/batch",
                       {"ops": [{"op": "stars", "recipeId": rid, "stars": 5, "at": hourAgo}]})["data"]["results"]
        check(cleared[0] == {"result": "already", "recipeId": rid, "stars": None}, f"a cleared rating: {cleared}")
        call(client, "POST", f"{R}/rating", {"recipeId": rid, "stars": 4})
        return "a queued mark once, an older star kept out, a newer note in, a cleared rating kept, a stranger's id refused"

    def manifest(client, state):
        data = call(client, "GET", f"{R}/saved/manifest?extra={state['secondId']}")["data"]
        byId = {entry["id"]: entry for entry in data["lists"]}
        check(data["lists"][0]["id"] == state["cravings"] and state["recipeId"] in byId[state["cravings"]]["recipeIds"],
              f"manifest lists: {data['lists']}")
        # The lists step took the second recipe off the list again, so only the first is left on it.
        check(byId[state["list"]]["recipeIds"] == [state["recipeId"]], f"a list's order: {byId[state['list']]}")
        recipes = {entry["id"]: entry for entry in data["recipes"]}
        # The second recipe is on no list: it is in the manifest only because `extra` named it.
        check(all(state["secondId"] not in entry["recipeIds"] for entry in data["lists"]),
              f"the second recipe is still on a list: {data['lists']}")
        check({state["recipeId"], state["secondId"]} <= set(recipes) and all(r["updatedAt"] for r in recipes.values()),
              f"manifest recipes: {data['recipes']}")
        # The manifest's `mine` is the recipe page's, read on real MySQL by a different query.
        for rid in (state["recipeId"], state["secondId"]):
            shown = call(client, "GET", f"{R}/recipes/{rid}")["data"]["mine"]
            check(recipes[rid].get("mine") == shown,
                  f"recipe {rid}'s mine in the manifest: {str(recipes[rid].get('mine'))[:200]} vs {str(shown)[:200]}")
        call(client, "GET", f"{R}/saved/manifest?extra=x", expect=400)
        return "every list with its recipes, each recipe's UpdatedAt and mine, the cook-mode extras"

    def together(client, state):
        """Four devices reconnecting at the same moment with changes for one recipe nobody has starred or noted:
        on real MySQL the missing rows' gap locks can deadlock, and every batch must still land, newest kept."""
        rid = state["secondId"]
        token = client.environ_base["HTTP_X_SESSION_TOKEN"]
        now = datetime.now(timezone.utc)
        before = user.lockRetries
        # A thread that dies or a barrier that breaks must end the step with a FAIL, never hang the process: the
        # barrier times out, the threads are daemons, and each keeps its own exception to name in the message.
        start = threading.Barrier(TOGETHER, timeout=30)
        answers = [None] * TOGETHER
        errors = [None] * TOGETHER

        def device(index):
            own = client.application.test_client()
            own.environ_base["HTTP_X_SESSION_TOKEN"] = token
            # A higher index is a later change, so the last device's must win.
            at = moment(now - timedelta(minutes=TOGETHER - index))
            ops = [{"op": "stars", "recipeId": rid, "stars": index + 1, "at": at},
                   {"op": "note", "recipeId": rid, "text": f"smoke device {index}", "at": at}]
            start.wait()
            answers[index] = own.post(f"{R}/sync/batch", json={"ops": ops})

        def guarded(index):
            try:
                device(index)
            except BaseException as error:
                errors[index] = f"{type(error).__name__}: {error}"[:200]
                start.abort()

        threads = [threading.Thread(target=guarded, args=(index,), daemon=True) for index in range(TOGETHER)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        failed = [f"device {index}: {error}" for index, error in enumerate(errors) if error]
        check(not failed, "batches sent together: " + "; ".join(failed))
        statuses = [answer.status_code if answer is not None else None for answer in answers]
        check(statuses == [200] * TOGETHER, f"batches sent together answered {statuses}")
        mine = call(client, "GET", f"{R}/recipes/{rid}")["data"]["mine"]
        check(mine["stars"] == TOGETHER and mine["note"] == f"smoke device {TOGETHER - 1}",
              f"after batches sent together: stars {mine['stars']}, note {mine['note']!r}")
        return (f"{TOGETHER} batches at once all landed, the newest kept; "
                f"{user.lockRetries - before} tried again after a lock conflict")

    def strangers(client, state):
        own = client.environ_base["HTTP_X_SESSION_TOKEN"]
        made = call(client, "POST", f"{R}/auth", {"username": "smoke-stranger", "password": "smoke-password",
                                                  "fingerprint": "smoke-device-" + secrets.token_hex(8),
                                                  "key": insertKey()})
        state["strangerToken"] = made["token"]
        client.environ_base["HTTP_X_SESSION_TOKEN"] = made["token"]
        try:
            call(client, "GET", f"{R}/lists/{state['list']}/recipes", expect=404)
            call(client, "POST", f"{R}/lists/rename", {"id": state["list"], "title": "Mine now"}, expect=404)
            call(client, "POST", f"{R}/lists/items/add", {"listId": state["list"], "recipeId": state["recipeId"]},
                 expect=404)
            call(client, "POST", f"{R}/devoured/remove", {"id": state["mark"]}, expect=404)
            theirs = call(client, "GET", f"{R}/lists")["data"]
            check(len(theirs) == 1 and theirs[0]["kind"] == "cravings", f"a stranger's lists: {theirs}")
            mine = call(client, "GET", f"{R}/recipes/{state['recipeId']}")["data"]["mine"]
            check(mine == {"craving": False, "lists": [], "devoured": [], "stars": None, "note": None},
                  f"a stranger sees: {mine}")
        finally:
            client.environ_base["HTTP_X_SESSION_TOKEN"] = own
        return "someone else's list, mark and keeps are 404 or empty for a second account"

    def remove(client, state):
        check(call(client, "POST", f"{A}/recipes/removed", {"keys": ["mealdb:smoke-1"]})["removed"] == 1, "not removed")
        check(call(client, "GET", f"{R}/recipes?q=smoke%20toast")["data"]["total"] == 0, "a removed recipe is shown")
        detail = call(client, "GET", f"{R}/recipes/{state['recipeId']}")["data"]
        check(detail["removed"] is True, "the saver lost a removed recipe")
        listed = call(client, "GET", f"{R}/lists/{state['list']}/recipes")["data"]["recipes"]
        check(listed and listed[0]["removed"] is True, f"the list lost a removed recipe: {listed}")
        call(client, "GET", f"{R}/images/{state['recipeId']}")
        own = client.environ_base["HTTP_X_SESSION_TOKEN"]
        client.environ_base["HTTP_X_SESSION_TOKEN"] = state["strangerToken"]
        try:
            call(client, "GET", f"{R}/recipes/{state['recipeId']}", expect=404)
            call(client, "GET", f"{R}/images/{state['recipeId']}", expect=404)
        finally:
            client.environ_base["HTTP_X_SESSION_TOKEN"] = own
        return "removed: hidden from the catalog and strangers, still the saver's"

    def signout(client, state):
        call(client, "POST", f"{R}/auth/logout", {"fingerprint": state["fingerprint"]})
        call(client, "GET", f"{R}/recipes", expect=401)
        check(call(client, "POST", f"{R}/device/identify", {"fingerprint": state["fingerprint"]})["status"] == "new",
              "the device still signs itself in")
        return "signed out, the session ends, the device is forgotten"

    return [("seed", seed), ("store", store), ("unknown", unknown), ("account", account), ("browse", browse),
            ("diet", diet), ("home", home), ("lists", lists), ("yours", yours), ("sync", sync), ("manifest", manifest),
            ("together", together), ("strangers", strangers), ("remove", remove), ("signout", signout)]


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
