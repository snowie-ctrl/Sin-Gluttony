import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/filters.mjs" as Filters

// Results, with the filter side panel: a mood, a search or Browse all open this page. The Catalog holds the state,
// so the page is rebuilt on every visit and comes back as it was left. More rows load as the grid nears its end.
Item {
    id: root
    objectName: "resultsPage"

    readonly property var results: Catalog.results

    Component.onCompleted: {
        if (Object.keys(Catalog.options).length === 0)
            Catalog.loadOptions()
        if (!root.results.answered && !root.results.loading)
            Catalog.apply()
    }

    FilterPanel {
        id: panel
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        width: 290
        visible: !Preferences.filterPanelCollapsed
    }

    Item {
        id: content
        anchors {
            left: panel.visible ? panel.right : parent.left
            right: parent.right
            top: parent.top
            bottom: parent.bottom
            leftMargin: Preferences.spacingLarge
            rightMargin: Preferences.spacingLarge
        }

        Row {
            id: header
            y: Preferences.spacingMedium
            height: 44
            spacing: Preferences.spacingMedium

            Chip {
                objectName: "showFilters"
                anchors.verticalCenter: parent.verticalCenter
                visible: Preferences.filterPanelCollapsed
                text: Words.filtersTitle + (Filters.activeCount(Catalog.filters) > 0
                                            ? " (" + Filters.activeCount(Catalog.filters) + ")" : "")
                onClicked: Preferences.filterPanelCollapsed = false
            }
            Text {
                objectName: "resultsTitle"
                anchors.verticalCenter: parent.verticalCenter
                text: Catalog.title.length === 0 ? Words.browseTitle
                      : (Catalog.filters.q ? "“" + Catalog.title + "”" : Catalog.title)
                color: Preferences.textPrimary
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeDisplay
            }
            Text {
                objectName: "resultsCount"
                anchors.verticalCenter: parent.verticalCenter
                visible: root.results.answered
                text: Words.recipeCount(root.results.total)
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }
        }

        Row {
            anchors { right: parent.right; verticalCenter: header.verticalCenter }
            spacing: 6
            Repeater {
                model: Words.SORTS.filter(s => s.value !== "relevance" || !!Catalog.filters.q)
                delegate: Chip {
                    required property var modelData
                    objectName: "sort-" + modelData.value
                    text: modelData.label
                    selected: (Catalog.filters.sort || (Catalog.filters.q ? "relevance" : "shuffle")) === modelData.value
                    onClicked: Catalog.setFilter("sort", modelData.value)
                }
            }
        }

        // The diet in force, under the title whether the panel is open or not: results it narrows always say so.
        DietChip {
            id: dietRow
            anchors { top: header.bottom; topMargin: Preferences.spacingSmall }
        }

        GridView {
            id: grid
            objectName: "resultsGrid"
            anchors { top: dietRow.bottom; topMargin: Preferences.spacingMedium; left: parent.left; right: parent.right; bottom: parent.bottom }
            clip: true
            cellWidth: Preferences.tileWidth + Preferences.spacingMedium
            cellHeight: Preferences.tileWidth * 0.75 + 52 + Preferences.spacingMedium
            model: root.results.tiles
            delegate: RecipeTile {
                required property var tile
                recipe: tile
                width: Preferences.tileWidth
            }
            ScrollBar.vertical: ScrollBar {}
            onAtYEndChanged: if (atYEnd) root.results.more()
            // A screen tall enough to show a whole page asks for the next one too.
            onCountChanged: if (atYEnd) Qt.callLater(root.results.more)
        }

        Text {
            anchors.centerIn: grid
            visible: root.results.loading && root.results.count === 0
            text: Words.loadingWords
            color: Preferences.textMuted
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeBody
        }

        Column {
            anchors.centerIn: grid
            visible: root.results.error.length > 0 && root.results.count === 0
            spacing: Preferences.spacingSmall
            Text {
                text: root.results.error
                color: Preferences.dangerColor
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }
            ActionButton { text: Words.tryAgain; onClicked: root.results.reload() }
        }

        Column {
            objectName: "resultsEmpty"
            anchors.centerIn: grid
            visible: root.results.answered && !root.results.loading && root.results.count === 0
                     && root.results.error.length === 0
            spacing: Preferences.spacingSmall
            Text {
                text: Words.nothingFits
                color: Preferences.textPrimary
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeHeading + 4
            }
            Text {
                text: Words.nothingFitsHint
                color: Preferences.textSecondary
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }
            Row {
                spacing: Preferences.spacingSmall
                ActionButton { text: Words.resetFilters; onClicked: Catalog.resetFilters() }
                ActionButton {
                    objectName: "resultsDietOff"
                    visible: Diet.hasProfile && Diet.enabled
                    primary: true
                    text: Words.switchDietOff
                    onClicked: Diet.enabled = false
                }
            }
        }
    }
}
