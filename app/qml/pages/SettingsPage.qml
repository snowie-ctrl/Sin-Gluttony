import QtQuick
import QtQuick.Controls
import "../logic/words.mjs" as Words
import "../logic/days.mjs" as Days

// Settings: the account (username, password, the devices that sign in by themselves, signing out), the diet
// profile, units, the colours, and how the app reaches the server. What Session says back (done, or why not) shows
// under the account, in plain words.
Flickable {
    id: root
    objectName: "settingsPage"

    contentWidth: width
    contentHeight: column.implicitHeight + 2 * Preferences.spacingLarge
    clip: true
    ScrollBar.vertical: ScrollBar {}

    property string accountMessage: ""
    property bool accountFailed: false

    // The devices are asked for once the page is up, unless they are on their way already.
    Component.onCompleted: Qt.callLater(function() { if (!Session.devicesLoading) Session.loadDevices() })

    Connections {
        target: Session
        function onAccountUpdated(what) {
            root.accountFailed = false
            root.accountMessage = Words.ACCOUNT_DONE[what] || ""
            if (what === "password") {
                currentPassword.text = ""
                newPassword.text = ""
            }
        }
        function onAccountFailed(what, message) {
            root.accountFailed = true
            root.accountMessage = message
        }
    }

    DietPopup { id: dietEditor }

    Column {
        id: column
        x: Preferences.spacingLarge
        y: Preferences.spacingLarge
        width: Math.min(root.width - 2 * Preferences.spacingLarge, 760)
        spacing: Preferences.spacingLarge

        Text {
            text: Words.settingsTitle
            color: Preferences.textPrimary
            font.family: Preferences.headingFont
            font.weight: Font.Black
            font.pixelSize: Preferences.fontSizeDisplay
        }

        Section {
            title: Words.accountTitle

            Row {
                width: parent.width
                spacing: Preferences.spacingSmall
                InputField {
                    id: username
                    objectName: "usernameField"
                    width: 280
                    text: Session.username
                    placeholderText: Words.username
                    maximumLength: 32
                    // Enter does what the button does, including being refused when the button is.
                    onAccepted: if (usernameSave.enabled) usernameSave.clicked()
                }
                ActionButton {
                    id: usernameSave
                    objectName: "usernameSave"
                    text: Words.changeUsername
                    onClicked: Session.changeUsername(username.text)
                }
            }
            Caption { text: Words.usernameHint }

            Row {
                width: parent.width
                spacing: Preferences.spacingSmall
                InputField {
                    id: currentPassword
                    objectName: "currentPasswordField"
                    width: 220
                    echoMode: TextInput.Password
                    placeholderText: Words.currentPassword
                    onAccepted: if (passwordSave.enabled) passwordSave.clicked()
                }
                InputField {
                    id: newPassword
                    objectName: "newPasswordField"
                    width: 220
                    echoMode: TextInput.Password
                    placeholderText: Words.newPassword
                    maximumLength: 256
                    onAccepted: if (passwordSave.enabled) passwordSave.clicked()
                }
                ActionButton {
                    id: passwordSave
                    objectName: "passwordSave"
                    text: Words.changePassword
                    enabled: currentPassword.text.length > 0 && newPassword.text.length > 0
                    onClicked: Session.changePassword(currentPassword.text, newPassword.text)
                }
            }
            Caption { text: Words.passwordHint }

            Text {
                objectName: "accountMessage"
                visible: root.accountMessage.length > 0
                width: parent.width
                wrapMode: Text.Wrap
                text: root.accountMessage
                color: root.accountFailed ? Preferences.dangerColor : Preferences.successColor
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeLabel
            }

            Text {
                topPadding: Preferences.spacingSmall
                text: Words.devicesTitle
                color: Preferences.textSecondary
                font.family: Preferences.appFont
                font.bold: true
                font.pixelSize: Preferences.fontSizeLabel
            }
            Repeater {
                model: Session.devices
                delegate: Row {
                    required property var modelData
                    objectName: "device-" + modelData.id
                    spacing: Preferences.spacingSmall
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 360
                        text: modelData.label + " · " + (modelData.current ? Words.thisDevice
                              : (modelData.lastSignIn ? Words.lastSignedIn(Days.label(String(modelData.lastSignIn).slice(0, 10),
                                                                                       Saved.today()))
                                                      : Words.notSignedInLately))
                        color: Preferences.textPrimary
                        font.family: Preferences.appFont
                        font.pixelSize: Preferences.fontSizeBody
                    }
                    ActionButton {
                        objectName: "forget-" + modelData.id
                        visible: !modelData.current
                        danger: true
                        text: Words.forget
                        onClicked: Session.removeDevice(modelData.id)
                    }
                }
            }
            Text {
                visible: Session.devicesError.length > 0
                text: Session.devicesError
                color: Preferences.dangerColor
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeLabel
            }

            ActionButton {
                objectName: "settingsSignOut"
                danger: true
                text: Words.signOut
                onClicked: Session.logout()
            }
        }

        Section {
            title: Words.dietTitle
            Row {
                spacing: Preferences.spacingSmall
                Text {
                    objectName: "settingsDiet"
                    anchors.verticalCenter: parent.verticalCenter
                    text: Diet.hasProfile ? Words.dietChip(Diet.diets, Diet.avoid) : Words.dietNone
                    color: Preferences.textPrimary
                    font.family: Preferences.appFont
                    font.pixelSize: Preferences.fontSizeBody
                }
                Chip {
                    objectName: "settingsDietEdit"
                    text: Words.dietEdit
                    onClicked: dietEditor.open()
                }
            }
        }

        Section {
            title: Words.unitsTitle
            Row {
                spacing: 6
                Chip {
                    objectName: "settings-units-metric"
                    text: Words.metric
                    selected: Preferences.units === "metric"
                    onClicked: Preferences.units = "metric"
                }
                Chip {
                    objectName: "settings-units-us"
                    text: Words.us
                    selected: Preferences.units === "us"
                    onClicked: Preferences.units = "us"
                }
            }
        }

        Section {
            title: Words.coloursTitle
            Row {
                spacing: Preferences.spacingSmall
                ActionButton {
                    objectName: "resetColours"
                    danger: true
                    text: Words.resetColours
                    onClicked: Preferences.resetColours()
                }
                Caption { anchors.verticalCenter: parent.verticalCenter; text: Words.resetColoursHint }
            }
        }

        Section {
            title: Words.connectionTitle
            Text {
                objectName: "connectionState"
                text: !Session.online ? Words.notConnected
                      : (Session.connectionRoute === "lan" ? Words.connectedAtHome : Words.connectedAway)
                color: Session.online ? Preferences.textPrimary : Preferences.dangerColor
                font.family: Preferences.appFont
                font.pixelSize: Preferences.fontSizeBody
            }
        }
    }

    // A card of settings under its heading.
    component Section: Rectangle {
        id: section
        property string title: ""
        default property alias content: body.data
        width: parent ? parent.width : 0
        height: body.implicitHeight + 2 * Preferences.spacingMedium
        radius: Preferences.cornerRadius
        color: Preferences.backgroundSecondary

        Column {
            id: body
            x: Preferences.spacingMedium
            y: Preferences.spacingMedium
            width: parent.width - 2 * Preferences.spacingMedium
            spacing: Preferences.spacingSmall

            Text {
                text: section.title
                color: Preferences.accentColor
                font.family: Preferences.headingFont
                font.weight: Font.Black
                font.pixelSize: Preferences.fontSizeHeading
            }
        }
    }

    component Caption: Text {
        color: Preferences.textMuted
        font.family: Preferences.appFont
        font.pixelSize: Preferences.fontSizeCaption
    }
}
