// Metric and US amounts for a recipe's ingredient lines, and the other temperature scale in its steps. Pure
// functions, table-tested in tests/qml/tst_units.qml. Volume never becomes weight: that would need each
// ingredient's density. Unit names are the catalog's (scraper/rules/units.json).
import * as Scale from "./scale.mjs"
import * as Words from "./words.mjs"

const MASS = { mg: 0.001, g: 1, kg: 1000, oz: 28.349523125, lb: 453.59237 }
const VOLUME = { ml: 1, cl: 10, dl: 100, l: 1000, tsp: 4.92892, tbsp: 14.7868, "fl oz": 29.5735, cup: 236.588,
                 pint: 473.176, quart: 946.353, gallon: 3785.41 }
const METRIC = ["mg", "g", "kg", "ml", "cl", "dl", "l"]
// Teaspoons and tablespoons are kitchen spoons in both systems, so they are never converted.
const SPOONS = ["tsp", "tbsp"]
// Written as they are, never with an s.
const SYMBOLS = ["mg", "g", "kg", "ml", "cl", "dl", "l", "tsp", "tbsp", "oz", "fl oz", "lb"]
const PLURALS = { pinch: "pinches", dash: "dashes", splash: "splashes", bunch: "bunches" }
const FRACTIONS = [[0, ""], [1 / 8, "⅛"], [1 / 4, "¼"], [1 / 3, "⅓"], [1 / 2, "½"], [2 / 3, "⅔"], [3 / 4, "¾"], [1, ""]]
// Every unit name and spelling the catalog knows, longest first, to find where a line's amount ends.
const UNIT_WORDS = [
    "cup", "cups", "tbsp", "tablespoon", "tablespoons", "tbs", "tbl", "tblsp", "tbsps", "tsp", "teaspoon", "teaspoons",
    "tsps", "g", "gram", "grams", "gr", "grammes", "kg", "kilogram", "kilograms", "kilo", "kilos", "mg", "milligram",
    "milligrams", "ml", "millilitre", "millilitres", "milliliter", "milliliters", "mls", "cl", "centilitre",
    "centilitres", "centiliter", "centiliters", "dl", "decilitre", "decilitres", "deciliter", "deciliters", "l",
    "litre", "litres", "liter", "liters", "oz", "ounce", "ounces", "fl oz", "fluid ounce", "fluid ounces", "fl. oz",
    "floz", "lb", "lbs", "pound", "pounds", "pint", "pints", "pt", "quart", "quarts", "qt", "gallon", "gallons", "gal",
    "pinch", "pinches", "dash", "dashes", "splash", "splashes", "drop", "drops", "shot", "shots", "jigger", "jiggers",
    "part", "parts", "clove", "cloves", "can", "cans", "tin", "tins", "jar", "jars", "package", "packages", "packet",
    "packets", "pkg", "slice", "slices", "piece", "pieces", "handful", "handfuls", "bunch", "bunches", "sprig",
    "sprigs", "stick", "sticks", "stalk", "stalks", "head", "heads", "knob", "knobs", "sheet", "sheets", "bottle",
    "bottles", "scoop", "scoops", "wedge", "wedges", "twist", "twists"
].sort((a, b) => b.length - a.length)

// A unit that is a package: the parenthesis after it is the package's size ("1 can (14 ounces)"), which scaling
// leaves true.
const CONTAINERS = ["can", "cans", "tin", "tins", "jar", "jars", "package", "packages", "packet", "packets", "pack",
                    "packs", "pkg", "bottle", "bottles", "box", "boxes", "bag", "bags", "carton", "cartons"]
// A parenthesis that gives an amount of its own: a number, then a unit ("(240 ml)", "(10 ½ cups)").
const ALTERNATE_AMOUNT = new RegExp(String.raw`^\([^)]*[\d½⅓⅔¼¾⅛⅜⅝⅞]\s*(?:`
                                    + UNIT_WORDS.map(word => word.replace(/\./g, String.raw`\.`)).join("|")
                                    + String.raw`)\b[^)]*\)\s*`, "i")

function inUnit(amount, by, unit) {
    const times = value => (value === null || value === undefined) ? null : value * by
    return { quantity: times(amount.quantity), quantityMax: times(amount.quantityMax), unit: unit }
}

// An amount in the chosen system. Spoons, counts and units with no conversion keep their unit.
export function convert(amount, unit, system, kind) {
    const same = inUnit(amount, 1, unit || null)
    if (amount.quantity === null || amount.quantity === undefined || !unit || SPOONS.includes(unit))
        return same
    const metric = METRIC.includes(unit)
    if (unit in MASS) {
        const grams = amount.quantity * MASS[unit]
        if (system === "metric") {
            if (grams >= 1000)
                return inUnit(amount, MASS[unit] / 1000, "kg")
            return grams < 1 ? inUnit(amount, MASS[unit] / 0.001, "mg") : inUnit(amount, MASS[unit], "g")
        }
        if (!metric)
            return same
        return grams / MASS.oz >= 16 ? inUnit(amount, MASS[unit] / MASS.lb, "lb") : inUnit(amount, MASS[unit] / MASS.oz, "oz")
    }
    if (unit in VOLUME) {
        const ml = amount.quantity * VOLUME[unit]
        if (system === "metric")
            return ml >= 1000 ? inUnit(amount, VOLUME[unit] / 1000, "l") : inUnit(amount, VOLUME[unit], "ml")
        if (!metric)
            return same
        if (ml < 15)
            return inUnit(amount, VOLUME[unit] / VOLUME.tsp, "tsp")
        if (kind === "drink")
            return inUnit(amount, VOLUME[unit] / VOLUME["fl oz"], "fl oz")
        return ml < 59 ? inUnit(amount, VOLUME[unit] / VOLUME.tbsp, "tbsp") : inUnit(amount, VOLUME[unit] / VOLUME.cup, "cup")
    }
    return same
}

// The nearest kitchen amount to a value: a whole number and one of ⅛ ¼ ⅓ ½ ⅔ ¾, or nothing at all. Something,
// however little, never rounds down to nothing.
function nearestKitchen(value) {
    let whole = Math.floor(value)
    let best = FRACTIONS[0]
    for (const candidate of FRACTIONS)
        if (Math.abs(value - whole - candidate[0]) < Math.abs(value - whole - best[0]))
            best = candidate
    if (best[0] === 1) {
        whole += 1
        best = FRACTIONS[0]
    }
    if (whole === 0 && best[1] === "")
        best = FRACTIONS[1]
    return { whole: whole, part: best }
}

// A kitchen amount: a whole number and the nearest of ⅛ ¼ ⅓ ½ ⅔ ¾. Something, however little, never reads as nothing.
export function fraction(value) {
    if (!(value > 0))
        return "0"
    const kitchen = nearestKitchen(value)
    return (kitchen.whole > 0 ? String(kitchen.whole) : "") + kitchen.part[1]
}

export function format(value, unit) {
    if (value === null || value === undefined)
        return ""
    if (!METRIC.includes(unit))
        return fraction(value)
    if (unit === "kg" || unit === "l")
        return String(Math.round(value * 100) / 100)
    if (value >= 100)
        return String(Math.round(value / 5) * 5)
    if (value >= 10)
        return String(Math.round(value))
    return String(Math.round(value * 10) / 10)
}

// The unit as it reads next to an amount. It is plural by the amount as shown, not as computed: 1.04 cups is
// shown as "1", so it reads "1 cup".
export function unitLabel(unit, value) {
    if (!unit)
        return ""
    if (SYMBOLS.includes(unit) || !(value > 0))
        return unit
    const kitchen = nearestKitchen(value)
    return kitchen.whole + kitchen.part[0] > 1 ? PLURALS[unit] || unit + "s" : unit
}

// The amount for a line, scaled and in the chosen system ("1⅛ cups", "4–6 cloves", "2"); "" for a line without one.
export function amountText(ingredient, by, system, kind) {
    if (ingredient.quantity === null || ingredient.quantity === undefined)
        return ""
    const converted = convert(Scale.scaled(ingredient, by), ingredient.unit, system, kind)
    const hasTop = converted.quantityMax !== null && converted.quantityMax !== undefined
    let text = format(converted.quantity, converted.unit)
    if (hasTop)
        text += "–" + format(converted.quantityMax, converted.unit)
    const label = unitLabel(converted.unit, hasTop ? converted.quantityMax : converted.quantity)
    return label ? text + " " + label : text
}

// One number of an amount ("1", "1.5", "1/2", "1½"), then a fraction that may follow it after a space ("1 ½",
// "1 1/2"). A second whole number is not part of the amount: in "1 9-inch pie shell" it is the size.
const NUMBER = String.raw`[\d½⅓⅔¼¾⅛⅜⅝⅞][\d.,/½⅓⅔¼¾⅛⅜⅝⅞]*(?:\s+(?:[½⅓⅔¼¾⅛⅜⅝⅞]|\d+/\d+))?`
const AMOUNT = new RegExp(String.raw`^(?:about\s+|approx\.?\s+)?` + NUMBER
                          + String.raw`(?:\s*(?:–|-|to)\s*(?=[\d½⅓⅔¼¾⅛⅜⅝⅞])` + NUMBER + String.raw`)?\s*`, "i")

// What follows a line's amount and unit ("1.5kg chicken thighs" → "chicken thighs"), or null when the line does
// not start with its amount ("Juice of 1 lemon").
export function restOf(line) {
    const text = (line || "").trim()
    const amount = text.match(AMOUNT)
    if (!amount)
        return null
    let rest = text.slice(amount[0].length)
    const lower = rest.toLowerCase()
    for (const word of UNIT_WORDS) {
        if (lower.startsWith(word) && !/[a-z]/.test(lower.charAt(word.length))) {
            rest = rest.slice(word.length)
            break
        }
    }
    return rest.replace(/^\.?\s*(?:of\s+)?/i, "").trim()
}

// A line as the recipe page shows it: as written while nothing changes it, otherwise the new amount and the rest
// of the line. A line whose amount is not at its start keeps its words and says the factor.
export function lineText(ingredient, by, system, kind) {
    if (ingredient.quantity === null || ingredient.quantity === undefined)
        return ingredient.line
    const converted = convert(ingredient, ingredient.unit, system, kind)
    if (Math.abs(by - 1) < 1e-9 && converted.unit === (ingredient.unit || null))
        return ingredient.line
    const rest = restOf(ingredient.line)
    if (rest === null)
        return ingredient.line + " (×" + fraction(by) + ")"
    const amount = amountText(ingredient, by, system, kind)
    // The line's own second amount ("1 cup (240 ml)") no longer matches the one shown, so it goes, unless it is a
    // package size.
    const alternate = rest.match(ALTERNATE_AMOUNT)
    const isPackage = CONTAINERS.includes(ingredient.unit)
        || (alternate && CONTAINERS.includes(rest.slice(alternate[0].length).split(/[\s,]/)[0].toLowerCase()))
    const dropped = alternate && !isPackage
    const kept = dropped ? rest.slice(alternate[0].length) : rest
    if (kept) {
        // What follows the unit may start with a comma ("1 cup, plus more"), or may once the bracket has gone
        // ("1 cup (240 ml), plus more"): either way it sits against the amount.
        const text = amount + (/^[,;]/.test(kept) ? "" : " ") + kept
        return dropped ? text.replace(/\s+([,;])/g, "$1") : text
    }
    return ingredient.name ? amount + " " + ingredient.name : amount
}

// A line with its "(optional)" marker, unless the line already says it is optional.
export function withOptional(text, optional) {
    return optional && !/\boptional\b/i.test(text) ? text + " (" + Words.optional + ")" : text
}

// "180°C" becomes "180°C (355°F)", and "350 F" becomes "350 F (175°C)", rounded to 5 degrees. A step that already
// gives both scales is left alone, whichever of the two comes first: "180°C (350°F)" and "350°F (180°C)".
export function withOtherScale(text) {
    return (text || "").replace(/(\d{2,3})\s*(?:°|º|degrees?\s*)\s*([CF])\b|(\d{3})\s?([CF])\b/g,
        (match, n1, s1, n2, s2, offset, whole) => {
            if (whole.slice(offset + match.length).replace(/^\s+/, "").startsWith("("))
                return match
            if (/\(\s*$/.test(whole.slice(0, offset)))
                return match
            const n = Number(n1 || n2)
            const celsius = (s1 || s2) === "C"
            const other = celsius ? Math.round((n * 9 / 5 + 32) / 5) * 5 : Math.round(((n - 32) * 5 / 9) / 5) * 5
            return match + " (" + other + "°" + (celsius ? "F" : "C") + ")"
        })
}
