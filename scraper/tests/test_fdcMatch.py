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


# --- per ingredient row (resolveTable / mappingForTable / syncList) ---

def _table(*rows):
    """A server-shaped table; rows are (name, fdcId, fdcFrom)."""
    import matching
    payload = {"ingredients": [{"id": i, "name": n, "parentId": None, "category": None, "contains": [],
                                "fdcId": f, "fdcFrom": s} for i, (n, f, s) in enumerate(rows, start=1)],
               "aliases": []}
    return matching.IngredientTable.fromServer(payload, set())


def test_file_pick_beats_db_owner_row(foods):
    table = _table(("onion", 900003, "owner"))
    assert fdcMatch.resolveTable(table, foods, {}, {"onion": 900001}) == {1: (900001, "owner")}
    assert fdcMatch.resolveTable(table, foods, {}, {"onion": None}) == {1: (None, "owner")}


def test_db_owner_row_beats_curated(foods):
    table = _table(("onion", 900003, "owner"))
    rules = {"fdcMap": {"onion": {"fdcId": 900005}}}
    assert fdcMatch.resolveTable(table, foods, rules, {}) == {1: (900003, "owner")}


def test_db_owner_none_means_no_mapping_and_nothing_sent(foods):
    table = _table(("onion", None, "owner"))
    rules = {"fdcMap": {"onion": {"fdcId": 900005}}}
    resolved = fdcMatch.resolveTable(table, foods, rules, {})
    assert resolved == {1: (None, "owner")}
    assert fdcMatch.mappingForTable(table, foods, rules, {}) == {}
    assert fdcMatch.syncList(table, resolved, foods) == []


def test_owner_id_missing_from_foods_falls_through_but_owner_row_is_kept(foods):
    table = _table(("onion", 1, "owner"))
    resolved = fdcMatch.resolveTable(table, foods, {"fdcMap": {"onion": {"fdcId": 900005}}}, {})
    assert resolved == {1: (900005, "curated")}
    assert fdcMatch.syncList(table, resolved, foods) == []


def test_curated_beats_settled_and_is_sent_as_curated(foods):
    table = _table(("onion", None, None))
    resolved = fdcMatch.resolveTable(table, foods, {"fdcMap": {"onion": {"fdcId": 900005}}}, {})
    assert resolved == {1: (900005, "curated")}
    assert fdcMatch.syncList(table, resolved, foods) == [{"ingredientId": 1, "fdcId": 900005, "from": "curated"}]


def test_settled_match_is_a_rule_row(foods):
    table = _table(("onion", None, None))
    resolved = fdcMatch.resolveTable(table, foods, {}, {})
    assert resolved == {1: (900001, "rule")}
    assert fdcMatch.syncList(table, resolved, foods) == [{"ingredientId": 1, "fdcId": 900001, "from": "rule"}]


def test_stored_rule_row_that_no_longer_settles_is_cleared(foods):
    table = _table(("dragonfruit", 900001, "rule"))
    resolved = fdcMatch.resolveTable(table, foods, {}, {})
    assert resolved == {1: (None, None)}
    assert fdcMatch.syncList(table, resolved, foods) == [{"ingredientId": 1, "fdcId": None, "from": None}]


def test_unchanged_row_is_not_sent(foods):
    table = _table(("onion", 900001, "rule"))
    assert fdcMatch.syncList(table, fdcMatch.resolveTable(table, foods, {}, {}), foods) == []


def test_sync_never_overwrites_a_stored_owner_row(foods):
    table = _table(("onion", 900003, "owner"))
    assert fdcMatch.syncList(table, {1: (900001, "rule")}, foods) == []
    assert fdcMatch.syncList(table, {1: (None, None)}, foods) == []
    assert fdcMatch.syncList(table, {1: (900001, "owner")}, foods) == [{"ingredientId": 1, "fdcId": 900001, "from": "owner"}]


def test_seed_rows_carry_no_fdc_id():
    import matching
    table = matching.IngredientTable.fromSeed([{"name": "onion"}], set())
    assert table.rows[1]["fdcId"] is None and table.rows[1]["fdcFrom"] is None


def test_mapping_for_table_matches_mapping_for_on_a_seed_table(foods):
    import matching
    table = matching.IngredientTable.fromSeed([{"name": "onion"}, {"name": "egg"}, {"name": "dragonfruit"}], set())
    rules = {"fdcMap": {"egg": {"fdcId": 900003}}}
    names = [r["name"] for r in table.rows.values()]
    assert fdcMatch.mappingForTable(table, foods, rules, {}) == fdcMatch.mappingFor(names, foods, rules, {})
    picks = {"onion": None, "egg": 900001}
    assert fdcMatch.mappingForTable(table, foods, rules, picks) == fdcMatch.mappingFor(names, foods, rules, picks)


def test_empty_cache_sends_nothing(foods):
    table = _table(("onion", 900001, "rule"), ("egg", None, None))
    resolved = fdcMatch.resolveTable(table, {}, {}, {})
    assert fdcMatch.syncList(table, resolved, {}) == []


def test_stored_id_missing_from_a_partial_cache_is_not_touched(foods):
    table = _table(("onion", 123456, "rule"))
    resolved = fdcMatch.resolveTable(table, foods, {}, {})
    assert resolved == {1: (900001, "rule")}
    assert fdcMatch.syncList(table, resolved, foods) == []


def test_file_pick_missing_from_foods_falls_through_and_never_overwrites_owner_row(foods):
    rules = {"fdcMap": {"onion": {"fdcId": 900005}}}
    owner = _table(("onion", 900003, "owner"))
    # the owner row's own id is valid, so it is the owner's choice after the unusable pick
    assert fdcMatch.resolveTable(owner, foods, rules, {"onion": 1}) == {1: (900003, "owner")}
    owner = _table(("onion", 123456, "owner"))
    resolved = fdcMatch.resolveTable(owner, foods, rules, {"onion": 1})
    assert resolved == {1: (900005, "curated")}
    assert fdcMatch.syncList(owner, resolved, foods) == []
    plain = _table(("onion", None, None))
    resolved = fdcMatch.resolveTable(plain, foods, rules, {"onion": 1})
    assert fdcMatch.syncList(plain, resolved, foods) == [{"ingredientId": 1, "fdcId": 900005, "from": "curated"}]
