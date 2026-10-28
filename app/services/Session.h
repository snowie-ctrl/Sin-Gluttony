// Copied from Pageturner Pageturner/services/Session.h at ad9342e; the account folder holds saved recipes instead of downloads.
#pragma once
#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QTimer>
#include <QVariantList>

#include "api/Api.h"
#include "services/AccountStore.h"


// Who is signed in, and signing in and out.
//
// A known device signs in by itself (/device/identify, matched on the device
// fingerprint); otherwise the sign-in page asks for a username and password,
// and a new account also needs a login key. Signing out tells the server to
// forget the device, so it asks again next time.
//
// With no server at start, the account signed in last opens offline when this
// device holds one of its saved recipes; otherwise the sign-in page says the
// server cannot be reached. When the server answers again the device
// identifies again: the same account carries on (reconnected); another account
// ends the offline one (its files stay on disk) and the device signs in as the
// account the server names; a device the server no longer knows goes back to
// signing in.
class Session : public QObject
{
    Q_OBJECT

    Q_PROPERTY(bool authenticated READ authenticated NOTIFY authChanged)
    Q_PROPERTY(int uid READ uid NOTIFY authChanged)
    Q_PROPERTY(QString username READ username NOTIFY authChanged)
    // True while a sign-in is on its way, so the page can show it is working
    // rather than flash the form at a device that will sign in by itself.
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    // "lan" when the app reaches the server on the home network, "public" otherwise.
    Q_PROPERTY(QString connectionRoute READ connectionRoute NOTIFY connectionRouteChanged)
    // Whether the server answers (Api's view); the shell's banner shows while it does not.
    Q_PROPERTY(bool online READ online NOTIFY onlineChanged)
    // Signed in from what this device keeps, with no server and no token:
    // reading comes from downloads and reports wait in the queue.
    Q_PROPERTY(bool offline READ offline NOTIFY authChanged)
    // No server at start and nothing kept to read without it: the sign-in
    // page shows the connection screen.
    Q_PROPERTY(bool unreachable READ unreachable NOTIFY unreachableChanged)
    // This account's devices that sign in by themselves:
    // [{id, label, current, lastSignIn}], newest first. The id is an opaque
    // name for the device, never its fingerprint.
    Q_PROPERTY(QVariantList devices READ devices NOTIFY devicesChanged)
    Q_PROPERTY(bool devicesLoading READ devicesLoading NOTIFY devicesChanged)
    // Why the last load failed; the devices shown stay as they were.
    Q_PROPERTY(QString devicesError READ devicesError NOTIFY devicesChanged)

public:
    explicit Session(Api &api, QObject *parent = nullptr);

    // The account's folder (AccountStore): signing in opens it, signing out
    // deletes it, an ended session closes it.
    void setStore(AccountStore *store) { m_store = store; }
    bool online() const { return m_api.online(); }
    bool offline() const { return m_offline; }
    bool unreachable() const { return m_unreachable; }
    // How long a device that started offline waits before asking the server
    // again when it answered with an error (15 s); tests shorten it.
    void setIdentifyRetry(int ms) { m_identifyRetry.setInterval(ms); }

    bool authenticated() const { return m_uid > 0; }
    int uid() const { return m_uid; }
    QString username() const { return m_username; }
    bool busy() const { return m_busy; }
    QString connectionRoute() const { return m_api.onLan() ? QStringLiteral("lan") : QStringLiteral("public"); }
    QVariantList devices() const { return m_devices; }
    bool devicesLoading() const { return m_devicesLoading; }
    QString devicesError() const { return m_devicesError; }

    Q_INVOKABLE void identifyDevice();
    // The connection screen's Retry.
    Q_INVOKABLE void retry();
    Q_INVOKABLE void login(const QString &username, const QString &password, const QString &key);
    // Deletes what the account keeps on this device. Without a session to tell
    // the server with (offline, a server that has stopped answering, or a
    // session it ended as this was asked for), a pending sign-out is left
    // (AccountStore::setPendingLogout) and told the next time the server
    // answers; until then the device never signs in by itself. Otherwise,
    // with nobody signed in, it does nothing.
    Q_INVOKABLE void logout();
    Q_INVOKABLE void changeUsername(const QString &username);
    // Other devices' sessions end on the server; this one carries on.
    Q_INVOKABLE void changePassword(const QString &current, const QString &password);
    Q_INVOKABLE void loadDevices();
    // Another device: it stops signing in by itself. This device signs out instead.
    Q_INVOKABLE void removeDevice(const QString &id);

signals:
    void authChanged();
    void busyChanged();
    void connectionRouteChanged();
    void loginSucceeded();
    void loginFailed(const QString &code, const QString &message);
    void signedOut();
    void onlineChanged();
    void unreachableChanged();
    // Opened offline as the account signed in last.
    void startedOffline();
    // An offline start reached the server as the same account: nothing on screen changes.
    void reconnected();
    void devicesChanged();
    // what is "username", "password" or "device".
    void accountUpdated(const QString &what);
    void accountFailed(const QString &what, const QString &message);

private:
    bool apply(const QJsonObject &payload);
    void setBusy(bool busy);
    void forget();
    void noAnswer();
    void setUnreachable(bool unreachable);
    void leavePendingLogout(int uid);
    void tellServerSignedOut(const QString &token);
    bool hasPendingLogout() const { return m_store && m_store->pendingLogout() > 0; }
    // Started offline, on the connection screen, or with a sign-out still to
    // tell: the device asks the server who it is again whenever it can, until
    // it is signed in, sent to sign in, or the sign-out is told.
    bool waitingForServer() const { return m_offline || m_unreachable || hasPendingLogout(); }

    Api &m_api;
    AccountStore *m_store = nullptr;
    bool m_offline = false;
    bool m_unreachable = false;
    QTimer m_identifyRetry;
    // Identify requests (and a pending sign-out's) on their way.
    int m_identifying = 0;
    // The account a 401 just ended, until the next sign-in: a sign-out asked
    // for meanwhile clears it (logout()).
    int m_endedUid = -1;
    int m_uid = -1;
    QString m_username;
    bool m_busy = false;
    QVariantList m_devices;
    bool m_devicesLoading = false;
    QString m_devicesError;
    int m_devicesGeneration = 0;
    // Bumped by forget(): an account reply for the last reader is dropped.
    int m_generation = 0;
};
