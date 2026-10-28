import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words

// Signing in, as in Pageturner. A known device never sees the form: identifyDevice is already on its way when this
// page appears, so it shows "Signing in…" until the answer says the device is new. With no server and nothing
// saved, it says the server can't be reached, with Try again. A new account also needs a sign-up key.
Rectangle {
    id: root
    objectName: "loginPage"

    color: Preferences.backgroundPrimary

    property bool wantsKey: false
    property string errorText: ""
    property bool submitted: false
    readonly property bool formReady: !Session.busy || root.submitted

    Component.onCompleted: if (form.visible) username.forceActiveFocus()

    function submit() {
        if (Session.busy)
            return
        if (username.text.trim().length === 0 || password.text.length === 0) {
            root.errorText = Words.enterUsernameAndPassword
            return
        }
        if (root.wantsKey && key.text.trim().length === 0) {
            root.errorText = Words.enterKey
            return
        }
        root.errorText = ""
        root.submitted = true
        Session.login(username.text, password.text, root.wantsKey ? key.text : "")
    }

    Connections {
        target: Session
        function onLoginFailed(code, message) {
            root.errorText = message
            root.submitted = false
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: 400
        height: column.implicitHeight + 64
        radius: Preferences.cornerRadius
        color: Preferences.backgroundSecondary
        border.color: Preferences.borderColor

        Column {
            id: column
            anchors.centerIn: parent
            width: parent.width - 64
            spacing: Preferences.spacingMedium

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "qrc:/images/gluttony.svg"
                sourceSize: Qt.size(56, 56)
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Words.signInTitle
                color: Preferences.textPrimary
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: 34
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Words.signInTagline
                color: Preferences.textSecondary
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }

            Text {
                objectName: "signingIn"
                anchors.horizontalCenter: parent.horizontalCenter
                visible: !root.formReady && !Session.unreachable
                text: Words.signingIn
                color: Preferences.textMuted
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }

            Column {
                visible: Session.unreachable
                width: parent.width
                spacing: Preferences.spacingSmall

                Text {
                    width: parent.width
                    text: Words.unreachable
                    wrapMode: Text.Wrap
                    color: Preferences.dangerColor
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeBody
                }
                ActionButton { text: Words.tryAgain; onClicked: Session.retry() }
            }

            Column {
                id: form
                visible: root.formReady && !Session.unreachable
                width: parent.width
                spacing: Preferences.spacingSmall
                onVisibleChanged: if (visible) username.forceActiveFocus()

                InputField {
                    id: username
                    objectName: "usernameField"
                    placeholderText: Words.username
                    onAccepted: password.forceActiveFocus()
                }
                InputField {
                    id: password
                    objectName: "passwordField"
                    placeholderText: Words.password
                    echoMode: TextInput.Password
                    onAccepted: root.wantsKey ? key.forceActiveFocus() : root.submit()
                }
                InputField {
                    id: key
                    objectName: "keyField"
                    visible: root.wantsKey
                    placeholderText: Words.signUpKey
                    onAccepted: root.submit()
                }
                CheckBox {
                    id: keyBox
                    objectName: "keyBox"
                    text: Words.haveAKey
                    checked: root.wantsKey
                    onToggled: root.wantsKey = checked
                    // Basic's own box is a light square, black on this card; this one is drawn in the app's colours.
                    indicator: Rectangle {
                        implicitWidth: 20
                        implicitHeight: 20
                        x: keyBox.leftPadding
                        y: keyBox.topPadding + (keyBox.availableHeight - height) / 2
                        radius: Preferences.controlRadius / 2
                        color: Preferences.backgroundTertiary
                        border.color: Preferences.borderColor
                        Text {
                            anchors.centerIn: parent
                            visible: keyBox.checked
                            text: "✓"
                            color: Preferences.accentColor
                            font.pixelSize: Preferences.fontSizeBody
                            font.bold: true
                        }
                    }
                    contentItem: Text {
                        leftPadding: keyBox.indicator.width + 8
                        text: keyBox.text
                        color: Preferences.textSecondary
                        font.family: Preferences.appFont
                        font.pixelSize: Preferences.fontSizeLabel
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                Text {
                    objectName: "loginError"
                    visible: root.errorText.length > 0
                    width: parent.width
                    text: root.errorText
                    wrapMode: Text.Wrap
                    color: Preferences.dangerColor
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeLabel
                }
                ActionButton {
                    objectName: "loginButton"
                    primary: true
                    width: parent.width
                    text: root.wantsKey ? Words.createAccount : Words.signIn
                    enabled: !Session.busy || !root.submitted
                    onClicked: root.submit()
                }
            }
        }
    }
}
