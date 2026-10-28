import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/filters.mjs" as Filters

// The filter panel: every group always visible, with whole-catalog counts from /filters, so each tick is one
// click. Each tick asks again at once (Catalog). It collapses to a button on the results page.
Rectangle {
    id: panel
    objectName: "filterPanel"

    color: Preferences.backgroundSecondary

    readonly property var f: Catalog.filters
    readonly property var o: Catalog.options

    Flickable {
        anchors.fill: parent
        anchors.margins: Preferences.spacingMedium
        contentHeight: groups.implicitHeight
        clip: true
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: groups
            width: parent.width
            spacing: Preferences.spacingMedium

            Item {
                width: parent.width
                height: 32
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Words.filtersTitle
                    color: Preferences.textPrimary
                    font.family: Preferences.headingFont
                    font.weight: Font.Black
                    font.pixelSize: Preferences.fontSizeHeading
                }
                Row {
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    spacing: 6
                    Chip { text: Words.resetFilters; onClicked: Catalog.resetFilters() }
                    Chip { objectName: "hideFilters"; text: "‹"; onClicked: Preferences.filterPanelCollapsed = true }
                }
            }

            Group {
                title: Words.FILTER_TITLES.diet
                visible: Diet.hasProfile
                Chip {
                    objectName: "filterDiet"
                    text: Words.dietChip(Diet.diets, Diet.avoid) + (Diet.enabled ? "" : " · " + Words.dietOffForNow)
                    selected: Diet.enabled
                    onClicked: Diet.enabled = !Diet.enabled
                }
            }

            Group {
                title: Words.FILTER_TITLES.kind
                Repeater {
                    model: Words.KINDS
                    delegate: Chip {
                        required property var modelData
                        objectName: "filter-kind-" + (modelData.value || "both")
                        text: modelData.label
                        selected: panel.f.kind === modelData.value
                        onClicked: Catalog.setFilter("kind", modelData.value)
                    }
                }
            }

            Group {
                title: Words.FILTER_TITLES.time
                Repeater {
                    model: Words.TIMES
                    delegate: Chip {
                        required property var modelData
                        objectName: "filter-time-" + modelData.value
                        text: modelData.label
                        selected: panel.f.maxMinutes === modelData.value
                        onClicked: Catalog.setFilter("maxMinutes", modelData.value)
                    }
                }
            }

            Group {
                title: Words.FILTER_TITLES.effort
                Repeater {
                    model: Words.EFFORTS
                    delegate: Chip {
                        required property var modelData
                        objectName: "filter-effort-" + modelData.value
                        text: modelData.label
                        selected: Filters.contains(panel.f.difficulty, modelData.value)
                        onClicked: Catalog.toggle("difficulty", modelData.value)
                    }
                }
            }

            Group {
                title: Words.FILTER_TITLES.course
                visible: Filters.courseOptions(panel.f.kind, panel.o).length > 0
                Repeater {
                    model: Filters.courseOptions(panel.f.kind, panel.o)
                    delegate: Chip {
                        required property var modelData
                        objectName: "filter-course-" + modelData.value
                        text: Words.courseWord(modelData.value) + "  " + modelData.count
                        selected: Filters.contains(panel.f.course, modelData.value)
                        onClicked: Catalog.toggle("course", modelData.value)
                    }
                }
            }

            Group {
                id: cuisines
                property bool all: false
                // The server takes up to Catalog.cuisineLimit cuisines at once, so the rest are dimmed until one is taken off.
                readonly property bool full: (panel.f.cuisine || []).length >= Catalog.cuisineLimit
                title: Words.FILTER_TITLES.cuisine
                visible: (panel.o.cuisines || []).length > 0
                Repeater {
                    model: (panel.o.cuisines || []).slice(0, cuisines.all ? 1000 : 12)
                    delegate: Chip {
                        required property var modelData
                        text: modelData.value + "  " + modelData.count
                        selected: Filters.contains(panel.f.cuisine, modelData.value)
                        enabled: selected || !cuisines.full
                        opacity: enabled ? 1 : 0.4
                        onClicked: Catalog.toggle("cuisine", modelData.value)
                    }
                }
                Chip {
                    visible: !cuisines.all && (panel.o.cuisines || []).length > 12
                    text: Words.showAll
                    onClicked: cuisines.all = true
                }
            }

            Group {
                title: Words.FILTER_TITLES.flavour
                visible: (panel.o.flavours || []).length > 0
                Repeater {
                    model: panel.o.flavours || []
                    delegate: Chip {
                        required property var modelData
                        text: modelData.value
                        selected: Filters.contains(panel.f.flavour, modelData.value)
                        onClicked: Catalog.toggle("flavour", modelData.value)
                    }
                }
            }

            Group {
                title: Words.FILTER_TITLES.occasion
                visible: (panel.o.occasions || []).length > 0
                Repeater {
                    model: panel.o.occasions || []
                    delegate: Chip {
                        required property var modelData
                        text: modelData.value
                        selected: Filters.contains(panel.f.occasion, modelData.value)
                        onClicked: Catalog.toggle("occasion", modelData.value)
                    }
                }
            }

            Group {
                title: Words.FILTER_TITLES.alcohol
                visible: panel.f.kind !== "food"
                Repeater {
                    model: Words.ALCOHOL
                    delegate: Chip {
                        required property var modelData
                        text: modelData.label
                        selected: Filters.contains(panel.f.alcohol, modelData.value)
                        onClicked: Catalog.toggle("alcohol", modelData.value)
                    }
                }
            }

            Group {
                title: Words.FILTER_TITLES.avoid
                Repeater {
                    model: Words.AVOID
                    delegate: Chip {
                        required property var modelData
                        objectName: "filter-avoid-" + modelData.value
                        text: modelData.label
                        selected: Filters.contains(panel.f.avoid, modelData.value)
                        onClicked: Catalog.toggle("avoid", modelData.value)
                    }
                }
            }

            IngredientPicker { key: "include"; title: Words.FILTER_TITLES.include }
            IngredientPicker { key: "exclude"; title: Words.FILTER_TITLES.exclude }
        }
    }

    // A titled group of chips.
    component Group: Column {
        id: group

        property string title: ""
        default property alias chips: flow.data

        width: parent ? parent.width : 240
        spacing: 6

        Text {
            text: group.title
            color: Preferences.accentColor
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
            font.bold: true
        }
        Flow {
            id: flow
            width: group.width
            spacing: 6
        }
    }

    // Must include or Leave out: the chosen ingredients as removable chips, and a field whose matches (from
    // /ingredients) show while it has the focus. Both pickers share the Catalog's matches; only the focused one shows them.
    component IngredientPicker: Column {
        id: picker

        property string key: "include"
        property string title: ""

        width: parent ? parent.width : 240
        spacing: 6

        Text {
            text: picker.title
            color: Preferences.accentColor
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
            font.bold: true
        }
        Flow {
            width: picker.width
            spacing: 6
            Repeater {
                model: panel.f[picker.key] || []
                delegate: Chip {
                    required property var modelData
                    text: modelData.name
                    selected: true
                    removable: true
                    onRemoveClicked: Catalog.removeIngredient(picker.key, modelData.id)
                }
            }
        }
        InputField {
            id: field
            objectName: "picker-" + picker.key
            width: picker.width
            placeholderText: Words.typeAnIngredient
            onTextEdited: Catalog.findIngredients(text)
            onActiveFocusChanged: if (activeFocus) Catalog.findIngredients(text)
        }
        Column {
            width: picker.width
            visible: field.activeFocus && field.text.length > 0
            Repeater {
                model: field.activeFocus ? Catalog.ingredientMatches : []
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    objectName: "match-" + picker.key + "-" + index
                    width: picker.width
                    height: 30
                    radius: Preferences.controlRadius
                    color: matchMouse.containsMouse ? Preferences.backgroundTertiary : "transparent"
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        x: 10
                        text: modelData.name
                        color: Preferences.textPrimary
                        font.family: Preferences.appFont
                        font.pixelSize: Preferences.fontSizeLabel
                    }
                    MouseArea {
                        id: matchMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        // On press, before anything can move the focus and hide the list.
                        onPressed: {
                            Catalog.addIngredient(picker.key, modelData.id, modelData.name)
                            field.text = ""
                        }
                    }
                }
            }
        }
    }
}
