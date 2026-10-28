import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import seedCandidates  # noqa: E402
import rulesData  # noqa: E402
from models import IngredientLine, Recipe, Step  # noqa: E402


def test_auditFindsAnAllergenTheEntryDoesNotDeclare():
    seed = [{"name": "paneer", "contains": []}, {"name": "peanut butter", "contains": ["peanut"]},
            {"name": "cheese", "contains": ["dairy"]}, {"name": "brie", "parent": "cheese"},
            {"name": "eggplant"}, {"name": "cider vinegar"}]
    assert seedCandidates.audit(seed) == [("paneer", "dairy", "paneer")]


def test_coverageCountsLinesAndCompleteRecipes():
    def recipe(*ids):
        return Recipe(source="mealdb", sourceId="1", kind="food", title="x", steps=[Step(text="s")],
                      ingredients=[IngredientLine(line="l", name="n", ingredientId=i) for i in ids],
                      facts={"complete": all(ids), "contains": [], "diets": []})
    assert seedCandidates.coverage([recipe(1, 2), recipe(3, None)]) == \
        {"lines": 4, "matched": 3, "recipes": 2, "complete": 1}


def test_everyAuditFindingInTheRealSeedIsAccepted():
    rules = rulesData.load()
    accepted = {(a["name"], a["item"]) for a in rules["auditAccepted"]}
    open_ = [f for f in seedCandidates.audit(rules["ingredients"]) if (f[0], f[1]) not in accepted]
    assert open_ == [], f"review these seed entries: {open_}"
