"""
Turns USDA FoodData Central's CSV downloads into one compact foods cache.

The files come from https://fdc.nal.usda.gov/download-datasets: the SR Legacy
and Foundation Foods CSV zips, unzipped into data/fdc/ (any folder depth).
Nothing here, or anywhere else in the scraper, calls USDA at run time: the
owner downloads the zips by hand now and then, and `python fdc.py import`
rebuilds data/fdc/foods.json.gz from them. (R1: no live lookups, so nutrition
never depends on a service that can change or vanish.)

A food is {"id", "description", "dataType", "per100g", "portions", "missing"}.
per100g holds the eight values the app shows; a nutrient the food has no
figure for is 0.0 and its field is named in "missing".
"""
import csv
import gzip
import json
import sys
import time

import config

REQUIRED_FILES = ("food.csv", "food_nutrient.csv", "food_portion.csv")
DATA_TYPES = ("foundation_food", "sr_legacy_food")
UNDETERMINED_UNIT = "9999"

# field -> FDC nutrient ids, preferred first
NUTRIENTS = {
    "calories": (1008, 2047, 2048),
    "proteinG": (1003,),
    "carbsG": (1005,),
    "fatG": (1004,),
    "satFatG": (1258,),
    "fibreG": (1079,),
    "sugarG": (2000, 1063),
    "sodiumMg": (1093,),
}
WANTED_IDS = {nutrientId for ids in NUTRIENTS.values() for nutrientId in ids}


def _rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _folders(root):
    """Every folder under root holding all three needed files, and every one holding some but not all."""
    complete, incomplete = [], []
    folders = {path.parent for path in root.rglob("*.csv")} if root.exists() else set()
    for folder in sorted(folders):
        have = [name for name in REQUIRED_FILES if (folder / name).exists()]
        if len(have) == len(REQUIRED_FILES):
            complete.append(folder)
        elif have or (folder / "nutrient.csv").exists() or (folder / "measure_unit.csv").exists():
            incomplete.append(folder)
    return complete, incomplete


def _portionUnit(row, unitNames):
    description = (row.get("portion_description") or "").strip()
    modifier = (row.get("modifier") or "").strip()
    if description:
        return description.lower()
    unitId = (row.get("measure_unit_id") or "").strip()
    if unitId in ("", "0", UNDETERMINED_UNIT):
        return modifier.lower()
    return ", ".join(part for part in (unitNames.get(unitId, ""), modifier) if part).lower()


def _readFolder(folder, log):
    """-> ({id: food}, number of Foundation foods dropped for having no energy)."""
    foods = {}
    for row in _rows(folder / "food.csv"):
        if row.get("data_type") in DATA_TYPES:
            foods[int(row["fdc_id"])] = {"id": int(row["fdc_id"]), "description": row["description"].strip(),
                                         "dataType": row["data_type"], "amounts": {}, "portions": []}
    wanted = {str(foodId): food for foodId, food in foods.items()}
    for row in _rows(folder / "food_nutrient.csv"):
        food = wanted.get(row["fdc_id"])
        if food is None:
            continue
        nutrientId, amount = _number(row["nutrient_id"]), _number(row["amount"])
        if nutrientId in WANTED_IDS and amount is not None:
            food["amounts"][int(nutrientId)] = amount
    unitNames = {}
    if (folder / "measure_unit.csv").exists():
        unitNames = {row["id"]: row["name"].strip() for row in _rows(folder / "measure_unit.csv")}
    for row in _rows(folder / "food_portion.csv"):
        food = wanted.get(row["fdc_id"])
        grams = _number(row.get("gram_weight"))
        if food is None or not grams or grams <= 0:
            continue
        amount = _number(row.get("amount"))
        if amount is not None and amount <= 0:
            continue
        food["portions"].append({"amount": 1.0 if amount is None else amount,
                                 "unit": _portionUnit(row, unitNames), "grams": grams})
    kept, dropped = {}, 0
    for foodId, food in foods.items():
        finished = _finish(food)
        if finished is None:
            dropped += 1
        else:
            kept[foodId] = finished
    return kept, dropped


def _finish(food):
    amounts = food.pop("amounts")
    per100g, missing = {}, []
    for field, ids in NUTRIENTS.items():
        value = next((amounts[i] for i in ids if i in amounts), None)
        per100g[field] = 0.0 if value is None else value
        if value is None:
            missing.append(field)
    if "calories" in missing and food["dataType"] == "foundation_food":
        if not {"proteinG", "fatG", "carbsG"} & set(missing):
            per100g["calories"] = round(4 * per100g["proteinG"] + 9 * per100g["fatG"] + 4 * per100g["carbsG"], 2)
            missing.remove("calories")
        else:
            return None
    food["per100g"] = per100g
    food["missing"] = missing
    return food


def importFolders(root=None, log=print):
    """Reads every complete FDC folder under root and writes the foods cache. Returns the number of foods written."""
    root = config.FDC_DIR if root is None else root
    complete, incomplete = _folders(root)
    for folder in incomplete:
        log(f"fdc: skipped {folder.name}: incomplete, it lacks {', '.join(n for n in REQUIRED_FILES if not (folder / n).exists())}")
    foods, sources = {}, []
    for folder in complete:
        found, dropped = _readFolder(folder, log)
        foods.update(found)
        sources.append(folder.name)
        log(f"fdc: {folder.name}: {len(found)} foods" + (f", dropped {dropped} Foundation foods with no energy" if dropped else ""))
    config.FDC_FOODS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(config.FDC_FOODS_FILE, "wt", encoding="utf-8") as f:
        json.dump({"importedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "sources": sources,
                   "foods": list(foods.values())}, f, ensure_ascii=False)
    return len(foods)


def loadFoods(path=None):
    """{id: food} from the cache; imports the CSVs first when there is no cache yet; {} when there is nothing."""
    path = config.FDC_FOODS_FILE if path is None else path
    if not path.exists():
        if not _folders(config.FDC_DIR)[0] or path != config.FDC_FOODS_FILE:
            return {}
        importFolders(log=lambda *_: None)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {food["id"]: food for food in json.load(f)["foods"]}


if __name__ == "__main__":
    if sys.argv[1:] == ["import"]:
        print(importFolders())
    else:
        sys.exit("usage: python fdc.py import")
