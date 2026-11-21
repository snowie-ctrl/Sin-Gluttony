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

    function test_everyPairingSlotHasALabel() {
        compare(Words.goesWith, "Goes with")
        compare(Words.slotLabel("side"), "On the side")
        compare(Words.slotLabel("sauce"), "Something saucy")
        compare(Words.slotLabel("dessert"), "For afters")
        compare(Words.slotLabel("drink"), "To drink")
        compare(Words.slotLabel("goes-on"), "Pile it on")
        compare(Words.slotLabel("snack"), "Something to nibble")
        compare(Words.slotLabel("pudding"), "pudding")      // a slot the app does not know yet still reads
    }

    function test_sourceName_data() {
        return [
            { tag: "bbcgoodfood", source: "bbcgoodfood", name: "BBC Good Food" },
            { tag: "budgetbytes", source: "budgetbytes", name: "Budget Bytes" },
            { tag: "recipetineats", source: "recipetineats", name: "RecipeTin Eats" },
            { tag: "pinchofyum", source: "pinchofyum", name: "Pinch of Yum" },
            { tag: "loveandlemons", source: "loveandlemons", name: "Love and Lemons" },
            { tag: "difford", source: "difford", name: "Difford's Guide" },
            { tag: "an old source", source: "wikibooks", name: "Wikibooks" },
            { tag: "unknown", source: "elsewhere", name: "elsewhere" },
            { tag: "none", source: null, name: "" }
        ]
    }

    function test_sourceName(row) {
        compare(Words.sourceName(row.source), row.name)
    }

    function test_nutritionWords() {
        compare(Words.nutritionTitle, "Per serving")
        compare(Words.nutritionMore, "More")
        compare(Words.nutritionLess, "Less")
        compare(Words.nutritionEstimated, "estimated")
        compare(Words.fromSite("Budget Bytes"), "From Budget Bytes ↗")
        compare(Words.NUTRIENTS.calories, "Calories")
        compare(Words.NUTRIENTS.sodiumMg, "Sodium")
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
