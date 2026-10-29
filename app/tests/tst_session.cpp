// Copied from Pageturner Pageturner/tests/tst_session.cpp at ad9342e; Gluttony paths; an offline start needs a saved recipe, not a download; usernames are 3 to 32 characters.
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include "FakeServer.h"
#include "api/Api.h"
#include "api/SessionAuth.h"
#include "services/AccountStore.h"
#include "services/Session.h"


static QString baseOf(const FakeServer &server)
{
    return QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server.serverPort());
}

static const QByteArray signedIn = R"({"status":"ok","UID":7,"username":"stub","token":"tok"})";

static const QString usernamePath = QStringLiteral("/api/gluttony/user/username");
static const QString passwordPath = QStringLiteral("/api/gluttony/user/password");
static const QString devicesPath = QStringLiteral("/api/gluttony/devices");
static const QString removePath = QStringLiteral("/api/gluttony/devices/remove");

static const QByteArray devicesJson = R"({"status":"ok","data":[
 {"id":"f00dfeedf00dfeed","label":"f00dfeed","current":true,"lastSignIn":"2026-10-12T08:00:00Z"},
 {"id":"0a1b2c3d4e5f6071","label":"0a1b2c3d","current":false,"lastSignIn":null}]})";

static int requestsTo(const FakeServer &server, const QString &path)
{
    int n = 0;
    for (const QUrl &url : server.requests)
        if (url.path() == path)
            ++n;
    return n;
}

static QJsonObject lastBody(const FakeServer &server, const QString &path)
{
    for (int i = server.requests.size() - 1; i >= 0; --i)
        if (server.requests[i].path() == path)
            return QJsonDocument::fromJson(server.bodies[i]).object();
    return {};
}

// Signs in the way the app does at start, so the calls carry a token. A free
// function, not a slot: QTest would run a slot as a test of its own.
static void signIn(FakeServer &server, Session &session)
{
    server.responses["/api/gluttony/device/identify"] = signedIn;
    session.identifyDevice();
    QTRY_VERIFY(session.authenticated());
}

static const QString deadBase = QStringLiteral("http://127.0.0.1:1/api/gluttony");

// What a reader left on this device: account 7 ("stub") with one saved recipe.
static void keepARecipe(AccountStore &store)
{
    store.open(7, "stub");
    QVERIFY(AccountStore::writeJson(store.recipeFile(1002), QJsonObject{{"id", 1002}}));
    store.close();
}


class TestSession : public QObject
{
    Q_OBJECT

    QTemporaryDir dir;

private slots:
    void initTestCase()
    {
        // AppConfig reads this once; it only has to exist so it stays quiet.
        const QString secrets = dir.filePath("secrets.json");
        QFile file(secrets);
        QVERIFY(file.open(QIODevice::WriteOnly));
        file.write("{\"apiBase\": \"http://127.0.0.1:1/api/gluttony\"}");
        file.close();
        qputenv("GLUTTONY_SECRETS", secrets.toUtf8());
    }

    void anUnknownDeviceStaysSignedOut()
    {
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = R"({"status":"new"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);

        session.identifyDevice();
        QVERIFY(session.busy());
        QTRY_VERIFY(!session.busy());
        QVERIFY(!session.authenticated());
        QCOMPARE(succeeded.count(), 0);
    }

    void aKnownDeviceSignsInByItself()
    {
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = signedIn;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);

        session.identifyDevice();
        QTRY_COMPARE(succeeded.count(), 1);
        QVERIFY(session.authenticated());
        QCOMPARE(session.uid(), 7);
        QCOMPARE(session.username(), QStringLiteral("stub"));
        QCOMPARE(api.sessionToken(), QStringLiteral("tok"));
        // The fingerprint goes in the body, as the server matches on it.
        QVERIFY(server.bodies.last().contains("\"fingerprint\""));
    }

    void aWrongPasswordSaysSo()
    {
        FakeServer server;
        server.statuses["/api/gluttony/auth"] = 401;
        server.responses["/api/gluttony/auth"] = R"({"status":"invalid_credentials"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy failed(&session, &Session::loginFailed);

        session.login("stub", "nope", QString());
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("invalid_credentials"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("Wrong username or password"));
        QVERIFY(!session.authenticated());
        QVERIFY(!session.busy());
    }

    void aUsedKeySaysSo()
    {
        FakeServer server;
        server.statuses["/api/gluttony/auth"] = 403;
        server.responses["/api/gluttony/auth"] = R"({"status":"invalid_key"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy failed(&session, &Session::loginFailed);

        session.login("newbie", "pw", "used-key");
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("That key has been used or does not exist"));
        QVERIFY(server.bodies.last().contains("\"key\":\"used-key\""));
    }

    void anUnreachableServerSaysSo()
    {
        Api api;
        api.setBases(QString(), "http://127.0.0.1:1/api/gluttony");
        Session session(api);
        QSignalSpy failed(&session, &Session::loginFailed);

        session.login("stub", "stub", QString());
        QTRY_COMPARE_WITH_TIMEOUT(failed.count(), 1, 10000);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("network"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("Could not reach the server"));
    }

    void aSecondSignInWhileBusyIsIgnored()
    {
        FakeServer server;
        server.responses["/api/gluttony/auth"] = signedIn;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);

        // Enter pressed twice, or Enter and a click: one request, not two.
        session.login("stub", "stub", QString());
        session.login("stub", "stub", QString());
        QTRY_COMPARE(succeeded.count(), 1);
        QTest::qWait(200);
        QCOMPARE(succeeded.count(), 1);
        int authRequests = 0;
        for (const QUrl &url : server.requests)
            if (url.path() == QStringLiteral("/api/gluttony/auth"))
                ++authRequests;
        QCOMPARE(authRequests, 1);
    }

    void aReplyWithoutAUidIsNotASignIn()
    {
        FakeServer server;
        server.responses["/api/gluttony/auth"] = R"({"status":"ok","username":"stub","token":"tok"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);
        QSignalSpy failed(&session, &Session::loginFailed);

        session.login("stub", "stub", QString());
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("bad_reply"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("The server sent an unexpected answer"));
        QCOMPARE(succeeded.count(), 0);
        QVERIFY(!session.authenticated());
        QVERIFY(api.sessionToken().isEmpty());
        QVERIFY(!session.busy());
    }

    void aDeviceReplyWithoutAUidStaysSignedOut()
    {
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = R"({"status":"ok","token":"tok"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);

        QTest::ignoreMessage(QtWarningMsg, "[auth] device reply had no user id");
        session.identifyDevice();
        QTRY_VERIFY(!session.busy());
        QCOMPARE(succeeded.count(), 0);
        QVERIFY(!session.authenticated());
        QVERIFY(api.sessionToken().isEmpty());
    }

    void signingOutTellsTheServerFirst()
    {
        FakeServer server;
        server.responses["/api/gluttony/auth"] = signedIn;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy signedOut(&session, &Session::signedOut);

        session.login("stub", "stub", QString());
        QTRY_VERIFY(session.authenticated());

        session.logout();
        QVERIFY(!session.authenticated());
        QVERIFY(api.sessionToken().isEmpty());
        QCOMPARE(signedOut.count(), 1);
        // The logout request left with the token, before it was dropped.
        QTRY_COMPARE(server.requests.last().path(), QStringLiteral("/api/gluttony/auth/logout"));
        QVERIFY(server.heads.last().contains("X-Session-Token: tok"));
    }

    void anEndedSessionSignsOut()
    {
        FakeServer server;
        server.responses["/api/gluttony/auth"] = signedIn;
        server.statuses["/api/gluttony/series/full"] = 401;
        server.responses["/api/gluttony/series/full"] = R"({"status":"error","message":"not signed in"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        QSignalSpy signedOut(&session, &Session::signedOut);

        session.login("stub", "stub", QString());
        QTRY_VERIFY(session.authenticated());
        QTest::ignoreMessage(QtWarningMsg, "[auth] the server ended the session");
        api.get("/series/full", {}, nullptr);
        QTRY_COMPARE(signedOut.count(), 1);
        QVERIFY(!session.authenticated());
        // The server already forgot the session, so nothing is sent to it.
        QVERIFY(server.requests.last().path() != QStringLiteral("/api/gluttony/auth/logout"));
    }

    void aNewUsernameIsTakenOnAtOnce()
    {
        FakeServer server;
        server.responses[usernamePath] = R"({"status":"ok","username":"reader"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy updated(&session, &Session::accountUpdated);
        QSignalSpy auth(&session, &Session::authChanged);

        session.changeUsername("  reader  ");
        QTRY_COMPARE(updated.count(), 1);
        QCOMPARE(updated.first().at(0).toString(), QStringLiteral("username"));
        QCOMPARE(session.username(), QStringLiteral("reader"));
        QCOMPARE(auth.count(), 1);
        QCOMPARE(lastBody(server, usernamePath).value("username").toString(), QStringLiteral("reader"));
    }

    void aTakenUsernameSaysSo()
    {
        FakeServer server;
        server.statuses[usernamePath] = 409;
        server.responses[usernamePath] = R"({"status":"username_taken"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy failed(&session, &Session::accountFailed);

        session.changeUsername("taken");
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("username"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("That username is taken"));
        QCOMPARE(session.username(), QStringLiteral("stub"));
    }

    void aUsernameOutsideThreeToThirtyTwoAsksNothing()
    {
        FakeServer server;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy failed(&session, &Session::accountFailed);

        session.changeUsername("   ");
        session.changeUsername(" ab ");
        session.changeUsername(QString(33, QLatin1Char('x')));
        QCOMPARE(failed.count(), 3);
        // The server's own limits (gluttonyUserRoutes.USERNAME_MIN and _MAX), in the app's words.
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("A username is 3 to 32 characters"));
        QTest::qWait(50);
        QCOMPARE(requestsTo(server, usernamePath), 0);
    }

    void aUsernameIsCountedInCharactersAsTheServerCountsThem()
    {
        FakeServer server;
        server.responses[usernamePath] = R"({"status":"ok","username":"x"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy failed(&session, &Session::accountFailed);
        QSignalSpy updated(&session, &Session::accountUpdated);
        // One character to the server, two UTF-16 units to Qt.
        const QString grin = QString::fromUtf8("\xF0\x9F\x98\x80");

        session.changeUsername(grin.repeated(2));
        QCOMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("A username is 3 to 32 characters"));
        QTest::qWait(50);
        QCOMPARE(requestsTo(server, usernamePath), 0);

        session.changeUsername(grin.repeated(3));
        QTRY_COMPARE(updated.count(), 1);
        QCOMPARE(lastBody(server, usernamePath).value("username").toString(), grin.repeated(3));
        session.changeUsername(grin.repeated(32));
        QTRY_COMPARE(updated.count(), 2);
        QCOMPARE(requestsTo(server, usernamePath), 2);
        QCOMPARE(failed.count(), 1);
    }

    void aWrongCurrentPasswordKeepsTheSession()
    {
        FakeServer server;
        server.statuses[passwordPath] = 401;
        server.responses[passwordPath] = R"({"status":"invalid_credentials"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy failed(&session, &Session::accountFailed);
        QSignalSpy signedOut(&session, &Session::signedOut);

        session.changePassword("nope", "longenough");
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("password"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("Your current password is not right"));
        QVERIFY(session.authenticated());
        QCOMPARE(signedOut.count(), 0);
    }

    void aShortPasswordAsksNothing()
    {
        FakeServer server;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy failed(&session, &Session::accountFailed);

        session.changePassword("stub", "short");
        QCOMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("A new password is 8 to 256 characters"));
        QTest::qWait(50);
        QCOMPARE(requestsTo(server, passwordPath), 0);
    }

    void aChangedPasswordIsAnnounced()
    {
        FakeServer server;
        server.responses[passwordPath] = R"({"status":"ok"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy updated(&session, &Session::accountUpdated);

        session.changePassword("stub", "longenough");
        QTRY_COMPARE(updated.count(), 1);
        QCOMPARE(updated.first().at(0).toString(), QStringLiteral("password"));
        const QJsonObject body = lastBody(server, passwordPath);
        QCOMPARE(body.value("current").toString(), QStringLiteral("stub"));
        QCOMPARE(body.value("password").toString(), QStringLiteral("longenough"));
    }

    void devicesAreListedAndRemoved()
    {
        FakeServer server;
        server.responses[devicesPath] = devicesJson;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy updated(&session, &Session::accountUpdated);

        session.loadDevices();
        QVERIFY(session.devicesLoading());
        QTRY_COMPARE(session.devices().size(), 2);
        QVERIFY(!session.devicesLoading());
        QCOMPARE(session.devices().at(0).toMap().value("current").toBool(), true);
        QCOMPARE(session.devices().at(1).toMap().value("id").toString(), QStringLiteral("0a1b2c3d4e5f6071"));

        session.removeDevice("0a1b2c3d4e5f6071");
        QTRY_COMPARE(updated.count(), 1);
        QCOMPARE(updated.first().at(0).toString(), QStringLiteral("device"));
        QCOMPARE(lastBody(server, removePath).value("id").toString(), QStringLiteral("0a1b2c3d4e5f6071"));
        // The device is named by its opaque id, never by a fingerprint.
        QVERIFY(!lastBody(server, removePath).contains("fingerprint"));
        // And the list is asked for again.
        QTRY_COMPARE(requestsTo(server, devicesPath), 2);
    }

    void theCurrentDeviceSignsOutInstead()
    {
        FakeServer server;
        server.statuses[removePath] = 400;
        server.responses[removePath] = R"({"status":"error","message":"this is the device asking: sign out instead"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        QSignalSpy failed(&session, &Session::accountFailed);

        session.removeDevice("f00dfeedf00dfeed");
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("This device signs out instead"));
    }

    void signingOutForgetsTheDevices()
    {
        FakeServer server;
        server.responses[devicesPath] = devicesJson;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        signIn(server, session);
        session.loadDevices();
        QTRY_COMPARE(session.devices().size(), 2);

        server.holdNext[devicesPath] = 1;
        session.loadDevices();
        QTRY_COMPARE(requestsTo(server, devicesPath), 2);
        session.logout();
        QVERIFY(session.devices().isEmpty());
        QVERIFY(!session.devicesLoading());
        server.releaseHeld();
        QTest::qWait(100);
        QVERIFY(session.devices().isEmpty());
    }

    // ---- No server (milestone 4) ----

    void noServerAndNothingKeptShowsTheConnectionScreen()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        QSignalSpy started(&session, &Session::startedOffline);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.unreachable(), 10000);
        QVERIFY(!session.busy());
        QVERIFY(!session.authenticated());
        QVERIFY(!session.online());
        QCOMPARE(started.count(), 0);
    }

    void noServerOpensTheLastAccountOfflineWhenItHasASavedRecipe()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        QSignalSpy started(&session, &Session::startedOffline);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);
        session.identifyDevice();
        QTRY_COMPARE_WITH_TIMEOUT(started.count(), 1, 10000);
        QVERIFY(session.offline());
        QVERIFY(session.authenticated());
        QCOMPARE(session.uid(), 7);
        QCOMPARE(session.username(), QStringLiteral("stub"));
        // No token: nothing is sent as this account until the server says so.
        QVERIFY(api.sessionToken().isEmpty());
        QCOMPARE(store.uid(), 7);
        QVERIFY(!session.unreachable());
        QCOMPARE(succeeded.count(), 0);
    }

    void theServerBackAsTheSameAccountCarriesOn()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = signedIn;
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);

        QSignalSpy reconnected(&session, &Session::reconnected);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);
        QSignalSpy signedOut(&session, &Session::signedOut);
        QSignalSpy changed(&store, &AccountStore::changed);
        api.setBases(QString(), baseOf(server));
        api.checkNow();
        QTRY_COMPARE(reconnected.count(), 1);
        QVERIFY(!session.offline());
        QVERIFY(session.online());
        QCOMPARE(api.sessionToken(), QStringLiteral("tok"));
        // Nothing on screen changes: no sign-in, no sign-out, the same folder.
        QCOMPARE(succeeded.count(), 0);
        QCOMPARE(signedOut.count(), 0);
        QCOMPARE(changed.count(), 0);
    }

    void aForgottenDeviceGoesBackToSignInAndKeepsItsFiles()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = R"({"status":"new"})";
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);

        QSignalSpy signedOut(&session, &Session::signedOut);
        api.setBases(QString(), baseOf(server));
        api.checkNow();
        QTRY_COMPARE(signedOut.count(), 1);
        QVERIFY(!session.authenticated());
        QVERIFY(!session.offline());
        QCOMPARE(store.uid(), -1);
        // Kept for that account: its queue goes when it signs in again.
        QVERIFY(QFile::exists(data.path() + "/accounts/7/recipes/1002.json"));
    }

    // The server has forgotten the device (removed in Settings, as a lost
    // device is signed out): the files stay for that account's next sign-in,
    // but no start without a server opens them any more.
    void aForgottenDeviceOpensNothingOfflineAtTheNextStart()
    {
        QTemporaryDir data;
        {
            AccountStore store(data.path());
            keepARecipe(store);
            FakeServer server;
            server.responses["/api/gluttony/device/identify"] = R"({"status":"new"})";
            Api api;
            api.setBases(QString(), deadBase);
            api.setPingDelays(60000, 60000);
            Session session(api);
            session.setStore(&store);
            session.identifyDevice();
            QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);
            QSignalSpy signedOut(&session, &Session::signedOut);
            api.setBases(QString(), baseOf(server));
            api.checkNow();
            QTRY_COMPARE(signedOut.count(), 1);
        }
        QVERIFY(QFile::exists(data.path() + "/accounts/7/recipes/1002.json"));

        // The next start, with no server.
        AccountStore store(data.path());
        QVERIFY(store.offlineAccount().isEmpty());
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        QSignalSpy started(&session, &Session::startedOffline);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.unreachable(), 10000);
        QCOMPARE(started.count(), 0);
        QVERIFY(!session.authenticated());
    }

    // The same when the device was never opened offline: a start with the
    // server there that hears "new" leaves nothing that opens without it.
    void anUnknownDeviceAtStartLeavesNothingToOpenOffline()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        QCOMPARE(store.offlineAccount().value("UID").toInt(), 7);
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = R"({"status":"new"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY(!session.busy());
        QVERIFY(!session.authenticated());
        QVERIFY(store.offlineAccount().isEmpty());
        QVERIFY(QFile::exists(data.path() + "/accounts/7/recipes/1002.json"));
    }

    void anotherAccountOnThisDeviceEndsTheOfflineOne()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = R"({"status":"ok","UID":8,"username":"other","token":"tok8"})";
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);

        QSignalSpy signedOut(&session, &Session::signedOut);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);
        api.setBases(QString(), baseOf(server));
        api.checkNow();
        QTRY_COMPARE(succeeded.count(), 1);
        QCOMPARE(signedOut.count(), 1);
        QCOMPARE(session.uid(), 8);
        QCOMPARE(store.uid(), 8);
        QVERIFY(QFile::exists(data.path() + "/accounts/7/recipes/1002.json"));
    }

    void theConnectionScreenGoesWhenTheServerAnswers()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = R"({"status":"new"})";
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.unreachable(), 10000);
        // Retry while the server is still away: still away.
        session.retry();
        QTRY_VERIFY_WITH_TIMEOUT(!session.busy(), 10000);
        QVERIFY(session.unreachable());

        api.setBases(QString(), baseOf(server));
        api.checkNow();
        QTRY_VERIFY(!session.unreachable());
        QVERIFY(!session.authenticated());
    }

    void signingInOpensTheAccountsFolder()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        FakeServer server;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        session.setStore(&store);
        signIn(server, session);
        QCOMPARE(store.uid(), 7);
        const QJsonObject account = AccountStore::readJson(store.file("account.json"));
        QCOMPARE(account.value("username").toString(), QStringLiteral("stub"));
        QVERIFY(!account.contains("token"));
    }

    void signingOutDeletesWhatTheAccountKept()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        FakeServer server;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        session.setStore(&store);
        signIn(server, session);
        QVERIFY(AccountStore::writeJson(store.recipeFile(1002), QJsonObject{{"id", 1002}}));
        session.logout();
        QVERIFY(!QFileInfo::exists(data.path() + "/accounts/7"));
        QCOMPARE(store.uid(), -1);
        QVERIFY(store.offlineAccount().isEmpty());
        // The server was still told first.
        QTRY_COMPARE(requestsTo(server, "/api/gluttony/auth/logout"), 1);
    }

    void anEndedSessionKeepsWhatTheAccountKept()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        FakeServer server;
        server.statuses["/api/gluttony/series/full"] = 401;
        server.responses["/api/gluttony/series/full"] = R"({"status":"error","message":"not signed in"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        session.setStore(&store);
        signIn(server, session);
        QVERIFY(AccountStore::writeJson(store.recipeFile(1002), QJsonObject{{"id", 1002}}));
        QSignalSpy signedOut(&session, &Session::signedOut);
        QTest::ignoreMessage(QtWarningMsg, "[auth] the server ended the session");
        api.get("/series/full", {}, nullptr);
        QTRY_COMPARE(signedOut.count(), 1);
        QCOMPARE(store.uid(), -1);
        QVERIFY(QFile::exists(data.path() + "/accounts/7/recipes/1002.json"));
        // Still the same device, still known to the server: an ended session is
        // not a sign-out, so a start with no server still opens these offline.
        QCOMPARE(store.offlineAccount().value("UID").toInt(), 7);
    }

    // ---- Coming back never gets stuck (carried from review) ----

    void aServerThatAnswersAnErrorIsAskedAgain()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        FakeServer server;
        server.statuses["/api/gluttony/device/identify"] = 503;
        server.responses["/api/gluttony/device/identify"] = R"({"status":"error","message":"busy, try again"})";
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.setIdentifyRetry(200);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);

        QSignalSpy reconnected(&session, &Session::reconnected);
        api.setBases(QString(), baseOf(server));
        api.checkNow();
        // The server is there but busy: still offline, asked again by itself.
        QTRY_VERIFY(requestsTo(server, "/api/gluttony/device/identify") >= 2);
        QVERIFY(session.online());
        QVERIFY(session.offline());
        QVERIFY(api.sessionToken().isEmpty());
        QCOMPARE(reconnected.count(), 0);

        server.statuses.remove("/api/gluttony/device/identify");
        server.responses["/api/gluttony/device/identify"] = signedIn;
        QTRY_COMPARE(reconnected.count(), 1);
        QVERIFY(!session.offline());
        QCOMPARE(api.sessionToken(), QStringLiteral("tok"));
    }

    void aServerThatGoesAwayMidIdentifyIsAskedOnItsReturn()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        auto *server = new FakeServer;
        server->holdNext["/api/gluttony/device/identify"] = 1;
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);

        api.setBases(QString(), baseOf(*server));
        api.checkNow();
        QTRY_COMPARE(requestsTo(*server, "/api/gluttony/device/identify"), 1);
        // The server goes before it answers: the connection drops, and the app is offline again.
        delete server;
        QTRY_VERIFY(!session.online());
        QTRY_VERIFY(!session.busy());
        QVERIFY(session.offline());

        FakeServer back;
        back.responses["/api/gluttony/device/identify"] = signedIn;
        QSignalSpy reconnected(&session, &Session::reconnected);
        api.setBases(QString(), baseOf(back));
        api.checkNow();
        QTRY_COMPARE(reconnected.count(), 1);
        QCOMPARE(api.sessionToken(), QStringLiteral("tok"));
    }

    void signingOutOfflineDeletesWhatTheAccountKept()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);
        QSignalSpy signedOut(&session, &Session::signedOut);
        session.logout();
        QCOMPARE(signedOut.count(), 1);
        QVERIFY(!QFileInfo::exists(data.path() + "/accounts/7"));
        QVERIFY(!session.offline());
        QVERIFY(!session.authenticated());
        // A second sign-out (a late "ready" from the sign-out flow) does nothing.
        session.logout();
        QCOMPARE(signedOut.count(), 1);
    }

    // ---- A sign-out is never undone (fix round 1) ----

    void aLateIdentifyAfterSigningOutChangesNothing()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = signedIn;
        server.holdNext["/api/gluttony/device/identify"] = 1;
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);

        // The server is back and the reconnecting identify is on its way when
        // the reader signs out of the offline shell.
        api.setBases(QString(), baseOf(server));
        api.checkNow();
        QTRY_COMPARE(requestsTo(server, "/api/gluttony/device/identify"), 1);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);
        QSignalSpy reconnected(&session, &Session::reconnected);
        session.logout();
        // The server is told at once, with the session the next identify brings.
        QTRY_COMPARE(requestsTo(server, "/api/gluttony/auth/logout"), 1);
        QVERIFY(server.heads.last().contains("X-Session-Token: tok"));
        QTRY_VERIFY(!QFile::exists(data.path() + "/accounts/pending-logout.json"));

        // The held answer lands now: the last reader's, so nothing comes of it.
        server.releaseHeld();
        QTest::qWait(200);
        QVERIFY(!session.authenticated());
        QVERIFY(api.sessionToken().isEmpty());
        QCOMPARE(succeeded.count(), 0);
        QCOMPARE(reconnected.count(), 0);
        QVERIFY(!QFileInfo::exists(data.path() + "/accounts/7"));
        QVERIFY(!QFile::exists(data.path() + "/accounts/last.json"));
        QVERIFY(!session.busy());
    }

    void signingOutOfflineLeavesASignOutForTheServer()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.offline(), 10000);
        session.logout();
        QVERIFY(!QFileInfo::exists(data.path() + "/accounts/7"));
        // Outside the account's folder, naming nothing but the account.
        const QJsonObject pending = AccountStore::readJson(data.path() + "/accounts/pending-logout.json");
        QCOMPARE(pending, (QJsonObject{{"uid", 7}}));
        // Still no server, and nothing to read: the connection screen, not the form.
        QVERIFY(session.unreachable());
    }

    // Signed in, then the server stops answering: the logout request would
    // only fail, leaving the server knowing the device, so it is left for later.
    void signingOutWhenTheServerHasStoppedAnsweringLeavesASignOutForIt()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = signedIn;
        Api api;
        api.setBases(QString(), baseOf(server));
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY(session.authenticated());
        api.setBases(QString(), deadBase);
        api.noteUnreachable(QUrl(deadBase + "/media/p001.webp"));
        QTRY_VERIFY(!api.online());

        session.logout();
        QVERIFY(!session.authenticated());
        QCOMPARE(requestsTo(server, "/api/gluttony/auth/logout"), 0);
        QCOMPARE(store.pendingLogout(), 7);
        QVERIFY(session.unreachable());
    }

    // Online, but the server did not record the sign-out (busy, failing, or the
    // session already gone): it still knows the device and would sign it
    // straight back in, so the sign-out is left for it like an offline one.
    void anOnlineSignOutTheServerDidNotRecordIsToldAgain_data()
    {
        QTest::addColumn<int>("status");
        QTest::addColumn<QByteArray>("body");
        QTest::newRow("busy") << 503 << QByteArray(R"({"status":"error","message":"busy, try again"})");
        QTest::newRow("failing") << 500 << QByteArray(R"({"status":"error","message":"server error"})");
        QTest::newRow("session gone") << 401 << QByteArray(R"({"status":"error","message":"not signed in"})");
    }
    void anOnlineSignOutTheServerDidNotRecordIsToldAgain()
    {
        QFETCH(int, status);
        QFETCH(QByteArray, body);
        QTemporaryDir data;
        AccountStore store(data.path());
        FakeServer server;
        Api api;
        api.setBases(QString(), baseOf(server));
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        signIn(server, session);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);
        // The first logout is refused; the one sent when the device next
        // identifies is recorded. That identify is held, so the marker can be seen.
        server.queuedStatuses["/api/gluttony/auth/logout"] = {status};
        server.queued["/api/gluttony/auth/logout"] = {body};
        server.holdNext["/api/gluttony/device/identify"] = 1;
        QTest::ignoreMessage(QtWarningMsg,
                             QRegularExpression(QStringLiteral("^\\[auth\\] logout not recorded on the server")));
        session.logout();
        QVERIFY(!session.authenticated());
        QTRY_COMPARE(store.pendingLogout(), 7);
        QVERIFY(QFile::exists(data.path() + "/accounts/pending-logout.json"));
        QVERIFY(!QFileInfo::exists(data.path() + "/accounts/7"));

        QTRY_COMPARE(requestsTo(server, "/api/gluttony/device/identify"), 2);
        server.releaseHeld();
        QTRY_COMPARE(requestsTo(server, "/api/gluttony/auth/logout"), 2);
        QTRY_COMPARE(store.pendingLogout(), -1);
        QTRY_VERIFY(!session.busy());
        QVERIFY(!session.authenticated());
        QVERIFY(api.sessionToken().isEmpty());
        QCOMPARE(succeeded.count(), 0);
    }

    void theNextStartWithAServerTellsItAndStaysSignedOut()
    {
        QTemporaryDir data;
        {
            AccountStore earlier(data.path());
            earlier.setPendingLogout(7);
        }
        AccountStore store(data.path());
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = signedIn;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        session.setStore(&store);
        QSignalSpy succeeded(&session, &Session::loginSucceeded);
        QSignalSpy changed(&store, &AccountStore::changed);
        session.identifyDevice();
        QTRY_COMPARE(requestsTo(server, "/api/gluttony/auth/logout"), 1);
        QVERIFY(server.heads.last().contains("X-Session-Token: tok"));
        QVERIFY(lastBody(server, "/api/gluttony/auth/logout").contains("fingerprint"));
        QTRY_VERIFY(!QFile::exists(data.path() + "/accounts/pending-logout.json"));
        QTRY_VERIFY(!session.busy());
        // Signed out, and nothing of the account was opened.
        QVERIFY(!session.authenticated());
        QVERIFY(!session.unreachable());
        QVERIFY(api.sessionToken().isEmpty());
        QCOMPARE(succeeded.count(), 0);
        QCOMPARE(changed.count(), 0);
        QVERIFY(!QFileInfo::exists(data.path() + "/accounts/7"));
        QVERIFY(!QFile::exists(data.path() + "/accounts/last.json"));
    }

    void aSignOutTheServerRefusesIsToldAgain()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        store.setPendingLogout(7);
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = signedIn;
        server.statuses["/api/gluttony/auth/logout"] = 503;
        server.responses["/api/gluttony/auth/logout"] = R"({"status":"error","message":"busy, try again"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        session.setStore(&store);
        session.setIdentifyRetry(200);
        QTest::ignoreMessage(QtWarningMsg,
                             QRegularExpression(QStringLiteral("^\\[auth\\] a sign-out made without the server is not on it yet")));
        session.identifyDevice();
        QTRY_COMPARE(requestsTo(server, "/api/gluttony/auth/logout"), 1);
        QTRY_VERIFY(!session.busy());
        QCOMPARE(store.pendingLogout(), 7);
        QVERIFY(!session.authenticated());

        server.statuses.remove("/api/gluttony/auth/logout");
        server.responses.remove("/api/gluttony/auth/logout");
        QTRY_VERIFY(requestsTo(server, "/api/gluttony/auth/logout") >= 2);
        QTRY_COMPARE(store.pendingLogout(), -1);
        QVERIFY(!QFile::exists(data.path() + "/accounts/pending-logout.json"));
        QVERIFY(!session.authenticated());
    }

    void anUnknownDeviceClearsTheSignOut()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        store.setPendingLogout(7);
        FakeServer server;
        server.responses["/api/gluttony/device/identify"] = R"({"status":"new"})";
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        session.setStore(&store);
        session.identifyDevice();
        QTRY_VERIFY(!session.busy());
        QCOMPARE(store.pendingLogout(), -1);
        QVERIFY(!QFile::exists(data.path() + "/accounts/pending-logout.json"));
        QCOMPARE(requestsTo(server, "/api/gluttony/auth/logout"), 0);
    }

    void aSignOutStillToTellOpensNothingOffline()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        keepARecipe(store);
        store.setPendingLogout(7);
        Api api;
        api.setBases(QString(), deadBase);
        api.setPingDelays(60000, 60000);
        Session session(api);
        session.setStore(&store);
        QSignalSpy started(&session, &Session::startedOffline);
        session.identifyDevice();
        QTRY_VERIFY_WITH_TIMEOUT(session.unreachable(), 10000);
        QCOMPARE(started.count(), 0);
        QVERIFY(!session.authenticated());
    }

    void signingInByHandDropsTheSignOut()
    {
        QTemporaryDir data;
        AccountStore store(data.path());
        store.setPendingLogout(7);
        FakeServer server;
        server.responses["/api/gluttony/auth"] = signedIn;
        Api api;
        api.setBases(QString(), baseOf(server));
        Session session(api);
        session.setStore(&store);
        session.login("stub", "stub", QString());
        QTRY_VERIFY(session.authenticated());
        QCOMPARE(store.pendingLogout(), -1);
        QCOMPARE(requestsTo(server, "/api/gluttony/auth/logout"), 0);
    }
};

QTEST_MAIN(TestSession)
#include "tst_session.moc"
