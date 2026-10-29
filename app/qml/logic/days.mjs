// Days as the app holds them: "YYYY-MM-DD" in the person's own calendar (the server stores the same). A day is
// never handed to `new Date(text)`, which reads it as midnight UTC and shows the day before anywhere west of
// Greenwich; every sum here is done on the parts, in UTC, where no clock ever changes.
import * as Words from "./words.mjs"

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/

function pad(n) {
    return (n < 10 ? "0" : "") + n
}

function parts(iso) {
    const match = DAY.exec(typeof iso === "string" ? iso : "")
    return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null
}

function isoOf(ms) {
    const d = new Date(ms)
    return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate())
}

// A real calendar day: "2026-02-29" is not one.
export function isDay(iso) {
    const p = parts(iso)
    return p !== null && isoOf(Date.UTC(p[0], p[1] - 1, p[2])) === iso
}

export function addDays(iso, n) {
    if (!isDay(iso))
        return ""
    const p = parts(iso)
    return isoOf(Date.UTC(p[0], p[1] - 1, p[2] + n))
}

// "today", "yesterday", "3 Oct", or "24 Dec 2025" for another year.
export function label(iso, today) {
    if (!isDay(iso))
        return ""
    if (iso === today)
        return Words.today
    if (iso === addDays(today, -1))
        return Words.yesterday
    const p = parts(iso)
    const shown = parts(today)
    return p[2] + " " + Words.MONTHS[p[1] - 1] + (shown && shown[0] === p[0] ? "" : " " + p[0])
}
