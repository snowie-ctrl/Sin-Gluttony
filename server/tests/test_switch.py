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
