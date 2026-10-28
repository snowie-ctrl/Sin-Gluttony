import calibration
import rulesData
from models import IngredientLine, Recipe, Step

RULES = rulesData.load()


def page(rating, timeText, steps):
    return Recipe(source="wikibooks", sourceId="x", kind="food", title="x",
                  ingredients=[IngredientLine(line="salt", name="salt")], steps=[Step(text=s) for s in steps],
                  hints={"difficultyRating": rating, "timeText": timeText})


def test_calibrationCountsAgreementWithWhatWikibooksStated():
    result = calibration.calibrate([
        page(1, "Total: 30 minutes", ["Bake 30 minutes."]),      # both agree
        page(5, "Total: 2 hours", ["Stir."]),                    # neither agrees
        page(None, None, ["Stir."]),                             # states nothing: not counted
    ], RULES)
    assert result["difficulty"] == {"n": 2, "agree": 1, "rate": 0.5}
    assert result["time"] == {"n": 2, "agree": 1, "rate": 0.5}


def test_otherSourcesAreNotCounted():
    other = page(1, "Total: 30 minutes", ["Bake 30 minutes."])
    other.source = "mealdb"
    assert calibration.calibrate([other], RULES)["time"] == {"n": 0, "agree": 0, "rate": None}


def test_aStatedTimeOverAWeekIsNotCounted():
    assert calibration.calibrate([page(1, "Total: 14 days", ["Stir."])], RULES)["time"] == {"n": 0, "agree": 0, "rate": None}
