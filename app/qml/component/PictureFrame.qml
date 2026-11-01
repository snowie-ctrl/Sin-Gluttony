import QtQuick
import "../logic/tiles.mjs" as Tiles

// A recipe's picture on the art ground, never on a warm one, so the chrome's colour never tints the food. A recipe
// kept on this device shows its copy's picture, for the thumbnail too (spec §6), online or not. Without a picture,
// or when it fails to load, the course placeholder (a plate or a glass) shows: never an empty box.
Rectangle {
    id: frame

    property int recipeId: 0
    property bool hasImage: false
    property string kind: "food"
    property bool large: false
    readonly property bool showingPlaceholder: !frame.hasImage || picture.status === Image.Error
                                               || picture.status === Image.Null

    color: Preferences.surfaceArt
    radius: Preferences.cornerRadius
    clip: true

    Image {
        id: picture
        objectName: "picture"
        anchors.fill: parent
        visible: status === Image.Ready
        // Read again whenever a copy or a picture lands (RecipeStore.revision); the address only changes when this
        // recipe's picture has, so nothing reloads for another recipe's.
        source: frame.hasImage && frame.recipeId > 0
                ? (RecipeStore.revision, RecipeStore.pictureUrl(frame.recipeId, frame.large)) : ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        sourceSize.width: frame.large ? 1200 : 400
    }

    TintedIcon {
        objectName: "placeholder"
        anchors.centerIn: parent
        visible: frame.showingPlaceholder
        source: Tiles.placeholderIcon(frame.kind)
        size: Math.max(24, Math.min(frame.width, frame.height) * 0.4)
        color: Preferences.textMuted
    }
}
