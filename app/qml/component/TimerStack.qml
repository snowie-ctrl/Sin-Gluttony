import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/timers.mjs" as Timers

// The kitchen timers, oldest first (spec §5): each counts down under its name; a finished one flashes and says so
// until it is dismissed. Cook mode shows the stack in a corner; once cook mode has closed the rail shows it compact,
// each timer's name in a tooltip.
Column {
    id: stack
    objectName: "timerStack"

    property bool compact: false

    spacing: Preferences.spacingSmall
    visible: Cook.timers.length > 0

    Repeater {
        model: Cook.timers
        delegate: Rectangle {
            id: timer
            required property var modelData
            objectName: "timer-" + modelData.id
            width: stack.compact ? 56 : 280
            height: stack.compact ? 52 : 64
            radius: Preferences.controlRadius
            color: modelData.done ? Preferences.accentSubtle : Preferences.backgroundSecondary
            border.width: 1
            border.color: modelData.done ? Preferences.accentColor : Preferences.borderColor

            // "Each chimes and flashes when done": the flash lasts until the timer is put away.
            SequentialAnimation on opacity {
                running: timer.modelData.done
                loops: Animation.Infinite
                alwaysRunToEnd: true
                NumberAnimation { to: 0.35; duration: 450 }
                NumberAnimation { to: 1; duration: 450 }
            }

            Column {
                anchors { left: parent.left; leftMargin: stack.compact ? 0 : 12; verticalCenter: parent.verticalCenter }
                width: stack.compact ? parent.width : parent.width - dismiss.width - 24
                spacing: 2
                Text {
                    objectName: "timerClock-" + timer.modelData.id
                    width: parent.width
                    horizontalAlignment: stack.compact ? Text.AlignHCenter : Text.AlignLeft
                    text: timer.modelData.done ? (stack.compact ? "✓" : Words.timerDone)
                                               : Timers.clock(timer.modelData.remaining)
                    color: timer.modelData.done ? Preferences.accentColor : Preferences.textPrimary
                    font.family: Preferences.appFont
                    font.bold: true
                    font.pixelSize: stack.compact ? Preferences.fontSizeLabel : Preferences.fontSizeHeading
                }
                Text {
                    visible: !stack.compact
                    width: parent.width
                    elide: Text.ElideRight
                    text: timer.modelData.label
                    color: Preferences.textSecondary
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeCaption
                }
            }

            // Full size: a named button. Compact (the rail): the whole timer, which stops it or puts it away.
            Chip {
                id: dismiss
                objectName: "timerDismiss-" + timer.modelData.id
                visible: !stack.compact
                anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                text: timer.modelData.done ? Words.dismiss : Words.stopTimer
                onClicked: Cook.dismissTimer(timer.modelData.id)
            }
            MouseArea {
                id: compactMouse
                objectName: stack.compact ? "timerDismiss-" + timer.modelData.id : ""
                anchors.fill: parent
                enabled: stack.compact
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: Cook.dismissTimer(timer.modelData.id)
            }
            ToolTip {
                visible: stack.compact && compactMouse.containsMouse
                text: timer.modelData.label + " · " + (timer.modelData.done ? Words.dismiss : Words.stopTimer)
                delay: 400
            }
        }
    }
}
