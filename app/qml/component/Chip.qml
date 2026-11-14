import QtQuick
import "../logic/chips.mjs" as Chips

// A pill: a filter value, a diet, an ingredient to remove. A chip that belongs to a filter kind (kind) is drawn in
// its family's colour (chips.mjs): outlined in the tone, filled with the accent-tinted ground when selected; a
// neutral one (diet, allergens) never takes the orange tint. A chip with no kind is a control and looks as before:
// plain, the accent around it when selected or outlined.
Rectangle {
    id: chip

    property string text: ""
    property string kind: ""
    property bool selected: false
    property bool outlined: false
    property bool removable: false
    property bool italic: false
    signal clicked()
    signal removeClicked()

    readonly property string family: Chips.familyOf(kind)
    readonly property color tone: Preferences[Chips.toneKey(family)]
    readonly property bool marked: selected || outlined

    implicitWidth: row.implicitWidth + 22
    implicitHeight: 30
    radius: height / 2
    color: family === "neutral" ? (mouse.containsMouse && !selected ? Qt.lighter(Preferences.backgroundTertiary, 1.15) : Preferences.backgroundTertiary)
         : selected ? Preferences.accentSubtle
         : (mouse.containsMouse ? Preferences.backgroundTertiary : Preferences.backgroundSecondary)
    border.width: family !== "" || marked ? 1 : 0
    border.color: family === "" || marked ? tone : Qt.rgba(tone.r, tone.g, tone.b, 0.35)

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
            objectName: "chipLabel"
            text: (chip.family === "neutral" && chip.selected ? "✓ " : "") + chip.text
            color: chip.family === "neutral" ? (chip.marked ? Preferences.textPrimary : chip.tone)
                 : chip.family !== "" ? chip.tone
                 : (chip.marked ? chip.tone : Preferences.textSecondary)
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
