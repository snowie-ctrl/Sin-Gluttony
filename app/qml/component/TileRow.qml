import QtQuick
import QtQuick.Controls

// A titled row of recipe tiles that scrolls sideways (Today's picks, Seconds?). An empty row is not shown.
Column {
    id: row

    property string title: ""
    property string hint: ""
    property var recipes: []

    spacing: Preferences.spacingSmall
    visible: row.recipes.length > 0

    Row {
        spacing: Preferences.spacingSmall

        Text {
            text: row.title
            color: Preferences.accentColor
            font.family: Preferences.headingFont
            font.weight: Font.Black
            font.pixelSize: Preferences.fontSizeHeading
        }

        Text {
            visible: row.hint.length > 0
            anchors.bottom: parent.bottom
            text: row.hint
            color: Preferences.textMuted
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeCaption
        }
    }

    // A whole number of tiles fills the row, each at least tileWidth, so the last one in view is never cut by a
    // sliver; the rest are reached by scrolling.
    ListView {
        id: list
        objectName: "tileRowList"
        readonly property int perView: Math.max(1, Math.floor((width + spacing) / (Preferences.tileWidth + spacing)))
        readonly property real tileWidth: (width - (perView - 1) * spacing) / perView
        width: row.width
        height: list.tileWidth * 0.75 + 56
        orientation: ListView.Horizontal
        spacing: Preferences.spacingMedium
        clip: true
        model: row.recipes
        delegate: RecipeTile {
            required property var modelData
            recipe: modelData
            width: list.tileWidth
            height: list.tileWidth * 0.75 + 52
        }
        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
    }
}
