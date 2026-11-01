import QtQuick
import QtTest
import "../../qml/logic/stepIngredients.mjs" as StepIngredients

TestCase {
    name: "StepIngredients"

    // Fixture recipe 1's lines: a known name unlike its line (lardons are bacon), an unknown ingredient, salt.
    readonly property var lines: [
        { line: "1.5 kg chicken thighs", name: "chicken thigh" },
        { line: "750 ml red wine", name: "red wine" },
        { line: "200 g lardons", name: "bacon" },
        { line: "12 pearl onions", name: null },
        { line: "Salt to taste", name: "salt" }
    ]

    function test_theFullNameOrItsLastWordLightsALine() {
        compare(StepIngredients.mentioned("Add the chicken thighs and the wine.", lines), [0, 1])
        compare(StepIngredients.mentioned("Turn the thighs over.", lines), [0])
        compare(StepIngredients.mentioned("Glaze the onions in butter.", lines), [3])
        compare(StepIngredients.mentioned("Season with SALT.", lines), [4])
    }

    function test_aFirstWordAloneLightsNothing() {
        // The owner's rule (2026-10-29): "chicken" alone does not name the chicken thighs, so a wrong line never lights.
        compare(StepIngredients.mentioned("Brown the chicken in batches.", lines), [])
        compare(StepIngredients.mentioned("Pour in the red sauce.", lines), [])
    }

    function test_wholeWordsOnly() {
        compare(StepIngredients.mentioned("Stir in the buttermilk.", [{ line: "50 g butter", name: "butter" }]), [])
        compare(StepIngredients.mentioned("Add the saltpetre.", lines), [])
    }

    function test_pluralsAndSingularsBothCount() {
        compare(StepIngredients.mentioned("Chop the tomatoes.", [{ line: "2 tomatoes", name: "tomato" }]), [0])
        compare(StepIngredients.mentioned("Add the berries.", [{ line: "1 cup berries", name: "berry" }]), [0])
        compare(StepIngredients.mentioned("Beat the egg.", [{ line: "3 eggs", name: "eggs" }]), [0])
        compare(StepIngredients.mentioned("Add the olives.", [{ line: "12 olives", name: "olive" }]), [0])
    }

    function test_anUnknownIngredientIsNamedByItsLine() {
        compare(StepIngredients.nameOf({ line: "1 cup water or homemade vegetable stock", name: null }), "water")
        compare(StepIngredients.nameOf({ line: "Filling (e.g. walnut filling, jam, etc.)", name: null }), "filling")
        compare(StepIngredients.nameOf({ line: "2 cloves garlic, crushed", name: null }), "garlic")
        compare(StepIngredients.nameOf({ line: "12 pearl onions", name: null }), "pearl onions")
        compare(StepIngredients.nameOf({ line: "x", name: "Chicken Thigh" }), "chicken thigh")
    }

    function test_nothingToMatchLightsNothing() {
        compare(StepIngredients.mentioned("", lines), [])
        compare(StepIngredients.mentioned("Add it.", []), [])
        compare(StepIngredients.mentioned("Add it.", undefined), [])
        // A short last word ("ea" from "1 ea. (2 lb) small pumpkin") says nothing on its own.
        compare(StepIngredients.mentioned("Cut each one.", [{ line: "1 ea. (2 lb) small pumpkin", name: null }]), [])
    }
}
