"""A valid recipe payload, as the scraper sends it, for tests to change one thing at a time."""


def recipe(sourceId="1", **changes):
    payload = {
        "key": f"mealdb:{sourceId}", "source": "mealdb", "sourceId": sourceId, "kind": "food",
        "title": "Cheese Toast", "dishKey": "cheese toast", "course": "main", "cuisine": None,
        "servings": 2, "servingsFrom": "source", "prepMinutes": None, "cookMinutes": None, "totalMinutes": 10,
        "timeFrom": "rule", "difficulty": 1, "difficultyFrom": "rule", "alcohol": None, "glass": None,
        "imagePath": "0123456789abcdef0123.jpg", "imageCredit": "TheMealDB", "videoUrl": None,
        "sourceUrl": f"https://www.themealdb.com/meal/{sourceId}", "licence": "TheMealDB",
        "credit": "Recipe data and imagery: TheMealDB", "searchText": "Cheese Toast bread cheddar",
        "ingredients": [
            {"line": "2 slices bread", "quantity": 2, "quantityMax": None, "unit": "slice", "ingredientId": 1,
             "unknownName": None, "note": None, "optional": False, "group": None},
            {"line": "50 g cheddar", "quantity": 50, "quantityMax": None, "unit": "g", "ingredientId": 2,
             "unknownName": None, "note": None, "optional": False, "group": None}],
        "steps": [{"text": "Toast the bread.", "group": None}, {"text": "Melt the cheese on top.", "group": None}],
        "tags": [{"type": "flavour", "tag": "savoury", "origin": "rule"},
                 {"type": "source", "tag": "Snack", "origin": "source"}],
        "facts": {"complete": True, "contains": ["dairy", "gluten"], "diets": ["vegetarian"]},
        "contentHash": "a" * 40,
    }
    payload.update(changes)
    return payload
