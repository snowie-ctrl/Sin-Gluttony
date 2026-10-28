// Small helpers for the filter panel's ticks.
export const FOOD_COURSES = ["breakfast", "starter", "main", "side", "dessert", "snack", "bread", "sauce"]
export const DRINK_COURSES = ["cocktail", "mocktail", "shot", "coffee/tea", "shake", "punch"]

// Whether a list filter holds a value. Values compare as text, so 2 and "2" are one difficulty.
export function contains(list, value) {
    return (list || []).some(item => String(item) === String(value))
}

// The course options (from /filters) that belong to the kind chosen: food's, drink's, or all of them.
export function courseOptions(kind, options) {
    const all = (options && options.courses) || []
    if (kind === "food")
        return all.filter(o => FOOD_COURSES.includes(o.value))
    if (kind === "drink")
        return all.filter(o => DRINK_COURSES.includes(o.value))
    return all
}

// How many filters narrow the results, for the collapsed panel's button. A search is the page's title, not a
// filter, and the sort narrows nothing.
export function activeCount(filters) {
    let n = 0
    for (const key in filters) {
        if (key === "sort" || key === "q")
            continue
        const value = filters[key]
        // A list that came out of a QVariantMap is not always a true Array, so a list is whatever has a length and
        // is not text.
        const isList = typeof value === "object" && value !== null && typeof value.length === "number"
        if (isList ? value.length > 0 : (value !== "" && value !== 0 && value !== null && value !== undefined))
            n += 1
    }
    return n
}
