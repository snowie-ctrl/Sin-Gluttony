// Home's moods: each is a name and the filters Browse opens with. A fixed list; the words are in words.mjs.
import * as Words from "./words.mjs"

export const MOODS = [
    { key: "quick", filters: { kind: "food", maxMinutes: 30, difficulty: [1] } },
    { key: "crowd", filters: { occasion: ["party"] } },
    { key: "sweet", filters: { course: ["dessert"] } },
    { key: "drinks", filters: { kind: "drink" } }
].map(m => ({ key: m.key, title: Words.MOOD_WORDS[m.key].title, hint: Words.MOOD_WORDS[m.key].hint, filters: m.filters }))

export function mood(key) {
    return MOODS.find(m => m.key === key) || null
}
