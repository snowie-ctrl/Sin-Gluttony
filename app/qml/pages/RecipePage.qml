import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/tiles.mjs" as Tiles
import "../logic/scale.mjs" as Scale
import "../logic/units.mjs" as Units
import "../logic/credit.mjs" as Credit
import "../logic/days.mjs" as Days

// The recipe page (layout A): a wide picture with the title over it, a strip of chips, the actions (♥ Craving,
// + List, ✓ Devoured on a day that can be changed, the stars, ✎ Note, with the note under them), then the
// ingredients in a column that stays put while the steps scroll, Seconds? and the credit the sources require.
// Quantities follow the servings (or multiplier) chosen and the units preference; clicking a changed line shows it
// as written. A recipe its source removed says so, and works as before for the person who kept it.
Item {
    id: root
    objectName: "recipePage"

    signal backRequested()

    readonly property var r: Recipes.recipe
    readonly property bool ready: Object.keys(root.r).length > 0
    readonly property real by: Scale.factor(root.r.servings || 0, Recipes.servings, Recipes.multiplier)
    readonly property string system: Preferences.units
    // Line index → true while that line shows its original text.
    property var shownOriginal: ({})

    // The first line of a different recipe starts at the top, but a reload of the same one keeps the place.
    property int shownId: 0
    // What the person keeps on this recipe; empty until its detail is in.
    readonly property var mine: Saved.mineId === (root.r.id || 0) && Saved.mineId > 0 ? Saved.mine : ({})
    // The day ✓ Devoured marks: today, unless moved back.
    property string devourDay: Saved.today()
    property string actionError: ""
    // The Devoured mark chosen for removal (0: none); removing needs the named button that then appears.
    property int pickedMark: 0
    readonly property bool markPicked: root.pickedMark > 0
        && (root.mine.devoured || []).some(mark => mark.id === root.pickedMark)
    // The stars rest while a star request for this recipe is on its way, so two quick taps cannot cross.
    readonly property bool starsBusy: Saved.starsSaving.indexOf(root.r.id || 0) >= 0

    onRChanged: {
        root.shownOriginal = ({})
        if ((root.r.id || 0) !== root.shownId) {
            root.shownId = root.r.id || 0
            flick.contentY = 0
            root.devourDay = Saved.today()
            root.actionError = ""
            root.pickedMark = 0
        }
    }

    Connections {
        target: Saved
        function onFailed(what, message) {
            if (what === "item" || what === "devoured" || what === "stars")
                root.actionError = message
        }
        function onDone(what) {
            root.actionError = ""
            if (what === "devoured")
                root.pickedMark = 0
        }
    }

    ListPopup { id: listPopup; recipeId: root.r.id || 0 }
    NotePopup { id: notePopup; recipeId: root.r.id || 0 }

    // A source link comes from the catalog's data, so only web addresses are handed to the browser.
    function openLink(link) {
        if (/^https?:\/\//i.test(link))
            Qt.openUrlExternally(link)
    }

    Text {
        anchors.centerIn: parent
        visible: Recipes.loading
        text: Words.loadingWords
        color: Preferences.textMuted
        font.family: Preferences.appFont
        font.pixelSize: Preferences.fontSizeBody
    }

    Column {
        objectName: "recipeGone"
        anchors.centerIn: parent
        visible: Recipes.gone
        spacing: Preferences.spacingSmall
        Text {
            text: Words.gone
            color: Preferences.textPrimary
            font.family: Preferences.headingFont
            font.weight: Font.Black
            font.pixelSize: Preferences.fontSizeHeading + 4
        }
        Text {
            text: Words.goneHint
            color: Preferences.textSecondary
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeBody
        }
        ActionButton { objectName: "recipeGoneBack"; text: "← " + Words.back; onClicked: root.backRequested() }
    }

    Column {
        objectName: "recipeError"
        anchors.centerIn: parent
        visible: Recipes.error.length > 0
        spacing: Preferences.spacingSmall
        Text {
            text: Recipes.error
            color: Preferences.dangerColor
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeBody
        }
        Row {
            spacing: Preferences.spacingSmall
            ActionButton { text: Words.tryAgain; onClicked: Recipes.reload() }
            ActionButton { text: "← " + Words.back; onClicked: root.backRequested() }
        }
    }

    Flickable {
        id: flick
        anchors.fill: parent
        visible: root.ready && !Recipes.loading && !Recipes.gone && Recipes.error.length === 0
        contentWidth: width
        contentHeight: page.height
        clip: true
        ScrollBar.vertical: ScrollBar {}

        Item {
            id: page
            x: Preferences.spacingLarge
            width: flick.width - 2 * Preferences.spacingLarge
            height: credit.y + credit.implicitHeight + 2 * Preferences.spacingLarge

            Item {
                id: hero
                y: Preferences.spacingMedium
                width: parent.width
                height: 380

                PictureFrame {
                    anchors.fill: parent
                    recipeId: root.r.id || 0
                    hasImage: !!root.r.hasImage
                    kind: root.r.kind || "food"
                    large: true
                }
                Rectangle {
                    anchors.fill: parent
                    radius: Preferences.cornerRadius
                    gradient: Gradient {
                        GradientStop { position: 0.4; color: "transparent" }
                        GradientStop { position: 1; color: "#e6140c08" }
                    }
                }
                Chip {
                    objectName: "recipeBack"
                    x: 16
                    y: 16
                    text: "← " + Words.back
                    onClicked: root.backRequested()
                }
                Column {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 24 }
                    spacing: 4
                    Text {
                        objectName: "recipeTitle"
                        width: parent.width
                        text: root.r.title || ""
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        color: "white"
                        font.family: Preferences.headingFont
                        font.weight: Font.Black
                        font.pixelSize: 40
                    }
                    Text {
                        text: [root.r.cuisine, Words.courseWord(root.r.course), Words.sourceName(root.r.source)]
                              .filter(Boolean).join(" · ")
                        color: Preferences.textSecondary
                        font.family: Preferences.appFont
                        font.pixelSize: Preferences.fontSizeBody
                    }
                }
            }

            Flow {
                id: chips
                anchors { top: hero.bottom; topMargin: Preferences.spacingMedium }
                width: parent.width
                spacing: Preferences.spacingSmall

                Chip {
                    visible: text.length > 0
                    text: Tiles.timeText(root.r.totalMinutes, root.r.timeFrom)
                    italic: root.r.timeFrom === "rule"
                }
                Chip {
                    visible: text.length > 0
                    text: Words.effortWord(root.r.difficulty).length > 0
                          ? (root.r.difficultyFrom === "rule" ? Words.about : "") + Words.effortWord(root.r.difficulty) : ""
                    italic: root.r.difficultyFrom === "rule"
                }
                Chip {
                    visible: text.length > 0
                    text: Words.servingsText(root.r.servings, root.r.servingsFrom)
                    italic: root.r.servingsFrom === "rule"
                }
                Chip {
                    visible: text.length > 0
                    text: Words.containsText(root.r.facts ? root.r.facts.contains : [])
                }
                Repeater {
                    model: root.r.facts ? root.r.facts.diets : []
                    delegate: Chip { required property var modelData; text: Words.dietChip([modelData], []) }
                }
                Repeater {
                    model: root.r.tags ? root.r.tags.flavour : []
                    delegate: Chip { required property var modelData; text: modelData }
                }
                Chip {
                    objectName: "unknownWarning"
                    visible: Diet.enabled && Diet.hasProfile && !!root.r.facts && !root.r.facts.complete
                    outlined: true
                    text: "⚠ " + Words.unknownIngredients
                }
                Chip {
                    objectName: "removedNote"
                    visible: !!root.r.removed
                    outlined: true
                    text: Words.goneNote
                }
            }

            Column {
                id: kept
                anchors { top: chips.bottom; topMargin: Preferences.spacingMedium }
                width: parent.width
                spacing: Preferences.spacingSmall

                Flow {
                    objectName: "recipeActions"
                    width: parent.width
                    spacing: Preferences.spacingSmall

                    Chip {
                        objectName: "actionCraving"
                        text: (root.mine.craving ? "♥ " : "♡ ") + Words.craving
                        selected: !!root.mine.craving
                        onClicked: Saved.setCraving(root.r.id, !root.mine.craving)
                    }
                    Chip {
                        objectName: "actionList"
                        text: "+ " + Words.addToList
                        onClicked: listPopup.open()
                    }
                    Row {
                        spacing: 4
                        Chip {
                            objectName: "actionDevoured"
                            text: "✓ " + Words.devoured
                            enabled: !Saved.devouring
                            opacity: enabled ? 1 : 0.6
                            onClicked: Saved.devour(root.r.id, root.devourDay)
                        }
                        Chip {
                            objectName: "devouredEarlier"
                            text: Words.earlier
                            onClicked: root.devourDay = Days.addDays(root.devourDay, -1)
                        }
                        Chip {
                            objectName: "devouredDay"
                            text: Days.label(root.devourDay, Saved.today())
                            onClicked: root.devourDay = Saved.today()
                        }
                        Chip {
                            objectName: "devouredLater"
                            text: Words.later
                            enabled: root.devourDay < Saved.today()
                            opacity: enabled ? 1 : 0.4
                            onClicked: root.devourDay = Days.addDays(root.devourDay, 1)
                        }
                    }
                    Stars {
                        objectName: "actionStars"
                        height: 30
                        enabled: !root.starsBusy
                        opacity: enabled ? 1 : 0.6
                        value: root.mine.stars || 0
                        onChosen: stars => Saved.setStars(root.r.id, stars === value ? 0 : stars)
                    }
                    Chip {
                        objectName: "actionNote"
                        text: "✎ " + (root.mine.note ? Words.editNote : Words.note)
                        onClicked: notePopup.open()
                    }
                }

                // Each time it was devoured, newest first. Choosing a mark offers a named, outlined button to take it
                // back off, so a stray tap never erases one.
                Flow {
                    width: parent.width
                    spacing: 6
                    visible: !!root.mine.devoured && root.mine.devoured.length > 0
                    Repeater {
                        model: root.mine.devoured || []
                        delegate: Chip {
                            required property var modelData
                            objectName: "devouredMark-" + modelData.id
                            text: "✓ " + Days.label(modelData.on, Saved.today())
                            selected: root.pickedMark === modelData.id
                            onClicked: root.pickedMark = root.pickedMark === modelData.id ? 0 : modelData.id
                        }
                    }
                    ActionButton {
                        objectName: "removeMark"
                        visible: root.markPicked
                        danger: true
                        text: Words.removeMark
                        onClicked: Saved.undevour(root.pickedMark)
                    }
                }

                Text {
                    objectName: "recipeNote"
                    visible: !!root.mine.note
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: root.mine.note || ""
                    color: Preferences.textSecondary
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeBody
                    font.italic: true
                }

                Text {
                    objectName: "actionError"
                    visible: root.actionError.length > 0
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: root.actionError
                    color: Preferences.dangerColor
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeLabel
                }
            }

            Item {
                id: body
                anchors { top: kept.bottom; topMargin: Preferences.spacingLarge }
                width: parent.width
                height: Math.max(ingredients.implicitHeight, method.implicitHeight)

                Column {
                    id: ingredients
                    objectName: "ingredientsColumn"
                    width: 380
                    spacing: Preferences.spacingSmall
                    // The ingredients stay in view while the steps scroll past, but only when the whole column fits
                    // in the view: a taller one scrolls with the page, so its last lines can still be reached.
                    readonly property bool fits: implicitHeight <= flick.height - 2 * Preferences.spacingMedium
                    y: fits ? Math.max(0, Math.min(flick.contentY - body.y + Preferences.spacingMedium,
                                                   body.height - implicitHeight))
                            : 0

                    Text {
                        text: Words.ingredientsTitle
                        color: Preferences.accentColor
                        font.family: Preferences.headingFont
                        font.weight: Font.Black
                        font.pixelSize: Preferences.fontSizeHeading + 2
                    }

                    Row {
                        spacing: 6
                        visible: (root.r.servings || 0) > 0
                        Chip { objectName: "servingsMinus"; text: "−"; onClicked: Recipes.servings = Recipes.servings - 1 }
                        Text {
                            objectName: "servingsValue"
                            anchors.verticalCenter: parent.verticalCenter
                            text: Recipes.servings + " " + Words.servingsWord
                            color: Preferences.textPrimary
                            font.family: Preferences.appFont
                            font.pixelSize: Preferences.fontSizeBody
                        }
                        Chip { objectName: "servingsPlus"; text: "+"; onClicked: Recipes.servings = Recipes.servings + 1 }
                    }
                    Row {
                        spacing: 6
                        visible: !((root.r.servings || 0) > 0)
                        Repeater {
                            model: Scale.MULTIPLIERS
                            delegate: Chip {
                                required property var modelData
                                objectName: "multiplier-" + modelData
                                text: "×" + Units.fraction(modelData)
                                selected: Math.abs(Recipes.multiplier - modelData) < 1e-9
                                onClicked: Recipes.multiplier = modelData
                            }
                        }
                    }
                    Row {
                        spacing: 6
                        Chip {
                            objectName: "units-metric"
                            text: Words.metric
                            selected: root.system === "metric"
                            onClicked: Preferences.units = "metric"
                        }
                        Chip {
                            objectName: "units-us"
                            text: Words.us
                            selected: root.system === "us"
                            onClicked: Preferences.units = "us"
                        }
                    }

                    Repeater {
                        model: root.r.ingredients || []
                        delegate: Column {
                            required property var modelData
                            required property int index
                            width: ingredients.width
                            spacing: 2

                            // A group heading starts each group.
                            Text {
                                visible: !!modelData.group && (index === 0 || root.r.ingredients[index - 1].group !== modelData.group)
                                topPadding: 8
                                text: modelData.group || ""
                                color: Preferences.accentColor
                                font.family: Preferences.appFont
                                font.bold: true
                                font.pixelSize: Preferences.fontSizeLabel
                            }
                            Text {
                                id: lineText
                                objectName: "ingredient-" + index
                                readonly property string shown: Units.lineText(modelData, root.by, root.system, root.r.kind)
                                width: parent.width
                                wrapMode: Text.Wrap
                                text: root.shownOriginal[index] ? Words.showOriginal + modelData.line
                                      : Units.withOptional(shown, modelData.optional)
                                color: Preferences.textPrimary
                                font.family: Preferences.appFont
                                font.pixelSize: Preferences.fontSizeBody

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: lineText.shown !== modelData.line
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: {
                                        const copy = Object.assign({}, root.shownOriginal)
                                        copy[index] = !copy[index]
                                        root.shownOriginal = copy
                                    }
                                }
                            }
                        }
                    }
                }

                Column {
                    id: method
                    x: ingredients.width + 48
                    width: body.width - x
                    spacing: Preferences.spacingMedium

                    Text {
                        text: Words.methodTitle
                        color: Preferences.accentColor
                        font.family: Preferences.headingFont
                        font.weight: Font.Black
                        font.pixelSize: Preferences.fontSizeHeading + 2
                    }
                    Repeater {
                        model: root.r.steps || []
                        delegate: Column {
                            required property var modelData
                            required property int index
                            width: method.width
                            spacing: 4

                            Text {
                                visible: !!modelData.group && (index === 0 || root.r.steps[index - 1].group !== modelData.group)
                                text: modelData.group || ""
                                color: Preferences.accentColor
                                font.family: Preferences.appFont
                                font.bold: true
                                font.pixelSize: Preferences.fontSizeLabel
                            }
                            Row {
                                width: parent.width
                                spacing: 12
                                Text {
                                    width: 28
                                    text: index + 1
                                    color: Preferences.accentColor
                                    font.family: Preferences.headingFont
                                    font.weight: Font.Black
                                    font.pixelSize: 22
                                }
                                Text {
                                    objectName: "step-" + index
                                    width: parent.width - 40
                                    wrapMode: Text.Wrap
                                    lineHeight: 1.3
                                    text: Units.withOtherScale(modelData.text)
                                    color: Preferences.textPrimary
                                    font.family: Preferences.appFont
                                    font.pixelSize: Preferences.fontSizeBody
                                }
                            }
                        }
                    }
                }
            }

            TileRow {
                id: seconds
                anchors { top: body.bottom; topMargin: 32 }
                width: parent.width
                title: Words.seconds
                hint: Words.secondsHint
                recipes: (root.r.versions || []).map(v => Object.assign({ kind: root.r.kind }, v))
            }

            Column {
                id: credit
                anchors { top: seconds.visible ? seconds.bottom : body.bottom; topMargin: 32 }
                width: parent.width
                spacing: 4

                Text {
                    width: parent.width
                    wrapMode: Text.Wrap
                    textFormat: Text.StyledText
                    linkColor: Preferences.accentColor
                    text: Credit.creditLine(root.r.credit, root.r.licence, root.r.sourceUrl)
                    onLinkActivated: link => root.openLink(link)
                    color: Preferences.textMuted
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeCaption
                }
                Text {
                    visible: !!root.r.imageCredit
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: Words.creditPicture + (root.r.imageCredit || "")
                    color: Preferences.textMuted
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeCaption
                }
                Text {
                    visible: !!root.r.videoUrl
                    textFormat: Text.StyledText
                    linkColor: Preferences.accentColor
                    text: '<a href="' + String(root.r.videoUrl || "").replace(/"/g, "%22") + '">' + Words.creditVideo + "</a>"
                    onLinkActivated: link => root.openLink(link)
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeCaption
                }
            }
        }
    }
}
