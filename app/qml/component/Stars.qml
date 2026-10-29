import QtQuick

// One to five stars. Clicking one chooses it; the page decides what a click on the stars already chosen means
// (it clears them).
Row {
    id: stars

    property int value: 0
    signal chosen(int stars)

    spacing: 2

    Repeater {
        model: 5
        delegate: Text {
            required property int index
            objectName: "star-" + (index + 1)
            text: "★"
            color: index < stars.value ? Preferences.accentColor : Preferences.textMuted
            font.pixelSize: Preferences.fontSizeHeading
            MouseArea {
                anchors.fill: parent
                anchors.margins: -2
                cursorShape: Qt.PointingHandCursor
                onClicked: stars.chosen(index + 1)
            }
        }
    }
}
