"""
Gluttony's admin routes on plutus, at /api/gluttony-admin. The scraper sends
recipes and removals here and reads the ingredient table; Surrogate reads the
counts and maps unknown ingredients. LAN only: the public tunnel's nginx never
routes this prefix. Every request needs X-Admin-Token. Validation lives in
gluttonyRules, so the routes stay thin.
"""
import hmac
import json
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from flask import Blueprint, jsonify, request

from . import DBUtils, gluttonyRules as rules

gluttonyAdminBP = Blueprint("gluttonyAdmin", __name__)

CONFIG_FILE = Path(__file__).resolve().parent / "gluttonyAdminConfig.json"
DB_NAME = "gluttony"
_tokenCache = {"mtime": None, "token": None}


def adminToken():
    """The token from gluttonyAdminConfig.json, read again whenever the file changes."""
    try:
        mtime = CONFIG_FILE.stat().st_mtime
    except (OSError, AttributeError, TypeError):
        return None
    if _tokenCache["mtime"] != mtime:
        try:
            _tokenCache["token"] = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("token") or None
        except (OSError, ValueError):
            _tokenCache["token"] = None
        _tokenCache["mtime"] = mtime
    return _tokenCache["token"]


@gluttonyAdminBP.before_request
def requireAdminToken():
    expected = adminToken()
    given = request.headers.get("X-Admin-Token", "")
    if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
        return jsonify({"status": "error", "message": "unauthorized"}), 401


def error(message, code=400):
    return jsonify({"status": "error", "message": message}), code


def body():
    """The JSON body as a dict, or {} (never Flask 3's automatic 415)."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@contextmanager
def database():
    conn = DBUtils.initConnection(DB_NAME)
    conn.autocommit = False
    cur = conn.cursor(dictionary=True)
    try:
        yield conn, cur
    finally:
        conn.rollback()             # nothing after a commit; anything half-done otherwise
        cur.close()
        conn.close()


# ---- recipes ----

def storeRecipe(cur, r):
    """Insert or update one recipe and replace all its child rows. The caller commits."""
    columns = rules.RECIPE_COLUMNS
    updates = ", ".join(f"{c} = VALUES({c})" for c in columns[2:])
    cur.execute(f"INSERT INTO Recipes ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) "
                f"ON DUPLICATE KEY UPDATE RecipeID = LAST_INSERT_ID(RecipeID), {updates}, RemovedAt = NULL",
                rules.recipeRow(r))
    recipeId = cur.lastrowid
    for table in rules.CHILD_TABLES:
        cur.execute(f"DELETE FROM {table} WHERE RecipeID = %s", (recipeId,))
    for position, line in enumerate(r["ingredients"], start=1):
        cur.execute("INSERT INTO RecipeIngredients (RecipeID, Position, Line, Quantity, QuantityMax, Unit, "
                    "IngredientID, UnknownName, Note, Optional, GroupHeading) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rules.ingredientRow(recipeId, position, line))
    for position, step in enumerate(r["steps"], start=1):
        cur.execute("INSERT INTO RecipeSteps (RecipeID, Position, Text, GroupHeading) VALUES (%s, %s, %s, %s)",
                    (recipeId, position, step["text"], rules.clip(step.get("group"), 120)))
    seen = set()
    for tag in r["tags"]:
        # The key ignores case and accents, as the utf8mb4_0900_ai_ci primary key does ("Café" = "Cafe").
        key = (tag["type"], "".join(c for c in unicodedata.normalize("NFKD", tag["tag"])
                                    if not unicodedata.combining(c)).casefold())
        if key not in seen:
            seen.add(key)
            cur.execute("INSERT INTO RecipeTags (RecipeID, Type, Tag, Origin) VALUES (%s, %s, %s, %s)",
                        (recipeId, tag["type"], tag["tag"], tag["origin"]))
    facts = r["facts"]
    cur.execute("INSERT INTO RecipeFacts (RecipeID, Complete) VALUES (%s, %s)", (recipeId, 1 if facts["complete"] else 0))
    for item in sorted(set(facts["contains"])):
        cur.execute("INSERT INTO RecipeContains (RecipeID, Item) VALUES (%s, %s)", (recipeId, item))
    for diet in sorted(set(facts["diets"])):
        cur.execute("INSERT INTO RecipeDiets (RecipeID, Diet) VALUES (%s, %s)", (recipeId, diet))
    return recipeId


@gluttonyAdminBP.route("/recipes/batch", methods=["POST"])
def recipesBatch():
    data = body()
    problem = rules.batchProblem(data)
    if problem:
        return error(problem)
    stored, failed = [], []
    with database() as (conn, cur):
        for recipe in data["recipes"]:
            key = recipe.get("key") if isinstance(recipe, dict) else None
            problem = rules.recipeProblem(recipe)
            if problem:
                failed.append({"key": key, "message": problem})
                continue
            # One transaction per recipe: a recipe that fails leaves nothing
            # half-written, and the rest of the batch is still stored.
            try:
                storeRecipe(cur, recipe)
                conn.commit()
                stored.append(key)
            except Exception as e:
                conn.rollback()
                failed.append({"key": key, "message": f"database write failed: {type(e).__name__}"})
    return jsonify({"status": "ok", "stored": stored, "failed": failed})


@gluttonyAdminBP.route("/recipes/removed", methods=["POST"])
def recipesRemoved():
    keys = body().get("keys")
    problem = rules.keysProblem(keys)
    if problem:
        return error(problem)
    removed = 0
    with database() as (conn, cur):
        for key in keys:
            source, sourceId = key.split(":", 1)
            cur.execute("UPDATE Recipes SET RemovedAt = NOW() WHERE Source = %s AND SourceID = %s "
                        "AND RemovedAt IS NULL", (source, sourceId))
            removed += cur.rowcount
        conn.commit()
    return jsonify({"status": "ok", "removed": removed})


@gluttonyAdminBP.route("/state", methods=["GET"])
def state():
    with database() as (conn, cur):
        cur.execute("SELECT Source, SourceID, ContentHash FROM Recipes WHERE RemovedAt IS NULL")
        rows = cur.fetchall()
    return jsonify({"status": "ok",
                    "recipes": [{"key": f"{r['Source']}:{r['SourceID']}", "hash": r["ContentHash"]} for r in rows]})


@gluttonyAdminBP.route("/stats", methods=["GET"])
def stats():
    with database() as (conn, cur):
        cur.execute("SELECT Source, Kind, COUNT(*) AS n FROM Recipes WHERE RemovedAt IS NULL "
                    "GROUP BY Source, Kind ORDER BY Source, Kind")
        rows = cur.fetchall()
        cur.execute("SELECT SUM(r.RemovedAt IS NULL) AS total, SUM(r.RemovedAt IS NOT NULL) AS removed, "
                    "SUM(r.RemovedAt IS NULL AND fa.Complete = 1) AS complete "
                    "FROM Recipes r LEFT JOIN RecipeFacts fa ON fa.RecipeID = r.RecipeID")
        totals = cur.fetchone() or {}
    return jsonify({"status": "ok", "total": int(totals.get("total") or 0), "removed": int(totals.get("removed") or 0),
                    "complete": int(totals.get("complete") or 0),
                    "bySource": [{"source": r["Source"], "kind": r["Kind"], "count": r["n"]} for r in rows]})


# ---- the ingredient table ----

@gluttonyAdminBP.route("/ingredients", methods=["GET"])
def ingredients():
    with database() as (conn, cur):
        cur.execute("SELECT IngredientID, Name, ParentID, Category, Origin FROM Ingredients ORDER BY IngredientID")
        rows = cur.fetchall()
        cur.execute("SELECT IngredientID, Item FROM IngredientContains ORDER BY IngredientID, Item")
        contains = cur.fetchall()
        cur.execute("SELECT Alias, IngredientID FROM IngredientAliases ORDER BY Alias")
        aliases = cur.fetchall()
    items = {}
    for row in contains:
        items.setdefault(row["IngredientID"], []).append(row["Item"])
    return jsonify({"status": "ok",
                    "ingredients": [{"id": r["IngredientID"], "name": r["Name"], "parentId": r["ParentID"],
                                     "category": r["Category"], "origin": r["Origin"],
                                     "contains": items.get(r["IngredientID"], [])} for r in rows],
                    "aliases": [{"alias": a["Alias"], "ingredientId": a["IngredientID"]} for a in aliases]})


@gluttonyAdminBP.route("/ingredients/seed", methods=["POST"])
def ingredientsSeed():
    entries = body().get("ingredients")
    problem = rules.seedProblem(entries)
    if problem:
        return error(problem)
    added = updated = kept = 0
    ids, seedNames = {}, []
    with database() as (conn, cur):
        for entry in entries:
            cur.execute("SELECT IngredientID, Origin FROM Ingredients WHERE Name = %s", (entry["name"],))
            row = cur.fetchone()
            if row and row["Origin"] == "owner":
                # The owner's mapping in Surrogate always wins over the seed.
                ids[entry["name"]] = row["IngredientID"]
                kept += 1
                continue
            if row:
                ingredientId = row["IngredientID"]
                cur.execute("UPDATE Ingredients SET Category = %s WHERE IngredientID = %s",
                            (entry.get("category"), ingredientId))
                cur.execute("DELETE FROM IngredientContains WHERE IngredientID = %s", (ingredientId,))
                updated += 1
            else:
                cur.execute("INSERT INTO Ingredients (Name, Category, Origin) VALUES (%s, %s, 'seed')",
                            (entry["name"], entry.get("category")))
                ingredientId = cur.lastrowid
                added += 1
            ids[entry["name"]] = ingredientId
            seedNames.append(entry["name"])
            for item in sorted(set(entry.get("contains", []))):
                cur.execute("INSERT INTO IngredientContains (IngredientID, Item) VALUES (%s, %s)", (ingredientId, item))
            for alias in entry.get("aliases", []):
                cur.execute("INSERT INTO IngredientAliases (Alias, IngredientID, Origin) VALUES (%s, %s, 'seed') "
                            "ON DUPLICATE KEY UPDATE IngredientID = IF(Origin = 'seed', VALUES(IngredientID), IngredientID)",
                            (alias, ingredientId))
        parents = {e["name"]: e.get("parent") for e in entries}
        for name in seedNames:
            cur.execute("UPDATE Ingredients SET ParentID = %s WHERE IngredientID = %s",
                        (ids.get(parents[name]), ids[name]))
        conn.commit()
    return jsonify({"status": "ok", "added": added, "updated": updated, "kept": kept})


@gluttonyAdminBP.route("/ingredients/unknown", methods=["GET"])
def ingredientsUnknown():
    limit, problem = rules.wholeNumberArg(request.args, "limit", 200, 1, 1000)
    if problem:
        return error(problem)
    with database() as (conn, cur):
        cur.execute("SELECT ri.UnknownName AS name, COUNT(DISTINCT ri.RecipeID) AS recipes, MIN(ri.Line) AS example "
                    "FROM RecipeIngredients ri JOIN Recipes r ON r.RecipeID = ri.RecipeID "
                    "WHERE ri.UnknownName IS NOT NULL AND r.RemovedAt IS NULL "
                    "GROUP BY ri.UnknownName ORDER BY recipes DESC, name LIMIT %s", (limit,))
        rows = cur.fetchall()
        cur.execute("SELECT COUNT(DISTINCT ri.UnknownName) AS n FROM RecipeIngredients ri "
                    "JOIN Recipes r ON r.RecipeID = ri.RecipeID WHERE ri.UnknownName IS NOT NULL AND r.RemovedAt IS NULL")
        total = (cur.fetchone() or {}).get("n", 0)
    return jsonify({"status": "ok", "unknown": [{"name": r["name"], "recipes": r["recipes"], "example": r["example"]}
                                                for r in rows], "total": total})


@gluttonyAdminBP.route("/ingredients/search", methods=["GET"])
def ingredientsSearch():
    q = (request.args.get("q") or "").strip()
    if not 1 <= len(q) <= 60:
        return error("q must be 1 to 60 characters")
    with database() as (conn, cur):
        cur.execute("SELECT IngredientID, Name, Category FROM Ingredients WHERE Name LIKE %s "
                    "ORDER BY CHAR_LENGTH(Name), Name LIMIT 20", (f"%{rules.likeEscape(q)}%",))
        rows = cur.fetchall()
    return jsonify({"status": "ok",
                    "ingredients": [{"id": r["IngredientID"], "name": r["Name"], "category": r["Category"]} for r in rows]})


@gluttonyAdminBP.route("/ingredients/map", methods=["POST"])
def ingredientsMap():
    data = body()
    problem = rules.mapProblem(data)
    if problem:
        return error(problem)
    with database() as (conn, cur):
        if "ingredientId" in data:
            cur.execute("SELECT IngredientID FROM Ingredients WHERE IngredientID = %s", (data["ingredientId"],))
            if not cur.fetchone():
                return error("no such ingredient", 404)
            ingredientId = data["ingredientId"]
        else:
            create = data["create"]
            cur.execute("SELECT IngredientID FROM Ingredients WHERE Name = %s", (create["name"].strip(),))
            if cur.fetchone():
                return error("an ingredient with that name already exists; map to it instead", 409)
            if create.get("parentId"):
                cur.execute("SELECT IngredientID FROM Ingredients WHERE IngredientID = %s", (create["parentId"],))
                if not cur.fetchone():
                    return error("no such parent ingredient", 404)
            cur.execute("INSERT INTO Ingredients (Name, ParentID, Category, Origin) VALUES (%s, %s, %s, 'owner')",
                        (create["name"].strip(), create.get("parentId"), create.get("category")))
            ingredientId = cur.lastrowid
            for item in sorted(set(create.get("contains", []))):
                cur.execute("INSERT INTO IngredientContains (IngredientID, Item) VALUES (%s, %s)", (ingredientId, item))
        cur.execute("INSERT INTO IngredientAliases (Alias, IngredientID, Origin) VALUES (%s, %s, 'owner') "
                    "ON DUPLICATE KEY UPDATE IngredientID = VALUES(IngredientID), Origin = 'owner'",
                    (data["alias"].strip(), ingredientId))
        conn.commit()
    return jsonify({"status": "ok", "ingredientId": ingredientId})
