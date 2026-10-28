import QtQuick
import QtTest
import "../../qml/logic/moods.mjs" as Moods

TestCase {
    name: "Moods"

    function test_theFourMoodsAndTheirFilters() {
        compare(Moods.MOODS.map(m => m.title), ["Quick fix", "Feed a crowd", "Sweet tooth", "Bottoms up"])
        compare(Moods.mood("quick").filters, { kind: "food", maxMinutes: 30, difficulty: [1] })
        compare(Moods.mood("crowd").filters, { occasion: ["party"] })
        compare(Moods.mood("sweet").filters, { course: ["dessert"] })
        compare(Moods.mood("drinks").filters, { kind: "drink" })
        compare(Moods.mood("nope"), null)
    }
}
