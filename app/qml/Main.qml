import QtQuick
import QtQuick.Controls

ApplicationWindow {
    id: window

    width: 1600
    height: 1000
    minimumWidth: 1100
    minimumHeight: 700
    visible: true

    title: "Gluttony"
    color: Preferences.backgroundPrimary
    font.family: Preferences.appFont

    // Which top-level page is showing, by name.
    property string topPage: "login-page"

    Component { id: loginPage; LoginPage {} }
    Component { id: navShell; NavShell {} }

    StackView {
        id: primaryStack
        anchors.fill: parent
        initialItem: loginPage
        replaceEnter: Transition {}
        replaceExit: Transition {}
    }

    Connections {
        target: Nav
        function onChangePage(page) {
            // Pages inside the shell are the shell's business.
            if (page !== "login-page" && page !== "nav-shell")
                return
            if (window.topPage === page)
                return
            primaryStack.replace(page === "login-page" ? loginPage : navShell)
            window.topPage = page
        }
    }

    Connections {
        target: Session
        function onLoginSucceeded() { Nav.navigateTo(Nav.startPage) }
        // No server, but this account's saved recipes are here (milestone 3): the shell opens on them.
        function onStartedOffline() { Nav.navigateTo(Nav.startPage) }
        function onSignedOut() { Nav.navigateTo("login-page") }
    }
}
