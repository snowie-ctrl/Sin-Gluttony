import QtQuick
import QtTest
import "../../qml/logic/credit.mjs" as Credit

TestCase {
    name: "Credit"

    function test_escapeStyled_data() {
        return [
            { tag: "plain", text: "Coq au Vin", escaped: "Coq au Vin" },
            { tag: "markup", text: "Fish & Chips <b>", escaped: "Fish &amp; Chips &lt;b&gt;" },
            { tag: "quote", text: 'Say "cheese"', escaped: "Say &quot;cheese&quot;" },
            { tag: "entity", text: "&amp;", escaped: "&amp;amp;" },
            { tag: "nothing", text: null, escaped: "" }
        ]
    }

    function test_escapeStyled(row) {
        compare(Credit.escapeStyled(row.text), row.escaped)
    }

    function test_creditLine_data() {
        return [
            { tag: "the licence is already in the credit",
              credit: "Wikibooks Cookbook, by its contributors, CC BY-SA 4.0", licence: "CC BY-SA 4.0", url: null,
              line: "Wikibooks Cookbook, by its contributors, CC BY-SA 4.0" },
            { tag: "case does not matter",
              credit: "Recipe data and imagery: TheMealDB", licence: "themealdb", url: null,
              line: "Recipe data and imagery: TheMealDB" },
            { tag: "a licence the credit does not name",
              credit: "Cookbook:Stew", licence: "CC BY-SA 4.0", url: null, line: "Cookbook:Stew · CC BY-SA 4.0" },
            { tag: "a page name with markup reads literally",
              credit: "Cookbook:Fish & Chips <b>", licence: "CC BY-SA 4.0", url: null,
              line: "Cookbook:Fish &amp; Chips &lt;b&gt; · CC BY-SA 4.0" },
            { tag: "the source link follows",
              credit: "Cookbook:Stew", licence: null, url: "https://en.wikibooks.org/wiki/Cookbook:Stew",
              line: 'Cookbook:Stew · <a href="https://en.wikibooks.org/wiki/Cookbook:Stew">Source</a>' },
            { tag: "only a link",
              credit: null, licence: null, url: 'https://example.org/"x"',
              line: '<a href="https://example.org/%22x%22">Source</a>' }
        ]
    }

    function test_creditLine(row) {
        compare(Credit.creditLine(row.credit, row.licence, row.url), row.line)
    }
}
