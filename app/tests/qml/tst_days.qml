import QtQuick
import QtTest
import "../../qml/logic/days.mjs" as Days

TestCase {
    name: "Days"

    function test_daysNeverShiftAcrossMonthsOrClockChanges() {
        // Month and year ends, a leap day, and the nights European and American clocks change.
        compare(Days.addDays("2026-10-31", 1), "2026-11-01")
        compare(Days.addDays("2026-03-01", -1), "2026-02-28")
        compare(Days.addDays("2028-03-01", -1), "2028-02-29")
        compare(Days.addDays("2026-12-31", 1), "2027-01-01")
        compare(Days.addDays("2026-03-29", 1), "2026-03-30")
        compare(Days.addDays("2026-11-01", 1), "2026-11-02")
        compare(Days.addDays("2026-10-28", -30), "2026-09-28")
    }

    function test_onlyRealDaysAreDays() {
        verify(Days.isDay("2026-10-28"))
        verify(Days.isDay("2028-02-29"))
        verify(!Days.isDay("2026-02-29"))
        verify(!Days.isDay("2026-13-01"))
        verify(!Days.isDay("28/10/2026"))
        verify(!Days.isDay(""))
        verify(!Days.isDay(undefined))
        compare(Days.addDays("nonsense", 1), "")
    }

    function test_aDayReadsAsAPersonSaysIt() {
        compare(Days.label("2026-10-28", "2026-10-28"), "today")
        compare(Days.label("2026-10-27", "2026-10-28"), "yesterday")
        compare(Days.label("2026-03-01", "2026-03-02"), "yesterday")
        compare(Days.label("2026-10-03", "2026-10-28"), "3 Oct")
        compare(Days.label("2025-12-24", "2026-10-28"), "24 Dec 2025")
        compare(Days.label("", "2026-10-28"), "")
    }
}
