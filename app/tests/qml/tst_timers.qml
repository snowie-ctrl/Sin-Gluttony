import QtQuick
import QtTest
import "../../qml/logic/timers.mjs" as Timers

TestCase {
    name: "Timers"

    function test_aStepsDurationIsItsTimer() {
        compare(Timers.timersIn("Pour in the wine, bring to a simmer, then cover and cook gently for 1 hour."),
                [{ seconds: 3600, text: "1 hour" }])
        compare(Timers.timersIn("Simmer 10 min, then rest for 5 minutes."),
                [{ seconds: 600, text: "10 min" }, { seconds: 300, text: "5 minutes" }])
        compare(Timers.timersIn("Roast for 1½ hours."), [{ seconds: 5400, text: "1½ hours" }])
        compare(Timers.timersIn("Roast for 1 1/2 hours."), [{ seconds: 5400, text: "1 1/2 hours" }])
        compare(Timers.timersIn("Leave 2h."), [{ seconds: 7200, text: "2h" }])
        compare(Timers.timersIn("Cook for 2.5 mins"), [{ seconds: 150, text: "2.5 mins" }])
    }

    function test_aRangeTimesItsLowerEnd() {
        // The owner's choice: the chime says it is time to check, so nothing overcooks.
        compare(Timers.timersIn("Bake for 20–25 minutes, until golden."), [{ seconds: 1200, text: "20–25 minutes" }])
        compare(Timers.timersIn("Bake 20 to 25 mins"), [{ seconds: 1200, text: "20 to 25 mins" }])
        compare(Timers.timersIn("Rest 1-2 hours"), [{ seconds: 3600, text: "1-2 hours" }])
    }

    function test_storingAndMakingAheadAreNotTimers() {
        compare(Timers.timersIn("The sauce keeps for up to 3 days."), [])
        compare(Timers.timersIn("Chill for 2 hours (it can be made 2 days in advance)."), [{ seconds: 7200, text: "2 hours" }])
        compare(Timers.timersIn("Store in the fridge for 2 hours."), [])
    }

    function test_noTimerOverADayOrWithoutADuration() {
        compare(Timers.timersIn("Marinate for 2 days."), [])
        compare(Timers.timersIn("Season to taste."), [])
        compare(Timers.timersIn("Heat the oven to 180°C."), [])
        compare(Timers.timersIn(""), [])
        compare(Timers.timersIn(undefined), [])
    }

    function test_theSameDurationTwiceIsOneTimer() {
        compare(Timers.timersIn("Cook 5 minutes, turn, cook 5 minutes more."), [{ seconds: 300, text: "5 minutes" }])
    }

    function test_theClockReadsLikeAKitchenTimer() {
        compare(Timers.clock(0), "0:00")
        compare(Timers.clock(0.2), "0:01")
        compare(Timers.clock(59), "0:59")
        compare(Timers.clock(61), "1:01")
        compare(Timers.clock(1200), "20:00")
        compare(Timers.clock(3600), "1:00:00")
        compare(Timers.clock(5025), "1:23:45")
        compare(Timers.clock(-3), "0:00")
    }
}
