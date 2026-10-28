// Copied from Pageturner Pageturner/qml/component/TintedIcon.qml at ad9342e; as it is.
import QtQuick
import QtQuick.Effects

// Recolours a black svg to `color` by using its alpha as a mask, the same
// trick Showtime's nav bar uses, so one icon file serves every state.
Item {
    id: tintedIcon

    property url source
    property color color: Preferences.textSecondary
    property int size: 22

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    Image {
        id: iconImage
        anchors.fill: parent
        source: tintedIcon.source
        sourceSize.width: tintedIcon.size
        sourceSize.height: tintedIcon.size
        fillMode: Image.PreserveAspectFit
        visible: false
    }

    Rectangle {
        id: iconTint
        anchors.fill: parent
        color: tintedIcon.color
        visible: false
    }

    MultiEffect {
        anchors.fill: parent
        source: iconTint
        maskEnabled: true
        maskSource: iconImage
    }
}
