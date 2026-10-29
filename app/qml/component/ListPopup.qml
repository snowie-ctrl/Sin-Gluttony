import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words

// + List: the person's own lists, each ticked when this recipe is on it; a click puts it on or takes it off. A new
// list is made here too, with this recipe already on it. Cravings is the ♥ beside, so it is not listed.
Popup {
    id: popup

    property int recipeId: 0
    property string error: ""

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: 420
    modal: true
    padding: Preferences.spacingLarge

    readonly property var mineLists: Saved.mineId === popup.recipeId && Saved.mine.lists ? Saved.mine.lists : []
    readonly property var customLists: Saved.lists.filter(l => l.kind === "custom")

    function onList(listId) {
        for (let i = 0; i < popup.mineLists.length; ++i)
            if (Number(popup.mineLists[i]) === listId)
                return true
        return false
    }

    onAboutToShow: {
        popup.error = ""
        field.text = ""
        if (!Saved.listsLoaded)
            Saved.load()
    }

    Connections {
        target: Saved
        function onFailed(what, message) {
            if (popup.opened && (what === "list" || what === "item"))
                popup.error = message
        }
        function onListCreated(listId) { field.text = "" }
    }

    background: Rectangle {
        color: Preferences.backgroundSecondary
        radius: Preferences.cornerRadius
        border.color: Preferences.borderColor
    }

    // The object name sits here, not on the Popup: a Popup is not an item, so only its content can be found.
    contentItem: Column {
        id: body
        objectName: "listPopup"
        spacing: Preferences.spacingSmall

        Text {
            id: heading
            text: Words.yourLists
            color: Preferences.textPrimary
            font.family: Preferences.headingFont
            font.weight: Font.Black
            font.pixelSize: Preferences.fontSizeHeading
        }

        Text {
            visible: Saved.listsLoaded && popup.customLists.length === 0
            text: Words.noListsYet
            color: Preferences.textMuted
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeBody
        }

        // The lists scroll, so the heading, "New list" and its error stay in the window however many there are (the
        // server allows 50).
        Flickable {
            id: listScroll
            objectName: "listScroll"
            visible: popup.customLists.length > 0
            width: parent.width
            height: Math.min(contentHeight, Math.max(0, (popup.parent ? popup.parent.height : 0)
                                                        - 2 * popup.padding - 2 * Preferences.spacingLarge
                                                        - heading.height - newListRow.height
                                                        - (popupError.visible ? popupError.height + body.spacing : 0)
                                                        - 2 * body.spacing))
            contentWidth: width
            contentHeight: listFlow.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            Flow {
                id: listFlow
                width: listScroll.width
                spacing: Preferences.spacingSmall
                Repeater {
                    model: popup.customLists
                    delegate: Chip {
                        required property var modelData
                        objectName: "listRow-" + modelData.id
                        text: (popup.onList(modelData.id) ? "✓ " : "") + modelData.title
                        selected: popup.onList(modelData.id)
                        onClicked: Saved.setInList(modelData.id, popup.recipeId, !popup.onList(modelData.id))
                    }
                }
            }
        }

        Row {
            id: newListRow
            width: parent.width
            spacing: Preferences.spacingSmall
            InputField {
                id: field
                objectName: "newListField"
                width: parent.width - create.width - parent.spacing
                placeholderText: Words.newList
                // The server takes 60 characters; Qt counts an emoji as two here, so this never lets more through.
                maximumLength: Saved.titleLimit
                onAccepted: if (create.enabled) create.clicked()
            }
            ActionButton {
                id: create
                objectName: "newListCreate"
                text: Words.create
                enabled: Saved.canCreateList && !Saved.busy && field.text.trim().length > 0
                onClicked: Saved.createList(field.text, popup.recipeId)
            }
        }

        Text {
            id: popupError
            objectName: "listPopupError"
            visible: popup.error.length > 0
            width: parent.width
            wrapMode: Text.Wrap
            text: popup.error
            color: Preferences.dangerColor
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
        }
    }
}
