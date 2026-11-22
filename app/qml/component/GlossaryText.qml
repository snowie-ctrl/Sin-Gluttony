import QtQuick
import QtQuick.Controls
import "../logic/glossary.mjs" as GlossaryLogic
import "../logic/words.mjs" as Words

// A step or ingredient line whose glossary words (spec 2026-11-19 part 3, 3.2) wear a dotted underline. Hovering
// one shows its definition, and "same as …" when another kitchen says it differently; a click or tap pins it in a
// small popup that Esc or a click elsewhere closes. A click anywhere else is the line's own (clicked()).
//
// Plain Text cannot say where a word sits, so the words are laid out by a read-only TextEdit, whose
// positionToRectangle gives each marked character's place; the dots are drawn under those.
Item {
    id: root

    property string text: ""
    // The bundled glossary as JSON text (main.cpp's GlossaryJson); glossary.mjs parses it once and keeps it.
    property string glossary: typeof GlossaryJson !== "undefined" ? GlossaryJson : "[]"
    property alias font: edit.font
    property alias color: edit.color
    property real lineHeight: 1             // proportional, as Text.lineHeight
    property bool clickable: false          // the pointing hand over plain text too
    readonly property var marks: GlossaryLogic.marks(root.text, root.glossary)
    // One dotted line per mark per visual line: {mark, x, y, width, top, bottom}.
    property var segments: []
    property var shownMark: null            // the mark whose popup is open
    property bool pinned: false
    readonly property int markCount: root.marks.length

    signal clicked()

    // Closes the popup; cook mode keeps the keys to itself, so its Esc closes a pinned popup through this.
    function closeTip() {
        tip.close()
    }

    implicitWidth: edit.implicitWidth
    implicitHeight: edit.implicitHeight

    function escaped(text) {
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    // The dotted lines' places. Each mark's cursor positions are grouped by line; a group ends at the next
    // position on the same line, or at the last character's own width where the line wraps.
    function relayout() {
        const out = []
        for (const mark of root.marks) {
            let group = null
            for (let p = mark.start; p <= mark.end; ++p) {
                const r = edit.positionToRectangle(p)
                if (group && Math.abs(r.y - group.y) < 1) {
                    group.right = r.x
                    group.last = p
                    continue
                }
                if (group) {
                    // the line wrapped after group.last: add that character's width
                    const c = root.text.charAt(group.last)
                    if (group.last < mark.end && !/\s/.test(c))
                        group.right += metrics.advanceWidth(c)
                    out.push(group)
                }
                group = p < mark.end ? { mark: mark, x: r.x, right: r.x, y: r.y, height: r.height, last: p } : null
            }
            if (group)
                out.push(group)
        }
        root.segments = out.filter(g => g.right > g.x).map(g => ({
            mark: g.mark, x: g.x, width: g.right - g.x, y: g.y + metrics.ascent + 2, top: g.y, bottom: g.y + g.height }))
    }

    function segmentAt(x, y) {
        for (const s of root.segments)
            if (x >= s.x && x <= s.x + s.width && y >= s.top && y <= s.bottom)
                return s
        return null
    }

    function show(segment, pin) {
        root.pinned = pin
        root.shownMark = segment.mark
        const below = root.mapToItem(tip.parent, segment.x, segment.bottom + 4)
        tip.x = Math.max(8, Math.min(below.x, tip.parent.width - tip.width - 8))
        tip.y = below.y + tip.implicitHeight > tip.parent.height - 8
                ? root.mapToItem(tip.parent, 0, segment.top).y - tip.implicitHeight - 4 : below.y
        if (!tip.opened)
            tip.open()
        else if (pin)
            tip.forceActiveFocus()
    }

    onMarksChanged: layoutTimer.restart()
    onWidthChanged: layoutTimer.restart()

    // The dots are laid out once the text has settled. A timer of the item's own rather than Qt.callLater: the
    // recipe page makes and drops these items as the recipe arrives, and a queued call into a dropped item tripped
    // the JS heap in debug builds.
    Timer {
        id: layoutTimer
        interval: 0
        onTriggered: root.relayout()
    }

    FontMetrics {
        id: metrics
        font: edit.font
    }

    TextEdit {
        id: edit
        width: root.width
        readOnly: true
        selectByMouse: false
        activeFocusOnPress: false
        wrapMode: TextEdit.Wrap
        textFormat: TextEdit.RichText
        // pre-wrap keeps every character where the plain text has it, so the marks' positions hold.
        text: "<div style=\"white-space: pre-wrap; line-height: " + Math.round(root.lineHeight * 100) + "%\">"
              + root.escaped(root.text) + "</div>"
        onContentHeightChanged: layoutTimer.restart()
        onContentWidthChanged: layoutTimer.restart()
    }

    Repeater {
        model: root.segments
        delegate: Row {
            required property var modelData
            x: modelData.x
            y: modelData.y
            spacing: 2
            Repeater {
                model: Math.max(1, Math.floor((modelData.width + 2) / 3))
                Rectangle { width: 1; height: 1; color: edit.color; opacity: 0.8 }
            }
        }
    }

    MouseArea {
        id: mouse
        objectName: "glossaryMouse"
        anchors.fill: parent
        hoverEnabled: true
        property var hovered: null
        cursorShape: hovered || root.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPositionChanged: event => {
            mouse.hovered = root.segmentAt(event.x, event.y)
            if (mouse.hovered && !root.pinned)
                root.show(mouse.hovered, false)
            else if (!mouse.hovered && !root.pinned && tip.opened)
                tip.close()
        }
        onExited: {
            mouse.hovered = null
            if (!root.pinned && tip.opened)
                tip.close()
        }
        onClicked: event => {
            const segment = root.segmentAt(event.x, event.y)
            if (segment)
                root.show(segment, true)
            else
                root.clicked()
        }
    }

    Popup {
        id: tip
        objectName: "glossaryPopup"
        parent: Overlay.overlay
        width: Math.min(360, parent ? parent.width - 16 : 360)
        padding: Preferences.spacingSmall + 4
        focus: root.pinned
        closePolicy: root.pinned ? Popup.CloseOnEscape | Popup.CloseOnPressOutside : Popup.NoAutoClose
        onOpened: if (root.pinned) tip.forceActiveFocus()
        onClosed: {
            root.pinned = false
            root.shownMark = null
        }

        background: Rectangle {
            color: Preferences.backgroundSecondary
            radius: Preferences.cornerRadius
            border.color: Preferences.borderColor
        }

        contentItem: Column {
            spacing: 4
            Text {
                objectName: "glossaryTerm"
                width: parent.width
                wrapMode: Text.Wrap
                text: root.shownMark ? root.shownMark.term : ""
                color: Preferences.textPrimary
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeLabel
            }
            Text {
                objectName: "glossaryDefinition"
                width: parent.width
                wrapMode: Text.Wrap
                text: root.shownMark ? root.shownMark.text : ""
                color: Preferences.textPrimary
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeCaption
            }
            Text {
                objectName: "glossarySame"
                visible: !!(root.shownMark && root.shownMark.same)
                width: parent.width
                wrapMode: Text.Wrap
                text: root.shownMark && root.shownMark.same ? Words.glossarySame(root.shownMark.same) : ""
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.italic: true
                font.pixelSize: Preferences.fontSizeCaption
            }
        }
    }
}
