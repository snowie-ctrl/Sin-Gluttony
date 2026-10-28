import config
import report
from models import IngredientLine, Recipe, Step


def recipe(*unknown):
    return Recipe(source="mealdb", sourceId="1", kind="food", title="x", steps=[Step(text="s")],
                  ingredients=[IngredientLine(line=f"1 {u}", name=u, unknownName=u) for u in unknown])


def test_unknownIngredientsAreRankedByRecipesBlocked():
    ranked = report.unknownIngredients([recipe("yuzu", "yuzu"), recipe("yuzu", "dashi"), recipe("dashi")])
    assert ranked == [{"name": "dashi", "recipes": 2, "example": "1 dashi"},
                      {"name": "yuzu", "recipes": 2, "example": "1 yuzu"}]


def test_skippedAreCountedByReasonAndTrimmed():
    skipped = [{"key": f"w:{n}", "title": str(n), "reason": "topic page", "detail": None} for n in range(3)]
    summary = report.summariseSkipped(skipped, keep=2)
    assert summary["skippedCount"] == 3 and len(summary["skipped"]) == 2
    assert summary["skippedByReason"] == {"topic page": 3}


def test_writeKeepsTheLastReportAndAppendsTheRunLine():
    report.write({"mode": "full", "outcome": "ok", "error": None, "startedAt": 1_760_000_000.0,
                  "endedAt": 1_760_000_100.0, "recipes": 5, "publish": {"changed": 2, "removed": 0, "dry": True}})
    assert config.LAST_REPORT_FILE.exists() and len(list(config.REPORT_DIR.glob("run-*.json"))) == 1
    assert report.lastRun() == {"mode": "full", "outcome": "ok", "error": None, "startedAt": 1_760_000_000.0,
                                "endedAt": 1_760_000_100.0, "recipes": 5, "changed": 2, "removed": 0, "dry": True}


def test_lastRunIsNoneBeforeAnyRun():
    assert report.lastRun() is None
