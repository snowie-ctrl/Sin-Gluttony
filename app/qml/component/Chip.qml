import QtQuick

// A pill: a filter value, a diet, an ingredient to remove. A selected chip takes the accent-tinted ground; an
// outlined one (the diet in force) shows the accent around it.
Rectangle {
    id: chip

    property string text: ""
    property bool selected: false
    property bool outlined: false
    property bool removable: false
    property bool italic: false
    signal clicked()
    signal removeClicked()

    implicitWidth: row.implicitWidth + 22
    implicitHeight: 30
    radius: height / 2
    color: selected ? Preferences.accentSubtle : (mouse.containsMouse ? Preferences.backgroundTertiary : Preferences.backgroundSecondary)
    border.width: selected || outlined ? 1 : 0
    border.color: Preferences.accentColor

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: chip.clicked()
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 6

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: chip.text
            color: chip.selected || chip.outlined ? Preferences.accentColor : Preferences.textSecondary
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
            font.italic: chip.italic
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            visible: chip.removable
            text: "×"
            color: Preferences.textMuted
            font.pixelSize: Preferences.fontSizeBody

            MouseArea {
                anchors.fill: parent
                anchors.margins: -4
                cursorShape: Qt.PointingHandCursor
                onClicked: chip.removeClicked()
            }
        }
    }
}
