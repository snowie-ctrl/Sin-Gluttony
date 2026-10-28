import QtQuick
import QtQuick.Controls
import "logic/words.mjs" as Words

// The app around its pages: the icon rail on the left, the top bar with search on every page, and the page beside
// them. Pages are swapped by name; a new shell starts on Nav.currentPage. While the server cannot be reached a
// banner under the top bar says so.
Rectangle {
    id: root
    objectName: "navShell"

    color: Preferences.backgroundPrimary

    property string currentPage: ""
    // The last page that is not a recipe, which the recipe page's Back returns to.
    property string lastListPage: "home-page"

    // Each page adds its own entry here (Tasks 19-22).
    readonly property var pageComponents: ({ "home-page": homePage, "results-page": resultsPage, "recipe-page": recipePage })
    readonly property string startPage: root.pageComponents[Nav.currentPage] !== undefined ? Nav.currentPage : "home-page"

    Component.onCompleted: {
        root.currentPage = root.startPage
        if (root.startPage !== "recipe-page")
            root.lastListPage = root.startPage
    }

    Connections {
        target: Nav
        function onChangePage(page) {
            if (root.pageComponents[page] === undefined)
                return
            if (page !== "recipe-page")
                root.lastListPage = page
            root.currentPage = page
        }
    }

    Component { id: homePage; HomePage {} }
    Component { id: resultsPage; ResultsPage {} }
    Component { id: recipePage; RecipePage { onBackRequested: Nav.navigateTo(root.lastListPage) } }

    Rectangle {
        id: rail
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        width: 68
        color: Preferences.backgroundSecondary

        Column {
            anchors { top: parent.top; topMargin: 16; horizontalCenter: parent.horizontalCenter }
            spacing: 10

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "qrc:/images/gluttony.svg"
                sourceSize: Qt.size(36, 36)
            }
            Item { width: 1; height: 12 }
            RailButton {
                objectName: "railHome"
                label: Words.navHome
                pageTag: "home-page"
                iconSource: "qrc:/images/home.svg"
                onActivated: Nav.navigateTo("home-page")
            }
            RailButton {
                objectName: "railBrowse"
                label: Words.navBrowse
                pageTag: "results-page"
                iconSource: "qrc:/images/catalog.svg"
                onActivated: {
                    if (!Catalog.results.answered && !Catalog.results.loading)
                        Catalog.openWith({}, "")
                    Nav.navigateTo("results-page")
                }
            }
        }

        RailButton {
            id: account
            objectName: "railAccount"
            anchors { bottom: parent.bottom; bottomMargin: 16; horizontalCenter: parent.horizontalCenter }
            label: Words.signedInAs(Session.username)
            iconSource: "qrc:/images/settings.svg"
            onActivated: accountMenu.open()

            // Basic's menu is light; this one is drawn in the app's colours, like the rest of the shell.
            Menu {
                id: accountMenu
                x: account.width + 8
                background: Rectangle {
                    implicitWidth: 220
                    color: Preferences.backgroundSecondary
                    border.color: Preferences.borderColor
                    radius: Preferences.controlRadius
                }
                AccountItem { text: Words.signedInAs(Session.username); enabled: false }
                AccountItem { objectName: "signOut"; text: Words.signOut; onTriggered: Session.logout() }
            }
        }
    }

    Rectangle {
        id: topBar
        anchors { left: rail.right; right: parent.right; top: parent.top }
        height: 64
        color: Preferences.backgroundPrimary

        SearchBar {
            id: searchSlot
            x: Preferences.spacingLarge
            anchors.verticalCenter: parent.verticalCenter
            width: 560
            height: 40
        }
    }

    Rectangle {
        id: banner
        objectName: "offlineBanner"
        visible: !Session.online
        anchors { left: rail.right; right: parent.right; top: topBar.bottom }
        height: visible ? 32 : 0
        color: Preferences.accentSubtle

        Text {
            anchors.centerIn: parent
            text: Words.offline
            color: Preferences.textPrimary
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
        }
    }

    Loader {
        id: pageLoader
        anchors { left: rail.right; right: parent.right; top: banner.bottom; bottom: parent.bottom }
        sourceComponent: root.pageComponents[root.currentPage] || null
    }

    // An account menu entry: the panel's text on its ground, the hover a shade lighter.
    component AccountItem: MenuItem {
        id: item
        contentItem: Text {
            leftPadding: Preferences.spacingSmall
            text: item.text
            color: item.enabled ? Preferences.textPrimary : Preferences.textSecondary
            font.family: Preferences.appFont
            font.pixelSize: Preferences.fontSizeLabel
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            implicitWidth: 220
            implicitHeight: 36
            radius: Preferences.controlRadius
            color: item.highlighted ? Preferences.backgroundTertiary : "transparent"
        }
    }

    // An icon with its label as a tooltip: the rail stays narrow so pages get the width.
    component RailButton: Rectangle {
        id: button

        property string label: ""
        property string pageTag: ""
        property url iconSource
        readonly property bool selected: pageTag.length > 0 && (root.currentPage === pageTag
                                         || (root.currentPage === "recipe-page" && root.lastListPage === pageTag))
        signal activated()

        width: 48
        height: 48
        radius: Preferences.controlRadius
        color: button.selected ? Preferences.accentSubtle
                               : (mouse.containsMouse ? Preferences.backgroundTertiary : "transparent")

        TintedIcon {
            anchors.centerIn: parent
            source: button.iconSource
            size: 24
            color: button.selected ? Preferences.accentColor : Preferences.textSecondary
        }

        // Beside the button rather than over it, in the app's colours rather than Basic's light ones.
        ToolTip {
            id: tip
            visible: mouse.containsMouse
            text: button.label
            delay: 400
            x: button.width + 8
            y: (button.height - height) / 2
            contentItem: Text {
                text: tip.text
                color: Preferences.textPrimary
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeLabel
            }
            background: Rectangle {
                color: Preferences.backgroundTertiary
                border.color: Preferences.borderColor
                radius: Preferences.controlRadius
            }
        }

        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: button.activated()
        }
    }
}
