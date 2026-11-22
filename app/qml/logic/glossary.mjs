// The glossary's marks (spec 2026-11-19 part 3, 3.2): which words of a step or ingredient line explain themselves
// on hover or tap. The terms ship in the app (assets/glossary.json, handed over as the GlossaryJson context property and parsed once per page), so
// this works offline. scraper/glossary.py finds the same words for the reports; keep the two in step.

// Everyday words never marked, whatever the glossary says. scraper/glossary.py's STOP is the same list.
export const STOP = [
    "add", "bake", "baked", "bakes", "baking", "boil", "boiled", "boiling", "chop", "chopped", "chopping",
    "cook", "cooked", "cooking", "cooks", "cut", "fry", "fried", "frying", "heat", "heated", "heating", "melt",
    "melted", "mix", "mixed", "mixes", "mixing", "pour", "poured", "serve", "served", "slice", "sliced", "stir",
    "stirred", "stirring", "stirs", "wash", "washed"
]

// A letter (any script with case) or a digit: what a whole word may not touch.
function isWordChar(c) {
    return /[0-9]/.test(c) || c.toLowerCase() !== c.toUpperCase()
}

// Lowercase one character at a time, so every index still points at the same character of the shown text.
function lower(text) {
    let out = ""
    for (let i = 0; i < text.length; ++i) {
        const c = text.charAt(i)
        const l = c.toLowerCase()
        out += l.length === 1 ? l : c
    }
    return out
}

// The glossary as the app hands it over: JSON text, parsed once per engine here and kept, so the pages hold only
// the small marks below rather than every entry.
let parsedText = null
let parsedList = []

function entries(glossary) {
    if (Array.isArray(glossary))
        return glossary
    if (typeof glossary !== "string" || !glossary)
        return []
    if (glossary !== parsedText) {
        parsedText = glossary
        try {
            const list = JSON.parse(glossary)
            parsedList = Array.isArray(list) ? list : []
        } catch (e) {
            parsedList = []
        }
    }
    return parsedList
}

// The spans of text to mark, in text order: [{start, end, term, text, same}], plain copies of the entry's words.
// Whole words only, case-insensitive; where forms overlap the longest wins ("blind bake" before "bake"); then only
// each term's first occurrence is kept. glossary is the list of entries, or that list as JSON text.
export function marks(text, glossary) {
    const list = entries(glossary)
    if (!text || !list.length)
        return []
    const low = lower(String(text))
    const found = []
    for (const entry of list) {
        if (!entry || STOP.indexOf(entry.term) >= 0)
            continue
        for (const form of entry.forms || []) {
            if (!form || STOP.indexOf(form) >= 0)
                continue
            for (let start = low.indexOf(form); start >= 0; start = low.indexOf(form, start + 1)) {
                const end = start + form.length
                if ((start === 0 || !isWordChar(low[start - 1])) && (end === low.length || !isWordChar(low[end])))
                    found.push({ start: start, end: end, entry: entry })
            }
        }
    }
    found.sort((a, b) => (b.end - b.start) - (a.end - a.start) || a.start - b.start)
    const kept = []
    for (const f of found)
        if (kept.every(k => f.end <= k.start || f.start >= k.end))
            kept.push(f)
    kept.sort((a, b) => a.start - b.start)
    const seen = {}
    return kept.filter(k => seen[k.entry.term] ? false : (seen[k.entry.term] = true))
               .map(k => ({ start: k.start, end: k.end, term: k.entry.term, text: k.entry.text || "",
                            same: k.entry.same || "" }))
}

// Whether some word's popup is pinned: then hovering another word shows nothing, so two never overlap. Only one is
// ever pinned, since a click anywhere else closes it.
let pinnedOpen = false
export function setPinned(on) { pinnedOpen = !!on }
export function anyPinned() { return pinnedOpen }
