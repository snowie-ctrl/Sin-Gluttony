import QtQuick
import QtTest
import "../../qml/logic/filters.mjs" as Filters

TestCase {
    name: "Filters"

    function test_containsComparesAsText() {
        verify(Filters.contains([1, 2], "2"))
        verify(Filters.contains(["Thai"], "Thai"))
        verify(!Filters.contains(undefined, "x"))
    }

    function test_coursesFollowTheKind() {
        const options = { courses: [{ value: "main", count: 9 }, { value: "cocktail", count: 4 }] }
        compare(Filters.courseOptions("food", options).map(o => o.value), ["main"])
        compare(Filters.courseOptions("drink", options).map(o => o.value), ["cocktail"])
        compare(Filters.courseOptions("", options).length, 2)
        compare(Filters.courseOptions("food", {}).length, 0)
    }

    function test_activeCountCountsWhatNarrows() {
        compare(Filters.activeCount({ kind: "", maxMinutes: 0, course: [], include: [], q: "" }), 0)
        compare(Filters.activeCount({ kind: "food", maxMinutes: 30, course: ["main", "side"], include: [{ id: 1 }],
                                      q: "x" }), 4)
    }
}
