// The credit line under a recipe: who it is from, its licence and a link to the source, as the sources require.
// It is shown as StyledText, and its words come from the catalog (a Wikibooks page name can hold "&" or "<"), so
// they are escaped and read literally. Table-tested in tests/qml/tst_credit.qml.
import * as Words from "./words.mjs"

export function escapeStyled(text) {
    if (text === null || text === undefined)
        return ""
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
}

// Every source's credit already names its licence ("…, CC BY-SA 4.0", "…TheMealDB"), so the licence is added
// only when the credit does not say it.
export function creditLine(credit, licence, sourceUrl) {
    const parts = []
    if (credit)
        parts.push(escapeStyled(credit))
    if (licence && !(credit && String(credit).toLowerCase().includes(String(licence).toLowerCase())))
        parts.push(escapeStyled(licence))
    if (sourceUrl)
        parts.push('<a href="' + String(sourceUrl).replace(/"/g, "%22") + '">' + Words.creditSource + "</a>")
    return parts.join(" · ")
}
