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

    // The model is a list of its own, changed in place: Cook.timers is a new list every second, which as the model
    // would rebuild every delegate (losing a click between its press and release, the rail's tooltip and a finished
    // timer's flash). Here a tick only updates the clock of the row it belongs to, and a dismissed timer's row goes
    // without touching the others.
    ListModel { id: rows }

    function sync() {
        const timers = Cook.timers
        for (let i = rows.count - 1; i >= 0; --i) {
            if (!timers.some(t => t.id === rows.get(i).timerId))
                rows.remove(i)
        }
        for (let i = 0; i < timers.length; ++i) {
            const t = timers[i]
            if (i < rows.count && rows.get(i).timerId === t.id) {
                if (rows.get(i).remaining !== t.remaining)
                    rows.setProperty(i, "remaining", t.remaining)
                if (rows.get(i).done !== t.done)
                    rows.setProperty(i, "done", t.done)
            } else {
                rows.insert(i, { timerId: t.id, label: t.label, remaining: t.remaining, done: t.done })
            }
        }
    }

    Component.onCompleted: stack.sync()
    Connections {
        target: Cook
        function onTimersChanged() { stack.sync() }
    }

    Repeater {
        model: rows
        delegate: Rectangle {
            id: timer
            required property int timerId
            required property string label
            required property int remaining
            required property bool done
            objectName: "timer-" + timer.timerId
            width: stack.compact ? 56 : 280
            height: stack.compact ? 52 : 64
            radius: Preferences.controlRadius
            color: timer.done ? Preferences.accentSubtle : Preferences.backgroundSecondary
            border.width: 1
            border.color: timer.done ? Preferences.accentColor : Preferences.borderColor

            // "Each chimes and flashes when done": the flash lasts until the timer is put away.
            SequentialAnimation on opacity {
                running: timer.done
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
                    objectName: "timerClock-" + timer.timerId
                    width: parent.width
                    horizontalAlignment: stack.compact ? Text.AlignHCenter : Text.AlignLeft
                    text: timer.done ? (stack.compact ? "✓" : Words.timerDone)
                                               : Timers.clock(timer.remaining)
                    color: timer.done ? Preferences.accentColor : Preferences.textPrimary
                    font.family: Preferences.appFont
                    font.bold: true
                    font.pixelSize: stack.compact ? Preferences.fontSizeLabel : Preferences.fontSizeHeading
                }
                Text {
                    visible: !stack.compact
                    width: parent.width
                    elide: Text.ElideRight
                    text: timer.label
                    color: Preferences.textSecondary
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeCaption
                }
            }

            // Full size: a named button. Compact (the rail): the whole timer, which stops it or puts it away.
            Chip {
                id: dismiss
                objectName: "timerDismiss-" + timer.timerId
                visible: !stack.compact
                anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                text: timer.done ? Words.dismiss : Words.stopTimer
                onClicked: Cook.dismissTimer(timer.timerId)
            }
            MouseArea {
                id: compactMouse
                objectName: stack.compact ? "timerDismiss-" + timer.timerId : ""
                anchors.fill: parent
                enabled: stack.compact
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: Cook.dismissTimer(timer.timerId)
            }
            ToolTip {
                visible: stack.compact && compactMouse.containsMouse
                text: timer.label + " · " + (timer.done ? Words.dismiss : Words.stopTimer)
                delay: 400
            }
        }
    }
}
