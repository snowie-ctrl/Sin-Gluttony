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
                                  "within35": 1.0, "pieceYields": 0}
    assert result["empty"] == {"n": 0, "median": None, "p25": None, "p75": None, "within20": None,
                               "within35": None, "pieceYields": 0}


def blocked(*blockers, hidden="no-nutrition"):
    """Each blocker is (reason, ingredient)."""
    return made(hiddenReason=hidden, hints={"blockers": [{"reason": r, "ingredient": i} for r, i in blockers]})


def test_calibrationLeavesOutPieceYields():
    pieces = sited(300, 100)
    pieces.servingsFrom = "yield"
    result = nutritionReport.calibrate([sited(100, 100), pieces])
    assert result["testsite"]["n"] == 1 and result["testsite"]["median"] == 1.0
    assert result["testsite"]["pieceYields"] == 1


def test_theQueueCountsWhatEachIngredientUnlocksAndBlocks():
    shutil.copytree(FIXTURES / "fdc" / "sr", config.FDC_DIR / "sr")
    fdc.importFolders(log=lambda *_: None)
    recipes = [blocked(("no-fdc", "saffron")), blocked(("no-fdc", "saffron"), ("no-fdc", "saffron")),
               blocked(("no-fdc", "saffron"), ("no-fdc", "sumac")),
               blocked(("no-fdc", "saffron"), ("unknown-ingredient", "sumac")),
               blocked(("no-fdc", "onion"), hidden="no-time"), blocked(("no-amount", "flour")),
               made(hiddenReason="no-nutrition")]
    queue = nutritionReport.fdcQueue(recipes, fdc.loadFoods())
    assert [(q["ingredient"], q["unlocks"], q["blocks"]) for q in queue] == [
        ("saffron", 2, 4), ("sumac", 0, 1)]
    queue = nutritionReport.fdcQueue([blocked(("no-fdc", "onion"))], fdc.loadFoods(), limit=1)
    assert queue[0]["candidates"][0]["fdcId"] == 900001
    assert set(queue[0]) == {"ingredient", "unlocks", "blocks", "candidates"}


def test_theUnknownQueueRanksNamesByWhatTheyUnlock():
    recipes = [blocked(("unknown-ingredient", "sumac")), blocked(("unknown-ingredient", "sumac")),
               blocked(("no-fdc", "saffron"), ("unknown-ingredient", "sumac")),
               blocked(("unknown-ingredient", "za'atar"), ("unknown-ingredient", "sumac")),
               blocked(("unknown-ingredient", "mace")), blocked(("unknown-ingredient", "mace"), hidden="no-time"),
               blocked(("no-amount", "flour"))]
    assert nutritionReport.unknownQueue(recipes) == [
        {"name": "sumac", "blocks": 4, "unlocks": 2}, {"name": "mace", "blocks": 1, "unlocks": 1},
        {"name": "za'atar", "blocks": 1, "unlocks": 0}]
    assert len(nutritionReport.unknownQueue(recipes, limit=1)) == 1
