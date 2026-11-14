// Chip families (look reset spec §3): a chip's colour comes from the filter kind it belongs to. Orange for what the
// dish is, rose for taste, amber for time and effort, neutral for diet and allergens so safety never reads as
// decoration. A chip with no kind (a control: Reset, a sort, Back) has no family and looks as it always did.
const FAMILIES = {
    kind: "orange", course: "orange", cuisine: "orange", occasion: "orange", craving: "orange", include: "orange",
    flavour: "rose",
    time: "amber", effort: "amber", timer: "amber",
    diet: "neutral", avoid: "neutral", contains: "neutral", alcohol: "neutral", exclude: "neutral"
}

const TONES = { orange: "accentColor", rose: "accentRose", amber: "accentAmber", neutral: "textSecondary" }

export function familyOf(kind) {
    return FAMILIES[kind] || ""
}

// The Preferences token a family is drawn in; a control chip uses the accent when selected, as before.
export function toneKey(family) {
    return TONES[family] || "accentColor"
}
