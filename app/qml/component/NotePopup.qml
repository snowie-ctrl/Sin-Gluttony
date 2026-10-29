import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words

// ✎ Note: a private note on this recipe. The count is in characters as the server counts them (an emoji is one),
// and Save rests past the limit, so nothing the server would refuse is sent. An empty note deletes it. Save also
// rests while an earlier note for this recipe is still on its way, so two answers cannot cross.
Popup {
    id: popup

    property int recipeId: 0
    property string error: ""
    readonly property int length: Saved.noteLength(field.text)
    readonly property bool sending: Saved.noteSaving.indexOf(popup.recipeId) >= 0

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: 560
    modal: true
    padding: Preferences.spacingLarge

    onAboutToShow: {
        popup.error = ""
        field.text = Saved.mineId === popup.recipeId && Saved.mine.note ? Saved.mine.note : ""
    }

    Connections {
        target: Saved
        function onDone(what) { if (what === "note") popup.close() }
        function onFailed(what, message) { if (popup.opened && what === "note") popup.error = message }
    }

    background: Rectangle {
        color: Preferences.backgroundSecondary
        radius: Preferences.cornerRadius
        border.color: Preferences.borderColor
    }

    contentItem: Column {
        objectName: "notePopup"
        spacing: Preferences.spacingSmall

        Text {
            text: Words.noteTitle
            color: Preferences.textPrimary
            font.family: Preferences.headingFont
            font.weight: Font.Black
            font.pixelSize: Preferences.fontSizeHeading
        }
        Text {
            text: Words.noteHint
            color: Preferences.textMuted
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeCaption
        }

        ScrollView {
            width: parent.width
            height: 200
            TextArea {
                id: field
                objectName: "noteField"
                wrapMode: TextArea.Wrap
                color: Preferences.textPrimary
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
                background: Rectangle {
                    radius: Preferences.controlRadius
                    color: Preferences.backgroundTertiary
                    border.width: field.activeFocus ? 1 : 0
                    border.color: Preferences.accentColor
                }
            }
        }

        Text {
            objectName: "noteCount"
            text: Words.noteCount(popup.length, Saved.noteLimit)
            color: popup.length > Saved.noteLimit ? Preferences.dangerColor : Preferences.textMuted
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeCaption
        }

        Text {
            objectName: "noteError"
            visible: popup.error.length > 0
            width: parent.width
            wrapMode: Text.Wrap
            text: popup.error
            color: Preferences.dangerColor
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
        }

        Row {
            spacing: Preferences.spacingSmall
            ActionButton {
                objectName: "noteSave"
                primary: true
                text: Words.save
                enabled: popup.length <= Saved.noteLimit && !popup.sending
                onClicked: Saved.setNote(popup.recipeId, field.text)
            }
            ActionButton { text: Words.cancel; onClicked: popup.close() }
        }
    }
}
