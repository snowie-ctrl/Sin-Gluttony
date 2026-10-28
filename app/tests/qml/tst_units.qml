import QtQuick
import QtTest
import "../../qml/logic/units.mjs" as Units

TestCase {
    name: "Units"

    function line(text, quantity, unit, quantityMax) {
        return { line: text, quantity: quantity, quantityMax: quantityMax === undefined ? null : quantityMax,
                 unit: unit, name: null }
    }

    function test_metricRoundsSensibly() {
        compare(Units.format(2.5, "g"), "2.5")
        compare(Units.format(12.4, "g"), "12")
        compare(Units.format(133, "g"), "135")
        compare(Units.format(1.25, "kg"), "1.25")
        compare(Units.format(1.5, "l"), "1.5")
    }

    function test_kitchenFractions() {
        compare(Units.fraction(0.6666666), "⅔")
        compare(Units.fraction(1.125), "1⅛")
        compare(Units.fraction(0.9999999), "1")
        compare(Units.fraction(3.3069), "3⅓")
        compare(Units.fraction(0.02), "⅛")
        compare(Units.fraction(2), "2")
    }

    function test_toMetric() {
        compare(Units.amountText(line("", 4, "oz"), 1, "metric", "food"), "115 g")
        compare(Units.amountText(line("", 3, "oz"), 1, "metric", "food"), "85 g")
        compare(Units.amountText(line("", 750, "ml"), 2, "metric", "food"), "1.5 l")
        compare(Units.amountText(line("", 1.5, "kg"), 2, "metric", "food"), "3 kg")
        compare(Units.amountText(line("", 1.5, "cup"), 1, "metric", "food"), "355 ml")
        compare(Units.amountText(line("", 2, "fl oz"), 1, "metric", "drink"), "59 ml")
    }

    function test_toUs() {
        compare(Units.amountText(line("", 1.5, "kg"), 1, "us", "food"), "3⅓ lb")
        compare(Units.amountText(line("", 200, "g"), 1, "us", "food"), "7 oz")
        compare(Units.amountText(line("", 750, "ml"), 1, "us", "food"), "3⅛ cups")
        compare(Units.amountText(line("", 30, "ml"), 1, "us", "food"), "2 tbsp")
        compare(Units.amountText(line("", 60, "ml"), 1, "us", "drink"), "2 fl oz")
        compare(Units.amountText(line("", 1, "cup"), 1, "us", "food"), "1 cup")
    }

    function test_spoonsAndCountsKeepTheirUnits() {
        compare(Units.amountText(line("", 2, "tsp"), 1, "metric", "food"), "2 tsp")
        compare(Units.amountText(line("", 2, "tbsp"), 1, "us", "food"), "2 tbsp")
        compare(Units.amountText(line("", 2, "clove", 3), 2, "metric", "food"), "4–6 cloves")
        compare(Units.amountText(line("", 1, "pinch"), 2, "metric", "food"), "2 pinches")
        compare(Units.amountText(line("", 4, null), 0.5, "metric", "food"), "2")
        compare(Units.amountText(line("Salt to taste", null, null), 2, "metric", "food"), "")
    }

    function test_oddServingsReadAsKitchenAmounts() {
        compare(Units.amountText(line("", 1.5, "cup"), 3 / 4, "us", "food"), "1⅛ cups")
        compare(Units.amountText(line("", 1.5, "cup"), 2 / 3, "us", "food"), "1 cup")
        compare(Units.amountText(line("", 3, null), 1 / 4, "us", "food"), "¾")
        compare(Units.amountText(line("", 4, "oz"), 3 / 4, "metric", "food"), "85 g")
    }

    function test_aUnitIsPluralByTheAmountShown() {
        compare(Units.amountText(line("", 250, "ml"), 1, "us", "food"), "1 cup")
        compare(Units.amountText(line("", 240, "ml"), 1, "us", "food"), "1 cup")
        compare(Units.amountText(line("", 1.04, "cup"), 1, "us", "food"), "1 cup")
        compare(Units.amountText(line("", 1.04, "clove"), 1, "metric", "food"), "1 clove")
        compare(Units.amountText(line("", 1.2, "cup"), 1, "us", "food"), "1¼ cups")
        compare(Units.amountText(line("", 0.72, "cup"), 1, "us", "food"), "¾ cup")
        compare(Units.amountText(line("", 1, "clove", 2.04), 1, "metric", "food"), "1–2 cloves")
    }

    function test_aSecondAmountInBracketsFollowsTheLine() {
        compare(Units.lineText(line("1 cup (240 ml) bulgur wheat", 1, "cup"), 2, "us", "food"), "2 cups bulgur wheat")
        compare(Units.lineText(line("2.5 L (10 ½ cups) water", 2.5, "l"), 0.75, "us", "food"), "8 cups water")
        compare(Units.lineText(line("220 g (7.75 oz) rice", 220, "g"), 1, "us", "food"), "7¾ oz rice")
        compare(Units.lineText(line("1 can (14–16 ounces) diced tomatoes", 1, "can"), 2, "metric", "food"),
                "2 cans (14–16 ounces) diced tomatoes")
        compare(Units.lineText(line("1 (14 oz) can diced tomatoes", 1, null), 2, "metric", "food"),
                "2 (14 oz) can diced tomatoes")
        compare(Units.lineText(line("1 cup (240 ml) bulgur wheat", 1, "cup"), 1, "us", "food"),
                "1 cup (240 ml) bulgur wheat")
        compare(Units.lineText(line("2 onions (about 3 large), diced", 2, null), 2, "us", "food"),
                "4 onions (about 3 large), diced")
    }

    function test_whereALinesAmountEnds() {
        compare(Units.restOf("1.5kg chicken thighs"), "chicken thighs")
        compare(Units.restOf("2 oz white rum"), "white rum")
        compare(Units.restOf("12 pearl onions"), "pearl onions")
        compare(Units.restOf("1 cup of flour"), "flour")
        compare(Units.restOf("2–3 cloves garlic, crushed"), "garlic, crushed")
        compare(Units.restOf("1 ½ cups red wine"), "red wine")
        compare(Units.restOf("3 large eggs"), "large eggs")
        compare(Units.restOf("1 lemon"), "lemon")
        compare(Units.restOf("Salt"), null)
    }

    // A second whole number is a size, not part of the amount ("1 9-inch pie shell"); a fraction after a whole
    // number still is ("1 1/2 cups").
    function test_aSizeAfterTheAmountStaysWithTheLine() {
        compare(Units.restOf("1 9-inch pie shell"), "9-inch pie shell")
        compare(Units.restOf("3 3-inch cinnamon sticks"), "3-inch cinnamon sticks")
        compare(Units.restOf("1 1/2 cups flour"), "flour")
        compare(Units.restOf("2 - 3 cloves garlic"), "garlic")
        compare(Units.lineText(line("1 9-inch pie shell", 1, null), 2, "metric", "food"), "2 9-inch pie shell")
        compare(Units.lineText(line("3 3-inch cinnamon sticks", 3, null), 2, "metric", "food"),
                "6 3-inch cinnamon sticks")
    }

    function test_aDroppedSecondAmountLeavesNoStraySpace() {
        compare(Units.lineText(line("1 cup (240 ml), plus more for dusting", 1, "cup"), 2, "us", "food"),
                "2 cups, plus more for dusting")
        compare(Units.lineText(line("200 g (7 oz); butter, softened", 200, "g"), 0.5, "metric", "food"),
                "100 g; butter, softened")
    }

    // Most optional lines already say so; the marker is added only to one that does not.
    function test_optionalIsSaidOnce() {
        compare(Units.withOptional("1 clove garlic (optional), minced", true), "1 clove garlic (optional), minced")
        compare(Units.withOptional("Optional: 1 tsp chilli flakes", true), "Optional: 1 tsp chilli flakes")
        compare(Units.withOptional("1 clove garlic, minced", true), "1 clove garlic, minced (optional)")
        compare(Units.withOptional("1 clove garlic", false), "1 clove garlic")
    }

    function test_aLineIsShownAsWrittenUnlessSomethingChanged() {
        compare(Units.lineText(line("200 g lardons", 200, "g"), 1, "metric", "food"), "200 g lardons")
        compare(Units.lineText(line("200 g lardons", 200, "g"), 0.5, "metric", "food"), "100 g lardons")
        compare(Units.lineText(line("1 ½ cups red wine", 1.5, "cup"), 1, "metric", "food"), "355 ml red wine")
        compare(Units.lineText(line("4 eggs", 4, null), 0.5, "metric", "food"), "2 eggs")
        compare(Units.lineText(line("Salt to taste", null, null), 2, "metric", "food"), "Salt to taste")
        compare(Units.lineText(line("2–3 cloves garlic, crushed", 2, "clove", 3), 2, "metric", "food"),
                "4–6 cloves garlic, crushed")
        compare(Units.lineText(line("2 oz white rum", 2, "fl oz"), 1, "us", "drink"), "2 oz white rum")
    }

    function test_aLineWhoseAmountIsNotAtTheStartSaysTheFactor() {
        compare(Units.lineText(line("Juice of 1 lemon", 1, null), 2, "metric", "food"), "Juice of 1 lemon (×2)")
        compare(Units.lineText(line("Juice of 1 lemon", 1, null), 0.5, "metric", "food"), "Juice of 1 lemon (×½)")
    }

    function test_temperaturesGetTheOtherScale() {
        compare(Units.withOtherScale("Heat the oven to 180°C."), "Heat the oven to 180°C (355°F).")
        compare(Units.withOtherScale("Bake at 350 F for an hour"), "Bake at 350 F (175°C) for an hour")
        compare(Units.withOtherScale("Cook at about 90°C"), "Cook at about 90°C (195°F)")
        compare(Units.withOtherScale("Bake at 180°C (350°F)."), "Bake at 180°C (350°F).")
        compare(Units.withOtherScale("Add 2 C of milk"), "Add 2 C of milk")
        compare(Units.withOtherScale(""), "")
    }
}
