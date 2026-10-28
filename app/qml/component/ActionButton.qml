import QtQuick

// The app's button. Primary is the molten gradient, for the one thing a screen is for. Danger is outlined in the
// danger colour and never filled, so it cannot be mistaken for primary (the gradient ends in crimson). Anything
// else is a quiet panel colour.
Rectangle {
    id: button

    property string text: ""
    property bool primary: false
    property bool danger: false
    signal clicked()

    implicitWidth: label.implicitWidth + 32
    implicitHeight: 38
    radius: Preferences.controlRadius
    opacity: enabled ? 1 : 0.45
    color: primary || danger ? "transparent"
                             : (mouse.containsMouse ? Qt.lighter(Preferences.backgroundTertiary, 1.25) : Preferences.backgroundTertiary)
    border.width: danger ? 1 : 0
    border.color: Preferences.dangerColor
    gradient: primary ? molten : null

    Gradient {
        id: molten
        orientation: Gradient.Horizontal
        GradientStop { position: 0; color: mouse.containsMouse ? Qt.lighter(Preferences.accentColor, 1.08) : Preferences.accentColor }
        GradientStop { position: 1; color: Preferences.accentDeep }
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: button.text
        color: button.primary ? Preferences.backgroundPrimary : (button.danger ? Preferences.dangerColor : Preferences.textPrimary)
        font.family: Preferences.appFont
        font.pixelSize: Preferences.fontSizeBody
        font.bold: button.primary
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: button.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
}
