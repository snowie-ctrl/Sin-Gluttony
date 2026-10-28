import QtQuick
import QtTest
import "../../qml/logic/tiles.mjs" as Tiles

TestCase {
    name: "Tiles"

    function test_timeText() {
        compare(Tiles.timeText(25, "source"), "25 min")
        compare(Tiles.timeText(105, "rule"), "about 1 h 45")
        compare(Tiles.timeText(120, "source"), "2 h")
        compare(Tiles.timeText(2880, "source"), "2 days")
        compare(Tiles.timeText(null, "rule"), "")
        compare(Tiles.timeText(0, "source"), "")
    }

    function test_metaLine() {
        compare(Tiles.metaLine({ totalMinutes: 15, timeFrom: "rule", difficulty: 1 }), "about 15 min · easy")
        compare(Tiles.metaLine({ totalMinutes: null, difficulty: 2 }), "medium")
        compare(Tiles.metaLine({}), "")
        verify(Tiles.guessedTime({ timeFrom: "rule" }))
        verify(!Tiles.guessedTime({ timeFrom: "source" }))
    }

    function test_placeholders() {
        compare(Tiles.placeholderIcon("drink"), "qrc:/images/glass.svg")
        compare(Tiles.placeholderIcon("food"), "qrc:/images/plate.svg")
        compare(Tiles.placeholderIcon(undefined), "qrc:/images/plate.svg")
    }
}
