// Scaling a recipe's quantities to other servings. Pure functions, table-tested in tests/qml/tst_scale.qml.
// A recipe that states no servings offers these multipliers instead.
export const MULTIPLIERS = [0.5, 1, 2, 3]

// How much every quantity is multiplied by: the servings chosen over those stated, or the multiplier.
export function factor(stated, chosen, multiplier) {
    if (stated > 0 && chosen > 0)
        return chosen / stated
    return multiplier > 0 ? multiplier : 1
}

// A line's quantity and the top of its range, times `by`. A line without one ("salt to taste") stays as it is.
export function scaled(ingredient, by) {
    const times = value => (value === null || value === undefined) ? null : value * by
    return { quantity: times(ingredient.quantity), quantityMax: times(ingredient.quantityMax) }
}
