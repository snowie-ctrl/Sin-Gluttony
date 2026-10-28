// What a recipe tile says under its picture. A time the rules guessed reads "about …".
import * as Words from "./words.mjs"

export function timeText(minutes, from) {
    if (!(minutes > 0))
        return ""
    let text
    if (minutes >= 1440) {
        const days = Math.round(minutes / 1440)
        text = days + (days === 1 ? " day" : " days")
    } else if (minutes >= 60) {
        const hours = Math.floor(minutes / 60), rest = minutes % 60
        text = rest ? hours + " h " + rest : hours + " h"
    } else {
        text = minutes + " min"
    }
    return from === "rule" ? Words.about + text : text
}

export function metaLine(tile) {
    return [timeText(tile.totalMinutes, tile.timeFrom), Words.effortWord(tile.difficulty)].filter(Boolean).join(" · ")
}

export function guessedTime(tile) {
    return tile.timeFrom === "rule"
}

// A recipe without a picture shows a plate or a glass on the art ground, never an empty box.
export function placeholderIcon(kind) {
    return kind === "drink" ? "qrc:/images/glass.svg" : "qrc:/images/plate.svg"
}
