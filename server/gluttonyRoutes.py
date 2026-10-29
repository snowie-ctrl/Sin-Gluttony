"""
Gluttony's read API, at /api/gluttony: what the app browses, filters and opens. Every route needs a session
(gluttonySession.py) except ping; the same blueprint answers on the LAN and, once nginx passes the prefix,
through gluttony.forculus.net. Accounts, the diet profile and what a person keeps live in gluttonyUserRoutes.py
on the same prefix; every tile here carries the person's flags (gluttonyKept.py).
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from . import gluttonyKept as kept, gluttonyRules as rules, gluttonySession as session

gluttonyBP = Blueprint("gluttony", __name__)
session.install(gluttonyBP)
database = session.database

MEDIA_ROOT = Path("/pool/appFiles/gluttony")
FROM_RECIPES = "FROM Recipes r LEFT JOIN RecipeFacts fa ON fa.RecipeID = r.RecipeID"


def ok(data=None):
    return jsonify({"status": "ok"} if data is None else {"status": "ok", "data": data}), 200


def fail(message, code):
    return jsonify({"status": "error", "message": message}), code


@gluttonyBP.route("/ping", methods=["GET"])
def ping():
    return ok()


def narrowed(cur, f):
    """The filters with the account's profile added (unless profile=off), and the ingredient sets for include and
    exclude, where asking for cheese also finds cheddar."""
    if f["profile"]:
        f = rules.withProfile(f, *session.profileOf(cur, session.requestUID()))
    includeSets, excludeIds = [], set()
    if "include" in f or "exclude" in f:
        cur.execute("SELECT IngredientID, ParentID FROM Ingredients")
        tree = cur.fetchall()
        includeSets = [rules.descendants(tree, [i]) for i in f.get("include", [])]
        excludeIds = rules.descendants(tree, f.get("exclude", []))
    return f, includeSets, excludeIds


@gluttonyBP.route("/recipes", methods=["GET"])
def recipes():
    f, problem = rules.parseFilters(request.args)
    if problem:
        return fail(problem, 400)
    with database() as (conn, cur):
        f, includeSets, excludeIds = narrowed(cur, f)
        where, params = rules.recipeWhere(f, includeSets, excludeIds)
        cur.execute(f"SELECT COUNT(*) AS n {FROM_RECIPES} WHERE {where}", params)
        total = (cur.fetchone() or {}).get("n", 0)
        order, orderParams = rules.recipeOrder(f, date.today().isoformat())
        cur.execute(f"SELECT {rules.TILE_COLUMNS} {FROM_RECIPES} WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
                    [*params, *orderParams, f["pageSize"], (f["page"] - 1) * f["pageSize"]])
        tiles = kept.attachTileFlags(cur, session.requestUID(), [rules.tile(r) for r in cur.fetchall()])
    return ok({"total": total, "page": f["page"], "pageSize": f["pageSize"], "recipes": tiles})


@gluttonyBP.route("/random", methods=["GET"])
def randomRecipe():
    """'Go on, then': one recipe that fits the filters and the profile, or null when nothing does."""
    f, problem = rules.parseFilters(request.args)
    if problem:
        return fail(problem, 400)
    with database() as (conn, cur):
        f, includeSets, excludeIds = narrowed(cur, f)
        where, params = rules.recipeWhere(f, includeSets, excludeIds)
        cur.execute(f"SELECT {rules.TILE_COLUMNS} {FROM_RECIPES} WHERE {where} ORDER BY RAND() LIMIT 1", params)
        row = cur.fetchone()
        picked = kept.attachTileFlags(cur, session.requestUID(), [rules.tile(row)])[0] if row else None
    return ok({"recipe": picked})


@gluttonyBP.route("/home", methods=["GET"])
def home():
    """Today's temptation and today's picks: food to cook, with a picture, fitting the profile, not made in the last
    30 days, in an order that holds for this person all day in their own zone. Then the person's own rows: Cravings
    in their order, and Again? (what they made, most recent first). Those are theirs, so the profile leaves them be."""
    profile = request.args.get("profile") or "on"
    if profile not in ("on", "off"):
        return fail("profile must be on or off", 400)
    uid = session.requestUID()
    day = rules.localDate((request.args.get("tz") or "")[:64], datetime.now(timezone.utc))
    cutoff = (date.fromisoformat(day) - timedelta(days=rules.RECENT_DAYS)).isoformat()
    with database() as (conn, cur):
        f = {"kind": "food", "course": list(rules.HOME_COURSES)}
        if profile == "on":
            f = rules.withProfile(f, *session.profileOf(cur, uid))
        where, params = rules.recipeWhere(f)
        order, orderParams = rules.homeOrder(uid, day)
        cur.execute(f"SELECT {rules.TILE_COLUMNS} {FROM_RECIPES} WHERE {where} AND r.ImagePath IS NOT NULL "
                    "AND NOT EXISTS (SELECT 1 FROM Devoured d WHERE d.UserID = %s AND d.RecipeID = r.RecipeID "
                    "AND d.MadeOn > %s) "
                    f"ORDER BY {order} LIMIT %s", [*params, uid, cutoff, *orderParams, rules.HOME_PICKS + 1])
        tiles = [rules.tile(r) for r in cur.fetchall()]
        cur.execute(f"SELECT {rules.TILE_COLUMNS}, r.RemovedAt FROM ListItems li "
                    "JOIN Lists l ON l.ListID = li.ListID JOIN Recipes r ON r.RecipeID = li.RecipeID "
                    "WHERE l.UserID = %s AND l.Kind = 'cravings' ORDER BY li.OrderIndex, li.AddedAt DESC LIMIT %s",
                    (uid, rules.HOME_ROW))
        cravings = [kept.savedTile(r) for r in cur.fetchall()]
        cur.execute(f"SELECT {rules.TILE_COLUMNS}, r.RemovedAt, MAX(d.MadeOn) AS LastMade FROM Devoured d "
                    "JOIN Recipes r ON r.RecipeID = d.RecipeID WHERE d.UserID = %s GROUP BY r.RecipeID "
                    "ORDER BY LastMade DESC, MAX(d.DevouredID) DESC LIMIT %s", (uid, rules.HOME_ROW))
        again = [kept.savedTile(r) for r in cur.fetchall()]
        kept.attachTileFlags(cur, uid, tiles + cravings + again)
    return ok({"date": day, "pick": tiles[0] if tiles else None, "picks": tiles[1:], "cravings": cravings,
               "again": again})


@gluttonyBP.route("/recipes/<int:recipeId>", methods=["GET"])
def recipe(recipeId):
    uid = session.requestUID()
    with database() as (conn, cur):
        cur.execute(f"SELECT r.*, fa.Complete {FROM_RECIPES} WHERE r.RecipeID = %s", (recipeId,))
        row = cur.fetchone()
        # A recipe part 1 removed answers only to someone who keeps it; anyone else hears it does not exist.
        if not row or (row.get("RemovedAt") is not None and not kept.keptBy(cur, uid, recipeId)):
            return fail("no such recipe", 404)
        cur.execute("SELECT ri.Position, ri.Line, ri.Quantity, ri.QuantityMax, ri.Unit, ri.IngredientID, i.Name, "
                    "ri.Note, ri.Optional, ri.GroupHeading FROM RecipeIngredients ri "
                    "LEFT JOIN Ingredients i ON i.IngredientID = ri.IngredientID "
                    "WHERE ri.RecipeID = %s ORDER BY ri.Position", (recipeId,))
        ingredients = cur.fetchall()
        cur.execute("SELECT Position, Text, GroupHeading FROM RecipeSteps WHERE RecipeID = %s ORDER BY Position",
                    (recipeId,))
        steps = cur.fetchall()
        cur.execute("SELECT Type, Tag FROM RecipeTags WHERE RecipeID = %s ORDER BY Type, Tag", (recipeId,))
        tags = cur.fetchall()
        cur.execute("SELECT Item FROM RecipeContains WHERE RecipeID = %s ORDER BY Item", (recipeId,))
        contains = cur.fetchall()
        cur.execute("SELECT Diet FROM RecipeDiets WHERE RecipeID = %s ORDER BY Diet", (recipeId,))
        diets = cur.fetchall()
        cur.execute("SELECT RecipeID, Title, Source, ImagePath FROM Recipes WHERE DishKey = %s AND RecipeID <> %s "
                    "AND RemovedAt IS NULL ORDER BY Title LIMIT 20", (row["DishKey"], recipeId))
        versions = cur.fetchall()
        detail = rules.recipeDetail(row, ingredients, steps, tags, contains, diets, versions)
        detail["removed"] = row.get("RemovedAt") is not None
        detail["mine"] = kept.mineOf(cur, uid, recipeId)
        kept.attachTileFlags(cur, uid, detail["versions"])
    return ok(detail)


@gluttonyBP.route("/filters", methods=["GET"])
def filters():
    shown = "FROM Recipes WHERE RemovedAt IS NULL"
    with database() as (conn, cur):
        counts = {}
        for name, column in (("kinds", "Kind"), ("courses", "Course"), ("cuisines", "Cuisine"),
                             ("difficulties", "Difficulty")):
            cur.execute(f"SELECT {column} AS v, COUNT(*) AS n {shown} AND {column} IS NOT NULL "
                        f"GROUP BY {column} ORDER BY n DESC")
            counts[name] = [{"value": r["v"], "count": r["n"]} for r in cur.fetchall()]
        cur.execute("SELECT t.Type, t.Tag AS v, COUNT(*) AS n FROM RecipeTags t JOIN Recipes r ON r.RecipeID = t.RecipeID "
                    "WHERE r.RemovedAt IS NULL AND t.Type IN ('flavour', 'occasion') GROUP BY t.Type, t.Tag ORDER BY n DESC")
        tags = cur.fetchall()
        counts["flavours"] = [{"value": r["v"], "count": r["n"]} for r in tags if r["Type"] == "flavour"]
        counts["occasions"] = [{"value": r["v"], "count": r["n"]} for r in tags if r["Type"] == "occasion"]
        cur.execute("SELECT d.Diet AS v, COUNT(*) AS n FROM RecipeDiets d JOIN Recipes r ON r.RecipeID = d.RecipeID "
                    "WHERE r.RemovedAt IS NULL GROUP BY d.Diet ORDER BY n DESC")
        counts["diets"] = [{"value": r["v"], "count": r["n"]} for r in cur.fetchall()]
    counts["avoid"] = list(rules.CONTAINS_ITEMS)
    return ok(counts)


@gluttonyBP.route("/ingredients", methods=["GET"])
def ingredients():
    q = (request.args.get("q") or "").strip()
    if not 1 <= len(q) <= 60:
        return fail("q must be 1 to 60 characters", 400)
    with database() as (conn, cur):
        cur.execute("SELECT IngredientID, Name FROM Ingredients WHERE Name LIKE %s ORDER BY CHAR_LENGTH(Name), Name "
                    "LIMIT 20", (f"%{rules.likeEscape(q)}%",))
        rows = cur.fetchall()
    return ok([{"id": r["IngredientID"], "name": r["Name"]} for r in rows])


def _picture(recipeId, folder):
    with database() as (conn, cur):
        row = kept.visibleRecipe(cur, session.requestUID(), recipeId)
    name = (row or {}).get("ImagePath")
    if not name or not rules.IMAGE_NAME.fullmatch(name):
        return fail("no picture", 404)
    target = MEDIA_ROOT / folder / name
    if not target.is_file():
        return fail("no picture", 404)
    response = send_file(target, mimetype="image/jpeg", conditional=True, max_age=86400)
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@gluttonyBP.route("/images/<int:recipeId>", methods=["GET"])
def image(recipeId):
    return _picture(recipeId, "images")


@gluttonyBP.route("/thumbs/<int:recipeId>", methods=["GET"])
def thumb(recipeId):
    return _picture(recipeId, "thumbs")
