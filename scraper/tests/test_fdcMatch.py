import shutil
import threading

import pytest

import config, fdc, fdcMatch
from conftest import FIXTURES


@pytest.fixture
def foods():
    shutil.copytree(FIXTURES / "fdc" / "sr", config.FDC_DIR / "sr")
    return fdc.loadFoods()


def test_exact_head_settles_and_prefers_raw(foods):
    assert fdcMatch.settle("onion", foods) == 900001          # "Onions, raw" beats "Onions, cooked, boiled"


def test_candidates_order(foods):
    ids = [c["fdcId"] for c in fdcMatch.candidates("onion", foods)]
    assert ids[:2] == [900001, 900005]


def test_candidate_fields_and_scores(foods):
    raw, boiled = fdcMatch.candidates("onions", foods)[:2]
    assert raw == {"fdcId": 900001, "description": "Onions, raw", "dataType": "sr_legacy_food", "score": 108}
    assert boiled["score"] == 100 - 10 - 10 - 1


def test_reordered_head_and_words_elsewhere(foods):
    flour = fdcMatch.candidates("flour wheat", foods)[0]
    assert flour["fdcId"] == 900002 and flour["score"] == 90 - 1
    oil = fdcMatch.candidates("olive oil", foods)[0]
    assert oil["fdcId"] == 900004 and oil["score"] == 60 + 10 + 8    # every word is the ingredient's; a fat, nothing cooked
    assert fdcMatch.settle("olive oil", foods) is None


def test_named_cooking_is_not_penalised(foods):
    assert fdcMatch.candidates("boiled onion", foods)[0]["fdcId"] == 900005


def test_unsure_is_none(foods):
    assert fdcMatch.settle("dragonfruit", foods) is None
    assert fdcMatch.candidates("dragonfruit", foods) == []


def test_precedence(foods):
    rules = {"fdcMap": {"onion": {"fdcId": 900005, "description": "x"}}}
    assert fdcMatch.mappingFor(["onion"], foods, rules, {})["onion"] == 900005
    assert fdcMatch.mappingFor(["onion"], foods, rules, {"onion": 900001})["onion"] == 900001
    assert "onion" not in fdcMatch.mappingFor(["onion"], foods, rules, {"onion": None})
    assert fdcMatch.mappingFor(["onion"], foods, {}, {}) == {"onion": 900001}


def test_override_to_unknown_food_is_ignored(foods):
    assert fdcMatch.mappingFor(["onion"], foods, {"fdcMap": {"onion": {"fdcId": 1}}}, {}) == {"onion": 900001}
    assert fdcMatch.mappingFor(["flour"], foods, {"fdcMap": {"flour": {"fdcId": 1}}}, {}) == {}


def test_picks_round_trip():
    assert fdcMatch.loadPicks() == {}
    fdcMatch.savePick("onion", 900001)
    fdcMatch.savePick("dragonfruit", None)
    assert fdcMatch.loadPicks() == {"onion": 900001, "dragonfruit": None}


def test_simultaneous_picks_all_survive():
    names = [f"food{i}" for i in range(20)]
    threads = [threading.Thread(target=fdcMatch.savePick, args=(n, 900001)) for n in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(fdcMatch.loadPicks()) == sorted(names)
