"""
What a person keeps, as the read API and the account routes both show it: the ♥ ✓ ★ flags on tiles, the `mine`
block on a recipe, and whether a recipe may be seen at all. A recipe removed or hidden by the gate is seen by nobody,
not even someone who keeps it (spec section 6); their rows stay, so it comes back if it is listed again. SQL only, on
the caller's cursor; every query names the user, so nothing of one person's ever reaches another.
"""
from . import gluttonyRules as rules

# One row per recipe asked about. The three subqueries each use an index on (UserID, RecipeID) or (RecipeID), so
# the cost grows with the page, not with how much the person keeps.
FLAGS_SQL = ("SELECT r.RecipeID, "
             "EXISTS (SELECT 1 FROM ListItems li JOIN Lists l ON l.ListID = li.ListID "
             "WHERE l.UserID = %s AND l.Kind = 'cravings' AND li.RecipeID = r.RecipeID) AS Craving, "
             "(SELECT COUNT(*) FROM Devoured d WHERE d.UserID = %s AND d.RecipeID = r.RecipeID) AS DevouredCount, "
             "(SELECT t.Stars FROM Ratings t WHERE t.UserID = %s AND t.RecipeID = r.RecipeID) AS Stars "
             "FROM Recipes r WHERE r.RecipeID IN ({marks})")


def attachTileFlags(cur, uid, tiles):
    """Adds craving, devouredCount and stars to every tile, in one query whatever the page size (and none for an
    empty page). The tiles are changed in place and returned."""
    if not tiles:
        return tiles
    ids = sorted({t["id"] for t in tiles})
    cur.execute(FLAGS_SQL.format(marks=", ".join(["%s"] * len(ids))), (uid, uid, uid, *ids))
    found = {row["RecipeID"]: row for row in cur.fetchall()}
    for t in tiles:
        row = found.get(t["id"], {})
        t["craving"] = bool(row.get("Craving"))
        t["devouredCount"] = int(row.get("DevouredCount") or 0)
        t["stars"] = row.get("Stars")
    return tiles


def visibleRecipe(cur, uid, recipeId):
    """The recipe's row ({RecipeID, RemovedAt, HiddenReason, ImagePath}) when it is shown, or None. A removed or
    hidden recipe is None for everyone, whoever keeps it, and looks the same as one that never existed. (`uid` stays
    so every caller still says whose request it is.)"""
    cur.execute("SELECT RecipeID, RemovedAt, HiddenReason, ImagePath FROM Recipes WHERE RecipeID = %s", (recipeId,))
    row = cur.fetchone()
    return row if row and rules.isShown(row) else None


def mineOf(cur, uid, recipeId):
    """Everything this person keeps on one recipe, for the recipe page's actions."""
    cur.execute("SELECT l.ListID, l.Kind FROM ListItems li JOIN Lists l ON l.ListID = li.ListID "
                "WHERE l.UserID = %s AND li.RecipeID = %s ORDER BY l.OrderIndex, l.ListID", (uid, recipeId))
    lists = cur.fetchall()
    cur.execute("SELECT DevouredID, MadeOn FROM Devoured WHERE UserID = %s AND RecipeID = %s "
                "ORDER BY MadeOn DESC, DevouredID DESC", (uid, recipeId))
    devoured = cur.fetchall()
    cur.execute("SELECT (SELECT Stars FROM Ratings WHERE UserID = %s AND RecipeID = %s) AS Stars, "
                "(SELECT NULLIF(Text, '') FROM Notes WHERE UserID = %s AND RecipeID = %s) AS Note",
                (uid, recipeId, uid, recipeId))
    extra = cur.fetchone() or {}
    return {"craving": any(row["Kind"] == "cravings" for row in lists),
            "lists": [row["ListID"] for row in lists if row["Kind"] == "custom"],
            "devoured": [{"id": row["DevouredID"], "on": rules.isoDate(row["MadeOn"])} for row in devoured],
            "stars": extra.get("Stars"), "note": extra.get("Note")}


def savedTile(row):
    """A tile from one of the person's own lists or history. Only shown recipes reach one, so `removed` is always
    false; it stays so older app builds keep working."""
    t = rules.tile(row)
    t["removed"] = False
    return t
