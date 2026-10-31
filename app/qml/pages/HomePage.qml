import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/moods.mjs" as Moods
import "../logic/tiles.mjs" as Tiles

// Home (layout B): today's temptation beside the mood tiles and Go on, then, with today's picks under them. All
// of it follows the diet profile on the server. When nothing fits, the temptation's place says so and offers to
// switch the diet off for now; the moods stay, since a mood with the diet off may still fit. With no server, only the
// saved rows show (spec §6): the copies on Cravings and those devoured, from the device, with a way to the Saved page.
Flickable {
    id: root
    objectName: "homePage"

    contentWidth: width
    contentHeight: column.implicitHeight + 2 * Preferences.spacingLarge
    clip: true
    ScrollBar.vertical: ScrollBar {}

    property string rollMessage: ""

    readonly property bool offline: !Session.online || Session.offline
    // Back from an outage Home is asked again: what it showed may be from before it (another day's pick, even).
    onOfflineChanged: if (!root.offline && !Home.loading) Home.load()

    // Signing in already asks Home; this is for a page that opens with nothing asked, or with rows a ♥ or a Devoured
    // mark has changed since. It waits a turn, because the shell is created in the same signal that starts the
    // sign-in's ask, and a second request would only supersede the first.
    Component.onCompleted: Qt.callLater(function() { if (!root.offline && (!Home.answered || Home.stale) && !Home.loading) Home.load() })

    Connections {
        target: Home
        function onPicked(recipeId) {
            Recipes.open(recipeId)
            Nav.navigateTo("recipe-page")
        }
        function onNothingFits() { root.rollMessage = Words.goOnThenNothing }
        function onRollFailed(reason) { root.rollMessage = reason }
    }

    function openPick() {
        Recipes.open(Home.pick.id)
        Nav.navigateTo("recipe-page")
    }

    Column {
        id: column
        x: Preferences.spacingLarge
        y: Preferences.spacingLarge
        width: root.width - 2 * Preferences.spacingLarge
        spacing: Preferences.spacingLarge

        DietChip {}

        Column {
            objectName: "offlineHome"
            visible: root.offline
            width: parent.width
            spacing: Preferences.spacingSmall
            Text {
                width: parent.width
                wrapMode: Text.Wrap
                text: Words.offlineHome
                color: Preferences.textPrimary
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeHeading
            }
            ActionButton {
                objectName: "offlineSavedButton"
                text: Words.savedRecipes
                onClicked: Nav.navigateTo("saved-page")
            }
        }

        Row {
            id: topRow
            visible: !root.offline
            width: parent.width
            height: 380
            spacing: Preferences.spacingMedium

            // Today's temptation, or what to say in its place.
            Item {
                id: hero
                objectName: "homePick"
                width: (parent.width - parent.spacing) * 0.58
                height: parent.height

                PictureFrame {
                    anchors.fill: parent
                    visible: Home.hasPick
                    recipeId: Home.pick.id || 0
                    hasImage: !!Home.pick.hasImage
                    kind: Home.pick.kind || "food"
                    large: true
                }

                Rectangle {
                    anchors.fill: parent
                    visible: Home.hasPick
                    radius: Preferences.cornerRadius
                    gradient: Gradient {
                        GradientStop { position: 0.45; color: "transparent" }
                        GradientStop { position: 1; color: "#e6140c08" }
                    }
                }

                Rectangle {
                    visible: Home.hasPick
                    x: 16
                    y: 16
                    height: 26
                    width: badge.implicitWidth + 20
                    radius: height / 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Preferences.accentColor }
                        GradientStop { position: 1; color: Preferences.accentDeep }
                    }
                    Text {
                        id: badge
                        anchors.centerIn: parent
                        text: Words.todaysTemptation.toUpperCase()
                        color: Preferences.backgroundPrimary
                        font.family: Preferences.appFont
                        font.pixelSize: Preferences.fontSizeCaption
                        font.bold: true
                    }
                }

                Column {
                    visible: Home.hasPick
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 20 }
                    spacing: 4

                    Text {
                        objectName: "homePickTitle"
                        width: parent.width
                        text: Home.pick.title || ""
                        elide: Text.ElideRight
                        color: "white"
                        font.family: Preferences.headingFont
                        font.weight: Font.Black
                        font.pixelSize: 34
                    }
                    Text {
                        text: [Home.pick.cuisine, Tiles.metaLine(Home.pick)].filter(Boolean).join(" · ")
                        font.italic: Tiles.guessedTime(Home.pick)
                        color: Preferences.textSecondary
                        font.family: Preferences.appFont
                        font.pixelSize: Preferences.fontSizeBody
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: Home.hasPick
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.openPick()
                }

                Rectangle {
                    anchors.fill: parent
                    visible: !Home.hasPick
                    radius: Preferences.cornerRadius
                    color: Preferences.backgroundSecondary

                    // A reload after a diet change has nothing to show yet, so it says it is asking.
                    Text {
                        anchors.centerIn: parent
                        visible: Home.loading && !Home.hasPick
                        text: Words.loadingWords
                        color: Preferences.textMuted
                        font.family: Preferences.appFont
                        font.pixelSize: Preferences.fontSizeBody
                    }

                    Column {
                        objectName: "homeError"
                        anchors.centerIn: parent
                        width: parent.width - 2 * Preferences.spacingLarge
                        visible: Home.error.length > 0 && !Home.loading
                        spacing: Preferences.spacingSmall
                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            text: Home.error
                            color: Preferences.dangerColor
                            font.family: Preferences.appFont
                            font.pixelSize: Preferences.fontSizeBody
                        }
                        ActionButton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: Words.tryAgain
                            onClicked: Home.load()
                        }
                    }

                    // Only a real answer of "nothing" says nothing fits: an outage must never offer to switch the diet
                    // off, and a reload still under way has not answered yet.
                    Column {
                        objectName: "nothingFits"
                        anchors.centerIn: parent
                        width: parent.width - 2 * Preferences.spacingLarge
                        visible: Home.answered && !Home.loading && Home.error.length === 0 && !Home.hasPick
                        spacing: Preferences.spacingSmall
                        Text {
                            text: Words.nothingFitsDiet
                            color: Preferences.textPrimary
                            font.family: Preferences.headingFont
                            font.weight: Font.Black
                            font.pixelSize: Preferences.fontSizeHeading + 4
                        }
                        Text {
                            visible: Diet.hasProfile && Diet.enabled
                            width: parent.width
                            wrapMode: Text.Wrap
                            text: Words.nothingFitsDietHint
                            color: Preferences.textSecondary
                            font.family: Preferences.appFont
                            font.pixelSize: Preferences.fontSizeBody
                        }
                        ActionButton {
                            objectName: "dietOffButton"
                            visible: Diet.hasProfile && Diet.enabled
                            primary: true
                            text: Words.switchDietOff
                            onClicked: Diet.enabled = false
                        }
                    }
                }
            }

            Column {
                width: (parent.width - parent.spacing) * 0.42
                height: parent.height
                spacing: Preferences.spacingSmall

                Grid {
                    id: moods
                    width: parent.width
                    columns: 2
                    spacing: Preferences.spacingSmall

                    Repeater {
                        model: Moods.MOODS
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            objectName: "mood-" + modelData.key
                            width: (moods.width - moods.spacing) / 2
                            height: (topRow.height - goButton.height - rollText.height - 3 * Preferences.spacingSmall) / 2
                            radius: Preferences.cornerRadius
                            // The molten gradient, a little deeper tile by tile.
                            gradient: Gradient {
                                GradientStop { position: 0; color: Qt.darker(Preferences.accentColor, 1 + index * 0.12) }
                                GradientStop { position: 1; color: Qt.darker(Preferences.accentDeep, 1 + index * 0.15) }
                            }

                            // Light text on the gradient's deep end, where both lines sit: textPrimary on accentDeep is
                            // about 4.9:1, and each tile only gets deeper.
                            Column {
                                anchors { left: parent.left; bottom: parent.bottom; margins: Preferences.spacingMedium }
                                spacing: 2
                                Text {
                                    text: modelData.title
                                    color: Preferences.textPrimary
                                    font.family: Preferences.headingFont
                                    font.weight: Font.Black
                                    font.pixelSize: Preferences.fontSizeHeading + 4
                                }
                                Text {
                                    text: modelData.hint
                                    color: Preferences.textPrimary
                                    font.family: Preferences.appFont
                                    font.pixelSize: Preferences.fontSizeCaption
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    Catalog.openWith(modelData.filters, modelData.title)
                                    Nav.navigateTo("results-page")
                                }
                            }
                        }
                    }
                }

                ActionButton {
                    id: goButton
                    objectName: "goOnThen"
                    width: parent.width
                    primary: true
                    text: Home.rolling ? Words.loadingWords : Words.goOnThen
                    enabled: !Home.rolling
                    onClicked: {
                        root.rollMessage = ""
                        Home.goOnThen()
                    }
                }

                Text {
                    id: rollText
                    width: parent.width
                    height: root.rollMessage.length > 0 ? implicitHeight : 0
                    text: root.rollMessage
                    wrapMode: Text.Wrap
                    color: Preferences.textMuted
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeLabel
                }
            }
        }

        // A failed reload while a pick is still shown (a Retry during an outage) says so here, since the pick
        // covers the place the error is shown otherwise.
        Row {
            objectName: "homeError"
            width: parent.width
            visible: Home.error.length > 0 && Home.hasPick && !Home.loading && !root.offline
            spacing: Preferences.spacingMedium
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - retry.width - parent.spacing
                wrapMode: Text.Wrap
                text: Home.error
                color: Preferences.dangerColor
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }
            ActionButton { id: retry; text: Words.tryAgain; onClicked: Home.load() }
        }

        TileRow {
            objectName: "cravingsRow"
            width: parent.width
            title: Words.cravings
            hint: Words.cravingsHint
            recipes: root.offline ? RecipeStore.cravings : Home.cravings
        }

        TileRow {
            objectName: "againRow"
            width: parent.width
            title: Words.again
            hint: Words.againHint
            recipes: root.offline ? RecipeStore.again : Home.again
        }

        TileRow {
            width: parent.width
            title: Words.todaysPicks
            recipes: root.offline ? [] : Home.picks
        }
    }
}
