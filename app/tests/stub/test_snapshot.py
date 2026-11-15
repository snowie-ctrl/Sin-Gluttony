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


def test_featuresNameTheNewCatalogsSitesBasicsNutritionAndDescription():
    found = snapshot.features(recipe(1, source="budgetbytes", description="A made-up line.",
                                     tags={"occasion": ["basic"]},
                                     nutrition={"calories": 300, "from": "estimate", "flagged": False}))
    assert {"budgetbytes", "basic", "nutritionEstimate", "description"} <= found
    assert "nutritionSource" not in found
    sourced = snapshot.features(recipe(2, nutrition={"calories": 300, "from": "source", "flagged": False}))
    assert "nutritionSource" in sourced and "nutritionEstimate" not in sourced
    plain = snapshot.features(recipe(3))
    assert not {"basic", "nutritionEstimate", "nutritionSource", "description"} & plain
    assert {"bbcgoodfood", "budgetbytes", "recipetineats", "pinchofyum", "loveandlemons", "difford", "basic",
            "nutritionEstimate", "nutritionSource", "description"} <= set(snapshot.FEATURES)


class Reply:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.data


def test_fetchSendsTheSessionToken(monkeypatch):
    sent = []

    def opener(request, timeout):
        sent.append(request)
        return Reply(b'{"status": "ok"}')

    monkeypatch.setattr(snapshot.urllib.request, "urlopen", opener)
    monkeypatch.setattr(snapshot.time, "sleep", lambda s: None)
    assert snapshot.fetch("http://stub.invalid/api/gluttony", "/recipes/1", token="made-up-token") == {"status": "ok"}
    assert sent[0].full_url == "http://stub.invalid/api/gluttony/recipes/1"
    assert sent[0].get_header("X-session-token") == "made-up-token"


def test_theTokenComesFromTheFlagOrTheEnvironment(monkeypatch):
    monkeypatch.setenv("GLUTTONY_SESSION", "from-the-environment")
    assert snapshot.parseArgs(["--base", "http://stub.invalid"]).token == "from-the-environment"
    assert snapshot.parseArgs(["--base", "http://stub.invalid", "--token", "from-the-flag"]).token == "from-the-flag"
    monkeypatch.delenv("GLUTTONY_SESSION")
    assert snapshot.parseArgs(["--base", "http://stub.invalid"]).token is None


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
