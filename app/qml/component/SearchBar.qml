import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/tiles.mjs" as Tiles

// Search on every page (Ctrl+K). What is typed asks for up to six recipes and five ingredients; the arrow keys
// walk both lists, and Enter opens the one highlighted, or with nothing highlighted, every result for the words
// typed. Choosing an ingredient opens Browse with it as Must include.
Item {
    id: root
    objectName: "searchBar"

    property int highlighted: -1
    readonly property int recipeCount: Catalog.quickRecipes.length
    readonly property int rowCount: recipeCount + Catalog.quickIngredients.length

    Shortcut {
        sequences: ["Ctrl+K"]
        onActivated: {
            field.forceActiveFocus()
            field.selectAll()
        }
    }

    function choose(index) {
        if (index >= 0 && index < root.recipeCount) {
            Recipes.open(Catalog.quickRecipes[index].id)
            Nav.navigateTo("recipe-page")
        } else if (index >= root.recipeCount && index < root.rowCount) {
            const ingredient = Catalog.quickIngredients[index - root.recipeCount]
            Catalog.openWith({}, Words.searchWith + ingredient.name)
            Catalog.addIngredient("include", ingredient.id, ingredient.name)
            Nav.navigateTo("results-page")
        } else if (field.text.trim().length > 0) {
            Catalog.search(field.text)
            Nav.navigateTo("results-page")
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
        visible: field.activeFocus && root.rowCount > 0 && Catalog.quickTerm === field.text.trim()
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
                visible: root.recipeCount > 0
                leftPadding: 8
                text: Words.searchRecipes
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeCaption
            }
            Repeater {
                model: Catalog.quickRecipes
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
                visible: Catalog.quickIngredients.length > 0
                leftPadding: 8
                topPadding: 6
                text: Words.searchIngredients
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeCaption
            }
            Repeater {
                model: Catalog.quickIngredients
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
