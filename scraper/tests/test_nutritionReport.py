import shutil

import config, fdc, nutritionReport
from conftest import FIXTURES
from models import Recipe


def made(source="testsite", **fields):
    return Recipe(source=source, sourceId="1", kind="food", title="Made-up", ingredients=[], steps=[], **fields)


def sited(estimate, own):
    return made(nutritionFrom="source", nutrition={"calories": own}, estimate={"calories": estimate})


def test_calibrationIsTheEstimateOverTheSitesOwnCalories():
    recipes = [sited(90, 100), sited(100, 100), sited(130, 100),
               made(nutritionFrom="estimate", nutrition={"calories": 50}, estimate={"calories": 50}),
               made(source="empty", nutritionFrom="source", nutrition={"calories": 100}, estimate=None)]
    result = nutritionReport.calibrate(recipes)
    assert result["testsite"] == {"n": 3, "median": 1.0, "p25": 0.95, "p75": 1.15, "within20": 0.667,
                                  "within35": 1.0}
    assert result["empty"] == {"n": 0, "median": None, "p25": None, "p75": None, "within20": None,
                               "within35": None}


def blocked(*names, hidden="no-nutrition", reason="no-fdc"):
    return made(hiddenReason=hidden, estimateBlocker={"line": "x", "reason": reason, "ingredient": names[0]},
                hints={"noFdc": sorted(names)})


def test_theQueueCountsWhatEachIngredientUnlocksAndBlocks():
    shutil.copytree(FIXTURES / "fdc" / "sr", config.FDC_DIR / "sr")
    fdc.importFolders(log=lambda *_: None)
    recipes = [blocked("saffron"), blocked("saffron"), blocked("saffron", "sumac"),
               blocked("onion", hidden="no-time"), blocked("flour", reason="no-amount"),
               made(hiddenReason="no-nutrition", estimateBlocker=None)]
    queue = nutritionReport.fdcQueue(recipes, fdc.loadFoods())
    assert [(q["ingredient"], q["unlocks"], q["blocks"]) for q in queue] == [("saffron", 2, 3), ("sumac", 0, 1)]
    queue = nutritionReport.fdcQueue([blocked("onion")], fdc.loadFoods(), limit=1)
    assert queue[0]["candidates"][0]["fdcId"] == 900001
    assert set(queue[0]) == {"ingredient", "unlocks", "blocks", "candidates"}
