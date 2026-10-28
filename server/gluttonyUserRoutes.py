# Copied from Pageturner/server/pageturnerRoutes.py at 062da3b; changes: the account routes only, on
# gluttonyDB's Users.UserID; usernames 3-32 characters; a sign-up's password is checked like a new one;
# the diet profile routes are new.
"""
Accounts and what a person keeps (the diet profile, at /me/diet), at /api/gluttony beside the read API
(gluttonyRoutes.py), which applies the saved profile to every search. docs/api.md is the contract. Users sign up with a login key the
owner inserts by hand, and a device that signed in once signs in by itself (/device/identify) until it signs
out.
"""
import hashlib
import secrets
from datetime import timedelta

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from . import gluttonyRules as rules, gluttonySession as session

gluttonyUserBP = Blueprint("gluttonyUser", __name__)
session.install(gluttonyUserBP)
database = session.database
fail = session.fail

USERNAME_MIN, USERNAME_MAX = 3, 32
PASSWORD_MIN, PASSWORD_MAX = 8, 256
# MySQL's error number for a duplicate key.
DUPLICATE_ENTRY = 1062


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
