// Which ingredient lines a step mentions, so cook mode can light them. A line is named by its ingredient's name (the
// catalog's; for an unknown ingredient, the line's words after its amount and unit, up to a comma, a bracket or an
// "or"). A step mentions the line when it holds that whole name, or the name's last word, as whole words, singular
// or plural: "chicken thigh" lights for "chicken thighs" and for "thighs", never for plain "chicken" (the owner's
// rule, 2026-10-29: a wrong line never lights). Pure functions, table-tested in tests/qml/tst_stepingredients.qml.
import * as Units from "./units.mjs"

// A last word shorter than this ("ea", "of") names nothing on its own.
const SHORTEST = 3

export function nameOf(ingredient) {
    if (ingredient && ingredient.name)
        return String(ingredient.name).toLowerCase().replace(/\s+/g, " ").trim()
    const line = String((ingredient && ingredient.line) || "")
    const rest = Units.restOf(line)
    let text = (rest === null ? line : rest).toLowerCase()
    text = text.split(/[,(;]/)[0].split(/\s+or\s+/)[0]
    return text.replace(/[^a-zÀ-ɏ'\s-]/g, " ").replace(/\s+/g, " ").trim()
}

// A word and its other number: "thigh" and "thighs", "tomato" and "tomatoes", "berry" and "berries", "eggs" and "egg".
function forms(word) {
    if (word.endsWith("ies"))
        return [word, word.slice(0, -3) + "y"]
    if (word.endsWith("es"))
        return [word, word.slice(0, -2), word.slice(0, -1)]
    if (word.endsWith("s"))
        return [word, word.slice(0, -1)]
    if (word.endsWith("y"))
        return [word, word.slice(0, -1) + "ies", word + "s"]
    return [word, word + "s", word + "es"]
}

function escaped(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

// The words as written, the last in any of its forms, standing alone (not inside a longer word).
function pattern(words) {
    const last = forms(words[words.length - 1]).map(escaped).join("|")
    const head = words.slice(0, -1).map(escaped).join("\\s+")
    return new RegExp("(?:^|[^a-zÀ-ɏ])" + (head ? head + "\\s+" : "") + "(?:" + last + ")(?![a-zÀ-ɏ])")
}

// The indices of the lines a step mentions, in the recipe's order.
export function mentioned(stepText, ingredients) {
    const text = String(stepText || "").toLowerCase()
    const lit = []
    if (!text)
        return lit
    for (let i = 0; i < (ingredients || []).length; ++i) {
        const words = nameOf(ingredients[i]).split(" ").filter(Boolean)
        if (!words.length)
            continue
        const last = words[words.length - 1]
        const whole = (words.length > 1 || last.length >= SHORTEST) && pattern(words).test(text)
        const tail = last.length >= SHORTEST && pattern([last]).test(text)
        if (whole || tail)
            lit.push(i)
    }
    return lit
}
