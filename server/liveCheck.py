"""
The rollout's live check (milestone 4): every route the app calls, against the real server, from this PC, with a
throwaway account the owner deletes afterwards (README, "Milestone 4: the rollout"). Never deployed. Run it on the
LAN base first (signing up), then through the tunnel (signing in, with --outside):

    server\\.venv\\Scripts\\python.exe server\\liveCheck.py --base <base> --username claude-check --sign-up
    server\\.venv\\Scripts\\python.exe server\\liveCheck.py --base https://<public host>/api/gluttony \\
        --username claude-check --outside --limits

The password comes from GLUTTONY_CHECK_PASSWORD and, with --sign-up, the login key from GLUTTONY_CHECK_KEY; neither
is ever printed, nor is the session token. Prints PASS or FAIL per step and stops at the first failure. Every
change it makes is taken back before it signs out. Standard library only.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

AGENT = "GluttonyLiveCheck/1.0"
MOODS = {"Quick fix": "kind=food&maxMinutes=30&difficulty=1", "Feed a crowd": "occasion=party",
         "Sweet tooth": "course=dessert", "Bottoms up": "kind=drink"}
NOTHING = {"craving": False, "lists": [], "devoured": [], "stars": None, "note": None}


class CheckFailed(Exception):
    pass


def check(condition, message):
    if not condition:
        raise CheckFailed(message)


def moment(at):
    """A UTC instant as the app stamps a queued change (YYYY-MM-DDTHH:MM:SS.sssZ)."""
    return at.strftime("%Y-%m-%dT%H:%M:%S.") + f"{at.microsecond // 1000:03d}Z"


class Server:
    """One device talking to one base URL, as the app does: its fingerprint on every request, its token once
    signed in."""

    def __init__(self, base, fingerprint):
        self.base = base.rstrip("/")
        self.root = self.base[: self.base.rindex("/api/gluttony")]
        self.fingerprint = fingerprint
        self.token = None

    def raw(self, url, method="GET", body=None, signed=True):
        # UTF-8 as the app sends it (Qt never escapes), so a batch's size here is its size on the wire.
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("User-Agent", AGENT)
        request.add_header("X-Device-Fingerprint", self.fingerprint)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if signed and self.token:
            request.add_header("X-Session-Token", self.token)
        try:
            with urllib.request.urlopen(request, timeout=60) as answer:
                return answer.status, answer.headers.get("Content-Type", ""), answer.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers.get("Content-Type", ""), error.read()
        except (urllib.error.URLError, OSError) as error:
            raise CheckFailed(f"{method} {url[len(self.root):] or '/'} reached nothing: "
                              f"{getattr(error, 'reason', error)}")

    def call(self, method, route, body=None, expect=200, signed=True):
        status, kind, data = self.raw(self.base + route, method, body, signed)
        if status != expect:
            raise CheckFailed(f"{method} {route} gave {status}: {data[:200].decode('utf-8', 'replace')}")
        return json.loads(data) if "json" in kind else data


def steps(args, password, key):
    def ping(s, state):
        check(s.call("GET", "/ping", signed=False).get("status") == "ok", "ping did not answer ok")
        return "answers"

    def locked(s, state):
        for route in ("/recipes", "/saved/manifest", "/images/1", "/me/diet"):
            s.call("GET", route, expect=401, signed=False)
        return "every route but ping, auth and device/identify needs a session"

    def outside(s, state):
        for path in ("/api/gluttony-admin/state", "/api/pageturner/ping", "/api/showtime/ping", "/"):
            status, _, _ = s.raw(s.root + path, signed=False)
            check(status == 404, f"{path} through this host gave {status}, not 404")
        return "only /api/gluttony/ answers on this host"

    def account(s, state):
        body = {"username": args.username, "password": password, "fingerprint": s.fingerprint}
        if args.sign_up:
            body["key"] = key
        made = s.call("POST", "/auth", body, signed=False)
        check(made.get("status") == "ok" and made.get("token"), f"signing in answered {made.get('status')}")
        s.token = made["token"]
        again = s.call("POST", "/device/identify", {"fingerprint": s.fingerprint}, signed=False)
        check(again.get("status") == "ok" and again.get("UID") == made["UID"], "the device does not sign itself in")
        return ("signed up with the key" if args.sign_up else "signed in") + ", and the device signs itself in"

    def catalog(s, state):
        filters = s.call("GET", "/filters")["data"]
        check(filters.get("kinds"), "the filters have no kinds")
        page = s.call("GET", "/recipes?pageSize=60&sort=shuffle")["data"]
        check(page["total"] > 0 and page["recipes"], "the catalog is empty")
        check({"craving", "devouredCount", "stars"} <= set(page["recipes"][0]),
              f"a tile has no flags: {sorted(page['recipes'][0])}")
        state["tiles"] = page["recipes"]
        return f"{page['total']} recipes, tiles with the person's flags"

    def moods(s, state):
        return ", ".join(f"{name} {s.call('GET', '/recipes?' + query)['data']['total']}"
                         for name, query in MOODS.items())

    def search(s, state):
        found = s.call("GET", "/recipes?q=chicken")["data"]["total"]
        names = s.call("GET", "/ingredients?q=chick")["data"]
        return f"'chicken' finds {found}, 'chick' names {len(names)} ingredients"

    def recipe(s, state):
        tile = state["tiles"][0]
        detail = s.call("GET", f"/recipes/{tile['id']}")["data"]
        check(detail["id"] == tile["id"] and "mine" in detail and detail.get("steps"),
              f"recipe {tile['id']} came back as {sorted(detail)}")
        state["recipeId"] = tile["id"]
        pictured = next((t for t in state["tiles"] if t.get("hasImage")), None)
        if not pictured:
            return f"recipe {tile['id']} opens; no tile on the page has a picture"
        for kind in ("images", "thumbs"):
            data = s.call("GET", f"/{kind}/{pictured['id']}")
            check(isinstance(data, bytes) and data[:2] == b"\xff\xd8", f"/{kind}/{pictured['id']} is not a JPEG")
        return f"recipe {tile['id']} opens; recipe {pictured['id']}'s pictures come with the session"

    def home(s, state):
        first = s.call("GET", "/home?tz=America/Chicago")["data"]
        second = s.call("GET", "/home?tz=America/Chicago")["data"]
        pick = (first["pick"] or {}).get("id")
        check(pick == (second["pick"] or {}).get("id"), "today's pick changed between two looks")
        picked = s.call("GET", "/random?kind=food")["data"]["recipe"]
        return f"today's pick {pick} and {len(first['picks'])} more; Go on, then gave {(picked or {}).get('id')}"

    def diet(s, state):
        s.call("POST", "/me/diet", {"diets": ["vegetarian"], "avoid": ["peanut"]})
        try:
            on = s.call("GET", "/recipes?pageSize=12&sort=shuffle")["data"]
            off = s.call("GET", "/recipes?profile=off")["data"]["total"]
            check(on["total"] <= off, f"the profile let more through ({on['total']}) than with it off ({off})")
            for tile in on["recipes"]:
                facts = s.call("GET", f"/recipes/{tile['id']}")["data"]["facts"]
                check(facts["complete"] and "vegetarian" in facts["diets"] and "peanut" not in facts["contains"],
                      f"recipe {tile['id']} broke the safety rule: {facts}")
        finally:
            s.call("POST", "/me/diet", {"diets": [], "avoid": []})
        return f"vegetarian, no peanuts: {on['total']} of {off}; every one checked is complete and fits"

    def lists(s, state):
        rid = state["recipeId"]
        cravings = next(entry for entry in s.call("GET", "/lists")["data"] if entry["kind"] == "cravings")
        made = s.call("POST", "/lists/create", {"title": "claude-check list"})["data"]
        state["cravings"], state["list"] = cravings["id"], made["id"]
        for listId in (cravings["id"], made["id"]):
            s.call("POST", "/lists/items/add", {"listId": listId, "recipeId": rid})
        page = s.call("GET", f"/lists/{made['id']}/recipes")["data"]["recipes"]
        check([t["id"] for t in page] == [rid] and page[0]["craving"], f"the list holds {page}")
        s.call("POST", "/lists/rename", {"id": made["id"], "title": "claude-check renamed"})
        return "a list made, filled, read and renamed; the craving flag shows on its tile"

    def yours(s, state):
        rid = state["recipeId"]
        today = datetime.now(timezone.utc).date().isoformat()
        clientId = str(uuid.uuid4())
        mark = s.call("POST", "/devoured/add", {"recipeId": rid, "on": today, "clientId": clientId})["data"]
        again = s.call("POST", "/devoured/add", {"recipeId": rid, "on": today, "clientId": clientId})["data"]
        check(again["already"] and again["id"] == mark["id"], f"a resent mark answered {again}")
        s.call("POST", "/rating", {"recipeId": rid, "stars": 4})
        s.call("POST", "/note", {"recipeId": rid, "text": "claude-check note"})
        mine = s.call("GET", f"/recipes/{rid}")["data"]["mine"]
        check(mine["craving"] and state["list"] in mine["lists"] and mine["stars"] == 4
              and mine["note"] == "claude-check note" and [m["id"] for m in mine["devoured"]] == [mark["id"]],
              f"mine is {mine}")
        state["mark"] = mark["id"]
        return "a mark stored once per clientId, stars and a note, all in mine"

    def sync(s, state):
        rid = state["recipeId"]
        hourAgo = moment(datetime.now(timezone.utc) - timedelta(hours=1))
        results = s.call("POST", "/sync/batch",
                         {"ops": [{"op": "stars", "recipeId": rid, "stars": 2, "at": hourAgo}]})["data"]["results"]
        check(results == [{"result": "already", "recipeId": rid, "stars": 4}], f"a late star answered {results}")
        return "a star queued before the newer one is kept out"

    def bigBatch(s, state):
        rid = state["recipeId"]
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        # The largest batch the app sends: 500 notes of 2,000 characters, two bytes each in UTF-8 (about 2 MB).
        # Older than the yours step's note, so each is answered "already" and the note stays.
        ops = [{"op": "note", "recipeId": rid, "text": f"{index:04d} " + "\u00e9" * 1995,
                "at": moment(start + timedelta(seconds=index))} for index in range(500)]
        size = len(json.dumps({"ops": ops}, ensure_ascii=False).encode("utf-8"))
        results = s.call("POST", "/sync/batch", {"ops": ops})["data"]["results"]
        check(len(results) == 500 and all(r["result"] in ("applied", "already") for r in results),
              f"the big batch: {[r for r in results if r['result'] not in ('applied', 'already')][:3]}")
        return f"a {size // 1024} KB batch of 500 changes is taken whole"

    def manifest(s, state):
        rid = state["recipeId"]
        data = s.call("GET", "/saved/manifest")["data"]
        byId = {entry["id"]: entry for entry in data["recipes"]}
        check(rid in byId and any(entry["id"] == state["list"] for entry in data["lists"]),
              f"the manifest lacks the list or the recipe: {data['lists']}")
        shown = s.call("GET", f"/recipes/{rid}")["data"]["mine"]
        check(byId[rid].get("mine") == shown, f"the manifest's mine {byId[rid].get('mine')} is not the recipe's {shown}")
        return "the list and the recipe, with its mine as the recipe page has it"

    def secondDevice(s, state):
        other = Server(s.base, s.fingerprint + "-b")
        made = other.call("POST", "/auth", {"username": args.username, "password": password,
                                            "fingerprint": other.fingerprint}, signed=False)
        check(made.get("token"), "a second device could not sign in")
        other.token = made["token"]
        try:
            mine = other.call("GET", f"/recipes/{state['recipeId']}")["data"]["mine"]
            check(mine["stars"] == 4 and mine["note"] == "claude-check note" and state["list"] in mine["lists"],
                  f"the second device sees {mine}")
        finally:
            other.call("POST", "/auth/logout", {"fingerprint": other.fingerprint})
        return "a second device signs in and finds the list, the stars and the note"

    def tidy(s, state):
        rid = state["recipeId"]
        s.call("POST", "/devoured/remove", {"id": state["mark"]})
        s.call("POST", "/rating", {"recipeId": rid, "stars": None})
        s.call("POST", "/note", {"recipeId": rid, "text": ""})
        s.call("POST", "/lists/items/remove", {"listId": state["cravings"], "recipeId": rid})
        s.call("POST", "/lists/delete", {"id": state["list"]})
        mine = s.call("GET", f"/recipes/{rid}")["data"]["mine"]
        check(mine == NOTHING, f"after tidying, mine is {mine}")
        return "everything it kept is taken back"

    def signout(s, state):
        s.call("POST", "/auth/logout", {"fingerprint": s.fingerprint})
        s.call("GET", "/recipes", expect=401)
        check(s.call("POST", "/device/identify", {"fingerprint": s.fingerprint}, signed=False)["status"] == "new",
              "the device still signs itself in")
        return "signed out: the session ends and the device is forgotten"

    def limits(s, state):
        wrong = {"username": args.username, "password": "wrong-password-0", "fingerprint": s.fingerprint}
        statuses = [s.raw(s.base + "/auth", "POST", wrong, signed=False)[0] for _ in range(6)]
        check(statuses[-1] == 429, f"six wrong sign-ins in a minute answered {statuses}")
        return f"wrong sign-ins answered {statuses}"

    chosen = [("ping", ping), ("locked", locked)]
    if args.outside:
        chosen.append(("outside", outside))
    chosen += [("account", account), ("catalog", catalog), ("moods", moods), ("search", search), ("recipe", recipe),
               ("home", home), ("diet", diet), ("lists", lists), ("yours", yours), ("sync", sync),
               ("bigBatch", bigBatch), ("manifest", manifest), ("secondDevice", secondDevice), ("tidy", tidy),
               ("signout", signout)]
    if args.limits:
        chosen.append(("limits", limits))
    return chosen


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gluttony's routes against the real server, from this PC")
    parser.add_argument("--base", required=True, help="the API base, ending in /api/gluttony")
    parser.add_argument("--username", required=True)
    parser.add_argument("--sign-up", action="store_true", help="sign up with GLUTTONY_CHECK_KEY instead of signing in")
    parser.add_argument("--outside", action="store_true", help="also check that nothing else answers on this host")
    parser.add_argument("--limits", action="store_true", help="end with six wrong sign-ins (the limiter's 429)")
    args = parser.parse_args(argv)
    password = os.environ.get("GLUTTONY_CHECK_PASSWORD", "")
    key = os.environ.get("GLUTTONY_CHECK_KEY", "")
    if len(password) < 8 or (args.sign_up and not key):
        print("set GLUTTONY_CHECK_PASSWORD (8 or more characters) and, with --sign-up, GLUTTONY_CHECK_KEY")
        return 2
    server = Server(args.base, "claude-check-" + uuid.uuid5(uuid.NAMESPACE_URL, args.username).hex[:16])
    state = {}
    for name, step in steps(args, password, key):
        try:
            print(f"PASS  {name}: {step(server, state)}", flush=True)
        except CheckFailed as failure:
            print(f"FAIL  {name}: {failure}", flush=True)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
