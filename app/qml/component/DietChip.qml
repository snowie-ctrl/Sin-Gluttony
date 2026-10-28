import QtQuick
import "../logic/words.mjs" as Words

// The saved diet, shown wherever results follow it. Clicking it switches the diet off for now, and on again; Edit
// opens the editor. With no profile it offers to set one.
Row {
    id: root

    spacing: Preferences.spacingSmall

    Chip {
        objectName: "dietChip"
        visible: Diet.hasProfile
        outlined: Diet.enabled
        text: (Diet.enabled ? "✓ " : "") + Words.dietChip(Diet.diets, Diet.avoid)
              + (Diet.enabled ? "" : " · " + Words.dietOffForNow)
        onClicked: Diet.enabled = !Diet.enabled
    }

    Chip {
        objectName: "dietEdit"
        text: Diet.hasProfile ? Words.dietEdit : Words.dietTitle + " +"
        onClicked: editor.open()
    }

    DietPopup { id: editor }
}
