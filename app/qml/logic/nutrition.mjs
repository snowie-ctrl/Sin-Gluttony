// A recipe's nutrition per serving, as the recipe page shows it: the main four (calories, protein, carbs, fat) and
// the rest under More. The values are per serving, so they never follow the servings chosen. A value the recipe
// does not have is left out. Calories are whole kcal; grams have one decimal under 10 and are whole from 10 up;
// sodium is whole mg. Table-tested in tests/qml/tst_nutrition.qml.
import * as Words from "./words.mjs"

const MAIN = ["calories", "proteinG", "carbsG", "fatG"]
const MORE = ["satFatG", "fibreG", "sugarG", "sodiumMg"]

export function valueText(key, value) {
    if (key === "calories")
        return Math.round(value) + " kcal"
    if (key === "sodiumMg")
        return Math.round(value) + " mg"
    const tenth = Math.round(value * 10) / 10
    return (tenth >= 10 ? String(Math.round(value)) : tenth.toFixed(1)) + " g"
}

function rowsOf(n, keys) {
    if (!n)
        return []
    return keys.filter(key => typeof n[key] === "number")
               .map(key => ({ key: key, label: Words.NUTRIENTS[key], value: valueText(key, n[key]) }))
}

export function mainRows(n) {
    return rowsOf(n, MAIN)
}

export function moreRows(n) {
    return rowsOf(n, MORE)
}

// Worked out from the ingredients rather than given by the recipe's own site.
export function isEstimate(n) {
    return !!n && n.from === "estimate"
}
