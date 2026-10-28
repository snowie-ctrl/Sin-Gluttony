import snapshot


def recipe(rid, course="main", **changes):
    base = {"id": rid, "course": course, "source": "mealdb", "timeFrom": "source", "servings": 2, "hasImage": True,
            "totalMinutes": 20, "versions": [], "facts": {"complete": True},
            "ingredients": [{"ingredientId": 1, "quantityMax": None, "group": None}],
            "steps": [{"text": "Stir.", "group": None}]}
    base.update(changes)
    return base


def test_featuresNameWhatARecipeShowsOff():
    found = snapshot.features(recipe(1, source="wikibooks", timeFrom="rule", servings=None, hasImage=False,
                                     ingredients=[{"ingredientId": None, "quantityMax": 3, "group": "Sauce"}],
                                     steps=[{"text": "Bake at 180°C.", "group": None}]))
    assert {"wikibooks", "guessedTime", "noServings", "unknownIngredient", "range", "groupHeading",
            "noPicture", "temperature", "complete"} <= found


def test_chooseCoversEveryFeatureBeforeFillingByCourse():
    plain = [recipe(i, course="main") for i in range(1, 50)]
    special = recipe(99, course="dessert", servings=None)
    chosen = snapshot.choose(plain + [special], 10)
    assert len(chosen) == 10 and 99 in [r["id"] for r in chosen]
    assert len({r["id"] for r in chosen}) == 10


def test_candidatesKeepSomeOfEveryCourseWhenTheListsAreCut():
    # Sixty ids per course, as the API lists them, and a cap far below the total: the last course must survive.
    listed = [list(range(c * 100, c * 100 + 60)) for c in range(14)]
    ids = snapshot.candidateIds(listed, 600)
    assert len(ids) == 600 and len(set(ids)) == 600
    assert all(any(i in ids for i in rows) for rows in listed)
    assert len(snapshot.candidateIds(listed, 28)) == 28 and {0, 1300} <= set(snapshot.candidateIds(listed, 28))


def test_candidatesDropRepeatsBetweenCourses():
    assert snapshot.candidateIds([[1, 2], [2, 3]], 10) == [1, 2, 3]
