import QtQuick
import QtTest
import "../../qml/logic/nutrition.mjs" as Nutrition

TestCase {
    name: "Nutrition"

    readonly property var full: ({ calories: 412.4, proteinG: 23.6, carbsG: 4.25, fatG: 9.96, satFatG: 3.04,
                                   fibreG: 12, sugarG: 0.5, sodiumMg: 812.2, from: "estimate", flagged: false })

    function test_mainRows_data() {
        return [
            { tag: "the main four, in order", n: full,
              rows: [{ key: "calories", label: "Calories", value: "412 kcal" },
                     { key: "proteinG", label: "Protein", value: "24 g" },
                     { key: "carbsG", label: "Carbs", value: "4.3 g" },
                     { key: "fatG", label: "Fat", value: "10 g" }] },
            { tag: "a null value is left out",
              n: { calories: 300, proteinG: null, carbsG: 10, fatG: 2, from: "source", flagged: false },
              rows: [{ key: "calories", label: "Calories", value: "300 kcal" },
                     { key: "carbsG", label: "Carbs", value: "10 g" },
                     { key: "fatG", label: "Fat", value: "2.0 g" }] },
            { tag: "no nutrition", n: null, rows: [] },
            { tag: "nothing known", n: { from: "source" }, rows: [] }
        ]
    }

    function test_mainRows(row) {
        compare(Nutrition.mainRows(row.n), row.rows)
    }

    function test_moreRows_data() {
        return [
            { tag: "the other four, in order", n: full,
              rows: [{ key: "satFatG", label: "Saturated fat", value: "3.0 g" },
                     { key: "fibreG", label: "Fibre", value: "12 g" },
                     { key: "sugarG", label: "Sugar", value: "0.5 g" },
                     { key: "sodiumMg", label: "Sodium", value: "812 mg" }] },
            { tag: "a null value is left out",
              n: { calories: 300, satFatG: null, fibreG: 2.04, sugarG: null, sodiumMg: 0, from: "source" },
              rows: [{ key: "fibreG", label: "Fibre", value: "2.0 g" },
                     { key: "sodiumMg", label: "Sodium", value: "0 mg" }] },
            { tag: "no nutrition", n: null, rows: [] }
        ]
    }

    function test_moreRows(row) {
        compare(Nutrition.moreRows(row.n), row.rows)
    }

    function test_format_data() {
        return [
            { tag: "kcal to a whole number", key: "calories", value: 412.4, text: "412 kcal" },
            { tag: "kcal rounds up", key: "calories", value: 99.5, text: "100 kcal" },
            { tag: "grams under ten to one decimal", key: "carbsG", value: 4.25, text: "4.3 g" },
            { tag: "grams of ten or more whole", key: "proteinG", value: 23.6, text: "24 g" },
            { tag: "grams that round to ten are whole", key: "fatG", value: 9.96, text: "10 g" },
            { tag: "sodium in whole mg", key: "sodiumMg", value: 812.2, text: "812 mg" }
        ]
    }

    function test_format(row) {
        compare(Nutrition.valueText(row.key, row.value), row.text)
    }

    function test_isEstimate() {
        compare(Nutrition.isEstimate(full), true)
        compare(Nutrition.isEstimate({ calories: 1, from: "source" }), false)
        compare(Nutrition.isEstimate(null), false)
    }
}
