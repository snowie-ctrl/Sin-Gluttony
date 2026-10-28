import QtQuick
import "../logic/tiles.mjs" as Tiles

// A recipe in a grid or a row: its picture, title and "about 15 min · easy". Opening it goes to the recipe page.
Item {
    id: tile

    property var recipe: ({})

    implicitWidth: Preferences.tileWidth
    implicitHeight: Preferences.tileWidth * 0.75 + 52

    PictureFrame {
        id: frame
        width: parent.width
        height: parent.width * 0.75
        recipeId: tile.recipe.id || 0
        hasImage: !!tile.recipe.hasImage
        kind: tile.recipe.kind || "food"

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            border.width: mouse.containsMouse ? 2 : 0
            border.color: Preferences.accentColor
        }
    }

    Text {
        id: title
        objectName: "tileTitle"
        anchors { top: frame.bottom; topMargin: 6; left: parent.left; right: parent.right }
        text: tile.recipe.title || ""
        elide: Text.ElideRight
        color: Preferences.textPrimary
        font.family: Preferences.appFont
        font.pixelSize: Preferences.fontSizeLabel
    }

    Text {
        anchors { top: title.bottom; topMargin: 2; left: parent.left; right: parent.right }
        text: Tiles.metaLine(tile.recipe)
        font.italic: Tiles.guessedTime(tile.recipe)
        elide: Text.ElideRight
        color: Preferences.textMuted
        font.family: Preferences.appFont
        font.pixelSize: Preferences.fontSizeCaption
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            Recipes.open(tile.recipe.id)
            Nav.navigateTo("recipe-page")
        }
    }
}
