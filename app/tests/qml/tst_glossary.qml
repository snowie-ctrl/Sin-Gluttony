import QtQuick
import QtTest
import "../../qml/logic/glossary.mjs" as Glossary

TestCase {
    name: "Glossary"

    readonly property var glossary: [
        { term: "fold", forms: ["fold", "folds", "folded", "folding"], kind: "technique", text: "Scoop gently." },
        { term: "blind bake", forms: ["blind bake", "blind baked", "baked blind"], kind: "technique", text: "Empty case." },
        { term: "caster sugar", forms: ["caster sugar"], kind: "word", text: "Fine sugar.", same: "superfine sugar" },
        { term: "hob", forms: ["hob"], kind: "word", text: "The rings on top." },
        { term: "bake", forms: ["bake", "baked"], kind: "technique", text: "A stop word: never shown." }
    ]

    // [shown text, term] per mark, so the tables read plainly.
    function marked(text) {
        return Glossary.marks(text, glossary).map(m => [text.slice(m.start, m.end), m.term])
    }

    function test_marks_data() {
        return [
            { tag: "whole words only", text: "Unfold the hobnob, then fold.", want: [["fold", "fold"]] },
            { tag: "the longest form wins", text: "Blind bake the case.", want: [["Blind bake", "blind bake"]] },
            { tag: "longest wins later in the line", text: "Line the tin, then baked blind.", want: [["baked blind", "blind bake"]] },
            { tag: "first occurrence per step", text: "Fold in half, then keep folding.", want: [["Fold", "fold"]] },
            { tag: "forms and case", text: "FOLDED with Caster Sugar on the HOB",
              want: [["FOLDED", "fold"], ["Caster Sugar", "caster sugar"], ["HOB", "hob"]] },
            { tag: "stop list", text: "Bake for 20 minutes until baked.", want: [] },
            { tag: "punctuation is an edge", text: "(fold), hob.", want: [["fold", "fold"], ["hob", "hob"]] },
            { tag: "digits are part of a word", text: "hob2 and 2fold", want: [] },
            { tag: "a lowercase that changes length", text: "İ fold", want: [["fold", "fold"]] },
            { tag: "accented letters are part of a word", text: "foldé, then fold", want: [["fold", "fold"]] }
        ]
    }

    function test_marks(data) {
        compare(marked(data.text), data.want)
    }

    function test_noGlossaryOrNoTextMarksNothing() {
        compare(Glossary.marks("Fold it.", undefined), [])
        compare(Glossary.marks("Fold it.", []), [])
        compare(Glossary.marks("", glossary), [])
        compare(Glossary.marks(undefined, glossary), [])
    }

    function test_theStopListHasTheEverydayWords() {
        for (const word of ["bake", "mix", "stir", "cook", "chop"])
            verify(Glossary.STOP.indexOf(word) >= 0, word)
    }

    function test_aMarkCarriesTheEntrysWords() {
        compare(Glossary.marks("Add caster sugar.", glossary),
                [{ start: 4, end: 16, term: "caster sugar", text: "Fine sugar.", same: "superfine sugar" }])
        compare(Glossary.marks("On the hob.", glossary)[0].same, "")
    }

    function test_theGlossaryMayComeAsJsonText() {
        const json = JSON.stringify(glossary)
        compare(Glossary.marks("Fold it on the hob.", json).map(m => m.term), ["fold", "hob"])
        compare(Glossary.marks("Fold it.", "not json"), [])
        compare(Glossary.marks("Fold it.", "{}"), [])
        compare(Glossary.marks("Fold it.", json).length, 1)   // the earlier text is parsed again after a bad one
    }
}
