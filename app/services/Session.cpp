// Copied from Pageturner Pageturner/services/Session.cpp at ad9342e; the account folder holds saved recipes instead of downloads; usernames are 3 to 32 characters, as Gluttony's server takes them.
#include "services/Session.h"
#include "api/AppConfig.h"

#include <QDebug>
#include <QJsonArray>
#include <QUrlQuery>

#include <utility>


Session::Session(Api &api, QObject *parent) : QObject(parent), m_api(api)
{
    connect(&m_api, &Api::routeChanged, this, &Session::connectionRouteChanged);

    // Back from an outage: an offline start, or the connection screen, asks
    // the server who this device is again.
    connect(&m_api, &Api::onlineChanged, this, [this]() {
        emit onlineChanged();
        if (m_api.online() && waitingForServer() && !m_busy)
            identifyDevice();
    });
    // A server that answered with an error (busy, failing) instead of who this
    // device is gives no other sign that it is worth asking again, so the
    // device asks again by itself until it is signed in or sent to sign in.
    m_identifyRetry.setSingleShot(true);
    m_identifyRetry.setInterval(15000);
    connect(&m_identifyRetry, &QTimer::timeout, this, [this]() {
        if (waitingForServer() && !m_busy)
            identifyDevice();
    });

    // The server has already dropped the session, so there is nothing to
    // tell it: forget it here and go back to the sign-in page.
    connect(&m_api, &Api::unauthorised, this, [this]() {
        if (!authenticated())
            return;
        qWarning() << "[auth] the server ended the session";
        // Kept, not deleted; but a sign-out the reader asked for just before
        // (its flush met this 401) still clears it (logout()).
        m_endedUid = m_uid;
        forget();
    });
}

void Session::setBusy(bool busy)
{
    if (busy == m_busy)
        return;
    m_busy = busy;
    emit busyChanged();
}

// A reply that is "ok" but names no user is not a sign-in: signed in means
// a positive UID, so nothing is changed and the caller says what went wrong.
bool Session::apply(const QJsonObject &payload)
{
    const int uid = payload.value("UID").toInt(-1);
    if (uid <= 0)
        return false;
    m_uid = uid;
    m_username = payload.value("username").toString();
    m_offline = false;
    m_endedUid = -1;
    m_identifyRetry.stop();
    // The account's folder before its token: what follows the folder (the
    // progress queue's file, the downloads folder, the download queue) has
    // moved to this account before anything can be sent as it. Downloads
    // waits for a token, and the token's arrival sets it going.
    if (m_store)
        m_store->open(m_uid, m_username);
    m_api.setSessionToken(payload.value("token").toString());
    emit authChanged();
    return true;
}

void Session::identifyDevice()
{
    ++m_identifying;
    setBusy(true);
    // A sign-out while this is on its way makes its answer the last reader's:
    // it must never sign the device back in or open the folder just deleted.
    const int generation = m_generation;
    // Sign-in waits until the app knows whether to use the home address or
    // the public one, so it never goes to an address that is about to change.
    m_api.whenReady([this, generation]() {
        QJsonObject body;
        body.insert("fingerprint", AppConfig::instance().deviceFingerprint());

        m_api.post("/device/identify", body, [this, generation](const Api::Result &result) {
            // Busy until the last of them is answered (a sign-out can send
            // another while one is still on its way).
            setBusy(--m_identifying > 0);
            if (generation != m_generation)
                return;
            if (!result.ok) {
                // No server: what this device keeps, or the connection screen.
                if (!m_api.online()) {
                    noAnswer();
                    return;
                }
                // Started offline (or on the connection screen) and the server
                // is there but did not say: asked again in a while, never left
                // online with no token.
                if (waitingForServer())
                    m_identifyRetry.start();
                // Not fatal: the user can still sign in by hand.
                qDebug() << "[auth] device not recognised:" << result.error;
                return;
            }
            setUnreachable(false);
            if (result.object.value("status").toString() == QLatin1String("new")) {
                // A sign-out the server was not told about has nothing left to
                // tell: the device is unknown to it.
                if (hasPendingLogout())
                    m_store->clearPendingLogout();
                // Forgotten while away: back to signing in. What the account
                // keeps stays on disk, its queue sent when it signs in again.
                if (m_offline)
                    forget();
                // The server no longer trusts this device (removed in Settings,
                // as a lost device is signed out), so no start without it opens
                // the account offline any more; its next sign-in names it again.
                // A session the server ended (a 401) is not this: same device,
                // still known, so that keeps its offline start.
                if (m_store && !authenticated())
                    m_store->forgetLast();
                return;
            }
            // Signed out while the server could not be told: it is told now,
            // with the session this answer brings, and the device stays signed
            // out (nothing is opened).
            if (hasPendingLogout()) {
                tellServerSignedOut(result.object.value("token").toString());
                return;
            }
            const bool resumed = m_offline && result.object.value("UID").toInt(-1) == m_uid;
            // Another account on this device now: the offline one ends first.
            if (m_offline && !resumed)
                forget();
            if (!apply(result.object)) {
                qWarning() << "[auth] device reply had no user id";
                return;
            }
            if (resumed)
                emit reconnected();
            else
                emit loginSucceeded();
        });
    });
}

void Session::tellServerSignedOut(const QString &token)
{
    if (token.isEmpty()) {
        qWarning() << "[auth] device reply had no session to sign out with";
        m_identifyRetry.start();
        return;
    }
    // Counted as part of identifying: the sign-in page waits on it rather
    // than offering the form to a device that is still being signed out.
    ++m_identifying;
    setBusy(true);
    const int generation = m_generation;
    QJsonObject body;
    body.insert("fingerprint", AppConfig::instance().deviceFingerprint());
    m_api.postAs(token, "/auth/logout", body, [this, generation](const Api::Result &result) {
        setBusy(--m_identifying > 0);
        if (generation != m_generation)
            return;
        if (result.ok) {
            m_store->clearPendingLogout();
            return;
        }
        // Kept, and told again the next time the server answers.
        qWarning() << "[auth] a sign-out made without the server is not on it yet:" << result.error;
        if (m_api.online())
            m_identifyRetry.start();
    });
}

void Session::retry()
{
    if (!m_busy)
        identifyDevice();
}

void Session::noAnswer()
{
    if (m_offline || authenticated())
        return;
    // A sign-out still to be told to the server: nothing opens by itself.
    const QVariantMap account = m_store && !hasPendingLogout() ? m_store->offlineAccount() : QVariantMap();
    if (account.isEmpty()) {
        setUnreachable(true);
        return;
    }
    m_uid = account.value("UID").toInt();
    m_username = account.value("username").toString();
    m_offline = true;
    m_store->open(m_uid, m_username);
    setUnreachable(false);
    emit authChanged();
    emit startedOffline();
}

void Session::setUnreachable(bool unreachable)
{
    if (unreachable == m_unreachable)
        return;
    m_unreachable = unreachable;
    emit unreachableChanged();
}

void Session::login(const QString &username, const QString &password, const QString &key)
{
    // Enter and a click, or two Enters, must not send two sign-ins.
    if (m_busy)
        return;
    setBusy(true);
    m_api.whenReady([this, username, password, key]() {
        QJsonObject body;
        body.insert("username", username.trimmed());
        body.insert("password", password);
        body.insert("fingerprint", AppConfig::instance().deviceFingerprint());
        if (!key.trimmed().isEmpty())
            body.insert("key", key.trimmed());

        m_api.post("/auth", body, [this](const Api::Result &result) {
            setBusy(false);
            if (!result.ok) {
                QString code = result.object.value("status").toString();
                if (code.isEmpty() || (code == QLatin1String("error") && result.httpStatus == 0))
                    code = QStringLiteral("network");

                QString message;
                if (code == QLatin1String("invalid_credentials"))
                    message = QStringLiteral("Wrong username or password");
                else if (code == QLatin1String("invalid_key"))
                    message = QStringLiteral("That key has been used or does not exist");
                else if (code == QLatin1String("username_taken"))
                    message = QStringLiteral("That username is taken");
                else if (code == QLatin1String("network"))
                    message = QStringLiteral("Could not reach the server");
                else
                    message = result.error;

                emit loginFailed(code, message);
                return;
            }

            if (!apply(result.object)) {
                emit loginFailed(QStringLiteral("bad_reply"),
                                 QStringLiteral("The server sent an unexpected answer"));
                return;
            }
            // Signed in by hand: the reader wants this device signed in, so a
            // sign-out still to be told to the server no longer stands.
            if (hasPendingLogout())
                m_store->clearPendingLogout();
            emit loginSucceeded();
        });
    });
}

void Session::logout()
{
    if (!authenticated()) {
        // The server ended the session while this sign-out was on its way
        // (its flush met the 401): what the reader asked for still happens.
        // The account is closed already, so nothing follows its folder.
        const int ended = std::exchange(m_endedUid, -1);
        if (ended > 0 && m_store) {
            m_store->wipeAccount(ended);
            leavePendingLogout(ended);
        }
        return;
    }
    const int uid = m_uid;
    // With no session (an offline start), or a server that has stopped
    // answering since, the server cannot be told now: the sign-out is left
    // for when it can, or it would take the device straight back in.
    const bool tellNow = !m_offline && m_api.online();
    // Sent before the token is dropped: the request is built (headers and
    // all) synchronously here, so it leaves with the right session.
    if (tellNow) {
        QJsonObject body;
        body.insert("fingerprint", AppConfig::instance().deviceFingerprint());
        m_api.post("/auth/logout", body, [this, uid](const Api::Result &result) {
            if (result.ok)
                return;
            qWarning() << "[auth] logout not recorded on the server:" << result.error;
            // No answer, a 5xx or a 401: the server still knows the device and
            // would sign it straight back in at the next start, so the sign-out
            // is left for it like one made offline. Not if someone has signed
            // in by hand since: that reader wants the device signed in.
            if (!authenticated())
                leavePendingLogout(uid);
        });
    }
    // Downloads, snapshots and queues belong to the account and leave this
    // device with it (Settings has already tried to send the queue). Everyone
    // following the folder lets go of it before it is deleted (AccountStore).
    if (m_store)
        m_store->wipe();
    forget();
    if (!tellNow)
        leavePendingLogout(uid);
}

void Session::leavePendingLogout(int uid)
{
    // Otherwise the server, still knowing the device, would sign it straight
    // back in the next time it answers.
    if (m_store)
        m_store->setPendingLogout(uid);
    // No server: nothing is left to read, so the connection screen; with one,
    // it is told now.
    if (!m_api.online())
        setUnreachable(true);
    else if (hasPendingLogout())
        identifyDevice();
}

void Session::forget()
{
    m_uid = -1;
    m_username.clear();
    m_offline = false;
    m_identifyRetry.stop();
    // Closed, not deleted: an ended session or a forgotten device keeps what
    // the account kept, for when it signs in again. Closed before the token
    // goes, so a report refused with 401 finds its own account's queue file
    // (Progress keeps it there) and nothing follows the token into the folder.
    if (m_store)
        m_store->close();
    m_api.setSessionToken(QString());
    // Nothing of this account is shown to the next one, nor any answer for it.
    ++m_generation;
    ++m_devicesGeneration;
    m_devices.clear();
    m_devicesLoading = false;
    m_devicesError.clear();
    emit devicesChanged();
    emit authChanged();
    emit signedOut();
}

void Session::changeUsername(const QString &username)
{
    const QString name = username.trimmed();
    // The server's limits (gluttonyUserRoutes.USERNAME_MIN and USERNAME_MAX), so it is never asked for one it refuses.
    // Counted in code points, as the server counts them; Qt's own size() counts an emoji twice.
    const qsizetype length = name.toUcs4().size();
    if (length < 3 || length > 32) {
        emit accountFailed(QStringLiteral("username"), QStringLiteral("A username is 3 to 32 characters"));
        return;
    }
    const int generation = m_generation;
    m_api.post("/user/username", QJsonObject{{"username", name}}, [this, generation, name](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (!result.ok) {
            const bool taken = result.object.value("status").toString() == QLatin1String("username_taken");
            emit accountFailed(QStringLiteral("username"),
                               taken ? QStringLiteral("That username is taken") : reasonOf(result));
            return;
        }
        // The account routes answer beside status, not inside data.
        m_username = result.object.value("username").toString(name);
        if (m_store)
            m_store->open(m_uid, m_username);
        emit authChanged();
        emit accountUpdated(QStringLiteral("username"));
    });
}

void Session::changePassword(const QString &current, const QString &password)
{
    if (password.size() < 8 || password.size() > 256) {
        emit accountFailed(QStringLiteral("password"), QStringLiteral("A new password is 8 to 256 characters"));
        return;
    }
    const int generation = m_generation;
    m_api.post("/user/password", QJsonObject{{"current", current}, {"password", password}},
               [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (!result.ok) {
            QString message = reasonOf(result);
            if (result.httpStatus == 401)
                message = QStringLiteral("Your current password is not right");
            else if (result.httpStatus == 429)
                message = QStringLiteral("Too many tries; wait a minute and try again");
            emit accountFailed(QStringLiteral("password"), message);
            return;
        }
        emit accountUpdated(QStringLiteral("password"));
    });
}

void Session::loadDevices()
{
    const int generation = ++m_devicesGeneration;
    m_devicesLoading = true;
    m_devicesError.clear();
    emit devicesChanged();
    m_api.get("/devices", QUrlQuery(), [this, generation](const Api::Result &result) {
        if (generation != m_devicesGeneration)
            return;
        m_devicesLoading = false;
        if (result.ok)
            m_devices = result.object.value("data").toArray().toVariantList();
        else
            m_devicesError = reasonOf(result);
        emit devicesChanged();
    });
}

void Session::removeDevice(const QString &id)
{
    const int generation = m_generation;
    m_api.post("/devices/remove", QJsonObject{{"id", id}}, [this, generation](const Api::Result &result) {
        if (generation != m_generation)
            return;
        if (!result.ok) {
            // The server refuses the device asking: that one signs out.
            emit accountFailed(QStringLiteral("device"), result.httpStatus == 400
                                                             ? QStringLiteral("This device signs out instead")
                                                             : reasonOf(result));
            return;
        }
        emit accountUpdated(QStringLiteral("device"));
        loadDevices();
    });
}
