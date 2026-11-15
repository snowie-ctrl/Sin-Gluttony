"""The catalog switch (gluttonySwitch.py): which new recipe a retired one hands on to, how what people kept moves,
and the run itself against the fake connection. Every recipe, list and person here is made up."""
from datetime import datetime

import pytest

from conftest import loadModule

NOW = datetime(2026, 11, 20, 9, 30, 0, 123000)


@pytest.fixture
def switch():
    return loadModule("gluttonySwitch")


def old(rid, dish="pancakes", kind="food", source="mealdb", removedAt=None):
    return {"RecipeID": rid, "Source": source, "DishKey": dish, "Kind": kind, "RemovedAt": removedAt}


def new(rid, dish="pancakes", kind="food", prep=None, cook=None, width=None, nutrition="estimate"):
    return {"RecipeID": rid, "DishKey": dish, "Kind": kind, "PrepMinutes": prep, "CookMinutes": cook,
            "ImageWidth": width, "NutritionFrom": nutrition}


def refs(**tables):
    return {table: tables.get(table, []) for table in ("ListItems", "Devoured", "Ratings", "Notes")}


def existing(**tables):
    return {table: tables.get(table, []) for table in ("ListItems", "Ratings", "Notes")}


# ---- which new recipe ----

def test_oneMatchIsTheTarget(switch):
    targets, several = switch.chooseTargets([old(1)], [new(500)])
    assert targets == {1: 500} and several == set()


def test_noMatchMeansNoTarget(switch):
    targets, _ = switch.chooseTargets([old(1, dish="flapjacks")], [new(500)])
    assert targets == {}


def test_theKindMustMatchToo(switch):
    targets, _ = switch.chooseTargets([old(1, dish="mojito", kind="drink")], [new(500, dish="mojito", kind="food")])
    assert targets == {}


def test_dishKeysMatchIgnoringCaseAndAccentsButNeverBlank(switch):
    targets, _ = switch.chooseTargets([old(1, dish="Crème Brûlée"), old(2, dish=""), old(3, dish="  ")],
                                      [new(500, dish="creme brulee"), new(501, dish=""), new(502, dish=" ")])
    assert targets == {1: 500}


@pytest.mark.parametrize("candidates, chosen", [
    # nutrition from the page beats every other fact
    ([new(500, prep=10, cook=20, width=2000), new(501, nutrition="source")], 501),
    # then prep and cook both given beat one given beat none
    ([new(500, prep=10, width=2000), new(501, prep=5, cook=5, width=900), new(502, width=3000)], 501),
    # then the wider picture
    ([new(500, prep=1, cook=1, width=900), new(501, prep=1, cook=1, width=1200)], 501),
    ([new(500, width=None), new(501, width=800)], 501),
    # then the lowest RecipeID
    ([new(502, prep=1, cook=1, width=900), new(501, prep=1, cook=1, width=900)], 501),
])
def test_severalMatchesPickTheOneWithTheMostFactsThenTheLowestId(switch, candidates, chosen):
    targets, several = switch.chooseTargets([old(1)], candidates)
    assert targets == {1: chosen} and several == {1}


def test_anAlreadyRemovedOldRecipeStillHandsOnWhatPeopleKept(switch):
    targets, _ = switch.chooseTargets([old(1, removedAt=datetime(2026, 1, 2))], [new(500)])
    assert targets == {1: 500}


# ---- moving what people kept ----

def test_unmatchedReferencesStayAndAreCounted(switch):
    writes, report = switch.planMoves({}, refs(
        ListItems=[{"ListID": 3, "RecipeID": 1, "OrderIndex": 0}], Devoured=[{"DevouredID": 9, "RecipeID": 1}],
        Ratings=[{"UserID": 7, "RecipeID": 1, "Stars": 4}], Notes=[{"UserID": 7, "RecipeID": 1, "Text": "nice"}]),
        existing(), NOW)
    assert writes == []
    for table in switch.TABLES:
        assert report[table]["moved"] == 0 and report[table]["notMoved"] == 1, table


def test_aRatingWithoutAClashMovesWithTheMomentOfTheMove(switch):
    writes, report = switch.planMoves({1: 500}, refs(Ratings=[{"UserID": 7, "RecipeID": 1, "Stars": 4}]),
                                      existing(), NOW)
    assert writes == [
        ("DELETE FROM Ratings WHERE UserID = %s AND RecipeID = %s", (7, 1)),
        ("INSERT INTO Ratings (UserID, RecipeID, Stars, UpdatedAt) VALUES (%s, %s, %s, %s) "
         "ON DUPLICATE KEY UPDATE Stars = VALUES(Stars), UpdatedAt = VALUES(UpdatedAt)", (7, 500, 4, NOW))]
    assert report["Ratings"] == {"moved": 1, "merged": 0, "notMoved": 0}


@pytest.mark.parametrize("moved, kept, result", [(5, 3, 5), (2, 4, 4), (None, 3, 3), (4, None, 4), (None, None, None)])
def test_aRatingClashKeepsTheHigherStars(switch, moved, kept, result):
    writes, report = switch.planMoves({1: 500}, refs(Ratings=[{"UserID": 7, "RecipeID": 1, "Stars": moved}]),
                                      existing(Ratings=[{"UserID": 7, "RecipeID": 500, "Stars": kept}]), NOW)
    assert writes[-1][1] == (7, 500, result, NOW)
    assert report["Ratings"] == {"moved": 1, "merged": 1, "notMoved": 0}


def test_aNoteClashJoinsTheTextsWithABlankLineKeptNoteFirst(switch):
    writes, report = switch.planMoves({1: 500}, refs(Notes=[{"UserID": 7, "RecipeID": 1, "Text": "less salt"}]),
                                      existing(Notes=[{"UserID": 7, "RecipeID": 500, "Text": "double it"}]), NOW)
    assert writes == [
        ("DELETE FROM Notes WHERE UserID = %s AND RecipeID = %s", (7, 1)),
        ("INSERT INTO Notes (UserID, RecipeID, Text, UpdatedAt) VALUES (%s, %s, %s, %s) "
         "ON DUPLICATE KEY UPDATE Text = VALUES(Text), UpdatedAt = VALUES(UpdatedAt)",
         (7, 500, "double it\n\nless salt", NOW))]
    assert report["Notes"] == {"moved": 1, "merged": 1, "notMoved": 0, "tooLong": 0}


@pytest.mark.parametrize("moved, kept, result", [
    ("", "double it", "double it"),          # a deleted note adds nothing
    ("double it", "", "double it"),
    ("", "", ""),                            # two deleted notes stay one deleted note (sync's tombstone)
    (" double it ", "double it", "double it"),  # the same words once
])
def test_deletedAndRepeatedNotesAddNothing(switch, moved, kept, result):
    writes, _ = switch.planMoves({1: 500}, refs(Notes=[{"UserID": 7, "RecipeID": 1, "Text": moved}]),
                                 existing(Notes=[{"UserID": 7, "RecipeID": 500, "Text": kept}]), NOW)
    assert writes[-1][1] == (7, 500, result, NOW)


def test_notesTooLongToJoinStayInPlaceAndAreReported(switch):
    writes, report = switch.planMoves({1: 500}, refs(Notes=[{"UserID": 7, "RecipeID": 1, "Text": "a" * 1000}]),
                                      existing(Notes=[{"UserID": 7, "RecipeID": 500, "Text": "b" * 999}]), NOW)
    assert writes == []
    assert report["Notes"] == {"moved": 0, "merged": 0, "notMoved": 1, "tooLong": 1}
    # exactly at the limit (999 + 2 + 999 = 2000) still joins
    writes, report = switch.planMoves({1: 500}, refs(Notes=[{"UserID": 7, "RecipeID": 1, "Text": "a" * 999}]),
                                      existing(Notes=[{"UserID": 7, "RecipeID": 500, "Text": "b" * 999}]), NOW)
    assert len(writes[-1][1][2]) == 2000 and report["Notes"]["tooLong"] == 0


def test_devouredKeepsBothDatesByMovingEachMark(switch):
    writes, report = switch.planMoves({1: 500}, refs(Devoured=[{"DevouredID": 9, "RecipeID": 1},
                                                               {"DevouredID": 12, "RecipeID": 1}]), existing(), NOW)
    assert writes == [("UPDATE Devoured SET RecipeID = %s WHERE DevouredID = %s", (500, 9)),
                      ("UPDATE Devoured SET RecipeID = %s WHERE DevouredID = %s", (500, 12))]
    assert report["Devoured"] == {"moved": 2, "merged": 0, "notMoved": 0}


def test_aListEntryMovesInPlace(switch):
    writes, report = switch.planMoves({1: 500}, refs(ListItems=[{"ListID": 3, "RecipeID": 1, "OrderIndex": -4}]),
                                      existing(), NOW)
    assert writes == [("UPDATE ListItems SET RecipeID = %s WHERE ListID = %s AND RecipeID = %s", (500, 3, 1))]
    assert report["ListItems"] == {"moved": 1, "merged": 0, "notMoved": 0}


def test_aListThatAlreadyHoldsTheNewRecipeKeepsOneEntry(switch):
    writes, report = switch.planMoves({1: 500}, refs(ListItems=[{"ListID": 3, "RecipeID": 1, "OrderIndex": -4}]),
                                      existing(ListItems=[{"ListID": 3, "RecipeID": 500}]), NOW)
    assert writes == [("DELETE FROM ListItems WHERE ListID = %s AND RecipeID = %s", (3, 1))]
    assert report["ListItems"] == {"moved": 1, "merged": 1, "notMoved": 0}


def test_twoRetiredRecipesOntoOneNewRecipeMergeForOnePerson(switch):
    targets = {1: 500, 2: 500}
    writes, report = switch.planMoves(targets, refs(
        ListItems=[{"ListID": 3, "RecipeID": 2, "OrderIndex": 5}, {"ListID": 3, "RecipeID": 1, "OrderIndex": -2}],
        Ratings=[{"UserID": 7, "RecipeID": 1, "Stars": 2}, {"UserID": 7, "RecipeID": 2, "Stars": 5}],
        Notes=[{"UserID": 7, "RecipeID": 2, "Text": "second"}, {"UserID": 7, "RecipeID": 1, "Text": "first"}]),
        existing(), NOW)
    lists = [w for w in writes if "ListItems" in w[0]]
    assert lists == [("UPDATE ListItems SET RecipeID = %s WHERE ListID = %s AND RecipeID = %s", (500, 3, 1)),
                     ("DELETE FROM ListItems WHERE ListID = %s AND RecipeID = %s", (3, 2))]
    assert [w[1] for w in writes if w[0].startswith("INSERT INTO Ratings")] == [(7, 500, 5, NOW)]
    assert [w[1] for w in writes if w[0].startswith("INSERT INTO Notes")] == [(7, 500, "first\n\nsecond", NOW)]
    assert report["ListItems"]["merged"] == 2 and report["Ratings"]["merged"] == 2 and report["Notes"]["merged"] == 2


def test_differentPeopleAndListsNeverMerge(switch):
    writes, report = switch.planMoves({1: 500}, refs(
        ListItems=[{"ListID": 3, "RecipeID": 1, "OrderIndex": 0}, {"ListID": 4, "RecipeID": 1, "OrderIndex": 0}],
        Ratings=[{"UserID": 7, "RecipeID": 1, "Stars": 2}, {"UserID": 8, "RecipeID": 1, "Stars": 5}]),
        existing(Ratings=[{"UserID": 8, "RecipeID": 600, "Stars": 1}]), NOW)
    assert [w[1] for w in writes if w[0].startswith("INSERT INTO Ratings")] == [(7, 500, 2, NOW), (8, 500, 5, NOW)]
    assert report["ListItems"] == {"moved": 2, "merged": 0, "notMoved": 0}
    assert report["Ratings"] == {"moved": 2, "merged": 0, "notMoved": 0}


# ---- the run, against the fake connection ----

WRITES = ("INSERT", "UPDATE", "DELETE")


def queue(retired=(), candidates=(), lists=(), devoured=(), ratings=(), notes=(), held=None):
    """fetchall answers in the order switch() reads; held (ListItems, Ratings, Notes already on the targets) only
    when something matched."""
    answers = [list(retired), list(candidates), list(lists), list(devoured), list(ratings), list(notes)]
    if held is not None:
        answers += [list(h) for h in held]
    return answers


def written(conn):
    return [s for s in conn.cur.executed if s[0].startswith(WRITES)]


KEPT = dict(retired=[old(1), old(2, dish="flapjacks")], candidates=[new(500)],
            lists=[{"ListID": 3, "RecipeID": 1, "OrderIndex": 0}], devoured=[{"DevouredID": 9, "RecipeID": 2}],
            ratings=[{"UserID": 7, "RecipeID": 1, "Stars": 4}], notes=[],
            held=([], [{"UserID": 7, "RecipeID": 500, "Stars": 5}], []))


def test_aDryRunReadsEverythingAndWritesNothing(switch, useDb):
    conn = useDb(fetchall=queue(**KEPT))
    report = switch.switch(apply=False, now=NOW)
    assert written(conn) == [] and conn.commits == 0 and conn.rollbacks == 1 and conn.closed
    assert report["applied"] is False
    assert report["ListItems"] == {"moved": 1, "merged": 0, "notMoved": 0}
    assert report["Devoured"] == {"moved": 0, "merged": 0, "notMoved": 1}
    assert report["Ratings"] == {"moved": 1, "merged": 1, "notMoved": 0}
    assert (report["retired"], report["newlyRetired"], report["shown"]) == (2, 2, 1)
    assert (report["referenced"], report["matched"]) == (2, 1)


def test_applyWritesTheMovesThenRetiresAndCommitsOnce(switch, useDb):
    conn = useDb(fetchall=queue(**KEPT))
    report = switch.switch(apply=True, now=NOW)
    sqls = [s for s, _ in written(conn)]
    assert sqls[0].startswith("UPDATE ListItems") and sqls[-1].startswith("UPDATE Recipes SET RemovedAt = NOW()")
    assert any(s.startswith("INSERT INTO Ratings") for s in sqls)
    assert conn.commits == 1 and conn.rollbacks == 0 and conn.closed and report["applied"] is True


def test_retireOnlyStampsRecipesNotYetRemoved(switch, useDb):
    conn = useDb(fetchall=queue(retired=[old(1, removedAt=datetime(2026, 1, 2)), old(2)], candidates=[new(500)]))
    report = switch.switch(apply=True, now=NOW)
    sql, params = written(conn)[-1]
    assert sql == "UPDATE Recipes SET RemovedAt = NOW() WHERE Source IN (%s, %s, %s) AND RemovedAt IS NULL"
    assert params == ("mealdb", "cocktaildb", "wikibooks")
    assert (report["retired"], report["newlyRetired"]) == (2, 1)


def test_theReadsLockAndOnlyCountShownSiteRecipes(switch, rules, useDb):
    conn = useDb(fetchall=queue(**KEPT))
    switch.switch(apply=False, now=NOW)
    selects = conn.cur.statements("SELECT")
    assert len(selects) == 9
    assert selects[0][1] == rules.OLD_SOURCES and selects[0][0].endswith("FOR UPDATE")
    candidates, params = selects[1]
    assert rules.SHOWN in candidates and "LEFT JOIN RecipeNutrition n" in candidates and candidates.endswith("FOR SHARE")
    assert params == rules.SITE_SOURCES
    for sql, params in selects[2:]:
        assert sql.endswith("FOR UPDATE"), sql
    assert selects[6][1] == (500,)


def test_nothingMatchedAsksForNoRowsOnTargets(switch, useDb):
    conn = useDb(fetchall=queue(retired=[old(1)], candidates=[new(500, dish="flapjacks")],
                                ratings=[{"UserID": 7, "RecipeID": 1, "Stars": 4}]))
    report = switch.switch(apply=True, now=NOW)
    assert len(conn.cur.statements("SELECT")) == 6
    assert [s for s, _ in written(conn)] == [
        "UPDATE Recipes SET RemovedAt = NOW() WHERE Source IN (%s, %s, %s) AND RemovedAt IS NULL"]
    assert report["Ratings"] == {"moved": 0, "merged": 0, "notMoved": 1}


def test_applyRefusesWhenNoSiteRecipeIsShown(switch, useDb):
    conn = useDb(fetchall=queue(retired=[old(1)], candidates=[]))
    with pytest.raises(switch.Refused, match="no site recipe is shown"):
        switch.switch(apply=True, now=NOW)
    assert written(conn) == [] and conn.commits == 0 and conn.rollbacks == 1 and conn.closed


def test_aFailedWriteRollsEverythingBack(switch, useDb):
    conn = useDb(fetchall=queue(**KEPT), failOn="INSERT INTO Ratings")
    with pytest.raises(RuntimeError):
        switch.switch(apply=True, now=NOW)
    assert conn.commits == 0 and conn.rollbacks == 1 and conn.closed


def test_theReportSaysPerTableWhatMovedAndWhatDidNot(switch, useDb):
    useDb(fetchall=queue(**KEPT))
    lines = switch.reportLines(switch.switch(apply=False, now=NOW), listing=True)
    text = "\n".join(lines)
    assert lines[0] == "switch: dry run, nothing was written (run again with --apply to switch)"
    assert "Ratings: 1 moved (1 merged with one already there), 0 not moved" in text
    assert "Devoured: 0 moved (0 merged with one already there), 1 not moved" in text
    assert "#1 mealdb pancakes (food) -> #500" in text and "#2 mealdb flapjacks (food) -> no match" in text


def test_mainIsADryRunUnlessAskedAndExitsOneWhenRefused(switch, useDb, capsys):
    conn = useDb(fetchall=queue(**KEPT))
    assert switch.main([]) == 0 and written(conn) == []
    assert "dry run" in capsys.readouterr().out
    useDb(fetchall=queue(retired=[old(1)], candidates=[]))
    assert switch.main(["--apply"]) == 1
    assert "switch: refused, nothing was changed: no site recipe is shown" in capsys.readouterr().out


def test_mainReportsAFailureAndExitsOne(switch, useDb, capsys):
    useDb(fetchall=queue(**KEPT), failOn="INSERT INTO Ratings")
    assert switch.main(["--apply"]) == 1
    assert "switch: failed, nothing was changed: RuntimeError" in capsys.readouterr().out
