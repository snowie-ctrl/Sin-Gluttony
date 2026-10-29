import QtQuick
import "../logic/words.mjs" as Words
import "../logic/tiles.mjs" as Tiles

// A recipe in a grid or a row: its picture with the person's ♥ ✓ ★ over it, its title, and "about 15 min · easy"
// (or a caption the list gives it, such as the day it was devoured). A recipe its source removed says so, and still
// opens. Opening it goes to the recipe page.
Item {
    id: tile

    property var recipe: ({})
    // Shown instead of the time and effort line when set.
    property string caption: ""
    // What the tile's answer said, with this session's changes over it (Saved's overlay).
    readonly property var flags: Saved.flagsRevision >= 0 ? Saved.flagsOf(tile.recipe) : ({})

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

    // On dark pills over the picture, so the food is never tinted.
    Row {
        objectName: "tileBadges"
        anchors { top: frame.top; right: frame.right; margins: Preferences.spacingSmall }
        spacing: 4

        Badge {
            objectName: "badgeCraving"
            visible: !!tile.flags.craving
            text: "♥"
            tint: Preferences.accentColor
        }
        Badge {
            objectName: "badgeDevoured"
            visible: tile.flags.devouredCount > 0
            text: Words.devouredBadge(tile.flags.devouredCount)
            tint: Preferences.successColor
        }
        Badge {
            objectName: "badgeStars"
            visible: tile.flags.stars > 0
            text: Words.starsBadge(tile.flags.stars)
            tint: Preferences.accentColor
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
        objectName: "tileMeta"
        anchors { top: title.bottom; topMargin: 2; left: parent.left; right: parent.right }
        text: tile.recipe.removed ? Words.goneFromSource
                                  : (tile.caption.length > 0 ? tile.caption : Tiles.metaLine(tile.recipe))
        font.italic: !!tile.recipe.removed || (tile.caption.length === 0 && Tiles.guessedTime(tile.recipe))
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

    component Badge: Rectangle {
        id: badge
        property string text: ""
        property color tint: Preferences.accentColor
        height: 22
        width: badgeText.implicitWidth + 12
        radius: height / 2
        color: Qt.rgba(Preferences.backgroundPrimary.r, Preferences.backgroundPrimary.g,
                       Preferences.backgroundPrimary.b, 0.8)
        Text {
            id: badgeText
            anchors.centerIn: parent
            text: badge.text
            color: badge.tint
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeCaption
            font.bold: true
        }
    }
}
