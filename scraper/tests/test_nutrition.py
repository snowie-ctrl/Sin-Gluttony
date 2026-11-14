import shutil

import pytest

import config, fdc, gate, matching, nutrition, rulesData
from conftest import FIXTURES
from models import IngredientLine, Recipe

SEED = [{"name": n} for n in ("onion", "flour", "egg", "olive oil", "salt", "gin", "triple sec")]
MAPPING = {"onion": 900001, "flour": 900002, "egg": 900003, "olive oil": 900004}


@pytest.fixture
def setup():
    shutil.copytree(FIXTURES / "fdc" / "sr", config.FDC_DIR / "sr")
    fdc.importFolders(log=lambda *_: None)
    rules = rulesData.load()
    table = matching.IngredientTable.fromSeed(SEED, set(rules["prepWords"]))
    return table, MAPPING, fdc.loadFoods(), rules


def line(text, name, quantity, unit, **fields):
    ids = {row["name"]: i for i, row in matching.IngredientTable.fromSeed(SEED, set()).rows.items()}
    return IngredientLine(line=text, name=name or text, quantity=quantity, unit=unit,
                          ingredientId=ids.get(name), **fields)


def recipe(lines, servings=1, kind="food", **fields):
    return Recipe(source="testsite", sourceId="1", kind=kind, title="Made-up", ingredients=lines, steps=[],
                  servings=servings, **fields)


def test_estimate_sums_and_divides(setup):
    r = recipe(servings=2, lines=[line("200 g flour", "flour", 200, "g"), line("2 large eggs", "egg", 2, None, note="large")])
    est, blocker = nutrition.estimate(r, *setup)
    assert blocker is None
    assert est["calories"] == round((364 * 2 + 143 * 1) / 2, 1)        # 200 g flour + 100 g egg, two servings


def test_refuses_when_any_required_line_fails(setup):
    r = recipe(servings=2, lines=[line("200 g flour", "flour", 200, "g"), line("1 dragonfruit", None, 1, None)])
    est, blocker = nutrition.estimate(r, *setup)
    assert est is None and blocker["reason"] == "unknown-ingredient" and blocker["line"] == "1 dragonfruit"


def test_blockers_name_the_ingredient(setup):
    r = recipe(lines=[line("1 onion", "onion", 1, None), line("2 tbsp salt", "salt", 2, "tbsp")])
    assert nutrition.estimate(r, *setup)[1] == {"line": "2 tbsp salt", "reason": "no-fdc", "ingredient": "salt"}
    r = recipe(lines=[line("some flour", "flour", None, None)])
    assert nutrition.estimate(r, *setup)[1]["reason"] == "no-amount"
    r = recipe(lines=[line("2 bunch flour", "flour", 2, "dozen")])
    assert nutrition.estimate(r, *setup)[1] == {"line": "2 bunch flour", "reason": "no-gram-rule", "ingredient": "flour"}


def test_a_mapped_food_missing_from_the_cache_is_no_fdc(setup):
    table, mapping, foods, rules = setup
    r = recipe(lines=[line("100 g flour", "flour", 100, "g")])
    assert nutrition.estimate(r, table, {"flour": 123}, foods, rules)[1]["reason"] == "no-fdc"


def test_skips_optional_taste_garnish_and_frying(setup):
    r = recipe(servings=1, lines=[line("100 g flour", "flour", 100, "g"),
                                  line("salt and pepper, to taste", "salt", None, None, note="to taste"),
                                  line("lemon twist", None, None, None, group="Garnish"),
                                  line("olive oil, for frying", "olive oil", None, None, note="for frying"),
                                  line("parsley (optional)", None, None, None, optional=True)])
    assert nutrition.estimate(r, *setup)[0]["calories"] == 364


def test_a_line_with_no_amount_and_no_skip_note_blocks(setup):
    r = recipe(lines=[line("olive oil", "olive oil", None, None)])
    assert nutrition.estimate(r, *setup)[1]["reason"] == "no-amount"


def test_drink_category(setup):
    r = recipe(kind="drink", servings=1, lines=[line("50ml gin", "gin", 50, "ml"), line("20ml triple sec", "triple sec", 20, "ml")])
    est, _ = nutrition.estimate(r, *setup)
    assert est["calories"] == round(231 * 0.5 + 330 * 0.2, 1)


def test_drink_in_grams_goes_through_its_density(setup):
    r = recipe(kind="drink", lines=[line("95 g gin", "gin", 95, "g")])
    assert nutrition.estimate(r, *setup)[0]["calories"] == 231     # 95 g at 0.95 g/ml is 100 ml


def test_no_servings_never_divides_by_zero(setup):
    r = recipe(servings=None, lines=[line("100 g flour", "flour", 100, "g")])
    assert nutrition.estimate(r, *setup) == (None, {"line": None, "reason": "no-servings", "ingredient": None})
    r = recipe(servings=0, lines=[line("100 g flour", "flour", 100, "g")])
    assert nutrition.estimate(r, *setup)[1]["reason"] == "no-servings"


def test_range_follows_yield_then_course_then_kind(setup):
    rules = setup[3]
    assert nutrition.rangeOf(recipe([], servingsFrom="yield", course="dessert"), rules) == (5, 1000)
    assert nutrition.rangeOf(recipe([], course="dessert"), rules) == (50, 1200)
    assert nutrition.rangeOf(recipe([], course="main"), rules) == (20, 2500)
    assert nutrition.rangeOf(recipe([], kind="drink", course="mocktail"), rules) == (0, 400)
    assert nutrition.rangeOf(recipe([], kind="drink"), rules) == (30, 600)


def test_choose_site_wins_and_range(setup):
    r = recipe(servings=1, lines=[line("100 g flour", "flour", 100, "g")], nutrition={"calories": 400})
    nutrition.choose(r, *setup)
    assert r.nutritionFrom == "source" and r.estimate["calories"] == 364 and not r.nutritionFlagged
    big = recipe(servings=1, lines=[line("3 kg flour", "flour", 3, "kg")])     # 10,920 kcal > 3 x 2,500
    nutrition.choose(big, *setup)
    assert big.nutrition is None and big.nutritionFrom is None
    mid = recipe(servings=1, lines=[line("1 kg flour", "flour", 1, "kg")])     # 3,640: flagged but shown
    nutrition.choose(mid, *setup)
    assert mid.nutritionFrom == "estimate" and mid.nutritionFlagged


def test_choose_records_the_blocker_and_is_repeatable(setup):
    r = recipe(lines=[line("1 dragonfruit", None, 1, None)])
    nutrition.choose(r, *setup)
    assert r.estimate is None and r.estimateBlocker["reason"] == "unknown-ingredient" and r.nutritionFrom is None
    ok = recipe(lines=[line("100 g flour", "flour", 100, "g")])
    nutrition.choose(ok, *setup)
    nutrition.choose(ok, *setup)
    assert ok.nutritionFrom == "estimate" and ok.nutrition == ok.estimate and gate.hasNutrition(ok)


def test_a_site_value_outside_the_range_is_flagged(setup):
    r = recipe(lines=[line("100 g flour", "flour", 100, "g")], nutrition={"calories": 5})
    nutrition.choose(r, *setup)
    assert r.nutritionFrom == "source" and r.nutritionFlagged


def test_drink_lines_use_the_sites_measures(setup):
    table = matching.IngredientTable.fromSeed(SEED + [{"name": "simple syrup"}], set())
    ids = {row["name"]: i for i, row in table.rows.items()}
    r = recipe(kind="drink", lines=[IngredientLine(line="1 tbsp simple syrup", name="simple syrup", quantity=1,
                                                   unit="tbsp", ingredientId=ids["simple syrup"])])
    _, mapping, foods, rules = setup
    est, _ = nutrition.estimate(r, table, mapping, foods, rules, measures={"tbsp": 20})
    assert est["calories"] == round(260 * 20 / 100, 1)


def test_a_chosen_estimate_that_later_fails_leaves_no_nutrition(setup):
    r = recipe(lines=[line("100 g flour", "flour", 100, "g")])
    nutrition.choose(r, *setup)
    assert r.nutritionFrom == "estimate"
    r.ingredients.append(line("1 dragonfruit", None, 1, None))
    nutrition.choose(r, *setup)
    assert r.nutrition is None and r.nutritionFrom is None and not r.nutritionFlagged


def test_estimate_records_every_ingredient_with_no_fdc_but_keeps_the_first_blocker(setup):
    table, mapping, foods, rules = setup
    r = recipe(lines=[line("1 dragonfruit", None, 1, None), line("2 tbsp salt", "salt", 2, "tbsp"),
                      line("1 egg", "egg", 1, None), line("1 onion", "onion", 1, None),
                      line("1 tbsp salt", "salt", 1, "tbsp")])
    blocker = nutrition.estimate(r, table, {"onion": 900001}, foods, rules)[1]
    assert blocker["reason"] == "unknown-ingredient"
    assert r.hints["noFdc"] == ["egg", "salt"]
    r = recipe(lines=[line("1 onion", "onion", 1, None)])
    r.hints["noFdc"] = ["salt"]
    nutrition.estimate(r, table, mapping, foods, rules)
    assert "noFdc" not in r.hints


def test_a_skip_note_wins_over_an_amount(setup):
    r = recipe(servings=1, lines=[line("100 g flour", "flour", 100, "g"),
                                  line("2 tsp olive oil, for brushing", "olive oil", 2, "tsp", note="for brushing"),
                                  line("1 tbsp flour, for dusting", "flour", 1, "tbsp", note="for dusting"),
                                  line("3 cups olive oil", "olive oil", 3, "cup", note="for deep frying"),
                                  line("flour", "flour", 1, "tbsp", note="for the work surface")])
    assert nutrition.estimate(r, *setup)[0]["calories"] == 364


def test_every_failing_line_is_a_blocker_once_in_line_order(setup):
    table, mapping, foods, rules = setup
    unknown = line("1 sumac", None, 1, None)
    unknown.unknownName = "sumac"
    r = recipe(servings=None, lines=[unknown, line("2 tbsp salt", "salt", 2, "tbsp"), line("1 egg", "egg", 1, None),
                                     line("some flour", "flour", None, None), line("1 tbsp salt", "salt", 1, "tbsp"),
                                     line("1 sumac", None, 1, None)])
    unknown2 = r.ingredients[-1]
    unknown2.unknownName = "sumac"
    est, first = nutrition.estimate(r, table, {"onion": 900001, "flour": 900002}, foods, rules)
    assert est is None and first["reason"] == "unknown-ingredient"
    assert r.hints["blockers"] == [{"reason": "unknown-ingredient", "ingredient": "sumac"},
                                   {"reason": "no-fdc", "ingredient": "salt"},
                                   {"reason": "no-fdc", "ingredient": "egg"},
                                   {"reason": "no-amount", "ingredient": "flour"},
                                   {"reason": "no-servings", "ingredient": None}]
    assert r.hints["noFdc"] == ["egg", "salt"]
    ok = recipe(lines=[line("100 g flour", "flour", 100, "g")])
    ok.hints["blockers"] = [{"reason": "x", "ingredient": None}]
    nutrition.estimate(ok, table, mapping, foods, rules)
    assert "blockers" not in ok.hints


def test_a_skip_phrase_after_plus_or_extra_qualifies_only_the_extra(setup):
    r = recipe(servings=1, lines=[line("200 g flour, plus extra for dusting", "flour", 200, "g",
                                       note="plus extra for dusting")])
    assert nutrition.estimate(r, *setup)[0]["calories"] == 728
    r = recipe(servings=1, lines=[line("200 g flour", "flour", 200, "g", note="extra for dusting"),
                                  line("100 g flour", "flour", 100, "g", note="for dusting")])
    assert nutrition.estimate(r, *setup)[0]["calories"] == 728


def test_extra_virgin_or_extra_large_before_a_skip_phrase_does_not_cancel_it():
    assert nutrition._skipsLine("extra virgin, for drizzling", "for drizzling")
    assert nutrition._skipsLine("extra large, for frying", "for frying")
    assert not nutrition._skipsLine("plus extra for drizzling", "for drizzling")
    assert not nutrition._skipsLine("extra for drizzling", "for drizzling")
