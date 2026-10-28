import json

import adaptWikibooks
import calibration
import matching
import rulesData
import tagging
from conftest import FIXTURES

RULES = rulesData.load()


def test_theRulesStayAboveTheCalibrationFloor():
    pages = sorted((FIXTURES / "calibration").glob("*.json"))
    assert pages, "run scripts/saveCalibrationPages.py"
    table = matching.IngredientTable.fromSeed(RULES["ingredients"], set(RULES["prepWords"]))
    recipes = [tagging.tagRecipe(adaptWikibooks.adaptPage(json.loads(p.read_text(encoding="utf-8")),
                                                          RULES["unitMap"]), table, RULES) for p in pages]
    result = calibration.calibrate(recipes, RULES)
    floor = RULES["difficulty"]["calibrationFloor"]
    assert result["difficulty"]["rate"] >= floor["difficulty"]
    assert result["time"]["rate"] >= floor["time"]
