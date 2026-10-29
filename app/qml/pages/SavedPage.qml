import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/days.mjs" as Days

// Saved: a tab for Cravings, one for each of the person's lists, and one for Devoured. A list's recipes are
// moved by their grip (⠿) and taken off with a named button; the person's own lists are renamed, moved and deleted from their
// header. Devoured is every time something was made, newest first or by stars. The open tab lives in Saved, so
// the page comes back where it was left.
Item {
    id: root
    objectName: "savedPage"

    readonly property bool onDevoured: Saved.devouredOpen
    readonly property var query: root.onDevoured ? Saved.devouredHistory : Saved.listRecipes
    readonly property var openList: {
        for (let i = 0; i < Saved.lists.length; ++i)
            if (Saved.lists[i].id === Saved.openListId)
                return Saved.lists[i]
        return null
    }
    readonly property bool custom: !root.onDevoured && root.openList !== null && root.openList.kind === "custom"
    // The cell a held grip is over, outlined until the grip is let go.
    property int dropAt: -1
    property string pageError: ""

    // A list's tab opens once the lists are in. Signing in has already asked for them, so this waits a turn and
    // asks only for what is missing.
    function showTab() {
        if (Saved.devouredOpen)
            Saved.openDevoured(Saved.devouredSort)
        else if (Saved.openListId > 0)
            Saved.openList(Saved.openListId)
        else if (Saved.cravingsId > 0)
            Saved.openList(Saved.cravingsId)
    }

    Component.onCompleted: Qt.callLater(function() {
        if (!Saved.listsLoaded)
            Saved.load()
        root.showTab()
    })

    Connections {
        target: Saved
        function onListsChanged() {
            if (!Saved.devouredOpen && Saved.openListId <= 0 && Saved.cravingsId > 0)
                Saved.openList(Saved.cravingsId)
        }
        function onOpenListChanged() {
            if (!Saved.devouredOpen && Saved.openListId <= 0 && Saved.cravingsId > 0)
                Saved.openList(Saved.cravingsId)
        }
        function onFailed(what, message) {
            // A refused rename or new list is said in its own popup; a refused delete has no popup left to say it.
            if (what === "lists" || what === "move" || what === "item" || (what === "list" && !titlePopup.opened))
                root.pageError = message
        }
        function onDone(what) { root.pageError = "" }
    }

    TitlePopup { id: titlePopup }

    Popup {
        id: deletePopup
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 420
        modal: true
        padding: Preferences.spacingLarge
        background: Rectangle {
            color: Preferences.backgroundSecondary
            radius: Preferences.cornerRadius
            border.color: Preferences.borderColor
        }
        contentItem: Column {
            objectName: "deletePopup"
            spacing: Preferences.spacingSmall
            Text {
                width: parent.width
                wrapMode: Text.Wrap
                text: Words.deleteListQuestion(root.openList ? root.openList.title : "")
                color: Preferences.textPrimary
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeHeading
            }
            Text {
                text: Words.deleteListHint
                color: Preferences.textSecondary
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }
            Row {
                spacing: Preferences.spacingSmall
                ActionButton {
                    objectName: "deleteConfirm"
                    danger: true
                    text: Words.deleteListWord
                    onClicked: {
                        Saved.deleteList(Saved.openListId)
                        deletePopup.close()
                    }
                }
                ActionButton { text: Words.cancel; onClicked: deletePopup.close() }
            }
        }
    }

    Column {
        id: head
        x: Preferences.spacingLarge
        y: Preferences.spacingMedium
        width: root.width - 2 * Preferences.spacingLarge
        spacing: Preferences.spacingSmall

        // The tabs, then + New list; with 50 lists there is no room for another.
        Flow {
            width: parent.width
            spacing: Preferences.spacingSmall

            Repeater {
                model: Saved.lists
                delegate: Chip {
                    required property var modelData
                    objectName: "tab-" + modelData.id
                    text: Words.listTabTitle(modelData)
                    selected: !root.onDevoured && Saved.openListId === modelData.id
                    onClicked: Saved.openList(modelData.id)
                }
            }
            Chip {
                objectName: "tab-devoured"
                text: Words.devoured
                selected: root.onDevoured
                onClicked: Saved.openDevoured(Saved.devouredSort)
            }
            Chip {
                objectName: "newListTab"
                visible: Saved.canCreateList
                text: Words.newListPlus
                onClicked: {
                    titlePopup.mode = "create"
                    titlePopup.open()
                }
            }
            Text {
                objectName: "listLimitReached"
                visible: Saved.listsLoaded && !Saved.canCreateList
                height: 30
                verticalAlignment: Text.AlignVCenter
                text: Words.listLimitReached
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeCaption
            }
        }

        Item {
            width: parent.width
            height: 44

            Text {
                objectName: "savedTitle"
                anchors.verticalCenter: parent.verticalCenter
                text: root.onDevoured ? Words.devoured
                      : (root.openList ? (root.openList.kind === "cravings" ? Words.cravings : root.openList.title) : "")
                color: Preferences.textPrimary
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeDisplay
            }

            Row {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 6
                visible: root.custom
                Chip {
                    objectName: "moveListEarlier"
                    visible: root.custom
                    text: Words.moveEarlier
                    onClicked: Saved.moveList(Saved.openListId, -1)
                }
                Chip {
                    objectName: "moveListLater"
                    visible: root.custom
                    text: Words.moveLater
                    onClicked: Saved.moveList(Saved.openListId, 1)
                }
                Chip {
                    objectName: "renameList"
                    visible: root.custom
                    text: Words.rename
                    onClicked: {
                        titlePopup.mode = "rename"
                        titlePopup.listId = Saved.openListId
                        titlePopup.open()
                    }
                }
                ActionButton {
                    objectName: "deleteList"
                    visible: root.custom
                    danger: true
                    text: Words.deleteListWord
                    onClicked: deletePopup.open()
                }
            }

            Row {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 6
                visible: root.onDevoured
                Chip {
                    objectName: "sort-recent"
                    visible: root.onDevoured
                    text: Words.newestFirst
                    selected: Saved.devouredSort === "recent"
                    onClicked: Saved.openDevoured("recent")
                }
                Chip {
                    objectName: "sort-stars"
                    visible: root.onDevoured
                    text: Words.byStars
                    selected: Saved.devouredSort === "stars"
                    onClicked: Saved.openDevoured("stars")
                }
            }
        }

        Text {
            objectName: "savedError"
            visible: text.length > 0
            width: parent.width
            wrapMode: Text.Wrap
            text: root.pageError.length > 0 ? root.pageError
                  : (Saved.listsError.length > 0 ? Saved.listsError : root.query.error)
            color: Preferences.dangerColor
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeBody
        }
        ActionButton {
            visible: root.query.error.length > 0 || Saved.listsError.length > 0
            text: Words.tryAgain
            onClicked: {
                if (Saved.listsError.length > 0)
                    Saved.load()
                root.query.reload()
            }
        }
    }

    GridView {
        id: grid
        objectName: "savedGrid"
        anchors { top: head.bottom; topMargin: Preferences.spacingMedium; left: parent.left; right: parent.right
                  bottom: parent.bottom; leftMargin: Preferences.spacingLarge; rightMargin: Preferences.spacingLarge }
        clip: true
        cellWidth: Preferences.tileWidth + Preferences.spacingMedium
        readonly property real tileHeight: Preferences.tileWidth * 0.75 + 52
        // A list's tiles have the button that takes them off under them; Devoured's do not.
        cellHeight: grid.tileHeight + (root.onDevoured ? 0 : 46) + Preferences.spacingMedium
        model: root.query.tiles
        ScrollBar.vertical: ScrollBar {}
        onAtYEndChanged: if (atYEnd) root.query.more()

        delegate: Item {
            id: cell
            required property var tile
            required property int index
            objectName: "savedCell-" + index
            width: Preferences.tileWidth
            height: grid.tileHeight + (root.onDevoured ? 0 : 46)

            RecipeTile {
                width: parent.width
                height: grid.tileHeight
                recipe: cell.tile
                caption: root.onDevoured ? Days.label(cell.tile.on, Saved.today()) : ""
            }

            Rectangle {
                width: parent.width
                height: grid.tileHeight
                visible: root.dropAt === cell.index
                color: "transparent"
                radius: Preferences.cornerRadius
                border.width: 2
                border.color: Preferences.accentColor
            }

            // The grip: hold it and let go over another cell to move this recipe there.
            Rectangle {
                objectName: "dragHandle"
                visible: !root.onDevoured
                anchors { left: parent.left; top: parent.top; margins: Preferences.spacingSmall }
                width: 26
                height: 26
                radius: 13
                color: Qt.rgba(Preferences.backgroundPrimary.r, Preferences.backgroundPrimary.g,
                               Preferences.backgroundPrimary.b, 0.8)
                Text {
                    anchors.centerIn: parent
                    text: "⠿"
                    color: Preferences.textPrimary
                    font.pixelSize: Preferences.fontSizeBody
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.SizeAllCursor
                    // The grid scrolls by dragging too; while a grip is held the drag is the grip's.
                    preventStealing: true
                    function cellUnder(mouse) {
                        const at = mapToItem(grid.contentItem, mouse.x, mouse.y)
                        return grid.indexAt(at.x, at.y)
                    }
                    onPositionChanged: mouse => root.dropAt = cellUnder(mouse)
                    onReleased: mouse => {
                        const to = cellUnder(mouse)
                        root.dropAt = -1
                        if (to >= 0 && to !== cell.index)
                            Saved.moveItem(cell.index, to)
                    }
                    onCanceled: root.dropAt = -1
                }
            }

            // A named danger button under the tile, never a bare glyph: taking a recipe off a list is destructive.
            ActionButton {
                objectName: "removeFromList"
                visible: !root.onDevoured
                anchors { left: parent.left; bottom: parent.bottom }
                danger: true
                text: Words.removeFromList
                onClicked: Saved.setInList(Saved.openListId, cell.tile.id, false)
            }
        }
    }

    Column {
        objectName: "savedEmpty"
        anchors.centerIn: grid
        visible: root.query.answered && !root.query.loading && root.query.count === 0 && root.query.error.length === 0
        spacing: Preferences.spacingSmall
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.onDevoured ? Words.noDevoured
                  : (root.openList && root.openList.kind === "cravings" ? Words.noCravings : Words.emptyList)
            color: Preferences.textPrimary
            font.family: Preferences.headingFont
            font.weight: Font.Black
            font.pixelSize: Preferences.fontSizeHeading
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.onDevoured ? Words.noDevouredHint
                  : (root.openList && root.openList.kind === "cravings" ? Words.noCravingsHint : Words.emptyListHint)
            color: Preferences.textSecondary
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeBody
        }
    }

    Text {
        anchors.centerIn: grid
        visible: root.query.loading && root.query.count === 0
        text: Words.loadingWords
        color: Preferences.textMuted
        font.family: Preferences.appFont
        font.pixelSize: Preferences.fontSizeBody
    }
}
