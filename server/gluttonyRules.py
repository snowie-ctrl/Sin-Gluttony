"""
Pure rules for Gluttony's routes: validation, the read API's filters and the
SQL they become, and the JSON shapes. Nothing here touches the database or the
disk, so every rule is tested directly and the routes stay thin.
"""
import re
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

INT_LIMIT = 2 ** 31 - 1
SOURCES = ("mealdb", "cocktaildb", "wikibooks")
KINDS = ("food", "drink")
FOOD_COURSES = ("breakfast", "starter", "main", "side", "dessert", "snack", "bread", "sauce")
DRINK_COURSES = ("cocktail", "mocktail", "shot", "coffee/tea", "shake", "punch")
COURSES = FOOD_COURSES + DRINK_COURSES
ALCOHOL = ("alcoholic", "non-alcoholic", "optional")
FROM = ("source", "rule")
FLAVOURS = ("sweet", "savoury", "spicy", "sour", "bitter")
OCCASIONS = ("weeknight", "party", "holiday", "brunch")
TAG_TYPES = ("flavour", "occasion", "source")
CONTAINS_ITEMS = ("meat", "poultry", "fish", "shellfish", "dairy", "egg", "gluten", "tree-nut", "peanut", "soy",
                  "sesame", "alcohol", "honey")
DIETS = ("vegetarian", "vegan", "gluten-free", "dairy-free")
SORTS = ("relevance", "quickest", "shuffle")
# InnoDB's default stopwords of three or more letters: a required one in boolean mode matches nothing.
STOPWORDS = frozenset(("about", "are", "com", "for", "from", "how", "that", "the", "this", "was", "what", "when",
                       "where", "who", "will", "with", "und", "www"))
PAGE_SIZE = 24
MAX_PAGE_SIZE = 60
MAX_BATCH = 200
MAX_KEYS = 1000
# Today's temptation is a dish to cook, never a sauce or a side.
HOME_COURSES = ("main", "breakfast")
HOME_PICKS = 8

RECIPE_COLUMNS = ("Source", "SourceID", "Kind", "Title", "DishKey", "Course", "Cuisine", "Servings", "ServingsFrom",
                  "PrepMinutes", "CookMinutes", "TotalMinutes", "TimeFrom", "Difficulty", "DifficultyFrom",
                  "Alcohol", "Glass", "ImagePath", "ImageCredit", "VideoUrl", "SourceUrl", "Licence", "Credit",
                  "SearchText", "ContentHash")
_FIELDS = ("source", "sourceId", "kind", "title", "dishKey", "course", "cuisine", "servings", "servingsFrom",
           "prepMinutes", "cookMinutes", "totalMinutes", "timeFrom", "difficulty", "difficultyFrom", "alcohol",
           "glass", "imagePath", "imageCredit", "videoUrl", "sourceUrl", "licence", "credit", "searchText",
           "contentHash")
_LIMITS = {"title": 255, "dishKey": 255, "cuisine": 40, "glass": 60, "imageCredit": 500, "videoUrl": 500,
           "sourceUrl": 500, "licence": 60, "credit": 500, "searchText": 4000}
CHILD_TABLES = ("RecipeIngredients", "RecipeSteps", "RecipeTags", "RecipeFacts", "RecipeContains", "RecipeDiets")
TILE_COLUMNS = ("r.RecipeID, r.Kind, r.Title, r.Course, r.Cuisine, r.TotalMinutes, r.TimeFrom, r.Difficulty, "
                "r.ImagePath, r.Source")

_HASH = re.compile(r"[0-9a-f]{40}")
IMAGE_NAME = re.compile(r"[0-9a-f]{20}\.jpg")
_WHOLE = re.compile(r"[0-9]{1,9}")


def clip(text, limit):
    return None if text is None else str(text)[:limit]


def _whole(value, low, high):
    """None, or an int (never a bool) from low to high."""
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and low <= value <= high)


def _text(value, high, low=1):
    return isinstance(value, str) and low <= len(value.strip()) and len(value) <= high


# ---- the scraper's payloads ----

def _lineProblem(line):
    if not isinstance(line, dict) or not isinstance(line.get("line"), str) or not line["line"].strip():
        return "every ingredient needs its line of text"
    if not _whole(line.get("ingredientId"), 1, INT_LIMIT):
        return "ingredientId must be a positive whole number or null"
    for name in ("quantity", "quantityMax"):
        value = line.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not 0 <= value < 1000000):
            return f"{name} must be a number from 0 to 999999 or null"
    if not isinstance(line.get("optional", False), bool):
        return "optional must be true or false"
    return None


def _factsProblem(facts):
    if not isinstance(facts, dict) or not isinstance(facts.get("complete"), bool):
        return "facts.complete must be true or false"
    contains, diets = facts.get("contains"), facts.get("diets")
    if not isinstance(contains, list) or not all(isinstance(v, str) and v in CONTAINS_ITEMS for v in contains):
        return f"facts.contains takes only {', '.join(CONTAINS_ITEMS)}"
    if not isinstance(diets, list) or not all(isinstance(v, str) and v in DIETS for v in diets):
        return f"facts.diets takes only {', '.join(DIETS)}"
    if not facts["complete"] and diets:
        return "an incomplete recipe meets no diet"
    return None


def recipeProblem(r):
    if not isinstance(r, dict):
        return "each recipe must be an object"
    if r.get("source") not in SOURCES:
        return f"source must be one of {', '.join(SOURCES)}"
    if not _text(r.get("sourceId"), 255):
        return "sourceId must be text of 1 to 255 characters"
    if r.get("key") != f"{r['source']}:{r['sourceId']}":
        return "key must be source:sourceId"
    if r.get("kind") not in KINDS:
        return f"kind must be one of {', '.join(KINDS)}"
    if not _text(r.get("title"), 1000) or not _text(r.get("dishKey"), 1000):
        return "title and dishKey are required"
    course = r.get("course")
    if course is not None and course not in (FOOD_COURSES if r["kind"] == "food" else DRINK_COURSES):
        return f"course {course!r} does not fit a {r['kind']}"
    for name, low, high in (("servings", 1, 1000), ("prepMinutes", 0, 10080), ("cookMinutes", 0, 10080),
                            ("totalMinutes", 0, 10080), ("difficulty", 1, 3)):
        if not _whole(r.get(name), low, high):
            return f"{name} must be a whole number from {low} to {high} or null"
    for name in ("servingsFrom", "timeFrom", "difficultyFrom"):
        if r.get(name) not in (None, *FROM):
            return f"{name} must be source, rule or null"
    if r.get("alcohol") not in (None, *ALCOHOL):
        return f"alcohol must be one of {', '.join(ALCOHOL)} or null"
    if r.get("imagePath") is not None and not IMAGE_NAME.fullmatch(str(r["imagePath"])):
        return "imagePath must be a picture name the scraper made"
    for name in ("licence", "credit", "searchText"):
        if not isinstance(r.get(name), str):
            return f"{name} must be text"
    if not _HASH.fullmatch(str(r.get("contentHash", ""))):
        return "contentHash must be 40 hex characters"
    ingredients = r.get("ingredients")
    if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 100:
        return "ingredients must be a list of 1 to 100 lines"
    for line in ingredients:
        problem = _lineProblem(line)
        if problem:
            return problem
    steps = r.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 200:
        return "steps must be a list of 1 to 200"
    if any(not isinstance(s, dict) or not _text(s.get("text"), 20000) for s in steps):
        return "every step needs its text"
    tags = r.get("tags")
    if not isinstance(tags, list) or len(tags) > 60:
        return "tags must be a list of at most 60"
    for tag in tags:
        if not isinstance(tag, dict) or tag.get("type") not in TAG_TYPES or tag.get("origin") not in FROM \
                or not _text(tag.get("tag"), 40):
            return "every tag needs a type, a tag of 1 to 40 characters and an origin"
        if tag["type"] == "flavour" and tag["tag"] not in FLAVOURS:
            return f"flavour takes only {', '.join(FLAVOURS)}"
        if tag["type"] == "occasion" and tag["tag"] not in OCCASIONS:
            return f"occasion takes only {', '.join(OCCASIONS)}"
    return _factsProblem(r.get("facts"))


def batchProblem(data):
    if not isinstance(data, dict):
        return "the body must be a JSON object"
    recipes = data.get("recipes")
    if not isinstance(recipes, list) or not 1 <= len(recipes) <= MAX_BATCH:
        return f"recipes must be a list of 1 to {MAX_BATCH}"
    return None


def keysProblem(keys):
    if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_KEYS:
        return f"keys must be a list of 1 to {MAX_KEYS}"
    for key in keys:
        if not isinstance(key, str) or ":" not in key or key.split(":", 1)[0] not in SOURCES:
            return "every key must be source:sourceId"
    return None


def recipeRow(r):
    return tuple(clip(r.get(field), _LIMITS[field]) if field in _LIMITS else r.get(field) for field in _FIELDS)


def ingredientRow(recipeId, position, line):
    return (recipeId, position, clip(line["line"], 500), line.get("quantity"), line.get("quantityMax"),
            clip(line.get("unit"), 20), line.get("ingredientId"), clip(line.get("unknownName"), 160),
            clip(line.get("note"), 255), 1 if line.get("optional") else 0, clip(line.get("group"), 120))


# ---- the ingredient table ----

def _containsProblem(contains):
    if not isinstance(contains, list) or not all(isinstance(v, str) and v in CONTAINS_ITEMS for v in contains):
        return f"contains takes only {', '.join(CONTAINS_ITEMS)}"
    return None


def seedProblem(entries):
    if not isinstance(entries, list) or not 1 <= len(entries) <= 5000:
        return "ingredients must be a list of 1 to 5000"
    names = {e["name"] for e in entries if isinstance(e, dict) and isinstance(e.get("name"), str)}
    for entry in entries:
        if not isinstance(entry, dict) or not _text(entry.get("name"), 120):
            return "every ingredient needs a name of 1 to 120 characters"
        if entry.get("parent") is not None and (not isinstance(entry["parent"], str) or entry["parent"] not in names):
            return f"{entry['name']}: its parent {entry['parent']!r} is not in this seed"
        if entry.get("category") is not None and not _text(entry["category"], 40):
            return f"{entry['name']}: category must be 1 to 40 characters"
        problem = _containsProblem(entry.get("contains", []))
        if problem:
            return f"{entry['name']}: {problem}"
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list) or len(aliases) > 50 or any(not _text(a, 160) for a in aliases):
            return f"{entry['name']}: aliases must be up to 50 texts of 1 to 160 characters"
    return None


def mapProblem(data):
    if not isinstance(data, dict):
        return "the body must be a JSON object"
    if not _text(data.get("alias"), 160):
        return "alias must be the unknown name, 1 to 160 characters"
    if ("ingredientId" in data) == ("create" in data):
        return "send one of ingredientId (map to an existing ingredient) or create (a new one)"
    if "ingredientId" in data:
        return None if _whole(data["ingredientId"], 1, INT_LIMIT) and data["ingredientId"] is not None \
            else "ingredientId must be a positive whole number"
    create = data["create"]
    if not isinstance(create, dict) or not _text(create.get("name"), 120):
        return "create.name must be 1 to 120 characters"
    if not _whole(create.get("parentId"), 1, INT_LIMIT):
        return "create.parentId must be a positive whole number or absent"
    if create.get("category") is not None and not _text(create["category"], 40):
        return "create.category must be 1 to 40 characters"
    return _containsProblem(create.get("contains", []))


# ---- the read API ----

def wholeNumberArg(args, name, default, low, high):
    """(value, problem) for a whole-number query parameter."""
    raw = args.get(name)
    if raw in (None, ""):
        return default, None
    if not _WHOLE.fullmatch(raw) or not low <= int(raw) <= high:
        return None, f"{name} must be a whole number from {low} to {high}"
    return int(raw), None


def _many(args, name):
    values = []
    for raw in args.getlist(name):
        values += [v.strip() for v in raw.split(",") if v.strip()]
    return values


def parseFilters(args):
    """(filters, problem). Every value is checked here, so a bad link gets a 400 that says why, never a 500."""
    f = {}
    kind = args.get("kind")
    if kind:
        if kind not in KINDS:
            return None, f"kind must be one of {', '.join(KINDS)}"
        f["kind"] = kind
    for name, allowed in (("course", COURSES), ("flavour", FLAVOURS), ("occasion", OCCASIONS), ("diet", DIETS),
                          ("avoid", CONTAINS_ITEMS), ("alcohol", ALCOHOL)):
        values = _many(args, name)
        bad = [v for v in values if v not in allowed]
        if bad:
            return None, f"unknown {name}: {bad[0]}"
        if values:
            f[name] = values
    cuisines = _many(args, "cuisine")
    if any(len(c) > 40 for c in cuisines) or len(cuisines) > 10:
        return None, "cuisine takes up to 10 names of at most 40 characters"
    if cuisines:
        f["cuisine"] = cuisines
    difficulties = _many(args, "difficulty")
    if difficulties:
        if any(d not in ("1", "2", "3") for d in difficulties):
            return None, "difficulty must be 1, 2 or 3"
        f["difficulty"] = [int(d) for d in difficulties]
    for name in ("include", "exclude"):
        ids = _many(args, name)
        if ids:
            if len(ids) > 10 or any(not _WHOLE.fullmatch(i) or not 0 < int(i) <= INT_LIMIT for i in ids):
                return None, f"{name} takes up to 10 ingredient ids"
            f[name] = [int(i) for i in ids]
    maxMinutes, problem = wholeNumberArg(args, "maxMinutes", None, 1, 10080)
    if problem:
        return None, problem
    if maxMinutes:
        f["maxMinutes"] = maxMinutes
    profile = args.get("profile") or "on"
    if profile not in ("on", "off"):
        return None, "profile must be on or off"
    f["profile"] = profile == "on"
    q = (args.get("q") or "").strip()
    if len(q) > 100:
        return None, "q must be at most 100 characters"
    if q:
        f["q"] = q
    sort = args.get("sort") or ("relevance" if q else "shuffle")
    if sort not in SORTS:
        return None, f"sort must be one of {', '.join(SORTS)}"
    f["sort"] = "shuffle" if sort == "relevance" and not q else sort
    for name, default, high in (("page", 1, 10000), ("pageSize", PAGE_SIZE, MAX_PAGE_SIZE)):
        value, problem = wholeNumberArg(args, name, default, 1, high)
        if problem:
            return None, problem
        f[name] = value
    return f, None


def descendants(rows, ids):
    """The ingredients asked for and everything under them: asking for cheese also finds cheddar."""
    children = {}
    for row in rows:
        if row["ParentID"] is not None:
            children.setdefault(row["ParentID"], []).append(row["IngredientID"])
    found, waiting = set(), list(ids)
    while waiting:
        current = waiting.pop()
        if current not in found:
            found.add(current)
            waiting += children.get(current, [])
    return found


def booleanQuery(q):
    """MySQL boolean-mode words: each word of three or more letters must appear, as a prefix. InnoDB skips shorter
    words and its default stopwords, so a required one would match nothing; they are dropped here."""
    words = [w for w in re.findall(r"[^\W_]+", (q or "").lower()) if len(w) >= 3 and w not in STOPWORDS][:8]
    return " ".join(f"+{w}*" for w in words)


def likeEscape(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def recipeWhere(f, includeSets=(), excludeIds=()):
    """The WHERE clause over `Recipes r LEFT JOIN RecipeFacts fa`. Within a filter any value may match; across filters all must."""
    clauses, params = ["r.RemovedAt IS NULL"], []

    def marks(values):
        return ", ".join(["%s"] * len(values))

    if "kind" in f:
        clauses.append("r.Kind = %s")
        params.append(f["kind"])
    for key, column in (("course", "r.Course"), ("cuisine", "r.Cuisine"), ("difficulty", "r.Difficulty"),
                        ("alcohol", "r.Alcohol")):
        if key in f:
            clauses.append(f"{column} IN ({marks(f[key])})")
            params += f[key]
    if "maxMinutes" in f:
        clauses.append("r.TotalMinutes IS NOT NULL AND r.TotalMinutes <= %s")
        params.append(f["maxMinutes"])
    for tagType in ("flavour", "occasion"):
        if tagType in f:
            clauses.append("EXISTS (SELECT 1 FROM RecipeTags t WHERE t.RecipeID = r.RecipeID AND t.Type = %s "
                           f"AND t.Tag IN ({marks(f[tagType])}))")
            params += [tagType, *f[tagType]]
    if "diet" in f or "avoid" in f:
        # The safety rule: only a recipe whose every ingredient is known can meet a diet or avoid an allergen.
        clauses.append("fa.Complete = 1")
    for diet in f.get("diet", []):
        clauses.append("EXISTS (SELECT 1 FROM RecipeDiets d WHERE d.RecipeID = r.RecipeID AND d.Diet = %s)")
        params.append(diet)
    if "avoid" in f:
        clauses.append("NOT EXISTS (SELECT 1 FROM RecipeContains c WHERE c.RecipeID = r.RecipeID "
                       f"AND c.Item IN ({marks(f['avoid'])}))")
        params += f["avoid"]
    for ids in includeSets:
        ids = sorted(ids)
        clauses.append("EXISTS (SELECT 1 FROM RecipeIngredients i WHERE i.RecipeID = r.RecipeID "
                       f"AND i.IngredientID IN ({marks(ids)}))")
        params += ids
    if excludeIds:
        ids = sorted(excludeIds)
        clauses.append("NOT EXISTS (SELECT 1 FROM RecipeIngredients x WHERE x.RecipeID = r.RecipeID "
                       f"AND x.IngredientID IN ({marks(ids)}))")
        params += ids
    if "q" in f:
        boolean = booleanQuery(f["q"])
        if boolean:
            clauses.append("MATCH(r.SearchText) AGAINST (%s IN BOOLEAN MODE)")
            params.append(boolean)
        else:
            clauses.append("r.Title LIKE %s")
            params.append(f"%{likeEscape(f['q'])}%")
    return " AND ".join(clauses), params


def withProfile(f, diets, avoids):
    """The filters with the account's saved diet profile added: a diet or allergen asked for and one saved both
    apply. The profile becomes ordinary diet and avoid filters, so the safety rule covers it like any other."""
    merged = dict(f)
    for key, saved in (("diet", diets), ("avoid", avoids)):
        values = list(f.get(key, []))
        values += [v for v in saved if v not in values]
        if values:
            merged[key] = values
    return merged


def dietProblem(data):
    """(diets, avoid, problem) for POST /me/diet: two lists of known words, each word once, in the catalog's order."""
    diets, avoid = data.get("diets", []), data.get("avoid", [])
    for name, word, values, allowed in (("diets", "diet", diets, DIETS), ("avoid", "avoid", avoid, CONTAINS_ITEMS)):
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            return None, None, f"{name} must be a list of words"
        bad = [v for v in values if v not in allowed]
        if bad:
            return None, None, f"unknown {word}: {bad[0]}"
    return [d for d in DIETS if d in diets], [a for a in CONTAINS_ITEMS if a in avoid], None


def recipeOrder(f, today):
    """ORDER BY: relevance for a search, quickest first, or a shuffle that stays the same all day."""
    boolean = booleanQuery(f.get("q", ""))
    if f["sort"] == "relevance" and boolean:
        return "MATCH(r.SearchText) AGAINST (%s IN BOOLEAN MODE) DESC, r.Title", [boolean]
    if f["sort"] == "quickest":
        return "r.TotalMinutes IS NULL, r.TotalMinutes, r.Title", []
    return "SHA1(CONCAT(r.RecipeID, ':', %s)), r.RecipeID", [today]


def localDate(tz, now):
    """The viewer's date: `now` (aware) in the zone they name, or in UTC for anything that isn't a zone this
    machine knows. A zone name never makes a request fail. (This is the one rule that reads the zone database.)"""
    try:
        zone = ZoneInfo(tz) if tz else timezone.utc
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = timezone.utc
    return now.astimezone(zone).date().isoformat()


def homeOrder(uid, day):
    """A shuffle per person per day: the same pick all day, another tomorrow, and not the same as a friend's."""
    return "SHA1(CONCAT(r.RecipeID, ':', %s, ':', %s)), r.RecipeID", [uid, day]


def number(value):
    """DECIMAL comes back as Decimal; JSON wants a plain number (2, not 2.000)."""
    if value is None:
        return None
    value = float(value)
    return int(value) if value.is_integer() else value


def tile(row):
    return {"id": row["RecipeID"], "kind": row["Kind"], "title": row["Title"], "course": row["Course"],
            "cuisine": row["Cuisine"], "totalMinutes": row["TotalMinutes"], "timeFrom": row["TimeFrom"],
            "difficulty": row["Difficulty"], "hasImage": bool(row["ImagePath"]), "source": row["Source"]}


def recipeDetail(row, ingredients, steps, tags, contains, diets, versions):
    grouped = {kind: [] for kind in TAG_TYPES}
    for tag in tags:
        grouped.setdefault(tag["Type"], []).append(tag["Tag"])
    return {
        "id": row["RecipeID"], "kind": row["Kind"], "title": row["Title"], "course": row["Course"],
        "cuisine": row["Cuisine"], "servings": row["Servings"], "servingsFrom": row["ServingsFrom"],
        "prepMinutes": row["PrepMinutes"], "cookMinutes": row["CookMinutes"], "totalMinutes": row["TotalMinutes"],
        "timeFrom": row["TimeFrom"], "difficulty": row["Difficulty"], "difficultyFrom": row["DifficultyFrom"],
        "alcohol": row["Alcohol"], "glass": row["Glass"], "hasImage": bool(row["ImagePath"]),
        "imageCredit": row["ImageCredit"], "videoUrl": row["VideoUrl"], "source": row["Source"],
        "sourceUrl": row["SourceUrl"], "licence": row["Licence"], "credit": row["Credit"],
        "ingredients": [{"line": i["Line"], "quantity": number(i["Quantity"]), "quantityMax": number(i["QuantityMax"]),
                         "unit": i["Unit"], "ingredientId": i["IngredientID"], "name": i["Name"], "note": i["Note"],
                         "optional": bool(i["Optional"]), "group": i["GroupHeading"]} for i in ingredients],
        "steps": [{"text": s["Text"], "group": s["GroupHeading"]} for s in steps],
        "tags": grouped,
        "facts": {"complete": bool(row["Complete"]), "contains": [c["Item"] for c in contains],
                  "diets": [d["Diet"] for d in diets]},
        "versions": [{"id": v["RecipeID"], "title": v["Title"], "source": v["Source"], "hasImage": bool(v["ImagePath"])}
                     for v in versions],
    }


def isoDate(value):
    """A DATE (or DATETIME) as MySQL hands it back, as "YYYY-MM-DD"; the app never sees a time with a day."""
    if value is None:
        return None
    return value.date().isoformat() if hasattr(value, "date") else value.isoformat()


# ---- what a person keeps ----

LIST_TITLE_MAX = 60
MAX_LISTS = 50
MAX_LIST_ITEMS = 2000


def listTitle(value):
    """(title, problem): a list's title, trimmed, 1 to 60 characters."""
    title = value.strip() if isinstance(value, str) else ""
    if not 1 <= len(title) <= LIST_TITLE_MAX:
        return None, f"a list title is 1 to {LIST_TITLE_MAX} characters"
    return title, None


def positiveId(value):
    """An id from a JSON body: a positive whole number (never a bool, never text), or None."""
    if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= INT_LIMIT:
        return value
    return None


def pageArgs(args):
    """(page, pageSize, problem) for a paged list of the person's own, with /recipes' bounds."""
    page, problem = wholeNumberArg(args, "page", 1, 1, 10000)
    if problem:
        return None, None, problem
    pageSize, problem = wholeNumberArg(args, "pageSize", PAGE_SIZE, 1, MAX_PAGE_SIZE)
    if problem:
        return None, None, problem
    return page, pageSize, None
