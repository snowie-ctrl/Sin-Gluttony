import QtQuick
import QtTest
import "../../qml/logic/scale.mjs" as Scale

TestCase {
    name: "Scale"

    function test_theChosenServingsOverTheStated() {
        compare(Scale.factor(4, 2, 1), 0.5)
        compare(Scale.factor(4, 6, 1), 1.5)
        compare(Scale.factor(2, 2, 3), 1)
    }

    function test_withoutStatedServingsTheMultiplierDecides() {
        compare(Scale.factor(0, 0, 2), 2)
        compare(Scale.factor(null, 0, 0.5), 0.5)
        compare(Scale.factor(null, 0, 0), 1)
    }

    function test_rangesScaleAtBothEndsAndToTasteStays() {
        compare(Scale.scaled({ quantity: 2, quantityMax: 3 }, 2), { quantity: 4, quantityMax: 6 })
        compare(Scale.scaled({ quantity: null, quantityMax: null }, 2), { quantity: null, quantityMax: null })
        compare(Scale.scaled({ quantity: 1.5 }, 0.5), { quantity: 0.75, quantityMax: null })
    }

    function test_theMultipliersOnOffer() {
        compare(Scale.MULTIPLIERS, [0.5, 1, 2, 3])
    }
}
