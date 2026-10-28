import pytest

import quantity
import rulesData

UNITS = rulesData.load()["unitMap"]


@pytest.mark.parametrize("text, expected", [
    ("1", 1.0), ("1.5", 1.5), ("1,5", 1.5), ("1/2", 0.5), ("1 1/2", 1.5), ("½", 0.5),
    ("1½", 1.5), ("1 ½", 1.5), ("3/0", None), ("1,000", 1000.0), ("2,500", 2500.0),
])
def test_toNumberReadsEveryWayOfWritingAnAmount(text, expected):
    assert quantity.toNumber(text) == expected


@pytest.mark.parametrize("line, qty, qtyMax, unit, name, note, optional", [
    ("2 cups all-purpose flour, sifted", 2.0, None, "cup", "all-purpose flour", "sifted", False),
    ("1 1/2 tbsp. olive oil", 1.5, None, "tbsp", "olive oil", None, False),
    ("200g plain flour", 200.0, None, "g", "plain flour", None, False),
    ("1,000 g flour", 1000.0, None, "g", "flour", None, False),
    ("2-3 cloves garlic", 2.0, 3.0, "clove", "garlic", None, False),
    ("2 to 3 cups of stock", 2.0, 3.0, "cup", "stock", None, False),
    ("½ tsp salt", 0.5, None, "tsp", "salt", None, False),
    ("Salt, to taste", None, None, None, "Salt", "to taste", False),
    ("1 (14 oz) can chopped tomatoes", 1.0, None, "can", "chopped tomatoes", "14 oz", False),
    ("pinch of nutmeg (optional)", None, None, "pinch", "nutmeg", None, True),
    ("3 large eggs", 3.0, None, None, "large eggs", None, False),
    ("  fresh   basil  ", None, None, None, "fresh basil", None, False),
    ("Oil for deep frying", None, None, None, "Oil", "for deep frying", False),
    ("2 tbsp butter for greasing, softened", 2.0, None, "tbsp", "butter", "softened; for greasing", False),
    ("Hamburger buns for serving", None, None, None, "Hamburger buns", "for serving", False),
    ("For the sauce", None, None, None, "For the sauce", None, False),
    ("1 teaspoon salt or to taste", 1.0, None, "tsp", "salt", "to taste", False),
])
def test_parseLineSplitsAmountUnitNameAndNotes(line, qty, qtyMax, unit, name, note, optional):
    item = quantity.parseLine(line, UNITS)
    assert (item.quantity, item.quantityMax, item.unit, item.name, item.note, item.optional) == \
        (qty, qtyMax, unit, name, note, optional)
    assert item.line == " ".join(line.split())


@pytest.mark.parametrize("measure, expected", [
    ("1/2 cup ", (0.5, None, "cup", None)),
    ("1 1/2 oz", (1.5, None, "oz", None)),
    ("Juice of 1", (None, None, None, "Juice of 1")),
    ("To taste", (None, None, None, "To taste")),
    ("Dash", (None, None, "dash", None)),
    ("", (None, None, None, None)),
    (None, (None, None, None, None)),
    ("   ", (None, None, None, None)),
    ("2 chopped", (2.0, None, None, "chopped")),
])
def test_parseMeasureHandlesTheDbsOddMeasures(measure, expected):
    assert quantity.parseMeasure(measure, UNITS) == expected
