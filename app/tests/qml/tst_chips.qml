import QtQuick
import QtTest
import "../../qml/logic/chips.mjs" as Chips

TestCase {
    name: "Chips"

    function test_eachKindHasItsFamily() {
        for (const k of ["kind", "course", "cuisine", "occasion", "craving", "include"])
            compare(Chips.familyOf(k), "orange", k)
        compare(Chips.familyOf("flavour"), "rose")
        for (const k of ["time", "effort", "timer"])
            compare(Chips.familyOf(k), "amber", k)
        for (const k of ["diet", "avoid", "contains", "alcohol", "exclude"])
            compare(Chips.familyOf(k), "neutral", k)
    }

    function test_controlsAndUnknownKindsHaveNoFamily() {
        compare(Chips.familyOf(""), "")
        compare(Chips.familyOf("sort"), "")
        compare(Chips.familyOf(undefined), "")
    }

    function test_eachFamilyNamesAToken() {
        compare(Chips.toneKey("orange"), "accentColor")
        compare(Chips.toneKey("rose"), "accentRose")
        compare(Chips.toneKey("amber"), "accentAmber")
        compare(Chips.toneKey("neutral"), "textSecondary")
        compare(Chips.toneKey(""), "accentColor")
    }
}
