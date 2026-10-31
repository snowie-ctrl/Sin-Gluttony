import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/tiles.mjs" as Tiles

// Search on every page (Ctrl+K). What is typed asks for up to six recipes and five ingredients; the arrow keys
// walk both lists, and Enter opens the one highlighted, or with nothing highlighted, every result for the words
// typed. Choosing an ingredient opens Browse with it as Must include. With no server it searches the saved recipes on
// the device by title, and Enter with nothing highlighted opens the Saved page.
Item {
    id: root
    objectName: "searchBar"

    property int highlighted: -1
    readonly property bool offline: !Session.online || Session.offline
    // Offline, the recipes are the device's copies whose title holds what is typed; there are no ingredients.
    readonly property var recipes: root.offline ? (RecipeStore.revision, RecipeStore.search(field.text)) : Catalog.quickRecipes
    readonly property var ingredients: root.offline ? [] : Catalog.quickIngredients
    readonly property int recipeCount: root.recipes.length
    readonly property int rowCount: recipeCount + root.ingredients.length

    Shortcut {
        sequences: ["Ctrl+K"]
        onActivated: {
            field.forceActiveFocus()
            field.selectAll()
        }
    }

    function choose(index) {
        if (index >= 0 && index < root.recipeCount) {
            Recipes.open(root.recipes[index].id)
            Nav.navigateTo("recipe-page")
        } else if (index >= root.recipeCount && index < root.rowCount) {
            const ingredient = root.ingredients[index - root.recipeCount]
            Catalog.openWith({}, Words.searchWith + ingredient.name)
            Catalog.addIngredient("include", ingredient.id, ingredient.name)
            Nav.navigateTo("results-page")
        } else if (field.text.trim().length > 0) {
            if (root.offline) {
                Nav.navigateTo("saved-page")
            } else {
                Catalog.search(field.text)
                Nav.navigateTo("results-page")
            }
        } else {
            return
        }
        root.finish()
    }

    function finish() {
        field.text = ""
        Catalog.quickSearch("")
        root.highlighted = -1
        field.focus = false
    }

    InputField {
        id: field
        objectName: "searchField"
        anchors.fill: parent
        placeholderText: Words.searchPlaceholder + "      Ctrl+K"
        onTextEdited: {
            root.highlighted = -1
            if (!root.offline)
                debounce.restart()
        }
        Keys.onDownPressed: root.highlighted = Math.min(root.highlighted + 1, root.rowCount - 1)
        Keys.onUpPressed: root.highlighted = Math.max(root.highlighted - 1, -1)
        Keys.onEscapePressed: root.finish()
        onAccepted: root.choose(root.highlighted)
    }

    // A pause in typing asks once, not once per letter.
    Timer {
        id: debounce
        interval: 200
        onTriggered: Catalog.quickSearch(field.text)
    }

    Popup {
        id: popup
        y: root.height + 6
        width: root.width
        padding: 8
        visible: field.activeFocus && (root.offline ? field.text.trim().length > 0
                                                    : root.rowCount > 0 && Catalog.quickTerm === field.text.trim())
        closePolicy: Popup.NoAutoClose

        background: Rectangle {
            color: Preferences.backgroundSecondary
            radius: Preferences.cornerRadius
            border.color: Preferences.borderColor
        }

        // The name sits on the content item: a Popup is not an item, so a test could not find it there.
        contentItem: Column {
            objectName: "searchPopup"
            spacing: 2

            Text {
                objectName: "searchOffline"
                visible: root.offline
                leftPadding: 8
                text: Words.offlineSearch
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeCaption
            }
            Text {
                objectName: "searchNoSaved"
                visible: root.offline && root.recipeCount === 0
                leftPadding: 8
                text: Words.noSavedMatch
                color: Preferences.textSecondary
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }
            Text {
                visible: root.recipeCount > 0 && !root.offline
                leftPadding: 8
                text: Words.searchRecipes
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeCaption
            }
            Repeater {
                model: root.recipes
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    objectName: "quickRecipe-" + index
                    width: popup.availableWidth
                    height: 48
                    radius: Preferences.controlRadius
                    color: root.highlighted === index || recipeMouse.containsMouse ? Preferences.backgroundTertiary : "transparent"

                    PictureFrame {
                        id: thumb
                        x: 6
                        anchors.verticalCenter: parent.verticalCenter
                        width: 48
                        height: 36
                        radius: Preferences.controlRadius
                        recipeId: modelData.id
                        hasImage: !!modelData.hasImage
                        kind: modelData.kind || "food"
                    }
                    Column {
                        anchors { left: thumb.right; leftMargin: 10; right: parent.right; verticalCenter: parent.verticalCenter }
                        Text {
                            width: parent.width
                            text: modelData.title
                            elide: Text.ElideRight
                            color: Preferences.textPrimary
                            font.family: Preferences.appFont
                            font.pixelSize: Preferences.fontSizeBody
                        }
                        Text {
                            text: Tiles.metaLine(modelData)
                            color: Preferences.textMuted
                            font.family: Preferences.appFont
                            font.pixelSize: Preferences.fontSizeCaption
                        }
                    }
                    MouseArea {
                        id: recipeMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onPressed: root.choose(index)
                    }
                }
            }

            Text {
                visible: root.ingredients.length > 0
                leftPadding: 8
                topPadding: 6
                text: Words.searchIngredients
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeCaption
            }
            Repeater {
                model: root.ingredients
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    objectName: "quickIngredient-" + index
                    width: popup.availableWidth
                    height: 34
                    radius: Preferences.controlRadius
                    color: root.highlighted === root.recipeCount + index || ingredientMouse.containsMouse
                           ? Preferences.backgroundTertiary : "transparent"
                    Text {
                        x: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: Words.searchWith + modelData.name
                        color: Preferences.textPrimary
                        font.family: Preferences.appFont
                        font.pixelSize: Preferences.fontSizeBody
                    }
                    MouseArea {
                        id: ingredientMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onPressed: root.choose(root.recipeCount + index)
                    }
                }
            }
        }
    }
}
