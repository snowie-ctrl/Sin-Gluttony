import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/scale.mjs" as Scale
import "../logic/units.mjs" as Units
import "../logic/timers.mjs" as Timers
import "../logic/stepIngredients.mjs" as StepIngredients

// Cook mode (spec §5): the whole window for one recipe. Every step is listed, the current one large and lit and the
// rest dimmed; ↑ ↓, space and a click move between them, and Esc leaves. Beside them the ingredients, scaled and in
// the units chosen on the recipe page, each ticked off with a click, the lines the current step names lit. A step's
// durations are timer chips; the timers stack in the corner and keep running after cook mode closes.
Rectangle {
    id: root
    objectName: "cookPage"

    color: Preferences.backgroundPrimary
    focus: true

    readonly property var r: Cook.recipe
    readonly property var steps: root.r.steps || []
    readonly property var lines: root.r.ingredients || []
    // The servings and multiplier chosen on the recipe page, when that page holds this recipe.
    readonly property real by: Recipes.recipeId === Cook.recipeId
                               ? Scale.factor(root.r.servings || 0, Recipes.servings, Recipes.multiplier) : 1
    readonly property var lit: Cook.step < root.steps.length
                               ? StepIngredients.mentioned(root.steps[Cook.step].text, root.lines) : []

    Component.onCompleted: root.forceActiveFocus()
    // Cook mode is modal while it is open: if something under it (the search field, by Ctrl+K) takes the focus, the
    // keys come back here, so ↑ ↓, space and Esc always reach cook mode.
    onActiveFocusChanged: if (!root.activeFocus && Cook.active) root.forceActiveFocus()
    Keys.onUpPressed: Cook.previous()
    Keys.onDownPressed: Cook.next()
    Keys.onSpacePressed: Cook.next()
    Keys.onEscapePressed: Cook.close()
    // The lowest item, so it only gets the presses nothing above it took: it keeps the keys with cook mode (a chip or a
    // line may otherwise take the focus) and, by accepting them, stops a click on blank space reaching the page
    // underneath (the search field, the rail, the recipe's buttons).
    MouseArea { anchors.fill: parent; onPressed: root.forceActiveFocus() }

    Item {
        id: header
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: Preferences.spacingLarge }
        height: 56

        Column {
            anchors { left: parent.left; verticalCenter: parent.verticalCenter }
            width: parent.width - leave.width - Preferences.spacingLarge
            spacing: 2
            Text {
                objectName: "cookTitle"
                width: parent.width
                elide: Text.ElideRight
                text: root.r.title || ""
                color: Preferences.textPrimary
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeDisplay
            }
            Row {
                spacing: Preferences.spacingMedium
                Text {
                    objectName: "cookStepOf"
                    text: Words.stepOf(Cook.step + 1, Math.max(1, root.steps.length))
                    color: Preferences.accentColor
                    font.family: Preferences.appFont
                    font.bold: true
                    font.pixelSize: Preferences.fontSizeLabel
                }
                Text {
                    text: Words.cookKeys
                    color: Preferences.textMuted
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeLabel
                }
            }
        }
        ActionButton {
            id: leave
            objectName: "cookLeave"
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            text: Words.cookLeave
            onClicked: Cook.close()
        }
    }

    // The ingredients: a column of its own that scrolls when it is long.
    Flickable {
        id: ingredientsView
        objectName: "cookIngredients"
        anchors { left: parent.left; top: header.bottom; bottom: parent.bottom; margins: Preferences.spacingLarge }
        width: 380
        contentHeight: lineColumn.implicitHeight
        clip: true
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: lineColumn
            width: ingredientsView.width
            spacing: 4

            Text {
                text: Words.ingredientsTitle
                color: Preferences.accentColor
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeHeading
                bottomPadding: Preferences.spacingSmall
            }
            Repeater {
                model: root.lines
                delegate: Rectangle {
                    id: line
                    required property var modelData
                    required property int index
                    readonly property bool ticked: Cook.ticks.indexOf(index) >= 0
                    readonly property bool isLit: root.lit.indexOf(index) >= 0
                    objectName: "cookLine-" + index
                    width: lineColumn.width
                    height: lineRow.implicitHeight + 12
                    radius: Preferences.controlRadius
                    color: line.isLit ? Preferences.accentSubtle : "transparent"

                    Row {
                        id: lineRow
                        x: 8
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 16
                        spacing: Preferences.spacingSmall
                        Text {
                            text: line.ticked ? "✓" : "○"
                            color: line.ticked ? Preferences.successColor : Preferences.textMuted
                            font.family: Preferences.appFont
                            font.pixelSize: Preferences.fontSizeBody
                        }
                        Text {
                            objectName: "cookLineText-" + line.index
                            width: parent.width - 24
                            wrapMode: Text.Wrap
                            text: Units.withOptional(Units.lineText(line.modelData, root.by, Preferences.units, root.r.kind),
                                                     line.modelData.optional)
                            color: line.ticked ? Preferences.successColor : Preferences.textPrimary
                            font.strikeout: line.ticked
                            font.family: Preferences.appFont
                            font.pixelSize: Preferences.fontSizeBody
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: Cook.toggleTick(line.index)
                    }
                }
            }
        }
    }

    // Every step; the current one keeps a third of the way down, so what comes next is in view.
    ListView {
        id: stepsView
        objectName: "cookSteps"
        anchors { left: ingredientsView.right; right: parent.right; top: header.bottom; bottom: parent.bottom
                  margins: Preferences.spacingLarge }
        clip: true
        spacing: Preferences.spacingMedium
        model: root.steps
        currentIndex: Cook.step
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: height * 0.3
        preferredHighlightEnd: height * 0.3 + 1
        highlightMoveDuration: 250
        ScrollBar.vertical: ScrollBar {}

        delegate: Rectangle {
            id: step
            required property var modelData
            required property int index
            readonly property bool current: index === Cook.step
            objectName: "cookStep-" + index
            width: stepsView.width
            height: stepColumn.implicitHeight + 2 * Preferences.spacingMedium
            radius: Preferences.cornerRadius
            color: step.current ? Preferences.backgroundSecondary : "transparent"
            border.width: step.current ? 1 : 0
            border.color: Preferences.accentColor
            opacity: step.current ? 1 : 0.45

            // Below the chips, so a timer chip takes its own click.
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: Cook.goTo(step.index)
            }

            Column {
                id: stepColumn
                x: Preferences.spacingMedium
                y: Preferences.spacingMedium
                width: parent.width - 2 * Preferences.spacingMedium
                spacing: Preferences.spacingSmall

                Text {
                    visible: !!step.modelData.group && (step.index === 0 || root.steps[step.index - 1].group !== step.modelData.group)
                    text: step.modelData.group || ""
                    color: Preferences.accentColor
                    font.family: Preferences.appFont
                    font.bold: true
                    font.pixelSize: Preferences.fontSizeLabel
                }
                Row {
                    width: parent.width
                    spacing: Preferences.spacingMedium
                    Text {
                        width: 36
                        text: step.index + 1
                        color: Preferences.accentColor
                        font.family: Preferences.headingFont
                        font.weight: Font.Black
                        font.pixelSize: step.current ? Preferences.fontSizeDisplay : Preferences.fontSizeHeading
                    }
                    Text {
                        objectName: "cookStepText-" + step.index
                        width: parent.width - 36 - Preferences.spacingMedium
                        wrapMode: Text.Wrap
                        lineHeight: 1.25
                        text: Units.withOtherScale(step.modelData.text)
                        color: Preferences.textPrimary
                        font.family: Preferences.appFont
                        font.pixelSize: step.current ? Preferences.fontSizeDisplay : Preferences.fontSizeHeading
                        MouseArea {
                            anchors.fill: parent
                            onClicked: Cook.goTo(step.index)
                        }
                    }
                }
                Flow {
                    width: parent.width
                    spacing: Preferences.spacingSmall
                    Repeater {
                        model: Timers.timersIn(step.modelData.text)
                        delegate: Chip {
                            required property var modelData
                            required property int index
                            objectName: "cookTimer-" + step.index + "-" + index
                            text: "⏱ " + modelData.text
                            onClicked: Cook.startTimer(modelData.seconds, Words.timerLabel(root.r.title || "", step.index + 1))
                        }
                    }
                }
            }
        }
    }

    TimerStack {
        objectName: "cookTimers"
        anchors { right: parent.right; bottom: parent.bottom; margins: Preferences.spacingLarge }
    }
}
