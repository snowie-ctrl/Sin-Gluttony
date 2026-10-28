import QtQuick
import QtTest
import "../../qml/logic/words.mjs" as Words

TestCase {
    name: "Words"

    function test_theDietChipSaysTheProfileInAFewWords() {
        compare(Words.dietChip(["vegetarian"], ["peanut"]), "Vegetarian · no peanuts")
        compare(Words.dietChip(["vegan", "gluten-free"], []), "Vegan · Gluten-free")
        compare(Words.dietChip([], ["tree-nut", "egg"]), "no tree nuts, eggs")
        compare(Words.dietChip([], []), "")
    }

    function test_smallWords() {
        compare(Words.effortWord(1), "easy")
        compare(Words.effortWord(3), "involved")
        compare(Words.effortWord(null), "")
        compare(Words.courseWord("coffee/tea"), "coffee or tea")
        compare(Words.sourceName("mealdb"), "TheMealDB")
        compare(Words.recipeCount(1), "1 recipe")
        compare(Words.recipeCount(212), "212 recipes")
        compare(Words.servingsText(4, "source"), "4 servings")
        compare(Words.servingsText(1, "rule"), "about 1 serving")
        compare(Words.servingsText(null, null), "")
        compare(Words.containsText(["alcohol", "dairy"]), "contains alcohol, dairy")
        compare(Words.containsText([]), "")
    }

    function test_everyDietAndAvoidItemHasALabel() {
        compare(Words.DIETS.map(d => d.value), ["vegetarian", "vegan", "gluten-free", "dairy-free"])
        compare(Words.AVOID.length, 13)
    }
}
