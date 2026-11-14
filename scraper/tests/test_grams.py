import json, shutil

import pytest

import config, fdc, grams
from conftest import FIXTURES
from models import IngredientLine as L


@pytest.fixture
def foods():
    shutil.copytree(FIXTURES / "fdc" / "sr", config.FDC_DIR / "sr")
    fdc.importFolders(log=lambda *_: None)
    return fdc.loadFoods()


@pytest.fixture
def dens():
    with open(config.BASE_DIR / "rules" / "densities.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def FLOUR(foods):
    return foods[900002]


@pytest.fixture
def EGG(foods):
    return foods[900003]


@pytest.fixture
def ONION(foods):
    return foods[900001]


@pytest.fixture
def COOKED_NO_PORTIONS(foods):
    return foods[900005]


@pytest.fixture
def OILNOPORTION(foods):
    return dict(foods[900004], portions=[])


def test_weight_and_range_midpoint(dens, FLOUR):
    assert grams.gramsOf(L(line="", name="flour", quantity=200, unit="g"), FLOUR, dens) == (200, None)
    assert grams.gramsOf(L(line="", name="flour", quantity=1, unit="lb"), FLOUR, dens)[0] == 453.6
    assert grams.amountOf(L(line="", name="x", quantity=2, quantityMax=3, unit="tbsp")) == 2.5
    assert grams.amountOf(L(line="", name="salt", quantity=None, unit="pinch")) == 1


def test_container_size_in_note(dens):
    line = L(line="2 x 400g cans tomatoes", name="tomatoes", quantity=2, unit="can", note="400g")
    assert grams.gramsOf(line, None, dens) == (800, None)
    first = L(line="", name="x", quantity=1, unit="jar", note="organic; 12 oz, or 340 g")
    assert grams.gramsOf(first, None, dens)[0] == 340.2
    assert grams.gramsOf(L(line="", name="x", quantity=1, unit="can"), None, dens) == (None, "no-gram-rule")


def test_volume_through_fdc_portion_then_density(dens, FLOUR, OILNOPORTION):
    assert grams.gramsOf(L(line="", name="flour", quantity=1, unit="cup"), FLOUR, dens)[0] == 125
    assert grams.gramsOf(L(line="", name="flour", quantity=1, unit="cup"), FLOUR, dens,
                         measures={"cup": 250})[0] == round(125 * 250 / 236.6, 1)
    oil = grams.gramsOf(L(line="", name="olive oil", quantity=100, unit="ml"), OILNOPORTION, dens,
                        ingredientName="olive oil")
    assert oil == (92.0, None)
    drink = {"mlDensity": 0.95}
    assert grams.gramsOf(L(line="", name="gin", quantity=50, unit="ml"), drink, dens) == (47.5, None)


def test_counts_use_size_then_medium(dens, EGG, ONION):
    assert grams.gramsOf(L(line="", name="egg", quantity=2, unit=None, note="large"), EGG, dens)[0] == 100
    assert grams.gramsOf(L(line="", name="egg", quantity=2, unit=None, note="large; beaten"), EGG, dens)[0] == 100
    assert grams.gramsOf(L(line="", name="onion", quantity=1, unit=None), ONION, dens)[0] == 110


def test_named_and_vague_units(dens, ONION):
    assert grams.gramsOf(L(line="", name="salt", quantity=None, unit="pinch"), None, dens) == (0.4, None)
    assert grams.gramsOf(L(line="", name="garlic", quantity=2, unit="clove"), ONION, dens) == (None, "no-gram-rule")


def test_refusals(dens, ONION, COOKED_NO_PORTIONS):
    assert grams.gramsOf(L(line="", name="onion", quantity=None, unit=None), ONION, dens) == (None, "no-amount")
    assert grams.gramsOf(L(line="", name="x", quantity=1, unit=None), COOKED_NO_PORTIONS, dens) == (None, "no-gram-rule")


def test_exact_portion_beats_a_modified_one(dens, FLOUR):
    food = dict(FLOUR, portions=[{"amount": 1.0, "unit": "cup, sifted", "grams": 110.0},
                                 {"amount": 1.0, "unit": "cup", "grams": 125.0}])
    assert grams.gramsOf(L(line="", name="flour", quantity=1, unit="cup"), food, dens)[0] == 125
    only = dict(FLOUR, portions=[{"amount": 1.0, "unit": "cup, sifted", "grams": 110.0}])
    assert grams.gramsOf(L(line="", name="flour", quantity=1, unit="cup"), only, dens)[0] == 110


def test_a_weight_portion_is_not_a_piece(dens, ONION):
    food = dict(ONION, portions=[{"amount": 1.0, "unit": "oz", "grams": 28.35}])
    assert grams.gramsOf(L(line="", name="shallot", quantity=2, unit=None), food, dens) == (None, "no-gram-rule")
    serving = dict(ONION, portions=[{"amount": 1.0, "unit": "serving", "grams": 50.0}])
    assert grams.gramsOf(L(line="", name="shallot", quantity=2, unit=None), serving, dens) == (None, "no-gram-rule")


def test_named_unit_through_a_portion(dens, ONION):
    garlic = dict(ONION, portions=[{"amount": 3.0, "unit": "cloves", "grams": 9.0}])
    assert grams.gramsOf(L(line="", name="garlic", quantity=2, unit="clove"), garlic, dens) == (6.0, None)


def test_a_count_whose_note_states_the_weight(dens, ONION):
    thighs = L(line="", name="chicken", quantity=5, unit=None, note="~1.2kg/2.4lb; skin-on")
    assert grams.gramsOf(thighs, ONION, dens) == (1200, None)
    breasts = L(line="", name="chicken", quantity=4, unit=None, note="200g each")
    assert grams.gramsOf(breasts, ONION, dens) == (800, None)
    potatoes = L(line="", name="potato", quantity=4, unit=None, note="2 1/2 lbs")
    assert grams.gramsOf(potatoes, ONION, dens) == (1134, None)
    ranged = L(line="", name="potato", quantity=2, unit=None, note="1-2 lb")
    assert grams.gramsOf(ranged, None, dens) == (680.4, None)
