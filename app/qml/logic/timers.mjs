// Kitchen timers from a step's own words. The durations are read by part 1's rules (scraper/tagging.py's
// _DURATION and cookingText, scraper/quantity.py's NUMBER and toNumber): the same numbers, units and ranges, and a
// clause about storing the food or making it ahead is not cooking time. A range times its lower end (the owner's
// choice, 2026-10-29), so the chime says it is time to check; the chip shows the range as written. A duration over a
// day is planning, not a timer. Pure functions, table-tested in tests/qml/tst_timers.qml.
const FRACTIONS = { "½": 1 / 2, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 1 / 4, "¾": 3 / 4, "⅕": 1 / 5, "⅛": 1 / 8, "⅜": 3 / 8,
                    "⅝": 5 / 8, "⅞": 7 / 8 }
const FR = "½⅓⅔¼¾⅕⅛⅜⅝⅞"
const NUMBER = String.raw`(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?\s?[${FR}]?|[${FR}])`
const MINUTES = { minute: 1, minutes: 1, min: 1, mins: 1, hour: 60, hours: 60, hr: 60, hrs: 60, h: 60, day: 1440,
                  days: 1440 }
const DURATION = new RegExp(String.raw`(${NUMBER})(?:\s*(?:-|–|to)\s*(${NUMBER}))?\s*(minutes?|mins?|hours?|hrs?|h|days?)\b`,
                            "gi")
const DAYS = String.raw`(?:${NUMBER})\s*(?:days?|weeks?|months?)`
const STORAGE = new RegExp(String.raw`\b(?:keeps|will\s+keep|can\s+be\s+kept|stor(?:e|ed|es|ing|age)\b(?!-)|leftovers?`
                           + String.raw`|shelf\s+life|will\s+last|lasts|in\s+advance|ahead\s+of\s+time|make[-\s]ahead`
                           + String.raw`|can\s+be\s+(?:prepared|made)|(?:up\s+to|within|no\s+more\s+than)\s+${DAYS})`, "i")
// Part 1 splits after . ! ? ; , followed by space, and at brackets. It keeps the punctuation with the clause before;
// nothing here reads it, so it is split away.
const CLAUSE_END = /[.!?;,]\s+|[()]/
const LONGEST = 24 * 60 * 60

// "1", "1.5", "1,5", "1,000", "1/2", "1 1/2", "½", "1½" and "1 ½" as a number; null when it can't be one.
function toNumber(text) {
    let total = 0
    for (let part of text.trim().split(/\s+/)) {
        if (/^\d{1,3}(?:,\d{3})+$/.test(part))
            part = part.replace(/,/g, "")
        else
            part = part.replace(",", ".")
        const last = part.slice(-1)
        if (part in FRACTIONS) {
            total += FRACTIONS[part]
        } else if (last in FRACTIONS) {
            total += Number(part.slice(0, -1)) + FRACTIONS[last]
        } else if (part.includes("/")) {
            const halves = part.split("/")
            if (Number(halves[1]) === 0)
                return null
            total += Number(halves[0]) / Number(halves[1])
        } else {
            total += Number(part)
        }
    }
    return Number.isFinite(total) ? total : null
}

// Every timer a step offers, in the order written: {seconds, text}.
export function timersIn(text) {
    const found = []
    for (const clause of String(text || "").split(CLAUSE_END)) {
        if (!clause || STORAGE.test(clause))
            continue
        DURATION.lastIndex = 0
        let match
        while ((match = DURATION.exec(clause)) !== null) {
            const lower = toNumber(match[1])
            if (lower === null || !(lower > 0))
                continue
            const seconds = Math.round(lower * MINUTES[match[3].toLowerCase()] * 60)
            if (seconds > LONGEST)
                continue
            const written = match[0].replace(/\s+/g, " ").trim()
            if (!found.some(timer => timer.seconds === seconds && timer.text === written))
                found.push({ seconds: seconds, text: written })
        }
    }
    return found
}

// Time left as a kitchen timer shows it: "4:05", "1:00:00". Part of a second still counts as a second.
export function clock(seconds) {
    const total = Math.max(0, Math.ceil(seconds || 0))
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    const rest = total % 60
    const two = n => (n < 10 ? "0" : "") + n
    return hours > 0 ? hours + ":" + two(minutes) + ":" + two(rest) : minutes + ":" + two(rest)
}
