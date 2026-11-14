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
