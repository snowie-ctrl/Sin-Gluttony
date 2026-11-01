# Copied from Pageturner/server/pageturnerRoutes.py at 062da3b; changes: the account routes only, on
# gluttonyDB's Users.UserID; usernames 3-32 characters; a sign-up's password is checked like a new one and makes
# the Cravings list; the diet profile, lists, Devoured, rating and note routes are new.
"""
Accounts and what a person keeps (the diet profile at /me/diet; lists, Cravings among them; Devoured marks, stars
and notes, and what the app did offline (/sync/batch)), at /api/gluttony beside the read API (gluttonyRoutes.py),
which applies the saved profile to every search. docs/api.md is the contract. Users sign up with a login key the
owner inserts by hand, and a device that signed in once signs in by itself (/device/identify) until it signs out.
Everything a person keeps is looked up together with their id, so someone else's id is answered 404, like an unknown
one.
"""
import hashlib
import random
import secrets
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from . import gluttonyKept as kept, gluttonyRules as rules, gluttonySession as session

gluttonyUserBP = Blueprint("gluttonyUser", __name__)
session.install(gluttonyUserBP)
database = session.database
fail = session.fail

USERNAME_MIN, USERNAME_MAX = 3, 32
PASSWORD_MIN, PASSWORD_MAX = 8, 256
# MySQL's error number for a duplicate key.
DUPLICATE_ENTRY = 1062
# MySQL's error numbers when two transactions want each other's locks: a deadlock (MySQL rolls one back) and a lock
# wait that ran out of time. Both leave nothing applied, so the transaction can simply be tried again.
LOCK_CONFLICTS = (1213, 1205)
# How many times /sync/batch tries a batch that met a lock conflict.
SYNC_ATTEMPTS = 3
# Batches tried again after a lock conflict since the server started; the smoke test reports it.
lockRetries = 0
# The one list every account has from sign-up. The app shows it in its own words; this is what the row holds.
CRAVINGS_TITLE = "Cravings"


def ok(data=None, status="ok", **extra):
    answer = {"status": status}
    if data is not None:
        answer["data"] = data
    answer.update(extra)
    return jsonify(answer), 200


def body():
    """The JSON body, or {} when there is none or it isn't an object, so validation can say what is missing."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def isoUtc(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


def usernameProblem(username):
    if not USERNAME_MIN <= len(username) <= USERNAME_MAX:
        return f"a username is {USERNAME_MIN} to {USERNAME_MAX} characters"
    return None


def passwordProblem(password):
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        return f"a password is {PASSWORD_MIN} to {PASSWORD_MAX} characters"
    return None


def createSession(cur, uid, fingerprint):
    """A new session token for this device. The user's ended sessions are cleared on the way, since nothing else
    ever removes them."""
    cur.execute("DELETE FROM Sessions WHERE UserID = %s AND ExpiresAt <= NOW()", (uid,))
    token = secrets.token_hex(32)
    cur.execute("INSERT INTO Sessions (Token, UserID, DeviceFingerprint, ExpiresAt) "
                "VALUES (%s, %s, %s, NOW() + INTERVAL %s DAY)", (token, uid, fingerprint, session.SESSION_DAYS))
    return token


def deviceId(fingerprint):
    """What a client may know of a device: the first 16 hex of its fingerprint's SHA-256. The fingerprint itself
    would sign the device in, so it never leaves the server."""
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


def currentFingerprint(cur, uid):
    cur.execute("SELECT DeviceFingerprint FROM Sessions WHERE Token = %s AND UserID = %s", (session.sessionToken(), uid))
    return (cur.fetchone() or {}).get("DeviceFingerprint")


@gluttonyUserBP.route("/device/identify", methods=["POST"])
@session.rateLimited(10)
def identifyDevice():
    fingerprint = str(body().get("fingerprint") or "")[:255]
    if not fingerprint:
        return fail("missing fingerprint", 400)
    with database() as (conn, cur):
        cur.execute("SELECT UserID FROM Devices WHERE Fingerprint = %s", (fingerprint,))
        device = cur.fetchone()
        if not device:
            return ok(status="new")
        uid = device["UserID"]
        cur.execute("SELECT Username FROM Users WHERE UserID = %s", (uid,))
        account = cur.fetchone() or {}
        token = createSession(cur, uid, fingerprint)
        conn.commit()
    return ok(UID=uid, username=account.get("Username"), token=token)


@gluttonyUserBP.route("/auth", methods=["POST"])
@session.rateLimited(5)
def auth():
    data = body()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    fingerprint = str(data.get("fingerprint") or "")[:255]
    key = str(data.get("key") or "").strip()
    if not username or not password or not fingerprint:
        return fail("missing credentials", 400)
    if key:
        problem = usernameProblem(username) or passwordProblem(password)
        if problem:
            return fail(problem, 400)
    elif len(username) > USERNAME_MAX:
        return fail("invalid_credentials", 401, status="invalid_credentials")

    with database() as (conn, cur):
        if key:
            # The key's row is locked, so two sign-ups racing on one key cannot both use it.
            cur.execute("SELECT KeyValue, Used FROM LoginKeys WHERE KeyValue = %s FOR UPDATE", (key[:64],))
            found = cur.fetchone()
            if not found or found["Used"]:
                return fail("invalid_key", 403, status="invalid_key")
            cur.execute("SELECT UserID FROM Users WHERE Username = %s", (username,))
            if cur.fetchone():
                return fail("username_taken", 409, status="username_taken")
            cur.execute("INSERT INTO Users (Username, PasswordHash) VALUES (%s, %s)",
                        (username, generate_password_hash(password)))
            uid = cur.lastrowid
            cur.execute("UPDATE LoginKeys SET Used = 1, UsedBy = %s WHERE KeyValue = %s", (uid, found["KeyValue"]))
            # In the same transaction as the account, so no account ever exists without its Cravings.
            # CravingsOf names the owner, so the table's unique key allows no second Cravings.
            cur.execute("INSERT INTO Lists (UserID, Title, Kind, OrderIndex, CravingsOf) "
                        "VALUES (%s, %s, 'cravings', 0, %s)", (uid, CRAVINGS_TITLE, uid))
        else:
            cur.execute("SELECT UserID, Username, PasswordHash FROM Users WHERE Username = %s", (username,))
            user = cur.fetchone()
            if not user or not check_password_hash(user["PasswordHash"], password):
                return fail("invalid_credentials", 401, status="invalid_credentials")
            uid, username = user["UserID"], user["Username"]
        # Remember the device either way, so it signs itself in next time.
        cur.execute("INSERT INTO Devices (Fingerprint, UserID) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE UserID = VALUES(UserID)", (fingerprint, uid))
        token = createSession(cur, uid, fingerprint)
        conn.commit()
    return ok(UID=uid, username=username, token=token)


@gluttonyUserBP.route("/auth/logout", methods=["POST"])
def signOut():
    """Sign out, and make this device forget the account; without dropping the Devices row the next start would
    sign straight back in. Only this device is forgotten."""
    fingerprint = str(body().get("fingerprint") or request.headers.get("X-Device-Fingerprint") or "")[:255]
    if not fingerprint:
        return fail("missing fingerprint", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        cur.execute("DELETE FROM Devices WHERE Fingerprint = %s AND UserID = %s", (fingerprint, uid))
        cur.execute("DELETE FROM Sessions WHERE DeviceFingerprint = %s AND UserID = %s", (fingerprint, uid))
        conn.commit()
    return ok()


@gluttonyUserBP.route("/user/username", methods=["POST"])
def changeUsername():
    username = body().get("username")
    username = username.strip() if isinstance(username, str) else ""
    problem = usernameProblem(username)
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        cur.execute("SELECT UserID FROM Users WHERE Username = %s AND UserID <> %s", (username, uid))
        if cur.fetchone():
            return fail("username_taken", 409, status="username_taken")
        try:
            cur.execute("UPDATE Users SET Username = %s WHERE UserID = %s", (username, uid))
        except Exception as error:
            # Two renames racing to one name: the unique key decides, and the loser hears the same answer.
            if getattr(error, "errno", None) == DUPLICATE_ENTRY:
                return fail("username_taken", 409, status="username_taken")
            raise
        conn.commit()
    return ok(username=username)


@gluttonyUserBP.route("/user/password", methods=["POST"])
@session.rateLimited(5)
def changePassword():
    """A new password needs the current one, so a borrowed, unlocked app cannot lock its owner out. Every other
    device is signed out and forgotten; this one stays signed in."""
    data = body()
    current, password = data.get("current"), data.get("password")
    if not isinstance(current, str) or not current or not isinstance(password, str) or not password:
        return fail("current and password are needed", 400)
    problem = passwordProblem(password)
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    token = session.sessionToken()
    with database() as (conn, cur):
        cur.execute("SELECT PasswordHash FROM Users WHERE UserID = %s", (uid,))
        user = cur.fetchone()
        if not user or not check_password_hash(user["PasswordHash"], current):
            return fail("invalid_credentials", 401, status="invalid_credentials")
        cur.execute("UPDATE Users SET PasswordHash = %s WHERE UserID = %s", (generate_password_hash(password), uid))
        cur.execute("DELETE FROM Devices WHERE UserID = %s AND Fingerprint NOT IN "
                    "(SELECT DeviceFingerprint FROM Sessions WHERE Token = %s)", (uid, token))
        cur.execute("DELETE FROM Sessions WHERE UserID = %s AND Token <> %s", (uid, token))
        conn.commit()
    return ok()


@gluttonyUserBP.route("/devices", methods=["GET"])
def devices():
    uid = session.requestUID()
    with database() as (conn, cur):
        here = currentFingerprint(cur, uid)
        cur.execute("SELECT d.Fingerprint, MAX(s.ExpiresAt) AS LastExpiry FROM Devices d "
                    "LEFT JOIN Sessions s ON s.DeviceFingerprint = d.Fingerprint AND s.UserID = d.UserID "
                    "WHERE d.UserID = %s GROUP BY d.Fingerprint "
                    "ORDER BY MAX(s.ExpiresAt) IS NULL, MAX(s.ExpiresAt) DESC, d.Fingerprint", (uid,))
        rows = cur.fetchall()
    return ok([{"id": deviceId(r["Fingerprint"]), "label": deviceId(r["Fingerprint"])[:8],
                "current": r["Fingerprint"] == here,
                "lastSignIn": isoUtc(r["LastExpiry"] - timedelta(days=session.SESSION_DAYS)) if r["LastExpiry"] else None}
               for r in rows])


@gluttonyUserBP.route("/devices/remove", methods=["POST"])
def removeDevice():
    """Sign another of this person's devices out and forget it. The device asking is refused: signing out is how
    it leaves. Only this person's own devices can be named; an id that matches none is nothing to remove."""
    wanted = body().get("id")
    wanted = wanted.strip() if isinstance(wanted, str) else ""
    if not wanted:
        return fail("missing id", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        here = currentFingerprint(cur, uid)
        if here is not None and wanted == deviceId(here):
            return fail("this is the device you are using: sign out instead", 400)
        cur.execute("SELECT Fingerprint FROM Devices WHERE UserID = %s", (uid,))
        fingerprint = next((r["Fingerprint"] for r in cur.fetchall() if deviceId(r["Fingerprint"]) == wanted), None)
        if fingerprint is None:
            return ok()
        cur.execute("DELETE FROM Sessions WHERE UserID = %s AND DeviceFingerprint = %s", (uid, fingerprint))
        cur.execute("DELETE FROM Devices WHERE UserID = %s AND Fingerprint = %s", (uid, fingerprint))
        conn.commit()
    return ok()


@gluttonyUserBP.route("/me/diet", methods=["GET"])
def getDiet():
    with database() as (conn, cur):
        diets, avoid = session.profileOf(cur, session.requestUID())
    return ok({"diets": diets, "avoid": avoid})


@gluttonyUserBP.route("/me/diet", methods=["POST"])
def setDiet():
    """Replace the saved profile whole, in one transaction, so a failed save leaves the old profile as it was."""
    diets, avoid, problem = rules.dietProblem(body())
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        cur.execute("DELETE FROM UserDiets WHERE UserID = %s", (uid,))
        cur.execute("DELETE FROM UserAvoids WHERE UserID = %s", (uid,))
        for diet in diets:
            cur.execute("INSERT INTO UserDiets (UserID, Diet) VALUES (%s, %s)", (uid, diet))
        for item in avoid:
            cur.execute("INSERT INTO UserAvoids (UserID, Item) VALUES (%s, %s)", (uid, item))
        conn.commit()
    return ok({"diets": diets, "avoid": avoid})


# ---- lists (Cravings is the one of kind 'cravings') ----

def listRow(row):
    return {"id": row["ListID"], "title": row["Title"], "kind": row["Kind"], "count": int(row.get("Count") or 0)}


def ownList(cur, uid, listId, lock=False):
    """One of this person's lists, or None (an unknown id and someone else's look the same). Locked when the
    caller is about to change it, so two changes to one list happen one after the other."""
    cur.execute("SELECT ListID, Title, Kind, OrderIndex FROM Lists WHERE ListID = %s AND UserID = %s"
                + (" FOR UPDATE" if lock else ""), (listId, uid))
    return cur.fetchone()


def listCount(cur, listId):
    cur.execute("SELECT COUNT(*) AS n FROM ListItems WHERE ListID = %s", (listId,))
    return int((cur.fetchone() or {}).get("n") or 0)


def moveAfter(cur, table, idColumn, scope, scopeParams, movedId, anchorIndex):
    """Puts one row right after the row at anchorIndex, or first when anchorIndex is None, within `scope` (one
    list's items, or one person's custom lists). Only the rows past the anchor shift, so a long list costs two
    statements, and a row added meanwhile on another device keeps its place."""
    if anchorIndex is None:
        cur.execute(f"SELECT COALESCE(MIN(OrderIndex), 0) AS low FROM {table} WHERE {scope}", scopeParams)
        low = int((cur.fetchone() or {}).get("low") or 0)
        cur.execute(f"UPDATE {table} SET OrderIndex = %s WHERE {scope} AND {idColumn} = %s",
                    (low - 1, *scopeParams, movedId))
        return
    cur.execute(f"UPDATE {table} SET OrderIndex = OrderIndex + 1 WHERE {scope} AND OrderIndex > %s "
                f"AND {idColumn} <> %s", (*scopeParams, anchorIndex, movedId))
    cur.execute(f"UPDATE {table} SET OrderIndex = %s WHERE {scope} AND {idColumn} = %s",
                (anchorIndex + 1, *scopeParams, movedId))


@gluttonyUserBP.route("/lists", methods=["GET"])
def lists():
    with database() as (conn, cur):
        cur.execute("SELECT l.ListID, l.Title, l.Kind, COUNT(li.RecipeID) AS Count FROM Lists l "
                    "LEFT JOIN ListItems li ON li.ListID = l.ListID WHERE l.UserID = %s "
                    "GROUP BY l.ListID, l.Title, l.Kind, l.OrderIndex "
                    "ORDER BY l.Kind = 'custom', l.OrderIndex, l.ListID", (session.requestUID(),))
        rows = cur.fetchall()
    return ok([listRow(r) for r in rows])


@gluttonyUserBP.route("/lists/create", methods=["POST"])
def createList():
    title, problem = rules.listTitle(body().get("title"))
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        # The person's row is locked, so two creates racing cannot both be the fiftieth.
        cur.execute("SELECT UserID FROM Users WHERE UserID = %s FOR UPDATE", (uid,))
        cur.execute("SELECT COUNT(*) AS n, COALESCE(MAX(OrderIndex), 0) AS top FROM Lists WHERE UserID = %s", (uid,))
        found = cur.fetchone() or {}
        if int(found.get("n") or 0) >= rules.MAX_LISTS:
            return fail(f"you can have at most {rules.MAX_LISTS} lists", 400)
        cur.execute("INSERT INTO Lists (UserID, Title, Kind, OrderIndex) VALUES (%s, %s, 'custom', %s)",
                    (uid, title, int(found.get("top") or 0) + 1))
        listId = cur.lastrowid
        conn.commit()
    return ok({"id": listId, "title": title, "kind": "custom", "count": 0})


@gluttonyUserBP.route("/lists/rename", methods=["POST"])
def renameList():
    data = body()
    listId = rules.positiveId(data.get("id"))
    if not listId:
        return fail("id must be a list id", 400)
    title, problem = rules.listTitle(data.get("title"))
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        row = ownList(cur, uid, listId, lock=True)
        if not row:
            return fail("no such list", 404)
        if row["Kind"] == "cravings":
            return fail("Cravings can't be renamed", 400)
        cur.execute("UPDATE Lists SET Title = %s WHERE ListID = %s AND UserID = %s", (title, listId, uid))
        count = listCount(cur, listId)
        conn.commit()
    return ok({"id": listId, "title": title, "kind": "custom", "count": count})


@gluttonyUserBP.route("/lists/delete", methods=["POST"])
def deleteList():
    """A list goes with its items (ON DELETE CASCADE); the recipes stay in the catalog."""
    listId = rules.positiveId(body().get("id"))
    if not listId:
        return fail("id must be a list id", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        row = ownList(cur, uid, listId, lock=True)
        if not row:
            return fail("no such list", 404)
        if row["Kind"] == "cravings":
            return fail("Cravings can't be deleted", 400)
        cur.execute("DELETE FROM Lists WHERE ListID = %s AND UserID = %s", (listId, uid))
        conn.commit()
    return ok()


@gluttonyUserBP.route("/lists/reorder", methods=["POST"])
def reorderLists():
    """One custom list moves after another (or first, after null or after Cravings). Cravings always shows first."""
    data = body()
    listId = rules.positiveId(data.get("id"))
    after = data.get("after")
    afterId = rules.positiveId(after)
    if not listId or (after is not None and not afterId):
        return fail("id must be a list id, and after a list id or null", 400)
    if afterId == listId:
        return fail("a list can't go after itself", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        moving = ownList(cur, uid, listId, lock=True)
        if not moving:
            return fail("no such list", 404)
        if moving["Kind"] == "cravings":
            return fail("Cravings stays first", 400)
        anchorIndex = None
        if afterId:
            anchor = ownList(cur, uid, afterId)
            if not anchor:
                return fail("no such list", 404)
            anchorIndex = None if anchor["Kind"] == "cravings" else anchor["OrderIndex"]
        moveAfter(cur, "Lists", "ListID", "UserID = %s AND Kind = 'custom'", (uid,), listId, anchorIndex)
        conn.commit()
    return ok()


def itemIds(data):
    return rules.positiveId(data.get("listId")), rules.positiveId(data.get("recipeId"))


@gluttonyUserBP.route("/lists/items/add", methods=["POST"])
def addToList():
    """Adding a recipe already on the list changes nothing, so a resent add is harmless."""
    listId, recipeId = itemIds(body())
    if not listId or not recipeId:
        return fail("listId and recipeId must be ids", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        if not ownList(cur, uid, listId, lock=True):
            return fail("no such list", 404)
        if not kept.visibleRecipe(cur, uid, recipeId):
            return fail("no such recipe", 404)
        cur.execute("SELECT COUNT(*) AS n, COALESCE(MIN(OrderIndex), 0) AS low, SUM(RecipeID = %s) AS here "
                    "FROM ListItems WHERE ListID = %s", (recipeId, listId))
        found = cur.fetchone() or {}
        count = int(found.get("n") or 0)
        if not int(found.get("here") or 0):
            if count >= rules.MAX_LIST_ITEMS:
                return fail(f"a list holds at most {rules.MAX_LIST_ITEMS} recipes", 400)
            cur.execute("INSERT INTO ListItems (ListID, RecipeID, OrderIndex) VALUES (%s, %s, %s)",
                        (listId, recipeId, int(found.get("low") or 0) - 1))
            count += 1
        conn.commit()
    return ok({"listId": listId, "recipeId": recipeId, "count": count})


@gluttonyUserBP.route("/lists/items/remove", methods=["POST"])
def removeFromList():
    listId, recipeId = itemIds(body())
    if not listId or not recipeId:
        return fail("listId and recipeId must be ids", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        if not ownList(cur, uid, listId, lock=True):
            return fail("no such list", 404)
        cur.execute("DELETE FROM ListItems WHERE ListID = %s AND RecipeID = %s", (listId, recipeId))
        count = listCount(cur, listId)
        conn.commit()
    return ok({"listId": listId, "recipeId": recipeId, "count": count})


def itemIndex(cur, listId, recipeId):
    cur.execute("SELECT OrderIndex FROM ListItems WHERE ListID = %s AND RecipeID = %s", (listId, recipeId))
    row = cur.fetchone()
    return None if row is None else row["OrderIndex"]


@gluttonyUserBP.route("/lists/items/reorder", methods=["POST"])
def reorderItems():
    """One recipe moves after another on the same list (or to the top, after null). A recipe or anchor that has
    left the list meanwhile (another device) is a 404, and the app shows the list again as the server holds it."""
    data = body()
    listId, recipeId = itemIds(data)
    after = data.get("after")
    afterId = rules.positiveId(after)
    if not listId or not recipeId or (after is not None and not afterId):
        return fail("listId and recipeId must be ids, and after a recipe id or null", 400)
    if afterId == recipeId:
        return fail("a recipe can't go after itself", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        if not ownList(cur, uid, listId, lock=True):
            return fail("no such list", 404)
        if itemIndex(cur, listId, recipeId) is None:
            return fail("that recipe is not on this list", 404)
        anchorIndex = None
        if afterId:
            anchorIndex = itemIndex(cur, listId, afterId)
            if anchorIndex is None:
                return fail("that recipe is not on this list", 404)
        moveAfter(cur, "ListItems", "RecipeID", "ListID = %s", (listId,), recipeId, anchorIndex)
        conn.commit()
    return ok()


@gluttonyUserBP.route("/lists/<int:listId>/recipes", methods=["GET"])
def listRecipes(listId):
    """A list's recipes, a page at a time, in the person's order. A recipe part 1 has removed stays, marked removed:
    the person kept it, so it is theirs to open."""
    page, pageSize, problem = rules.pageArgs(request.args)
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        row = ownList(cur, uid, listId)
        if not row:
            return fail("no such list", 404)
        total = listCount(cur, listId)
        cur.execute(f"SELECT {rules.TILE_COLUMNS}, r.RemovedAt FROM ListItems li "
                    "JOIN Recipes r ON r.RecipeID = li.RecipeID WHERE li.ListID = %s "
                    "ORDER BY li.OrderIndex, li.AddedAt DESC, r.RecipeID LIMIT %s OFFSET %s",
                    (listId, pageSize, (page - 1) * pageSize))
        tiles = kept.attachTileFlags(cur, uid, [kept.savedTile(r) for r in cur.fetchall()])
    return ok({"total": total, "page": page, "pageSize": pageSize, "list": listRow(dict(row, Count=total)),
               "recipes": tiles})


# ---- Devoured, stars and notes ----

def devouredCount(cur, uid, recipeId):
    cur.execute("SELECT COUNT(*) AS n FROM Devoured WHERE UserID = %s AND RecipeID = %s", (uid, recipeId))
    return int((cur.fetchone() or {}).get("n") or 0)


class Refusal(Exception):
    """A change the person may not make, with the words and status its route answers."""

    def __init__(self, message, code):
        super().__init__(message)
        self.message = message
        self.code = code


def storeMark(cur, uid, recipeId, day, clientId):
    """(row, already): the mark named by clientId, stored now or found from before ({DevouredID, RecipeID, MadeOn}).
    The same mark sent again, by a retry or the offline queue, is found and never counted twice. Raises Refusal for
    a recipe the person may not see, or a clientId another account holds."""
    if not kept.visibleRecipe(cur, uid, recipeId):
        raise Refusal("no such recipe", 404)
    cur.execute("SELECT DevouredID, RecipeID, MadeOn FROM Devoured WHERE ClientID = %s AND UserID = %s",
                (clientId, uid))
    found = cur.fetchone()
    if found:
        return found, True
    try:
        cur.execute("INSERT INTO Devoured (UserID, RecipeID, MadeOn, ClientID) VALUES (%s, %s, %s, %s)",
                    (uid, recipeId, day, clientId))
        return {"DevouredID": cur.lastrowid, "RecipeID": recipeId, "MadeOn": day}, False
    except Exception as error:
        if getattr(error, "errno", None) != DUPLICATE_ENTRY:
            raise
    # The unique key on ClientID is global, so the row that holds this id is either this person's own (a resend
    # that raced its twin: answer it as stored) or someone else's (never theirs to see, and never overwritten:
    # refuse). A locking read, because the transaction's snapshot predates the twin.
    cur.execute("SELECT DevouredID, RecipeID, MadeOn, UserID FROM Devoured WHERE ClientID = %s LOCK IN SHARE MODE",
                (clientId,))
    found = cur.fetchone()
    if not found or found["UserID"] != uid:
        raise Refusal("that clientId is in use", 409)
    return found, True


@gluttonyUserBP.route("/devoured/add", methods=["POST"])
def devour():
    """One more time the person made the recipe. The app names the mark (clientId), so the same mark sent again,
    by a retry or a queue, is answered with the row already stored and never counted twice."""
    data = body()
    recipeId = rules.positiveId(data.get("recipeId"))
    if not recipeId:
        return fail("recipeId must be a recipe id", 400)
    day, problem = rules.madeOn(data.get("on"), datetime.now(timezone.utc).date())
    if problem:
        return fail(problem, 400)
    clientId = data.get("clientId")
    problem = rules.clientIdProblem(clientId)
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        try:
            found, already = storeMark(cur, uid, recipeId, day, clientId)
        except Refusal as refusal:
            return fail(refusal.message, refusal.code)
        count = devouredCount(cur, uid, found["RecipeID"])
        conn.commit()
    return ok({"id": found["DevouredID"], "recipeId": found["RecipeID"], "on": rules.isoDate(found["MadeOn"]),
               "count": count, "already": already})


@gluttonyUserBP.route("/devoured/remove", methods=["POST"])
def undevour():
    markId = rules.positiveId(body().get("id"))
    if not markId:
        return fail("id must be a Devoured mark's id", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        cur.execute("SELECT RecipeID FROM Devoured WHERE DevouredID = %s AND UserID = %s", (markId, uid))
        row = cur.fetchone()
        if not row:
            return fail("no such Devoured mark", 404)
        cur.execute("DELETE FROM Devoured WHERE DevouredID = %s AND UserID = %s", (markId, uid))
        count = devouredCount(cur, uid, row["RecipeID"])
        conn.commit()
    return ok({"id": markId, "recipeId": row["RecipeID"], "count": count})


HISTORY_ORDER = {"recent": "d.MadeOn DESC, d.DevouredID DESC",
                 "stars": "t.Stars IS NULL, t.Stars DESC, d.MadeOn DESC, d.DevouredID DESC"}


@gluttonyUserBP.route("/devoured", methods=["GET"])
def devouredHistory():
    """Every time the person made something, newest first or best-starred first, a page at a time. Each tile is one
    mark, with its day and id; a recipe part 1 has removed stays, marked removed."""
    page, pageSize, problem = rules.pageArgs(request.args)
    if problem:
        return fail(problem, 400)
    sort = request.args.get("sort") or "recent"
    if sort not in HISTORY_ORDER:
        return fail("sort must be recent or stars", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        cur.execute("SELECT COUNT(*) AS n FROM Devoured WHERE UserID = %s", (uid,))
        total = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(f"SELECT {rules.TILE_COLUMNS}, r.RemovedAt, d.DevouredID, d.MadeOn FROM Devoured d "
                    "JOIN Recipes r ON r.RecipeID = d.RecipeID "
                    "LEFT JOIN Ratings t ON t.UserID = d.UserID AND t.RecipeID = d.RecipeID "
                    f"WHERE d.UserID = %s ORDER BY {HISTORY_ORDER[sort]} LIMIT %s OFFSET %s",
                    (uid, pageSize, (page - 1) * pageSize))
        tiles = [dict(kept.savedTile(r), devouredId=r["DevouredID"], on=rules.isoDate(r["MadeOn"]))
                 for r in cur.fetchall()]
        kept.attachTileFlags(cur, uid, tiles)
    return ok({"total": total, "page": page, "pageSize": pageSize, "recipes": tiles})


@gluttonyUserBP.route("/rating", methods=["POST"])
def rate():
    data = body()
    recipeId = rules.positiveId(data.get("recipeId"))
    if not recipeId:
        return fail("recipeId must be a recipe id", 400)
    stars, problem = rules.starsValue(data.get("stars"))
    if problem or "stars" not in data:
        return fail(problem or "stars must be a whole number from 1 to 5, or null", 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        if not kept.visibleRecipe(cur, uid, recipeId):
            return fail("no such recipe", 404)
        # Cleared stars stay as a row (Stars NULL) stamped with when they were cleared (schema-part2.sql).
        cur.execute("INSERT INTO Ratings (UserID, RecipeID, Stars, UpdatedAt) VALUES (%s, %s, %s, UTC_TIMESTAMP(3)) "
                    "ON DUPLICATE KEY UPDATE Stars = VALUES(Stars), UpdatedAt = VALUES(UpdatedAt)",
                    (uid, recipeId, stars))
        conn.commit()
    return ok({"recipeId": recipeId, "stars": stars})


@gluttonyUserBP.route("/note", methods=["POST"])
def note():
    data = body()
    recipeId = rules.positiveId(data.get("recipeId"))
    if not recipeId:
        return fail("recipeId must be a recipe id", 400)
    text, problem = rules.noteText(data.get("text"))
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        if not kept.visibleRecipe(cur, uid, recipeId):
            return fail("no such recipe", 404)
        # A deleted note stays as a row with no text, stamped with when it was deleted (schema-part2.sql).
        cur.execute("INSERT INTO Notes (UserID, RecipeID, Text, UpdatedAt) VALUES (%s, %s, %s, UTC_TIMESTAMP(3)) "
                    "ON DUPLICATE KEY UPDATE Text = VALUES(Text), UpdatedAt = VALUES(UpdatedAt)",
                    (uid, recipeId, text))
        conn.commit()
    return ok({"recipeId": recipeId, "note": text or None})


# ---- what the app did offline ----

def storeNewer(cur, table, column, uid, recipeId, value, at):
    """(applied, held): writes a rating's stars or a note's text as of `at`, unless the row already holds a change
    made at that moment or after it (a newer change, or this same one sent again). `held` is what the row holds
    afterwards. The row is read locked, so two batches can't both decide they are newer."""
    cur.execute(f"SELECT {column}, UpdatedAt FROM {table} WHERE UserID = %s AND RecipeID = %s FOR UPDATE",
                (uid, recipeId))
    row = cur.fetchone()
    if row and row["UpdatedAt"] >= at:
        return False, row[column]
    cur.execute(f"INSERT INTO {table} (UserID, RecipeID, {column}, UpdatedAt) VALUES (%s, %s, %s, %s) "
                f"ON DUPLICATE KEY UPDATE {column} = VALUES({column}), UpdatedAt = VALUES(UpdatedAt)",
                (uid, recipeId, value, at))
    return True, value


def refused(message):
    return {"result": "refused", "message": message}


def applyChange(cur, uid, change, now):
    """One queued change, made as its own route would make it, and the answer the app reads for it."""
    kind = change.get("op")
    if kind not in rules.SYNC_OPS:
        return refused("op must be devoured, stars or note")
    recipeId = rules.positiveId(change.get("recipeId"))
    if not recipeId:
        return refused("recipeId must be a recipe id")
    at, problem = rules.syncAt(change.get("at"), now)
    if problem:
        return refused(problem)
    if kind == "devoured":
        day, problem = rules.madeOn(change.get("on"), now.date())
        problem = problem or rules.clientIdProblem(change.get("clientId"))
        if problem:
            return refused(problem)
        try:
            found, already = storeMark(cur, uid, recipeId, day, change["clientId"])
        except Refusal as refusal:
            return refused(refusal.message)
        return {"result": "already" if already else "applied", "id": found["DevouredID"],
                "recipeId": found["RecipeID"], "on": rules.isoDate(found["MadeOn"]),
                "count": devouredCount(cur, uid, found["RecipeID"])}
    if kind == "stars":
        stars, problem = rules.starsValue(change.get("stars"))
        if problem or "stars" not in change:
            return refused(problem or "stars must be a whole number from 1 to 5, or null")
        if not kept.visibleRecipe(cur, uid, recipeId):
            return refused("no such recipe")
        applied, held = storeNewer(cur, "Ratings", "Stars", uid, recipeId, stars, at)
        return {"result": "applied" if applied else "already", "recipeId": recipeId, "stars": held}
    text, problem = rules.noteText(change.get("text"))
    if problem:
        return refused(problem)
    if not kept.visibleRecipe(cur, uid, recipeId):
        return refused("no such recipe")
    applied, held = storeNewer(cur, "Notes", "Text", uid, recipeId, text, at)
    return {"result": "applied" if applied else "already", "recipeId": recipeId, "note": held or None}


def retryPause(attempt):
    """A short, jittered wait before a batch that lost a lock conflict is tried again. A deadlock victim that retried
    at once would re-take its gap lock while the other devices' batches still hold theirs and be the victim again; the
    jitter spreads the devices out, and the wait grows a little with each try."""
    time.sleep(random.uniform(0.02, 0.1) * (attempt + 1))


@gluttonyUserBP.route("/sync/batch", methods=["POST"])
def syncBatch():
    """What the app did while it couldn't reach the server (Devoured marks, stars, notes), up to 500 changes,
    applied oldest first and answered one by one in the order sent. A mark is stored once per clientId; stars and
    notes keep whichever change is newest, so a queue that arrives late never undoes something done since. A change
    that can't be made is refused with its reason, and never stops the others; a batch that meets a lock conflict is
    tried again whole, and a server error applies nothing."""
    ops, problem = rules.syncOps(body().get("ops"))
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    now = datetime.now(timezone.utc)

    def oldestFirst(index):
        # A change whose moment is unreadable is refused whatever its place, so it may go first.
        at, _ = rules.syncAt(ops[index].get("at"), now)
        return at or datetime.min

    global lockRetries
    # Two devices sending changes for the same recipe at once can deadlock on the gap locks storeNewer's FOR UPDATE
    # takes on a row that does not exist yet. MySQL rolls one batch back whole, so it is tried again whole.
    for attempt in range(SYNC_ATTEMPTS):
        try:
            results = [None] * len(ops)
            with database() as (conn, cur):
                for index in sorted(range(len(ops)), key=oldestFirst):
                    results[index] = applyChange(cur, uid, ops[index], now)
                conn.commit()
            return ok({"results": results})
        except Exception as error:
            if getattr(error, "errno", None) not in LOCK_CONFLICTS or attempt == SYNC_ATTEMPTS - 1:
                raise
            lockRetries += 1
            retryPause(attempt)


def stamp(moment):
    """A recipe's UpdatedAt as the manifest gives it. The app only compares it with the one it stored with its copy,
    so it is the column as it stands, to the second."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S") if moment else None


@gluttonyUserBP.route("/saved/manifest", methods=["GET"])
def savedManifest():
    """What the app keeps for use without a server: every list (Cravings first, then the person's order) with its
    recipes in their order, and every recipe on them with when part 1 last changed it, so the app fetches only what
    has moved on. Each recipe also carries the person's own `mine` block, as /recipes/<id> gives it: a star, a note,
    a mark or a list changed on another device reaches this device's copy without fetching the recipe again, and a
    mark or list removal (which leaves no row to date) is seen too. `extra` names recipes the app opened in cook
    mode, which it keeps beside them; one the person may no longer see (its source removed it, and they don't keep
    it) is left out, and the app lets its copy go."""
    extra, problem = rules.extraIds(request.args.get("extra"))
    if problem:
        return fail(problem, 400)
    uid = session.requestUID()
    with database() as (conn, cur):
        cur.execute("SELECT ListID, Title, Kind FROM Lists WHERE UserID = %s "
                    "ORDER BY Kind = 'custom', OrderIndex, ListID", (uid,))
        lists = [{"id": row["ListID"], "title": row["Title"], "kind": row["Kind"], "recipeIds": []}
                 for row in cur.fetchall()]
        byId = {entry["id"]: entry for entry in lists}
        cur.execute("SELECT li.ListID, li.RecipeID FROM ListItems li JOIN Lists l ON l.ListID = li.ListID "
                    "WHERE l.UserID = %s ORDER BY li.ListID, li.OrderIndex, li.AddedAt DESC, li.RecipeID", (uid,))
        for row in cur.fetchall():
            byId[row["ListID"]]["recipeIds"].append(row["RecipeID"])
        listed = {rid for entry in lists for rid in entry["recipeIds"]}
        ids = sorted(listed | set(extra))
        recipes = []
        if ids:
            marks = ", ".join(["%s"] * len(ids))
            # The person's stars and note ride along with each recipe's row; a cleared rating or a deleted note is
            # a row with no value (schema-part2.sql), read as null, as mineOf reads it.
            cur.execute("SELECT r.RecipeID, r.UpdatedAt, r.RemovedAt, t.Stars, NULLIF(n.Text, '') AS Note "
                        "FROM Recipes r "
                        "LEFT JOIN Ratings t ON t.UserID = %s AND t.RecipeID = r.RecipeID "
                        "LEFT JOIN Notes n ON n.UserID = %s AND n.RecipeID = r.RecipeID "
                        f"WHERE r.RecipeID IN ({marks}) ORDER BY r.RecipeID", (uid, uid, *ids))
            rows = cur.fetchall()
            cur.execute(f"SELECT RecipeID, DevouredID, MadeOn FROM Devoured WHERE UserID = %s AND RecipeID IN ({marks}) "
                        "ORDER BY RecipeID, MadeOn DESC, DevouredID DESC", (uid, *ids))
            devoured = {}
            for row in cur.fetchall():
                devoured.setdefault(row["RecipeID"], []).append({"id": row["DevouredID"],
                                                                 "on": rules.isoDate(row["MadeOn"])})
            cravings = {rid for entry in lists if entry["kind"] == "cravings" for rid in entry["recipeIds"]}
            # The person's own lists in their order, as mineOf names them (Cravings is `craving`, not a list).
            custom = [(entry["id"], set(entry["recipeIds"])) for entry in lists if entry["kind"] == "custom"]
            for row in rows:
                rid = row["RecipeID"]
                removed = row["RemovedAt"] is not None
                if removed and rid not in listed and not kept.keptBy(cur, uid, rid):
                    continue
                mine = {"craving": rid in cravings, "lists": [listId for listId, held in custom if rid in held],
                        "devoured": devoured.get(rid, []), "stars": row["Stars"], "note": row["Note"]}
                recipes.append({"id": rid, "updatedAt": stamp(row["UpdatedAt"]), "removed": removed, "mine": mine})
    return ok({"lists": lists, "recipes": recipes})
