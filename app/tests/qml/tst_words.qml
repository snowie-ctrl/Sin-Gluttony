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

    function test_theBadgesSayLittle() {
        compare(Words.devouredBadge(1), "✓")
        compare(Words.devouredBadge(3), "✓3")
        compare(Words.devouredBadge(0), "")
        compare(Words.starsBadge(4), "★4")
        compare(Words.starsBadge(0), "")
        compare(Words.MONTHS.length, 12)
        compare(Words.goneFromSource, "gone from its source")
    }

    function test_cookAndOfflineWords() {
        compare(Words.stepOf(2, 7), "Step 2 of 7")
        compare(Words.timerLabel("Stub Coq au Vin", 3), "Stub Coq au Vin · step 3")
        compare(Words.queuedWarning(1), "1 change made offline hasn't reached the server yet. Signing out deletes it.")
        compare(Words.queuedWarning(3), "3 changes made offline haven't reached the server yet. Signing out deletes them.")
        compare(Words.syncWhat({ op: "devoured", on: "2026-10-28" }, "yesterday"), "✓ Devoured yesterday")
        compare(Words.syncWhat({ op: "stars", stars: 4 }, ""), "★ 4 stars")
        compare(Words.syncWhat({ op: "stars", stars: null }, ""), "Stars cleared")
        compare(Words.syncWhat({ op: "note", text: "less salt" }, ""), "✎ Note")
        compare(Words.syncWhat({ op: "note", text: "" }, ""), "Note deleted")
    }
}
