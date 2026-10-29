import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words

// A list's title: a new list, or a new name for one. It closes once the server has it, and stays open with the
// server's words when it refuses (the fiftieth list, a title it will not take).
Popup {
    id: popup

    // "create" or "rename".
    property string mode: "create"
    property int listId: 0
    property string error: ""

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: 420
    modal: true
    padding: Preferences.spacingLarge

    onAboutToShow: {
        popup.error = ""
        field.text = popup.mode === "rename" ? Saved.listTitle(popup.listId) : ""
        field.forceActiveFocus()
    }

    Connections {
        target: Saved
        function onDone(what) { if (popup.opened && what === "list") popup.close() }
        function onFailed(what, message) { if (popup.opened && what === "list") popup.error = message }
    }

    function submit() {
        popup.error = ""
        if (popup.mode === "rename")
            Saved.renameList(popup.listId, field.text)
        else
            Saved.createList(field.text, 0)
    }

    background: Rectangle {
        color: Preferences.backgroundSecondary
        radius: Preferences.cornerRadius
        border.color: Preferences.borderColor
    }

    // The object name sits here, not on the Popup: a Popup is not an item, so only its content can be found.
    contentItem: Column {
        objectName: "titlePopup"
        spacing: Preferences.spacingSmall

        Text {
            text: popup.mode === "rename" ? Words.renameList : Words.newList
            color: Preferences.textPrimary
            font.family: Preferences.headingFont
            font.weight: Font.Black
            font.pixelSize: Preferences.fontSizeHeading
        }

        InputField {
            id: field
            objectName: "titleField"
            // The server takes 60 characters; Qt counts an emoji as two here, so this never lets more through.
            maximumLength: Saved.titleLimit
            // Enter is the Save button's click, so it keeps the button's guards (a request already on its way).
            onAccepted: if (save.enabled) save.clicked()
        }

        Text {
            objectName: "titleError"
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
                id: save
                objectName: "titleSave"
                primary: true
                text: popup.mode === "rename" ? Words.save : Words.create
                enabled: !Saved.busy && field.text.trim().length > 0
                onClicked: popup.submit()
            }
            ActionButton { text: Words.cancel; onClicked: popup.close() }
        }
    }
}
