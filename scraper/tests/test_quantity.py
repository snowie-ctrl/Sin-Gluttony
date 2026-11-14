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


@pytest.mark.parametrize("line, qty, qtyMax, unit, name, note", [
    ("2 x 400g cans chopped tomatoes", 2.0, None, "can", "chopped tomatoes", "400g"),
    ("1 × 20g pack flat-leaf parsley", 1.0, None, "package", "flat-leaf parsley", "20g"),
    ("2 x 150g salmon fillets", 2.0, None, None, "salmon fillets", "150g"),
    ("200g/7oz plain flour", 200.0, None, "g", "plain flour", "7oz"),
    ("250ml / 9fl oz milk", 250.0, None, "ml", "milk", "9fl oz"),
    ("1 cup / 250 ml chicken stock", 1.0, None, "cup", "chicken stock", "250 ml"),
    ("1⁄2 tsp ground cumin", 0.5, None, "tsp", "ground cumin", None),
    ("1 Tbsp olive oil ($0.32)", 1.0, None, "tbsp", "olive oil", None),
    ("2 cloves garlic ($0.16*)", 2.0, None, "clove", "garlic", None),
    ("Juice of 1 lemon", 1.0, None, None, "lemon", "juice"),
    ("zest and juice of 2 limes", 2.0, None, None, "limes", "zest and juice"),
    ("a pinch of chilli flakes", 1.0, None, "pinch", "chilli flakes", None),
    ("A small bunch of coriander, chopped", 1.0, None, "bunch", "coriander", "small; chopped"),
    ("small bunch mint", None, None, "bunch", "mint", "small"),
    ("Top up with soda water", None, None, None, "soda water", "to top up"),
    ("1 large onion, diced", 1.0, None, None, "large onion", "diced"),
    # shapes the reviewer and the real dry run found
    ("8oz/225g butter", 8.0, None, "oz", "butter", "225g"),
    ("2 cups/250 g flour", 2.0, None, "cup", "flour", "250 g"),
    ("750ml/1¼ pints milk", 750.0, None, "ml", "milk", "1¼ pints"),
    ("150 g/5oz bacon (chopped then cooked)", 150.0, None, "g", "bacon", "chopped then cooked; 5oz"),
    ("1 cup + 2 tbsp flour", 1.0, None, "cup", "flour", "+ 2 tbsp"),
    ("3/4 cup plus 2 tbsp flour", 0.75, None, "cup", "flour", "plus 2 tbsp"),
    ("1 15-ounce can chickpeas", 1.0, None, "can", "chickpeas", "15-ounce"),
    ("1 12-oz bottle beer", 1.0, None, "bottle", "beer", "12-oz"),
    ("1 15oz. can black beans ( $0.89)", 1.0, None, "can", "black beans", "15oz."),
    ("2 14.5 oz. cans diced tomatoes (with juices, $2.12*)", 2.0, None, "can", "diced tomatoes", "with juices; 14.5 oz."),
    ("1/4 tsp.salt", 0.25, None, "tsp", "salt", None),
    ("0.5 x 7g sachet fast-action dried yeast", 0.5, None, "package", "fast-action dried yeast", "7g"),
    ("250 - 300 g / 8 - 10 oz pasta", 250.0, 300.0, "g", "pasta", "8 - 10 oz"),
    ("3 x 400g / 14oz cans cannellini beans", 3.0, None, "can", "cannellini beans", "400g / 14oz"),
    ("2 tbsp butter plus 1 tbsp melted", 2.0, None, "tbsp", "butter", "plus 1 tbsp melted"),
    ("200g caster sugar plus 3 tbsp", 200.0, None, "g", "caster sugar", "plus 3 tbsp"),
    ("1 1/2 cups flour + 2-3 tablespoons for dusting", 1.5, None, "cup", "flour", "+ 2-3 tablespoons for dusting"),
    ("1 whole chicken approx 1.2kg", 1.0, None, None, "whole chicken", "approx 1.2kg"),
    ("heaping 1/2 cup mini marshmallows", 0.5, None, "cup", "mini marshmallows", "heaping"),
    ("about 2 cups stock", 2.0, None, "cup", "stock", "about"),
    ("juice of a lemon", 1.0, None, None, "lemon", "juice"),
    ("Zest of an orange", 1.0, None, None, "orange", "zest"),
    ("2 x 400g tins chopped tomatoes", 2.0, None, "can", "chopped tomatoes", "400g"),
])
def test_parseLineReadsTheRecipeSitesPatterns(line, qty, qtyMax, unit, name, note):
    item = quantity.parseLine(line, UNITS)
    assert (item.quantity, item.quantityMax, item.unit, item.name, item.note) == (qty, qtyMax, unit, name, note)
