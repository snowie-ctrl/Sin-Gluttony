import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words

// The diet editor: what this person eats and what they avoid. Saving replaces the profile on the server and
// switches it on; a refusal stays open and says why. Until the saved profile has been read, Save stays off: saving
// blind would replace a profile the editor never showed, and drop its avoids.
Popup {
    id: popup

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: 540
    modal: true
    padding: Preferences.spacingLarge

    property var chosenDiets: []
    property var chosenAvoid: []
    // Whether the choices hold the saved profile yet; a profile that loads while the editor is open fills them then.
    property bool filled: false

    function fill() {
        popup.chosenDiets = Array.from(Diet.diets)
        popup.chosenAvoid = Array.from(Diet.avoid)
        popup.filled = true
    }

    onAboutToShow: {
        Diet.clearError()
        popup.filled = false
        popup.chosenDiets = []
        popup.chosenAvoid = []
        if (Diet.loaded)
            popup.fill()
        else
            Diet.load()
    }

    function toggled(list, value) {
        const copy = list.slice()
        const at = copy.indexOf(value)
        if (at >= 0)
            copy.splice(at, 1)
        else
            copy.push(value)
        return copy
    }

    Connections {
        target: Diet
        function onSaved() { popup.close() }
        function onChanged() {
            if (popup.opened && !popup.filled && Diet.loaded)
                popup.fill()
        }
    }

    background: Rectangle {
        color: Preferences.backgroundSecondary
        radius: Preferences.cornerRadius
        border.color: Preferences.borderColor
    }

    // The object name sits here, not on the Popup: a Popup is not an item, so only its content can be found.
    contentItem: Column {
        objectName: "dietPopup"
        spacing: Preferences.spacingMedium

        Text {
            text: Words.dietTitle
            color: Preferences.accentColor
            font.family: Preferences.headingFont
            font.weight: Font.Black
            font.pixelSize: Preferences.fontSizeHeading + 4
        }

        Text {
            text: Words.dietDiets
            color: Preferences.textSecondary
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
        }
        Flow {
            width: parent.width
            spacing: 8
            Repeater {
                model: Words.DIETS
                delegate: Chip {
                    required property var modelData
                    objectName: "diet-" + modelData.value
                    text: modelData.label
                    selected: popup.chosenDiets.indexOf(modelData.value) >= 0
                    onClicked: popup.chosenDiets = popup.toggled(popup.chosenDiets, modelData.value)
                }
            }
        }

        Text {
            text: Words.dietAvoid
            color: Preferences.textSecondary
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
        }
        Flow {
            width: parent.width
            spacing: 8
            Repeater {
                model: Words.AVOID
                delegate: Chip {
                    required property var modelData
                    objectName: "avoid-" + modelData.value
                    text: modelData.label
                    selected: popup.chosenAvoid.indexOf(modelData.value) >= 0
                    onClicked: popup.chosenAvoid = popup.toggled(popup.chosenAvoid, modelData.value)
                }
            }
        }

        Column {
            objectName: "dietLoadFailed"
            visible: !Diet.loaded && Diet.error.length > 0
            width: parent.width
            spacing: Preferences.spacingSmall
            Text {
                width: parent.width
                text: Words.dietLoadFailed
                wrapMode: Text.Wrap
                color: Preferences.dangerColor
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }
            Text {
                width: parent.width
                text: Diet.error
                wrapMode: Text.Wrap
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeLabel
            }
            ActionButton { objectName: "dietLoadRetry"; text: Words.tryAgain; onClicked: Diet.load() }
        }

        Text {
            visible: Diet.loaded && Diet.error.length > 0
            width: parent.width
            text: Diet.error
            wrapMode: Text.Wrap
            color: Preferences.dangerColor
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
        }

        Row {
            spacing: Preferences.spacingSmall
            ActionButton {
                objectName: "dietSave"
                primary: true
                text: Words.dietSave
                enabled: Diet.loaded && !Diet.saving
                onClicked: Diet.save(popup.chosenDiets, popup.chosenAvoid)
            }
            ActionButton { text: Words.dietCancel; onClicked: popup.close() }
        }
    }
}
