// Copied from Pageturner Pageturner/tests/tst_api.cpp at ad9342e; Gluttony paths; pictureUrl.
#include <QElapsedTimer>
#include <QFile>
#include <QJsonObject>
#include <QPointer>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>

#include <algorithm>
#include <memory>
#include <utility>

#include "FakeServer.h"
#include "api/Api.h"
#include "api/SessionAuth.h"


// Accepts connections and never answers: a network that is there but dead.
class SilentServer : public QTcpServer
{
public:
    SilentServer() { listen(QHostAddress::LocalHost, 0); }

protected:
    void incomingConnection(qintptr handle) override
    {
        auto *socket = new QTcpSocket(this);
        socket->setSocketDescriptor(handle);
    }
};

// Answers every request with the raw bytes `answer` until `park` is set, then
// keeps each request waiting until release(), which answers them, and every
// request after, with what the test chooses: a reply that arrives only after
// something else has happened. Empty bytes close the connection unanswered;
// Qt asks again a couple of times before giving up, and those are closed too.
class ParkingServer : public QTcpServer
{
public:
    bool park = false;

    explicit ParkingServer(QByteArray answer) : m_answer(std::move(answer)) { listen(QHostAddress::LocalHost, 0); }

    int parkedCount() const { return int(m_parked.size()); }

    void release(const QByteArray &raw)
    {
        m_answer = raw;
        park = false;
        for (const QPointer<QTcpSocket> &socket : std::exchange(m_parked, {})) {
            if (!socket)
                continue;
            socket->write(raw);
            socket->disconnectFromHost();
        }
    }

protected:
    void incomingConnection(qintptr handle) override
    {
        auto *socket = new QTcpSocket(this);
        socket->setSocketDescriptor(handle);
        auto buffer = std::make_shared<QByteArray>();
        connect(socket, &QTcpSocket::readyRead, this, [this, socket, buffer]() {
            buffer->append(socket->readAll());
            if (!buffer->contains("\r\n\r\n"))
                return;   // only GETs come here, so the head is the whole request
            if (park) {
                m_parked.append(socket);
                return;
            }
            socket->write(m_answer);
            socket->disconnectFromHost();
        });
    }

private:
    QByteArray m_answer;
    QList<QPointer<QTcpSocket>> m_parked;
};

static QString baseOf(const QTcpServer &server)
{
    return QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server.serverPort());
}

// The tunnel's own page for a down origin, as it arrives on the wire.
static QByteArray tunnelDown()
{
    const QByteArray page = "<html>origin unreachable</html>";
    return "HTTP/1.1 530 Error\r\nContent-Type: text/html\r\nConnection: close\r\nContent-Length: "
           + QByteArray::number(page.size()) + "\r\n\r\n" + page;
}

static int closedPort()
{
    QTcpServer probe;
    probe.listen(QHostAddress::LocalHost, 0);
    const int port = probe.serverPort();
    probe.close();
    return port;
}


class TestApi : public QObject
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
        file.write(QStringLiteral("{\"apiBase\": \"http://127.0.0.1:%1/api/gluttony\"}")
                       .arg(closedPort()).toUtf8());
        file.close();
        qputenv("GLUTTONY_SECRETS", secrets.toUtf8());
    }

    void withoutAHomeAddressThePublicOneIsUsedAtOnce()
    {
        FakeServer pub;
        Api api;
        api.setBases(QString(), baseOf(pub));
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QVERIFY(ready);
        QVERIFY(!api.onLan());
        QCOMPARE(api.baseUrl(), baseOf(pub));
    }

    void aHomeAddressThatAnswersIsUsed()
    {
        FakeServer lan, pub;
        Api api;
        api.setBases(baseOf(lan), baseOf(pub));
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        QVERIFY(api.onLan());
        QCOMPARE(lan.requests.first().path(), QStringLiteral("/api/gluttony/ping"));

        api.get("/meta/filters", QUrlQuery(), nullptr);
        QTRY_COMPARE_WITH_TIMEOUT(int(lan.requests.size()), 2, 3000);
        QCOMPARE(int(pub.requests.size()), 0);
    }

    void aRefusingHomeAddressFallsBack()
    {
        FakeServer pub;
        Api api;
        api.setBases(QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(closedPort()), baseOf(pub));
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 5000);
        QVERIFY(!api.onLan());
        QCOMPARE(api.baseUrl(), baseOf(pub));
    }

    void aSilentHomeAddressFallsBackWithinTheTimeout()
    {
        SilentServer lan;
        FakeServer pub;
        Api api;
        api.setBases(baseOf(lan), baseOf(pub));
        bool ready = false;
        QElapsedTimer clock;
        clock.start();
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 5000);
        QVERIFY(!api.onLan());
        QVERIFY(clock.elapsed() < 4000);
    }

    // A call may ask for its own transfer timeout (the queue's batch waits
    // longer than the default 20 s); the others keep the default.
    void aCallCanAskForItsOwnTransferTimeout()
    {
        SilentServer silent;
        Api api;
        api.setBases(QString(), baseOf(silent));
        api.setPingDelays(60000, 60000);
        bool answered = false;
        Api::Result result;
        QElapsedTimer clock;
        clock.start();
        api.post("/progress/batch", QJsonObject(), [&](const Api::Result &r) { answered = true; result = r; }, 300);
        QTRY_VERIFY_WITH_TIMEOUT(answered, 5000);
        QCOMPARE(result.httpStatus, 0);
        QVERIFY(!result.ok);
        QVERIFY(clock.elapsed() < 4000);
    }

    void everyWaiterRunsOnce()
    {
        FakeServer lan, pub;
        Api api;
        api.setBases(baseOf(lan), baseOf(pub));
        int first = 0, second = 0;
        api.whenReady([&]() { ++first; });
        api.whenReady([&]() { ++second; });
        QTRY_VERIFY_WITH_TIMEOUT(first == 1 && second == 1, 3000);
        QTest::qWait(200);
        QCOMPARE(first, 1);
        QCOMPARE(second, 1);
        QCOMPARE(int(lan.requests.size()), 1);   // one probe for both
    }

    void losingTheHomeAddressMidSessionSwitches()
    {
        FakeServer pub;
        auto lan = std::make_unique<FakeServer>();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        QVERIFY(api.onLan());

        QSignalSpy changed(&api, &Api::routeChanged);
        lan->close();
        bool failed = false;
        api.get("/meta/filters", QUrlQuery(), [&](const Api::Result &result) { failed = !result.ok; });
        QTRY_VERIFY_WITH_TIMEOUT(failed, 6000);
        QTRY_VERIFY_WITH_TIMEOUT(!api.onLan(), 6000);
        QCOMPARE(int(changed.count()), 1);
        QCOMPARE(api.baseUrl(), baseOf(pub));
        // The public address may well answer: re-checking is not being offline.
        QVERIFY(api.online());
    }

    void bothAddressesGetTheToken()
    {
        FakeServer lan, pub;
        Api api;
        api.setBases(baseOf(lan), baseOf(pub));
        api.setSessionToken("tok");
        QCOMPARE(SessionAuth::instance().headerFor(QUrl(baseOf(lan) + "/ping")), QByteArray("tok"));
        QCOMPARE(SessionAuth::instance().headerFor(QUrl(baseOf(pub) + "/ping")), QByteArray("tok"));
        QVERIFY(SessionAuth::instance().headerFor(QUrl("http://elsewhere.example/x")).isEmpty());
    }

    void theTokenChangingIsAnnounced()
    {
        Api api;
        QSignalSpy changed(&api, &Api::sessionTokenChanged);
        api.setSessionToken("tok");
        QCOMPARE(changed.count(), 1);
        // The same token again is not a change.
        api.setSessionToken("tok");
        QCOMPARE(changed.count(), 1);
        api.setSessionToken(QString());
        QCOMPARE(changed.count(), 2);
    }

    void pictureUrlJoinsTheBase()
    {
        Api api;
        api.setBases(QString(), "http://example.test/api/gluttony");
        QCOMPARE(api.pictureUrl("thumbs", 12), QStringLiteral("http://example.test/api/gluttony/thumbs/12"));
        QCOMPARE(api.pictureUrl("images", 12), QStringLiteral("http://example.test/api/gluttony/images/12"));
        QCOMPARE(api.pictureUrl("thumbs", 0), QString());
    }
    void aRejectedTokenIsAnnounced()
    {
        FakeServer server;
        server.statuses["/api/gluttony/series/full"] = 401;
        server.responses["/api/gluttony/series/full"] = R"({"status":"error","message":"not signed in"})";

        Api api;
        api.setBases(QString(), baseOf(server));
        QSignalSpy unauthorised(&api, &Api::unauthorised);

        // Without a token a 401 is just a failed call (a wrong password, say).
        bool done = false;
        api.get("/series/full", {}, [&](const Api::Result &) { done = true; });
        QTRY_VERIFY(done);
        QCOMPARE(unauthorised.count(), 0);

        api.setSessionToken("tok");
        done = false;
        api.get("/series/full", {}, [&](const Api::Result &result) { done = true; QVERIFY(!result.ok); });
        QTRY_VERIFY(done);
        QCOMPARE(unauthorised.count(), 1);
    }

    // A wrong current password is a refusal: signing out over a typo would
    // throw the reader back to the sign-in page.
    void aWrongCurrentPasswordIsNotAnEndedSession()
    {
        FakeServer server;
        server.statuses["/api/gluttony/user/password"] = 401;
        server.responses["/api/gluttony/user/password"] = R"({"status":"invalid_credentials"})";

        Api api;
        api.setBases(QString(), baseOf(server));
        api.setSessionToken("tok");
        QSignalSpy unauthorised(&api, &Api::unauthorised);

        bool done = false;
        Api::Result seen;
        api.post("/user/password", QJsonObject{{"current", "nope"}, {"password", "longenough"}},
                 [&](const Api::Result &result) { seen = result; done = true; });
        QTRY_VERIFY(done);
        QVERIFY(!seen.ok);
        QCOMPARE(seen.httpStatus, 401);
        QCOMPARE(seen.object.value("status").toString(), QStringLiteral("invalid_credentials"));
        QCOMPARE(unauthorised.count(), 0);
    }

    void aSignedIn401WithNoBodyStillEndsTheSession()
    {
        FakeServer server;
        server.statuses["/api/gluttony/series/full"] = 401;
        server.responses["/api/gluttony/series/full"] = "";

        Api api;
        api.setBases(QString(), baseOf(server));
        api.setSessionToken("tok");
        QSignalSpy unauthorised(&api, &Api::unauthorised);

        bool done = false;
        api.get("/series/full", {}, [&](const Api::Result &) { done = true; });
        QTRY_VERIFY(done);
        QCOMPARE(unauthorised.count(), 1);
    }

    // Qt's text for an HTTP error names the whole address, host included; a
    // failure with no body to explain it is shown as its status instead.
    void anErrorWithNoBodyIsNamedByItsStatusNotItsAddress()
    {
        FakeServer server;
        server.statuses["/api/gluttony/lists"] = 502;
        server.responses["/api/gluttony/lists"] = "";

        Api api;
        api.setBases(QString(), baseOf(server));

        bool done = false;
        Api::Result seen;
        api.get("/lists", {}, [&](const Api::Result &result) { seen = result; done = true; });
        QTRY_VERIFY(done);
        QVERIFY(!seen.ok);
        QCOMPARE(seen.httpStatus, 502);
        QCOMPARE(reasonOf(seen), QStringLiteral("HTTP 502"));
    }

    // ---- Whether the server answers (milestone 4) ----

    void aRefusedConnectionIsOffline()
    {
        Api api;
        api.setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(closedPort()));
        api.setPingDelays(60000, 60000);
        QVERIFY(api.online());
        QSignalSpy changed(&api, &Api::onlineChanged);
        bool done = false;
        bool offlineWhenAnswered = false;
        api.get("/series/full", {}, [&](const Api::Result &result) {
            // Already offline when the caller hears of it.
            offlineWhenAnswered = !api.online() && result.httpStatus == 0;
            done = true;
        });
        QTRY_VERIFY(done);
        QVERIFY(offlineWhenAnswered);
        QCOMPARE(changed.count(), 1);
    }

    void theTunnelsOwnPageForADownOriginIsOffline()
    {
        for (const int status : {502, 521, 522, 523, 530}) {
            FakeServer server;
            server.statuses["/api/gluttony/lists"] = status;
            server.responses["/api/gluttony/lists"] = "<html><body>origin unreachable</body></html>";
            Api api;
            api.setBases(QString(), baseOf(server));
            api.setPingDelays(60000, 60000);
            bool done = false;
            api.get("/lists", {}, [&](const Api::Result &) { done = true; });
            QTRY_VERIFY(done);
            QVERIFY2(!api.online(), qPrintable(QString::number(status)));
        }
    }

    void theServerAnsweringAnErrorIsStillOnline()
    {
        FakeServer server;
        server.statuses["/api/gluttony/progress/update"] = 503;
        server.responses["/api/gluttony/progress/update"] = R"({"status":"error","message":"busy, try again"})";
        server.statuses["/api/gluttony/lists"] = 502;
        server.responses["/api/gluttony/lists"] = R"({"status":"error","message":"server error"})";
        server.statuses["/api/gluttony/series/full"] = 404;
        server.responses["/api/gluttony/series/full"] = "";
        Api api;
        api.setBases(QString(), baseOf(server));
        api.setPingDelays(60000, 60000);
        QSignalSpy changed(&api, &Api::onlineChanged);
        int answered = 0;
        api.post("/progress/update", QJsonObject(), [&](const Api::Result &) { ++answered; });
        api.get("/lists", {}, [&](const Api::Result &) { ++answered; });
        api.get("/series/full", {}, [&](const Api::Result &) { ++answered; });
        QTRY_COMPARE(answered, 3);
        QVERIFY(api.online());
        QCOMPARE(changed.count(), 0);
    }

    void whileOfflineAPingBringsItBack()
    {
        FakeServer server;
        Api api;
        api.setBases(QString(), baseOf(server));
        api.setPingDelays(100, 400);
        QSignalSpy changed(&api, &Api::onlineChanged);
        api.noteUnreachable(QUrl(baseOf(server) + "/media/p001.webp"));
        QVERIFY(!api.online());
        QTRY_VERIFY(api.online());
        QCOMPARE(changed.count(), 2);
        QCOMPARE(server.requests.last().path(), QStringLiteral("/api/gluttony/ping"));
    }

    void pingsWaitLongerWhileNothingAnswers()
    {
        FakeServer server;
        server.statuses["/api/gluttony/ping"] = 530;
        server.responses["/api/gluttony/ping"] = "<html>origin unreachable</html>";
        Api api;
        api.setBases(QString(), baseOf(server));
        api.setPingDelays(100, 400);
        api.noteUnreachable(QUrl(baseOf(server) + "/media/p001.webp"));
        // Tries at about 100, 300, 700, 1100 and 1500 ms: a fixed 100 ms would
        // have made about fifteen.
        QTest::qWait(1500);
        int pings = 0;
        for (const QUrl &url : server.requests)
            if (url.path() == QLatin1String("/api/gluttony/ping"))
                ++pings;
        QVERIFY2(pings >= 3 && pings <= 6, qPrintable(QString::number(pings)));
        QVERIFY(!api.online());
    }

    void checkNowDoesNotWait()
    {
        FakeServer server;
        Api api;
        api.setBases(QString(), baseOf(server));
        api.setPingDelays(60000, 60000);
        api.noteUnreachable(QUrl(baseOf(server) + "/media/p001.webp"));
        api.checkNow();
        QTRY_VERIFY(api.online());
    }

    void anyAnswerBringsItBack()
    {
        FakeServer server;
        Api api;
        api.setBases(QString(), baseOf(server));
        api.setPingDelays(60000, 60000);
        api.noteUnreachable(QUrl(baseOf(server) + "/media/p001.webp"));
        bool done = false;
        api.get("/lists", {}, [&](const Api::Result &) { done = true; });
        QTRY_VERIFY(done);
        QVERIFY(api.online());
    }

    // A page that PageStore or Downloads could not fetch is judged like a failed
    // call of Api's own: the home address going quiet is a reason to look again,
    // not to call the app offline.
    void aPageFailingOnTheHomeAddressReprobesInsteadOfGoingOffline()
    {
        FakeServer pub;
        auto lan = std::make_unique<FakeServer>();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        api.setPingDelays(60000, 60000);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        QVERIFY(api.onLan());

        QSignalSpy online(&api, &Api::onlineChanged);
        const QUrl page(baseOf(*lan) + "/media/p001.webp");
        lan->close();
        api.noteUnreachable(page);
        QVERIFY(api.online());
        // The probe finds the home address gone and settles on the public one.
        QTRY_VERIFY_WITH_TIMEOUT(!api.onLan(), 6000);
        QCOMPARE(api.baseUrl(), baseOf(pub));
        QVERIFY(api.online());
        QCOMPARE(online.count(), 0);
    }

    void aPageFailingOnThePublicAddressIsOffline()
    {
        FakeServer pub;
        Api api;
        api.setBases(QString(), baseOf(pub));
        api.setPingDelays(60000, 60000);
        QVERIFY(api.online());
        api.noteUnreachable(QUrl(baseOf(pub) + "/media/p001.webp"));
        QVERIFY(!api.online());
    }

    // Only a failure on the address in use decides offline. At home that is the
    // home address, so a page still on its way to the public one (asked for
    // before the app came back on the home server) says nothing about it.
    void aPageFailingOnThePublicAddressWhileAtHomeIsIgnored()
    {
        FakeServer lan, pub;
        Api api;
        api.setBases(baseOf(lan), baseOf(pub));
        api.setPingDelays(60000, 60000);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        QVERIFY(api.onLan());
        QSignalSpy online(&api, &Api::onlineChanged);
        api.noteUnreachable(QUrl(baseOf(pub) + "/media/p001.webp"));
        QVERIFY(api.online());
        QCOMPARE(online.count(), 0);
    }

    // The reader leaves home Wi-Fi: the first home-address failure moves the app
    // to the public address, and requests still on their way to the home address
    // then fail too. The server answers; those failures are not the app offline.
    void aLateFailureOnTheHomeAddressAfterTheSwitchIsNotOffline()
    {
        FakeServer pub;
        auto lan = std::make_unique<FakeServer>();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        api.setPingDelays(60000, 60000);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        QVERIFY(api.onLan());

        // A request to the home address that is never answered, while the home
        // address is still there.
        lan->holdNext["/api/gluttony/lists"] = 1;
        bool done = false;
        int status = -1;
        api.get("/lists", {}, [&](const Api::Result &result) { done = true; status = result.httpStatus; });
        QTRY_VERIFY(!lan->requests.isEmpty() && lan->requests.last().path() == QLatin1String("/api/gluttony/lists"));

        // The first failure settles the route on the public address.
        QSignalSpy online(&api, &Api::onlineChanged);
        const QUrl page(baseOf(*lan) + "/media/p001.webp");   // before close(): the port is gone after
        lan->close();
        api.noteUnreachable(page);
        QTRY_VERIFY_WITH_TIMEOUT(!api.onLan(), 6000);

        // Now the parked request dies with the home server.
        lan.reset();
        QTRY_VERIFY(done);
        QCOMPARE(status, 0);
        QVERIFY(api.online());
        api.noteUnreachable(QUrl(baseOf(pub) + "/media/p001.webp"));
        QVERIFY(!api.online());   // a failure on the public address still is
        QCOMPARE(online.count(), 1);
    }

    void aLateFailureOnTheHomeAddressViaNoteUnreachableIsIgnored()
    {
        FakeServer pub;
        auto lan = std::make_unique<FakeServer>();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        api.setPingDelays(60000, 60000);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        const QUrl page(baseOf(*lan) + "/media/p001.webp");
        lan->close();
        api.noteUnreachable(page);
        QTRY_VERIFY_WITH_TIMEOUT(!api.onLan(), 6000);

        // The first report started a check, and its last step is a /ping to the
        // public address. That request may still be on its way when the route
        // switches, so it is waited for before the count is taken: otherwise it
        // would land during the wait below and look like a second check.
        const QString ping = QStringLiteral("/api/gluttony/ping");
        QTRY_VERIFY_WITH_TIMEOUT(
            std::any_of(pub.requests.cbegin(), pub.requests.cend(), [&](const QUrl &url) { return url.path() == ping; }),
            3000);

        // Reported again after the switch: the route has moved, nothing to check.
        const int before = pub.requests.size();
        api.noteUnreachable(page);
        QVERIFY(api.online());
        QTest::qWait(200);
        QVERIFY(api.online());
        QCOMPARE(int(pub.requests.size()), before);
    }

    // The server box itself down (the common outage at home): neither address
    // answers, so the check that a failure started ends with the app offline and
    // pinging, rather than claiming online until some later call fails.
    void aRecheckWhereNeitherAddressAnswersGoesOfflineAndPings()
    {
        FakeServer pub;
        pub.statuses["/api/gluttony/ping"] = 530;
        pub.responses["/api/gluttony/ping"] = "<html>origin unreachable</html>";
        auto lan = std::make_unique<FakeServer>();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        api.setPingDelays(100, 400);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        QVERIFY(api.onLan());

        lan->close();
        bool failed = false;
        api.get("/lists", {}, [&](const Api::Result &result) { failed = !result.ok; });
        QTRY_VERIFY_WITH_TIMEOUT(failed, 6000);
        // Still looking at the moment the call fails; then the public address
        // does not answer either.
        QTRY_VERIFY_WITH_TIMEOUT(!api.online(), 6000);
        QVERIFY(!api.onLan());
        const auto pings = [&]() {
            int n = 0;
            for (const QUrl &url : pub.requests)
                if (url.path() == QLatin1String("/api/gluttony/ping"))
                    ++n;
            return n;
        };
        const int first = pings();
        QVERIFY(first >= 1);
        QTRY_VERIFY_WITH_TIMEOUT(pings() > first, 3000);
    }

    // ---- Coming back at home (final review) ----

    // The home server back before the tunnel (cloudflared is its own machine):
    // the pings look at the home address too, so the app comes back on it
    // instead of staying offline until a restart.
    void whileOfflineTheHomeAddressComingBackBringsItBackAtHome()
    {
        FakeServer pub;
        pub.statuses["/api/gluttony/ping"] = 530;
        pub.responses["/api/gluttony/ping"] = "<html>origin unreachable</html>";
        auto lan = std::make_unique<FakeServer>();
        const quint16 port = lan->serverPort();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        api.setPingDelays(100, 400);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        QVERIFY(api.onLan());

        lan->close();
        api.get("/lists", {}, nullptr);
        QTRY_VERIFY_WITH_TIMEOUT(!api.online(), 6000);
        QVERIFY(!api.onLan());
        // Still down for a few pings, then back on the same address.
        QTest::qWait(400);
        QVERIFY(!api.online());
        QVERIFY(lan->listen(QHostAddress::LocalHost, port));
        QTRY_VERIFY_WITH_TIMEOUT(api.online(), 6000);
        QVERIFY(api.onLan());
        QCOMPARE(api.baseUrl(), baseOf(*lan));
    }

    // The ping that went to the public address beside the home probe fails after
    // home has answered (the LAN is quicker than the tunnel's round trip): with
    // the tunnel's own page for a down origin, or with no answer at all (a
    // connection closed unanswered; in the app, the 20 s timeout). The app is on
    // the home address by then, so neither takes it offline again.
    void theTunnelsLateAnswerAfterHomeCameBackDoesNotTakeItOffline_data()
    {
        QTest::addColumn<QByteArray>("late");
        QTest::newRow("tunnel 530") << tunnelDown();
        QTest::newRow("no answer") << QByteArray();
    }

    void theTunnelsLateAnswerAfterHomeCameBackDoesNotTakeItOffline()
    {
        QFETCH(QByteArray, late);
        ParkingServer pub(tunnelDown());
        auto lan = std::make_unique<FakeServer>();
        const quint16 port = lan->serverPort();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        api.setPingDelays(60000, 60000);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        lan->close();
        api.get("/lists", {}, nullptr);
        QTRY_VERIFY_WITH_TIMEOUT(!api.online(), 6000);
        QVERIFY(!api.onLan());

        // Home is back; the public ping is held until home has answered.
        QVERIFY(lan->listen(QHostAddress::LocalHost, port));
        pub.park = true;
        QSignalSpy online(&api, &Api::onlineChanged);
        api.checkNow();
        QTRY_VERIFY_WITH_TIMEOUT(api.online() && api.onLan(), 6000);
        QTRY_COMPARE_WITH_TIMEOUT(pub.parkedCount(), 1, 3000);

        pub.release(late);
        QTest::qWait(300);
        QVERIFY(api.online());
        QVERIFY(api.onLan());
        QCOMPARE(online.count(), 1);
    }

    // Away from home the home address never answers; the public one coming back
    // is enough, as before.
    void whileOfflineThePublicAddressAloneBringsItBack()
    {
        FakeServer pub;
        pub.statuses["/api/gluttony/ping"] = 530;
        pub.responses["/api/gluttony/ping"] = "<html>origin unreachable</html>";
        const QString lanBase = QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(closedPort());
        Api api;
        api.setBases(lanBase, baseOf(pub));
        api.setPingDelays(100, 400);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        QVERIFY(!api.onLan());
        api.get("/ping", {}, nullptr);
        QTRY_VERIFY_WITH_TIMEOUT(!api.online(), 6000);

        pub.statuses.remove("/api/gluttony/ping");
        pub.responses.remove("/api/gluttony/ping");
        QTRY_VERIFY_WITH_TIMEOUT(api.online(), 6000);
        QVERIFY(!api.onLan());
        QCOMPARE(api.baseUrl(), baseOf(pub));
    }

    // Both back at once: home is preferred, as at start-up.
    void whenBothComeBackTheHomeAddressIsPreferred()
    {
        FakeServer pub;
        pub.statuses["/api/gluttony/ping"] = 530;
        pub.responses["/api/gluttony/ping"] = "<html>origin unreachable</html>";
        auto lan = std::make_unique<FakeServer>();
        const quint16 port = lan->serverPort();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        api.setPingDelays(60000, 60000);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        lan->close();
        api.get("/lists", {}, nullptr);
        QTRY_VERIFY_WITH_TIMEOUT(!api.online(), 6000);
        QVERIFY(!api.onLan());

        pub.statuses.remove("/api/gluttony/ping");
        pub.responses.remove("/api/gluttony/ping");
        QVERIFY(lan->listen(QHostAddress::LocalHost, port));
        // The connection screen's Retry.
        api.checkNow();
        QTRY_VERIFY_WITH_TIMEOUT(api.online() && api.onLan(), 6000);
    }

    // Sign-in waits for an address (Session's Retry identifies through
    // whenReady): offline, that looks at the home address again too.
    void whileOfflineWaitingForAnAddressLooksAtHomeAgain()
    {
        FakeServer pub;
        pub.statuses["/api/gluttony/ping"] = 530;
        pub.responses["/api/gluttony/ping"] = "<html>origin unreachable</html>";
        auto lan = std::make_unique<FakeServer>();
        const quint16 port = lan->serverPort();
        Api api;
        api.setBases(baseOf(*lan), baseOf(pub));
        api.setPingDelays(60000, 60000);
        bool ready = false;
        api.whenReady([&]() { ready = true; });
        QTRY_VERIFY_WITH_TIMEOUT(ready, 3000);
        lan->close();
        api.get("/lists", {}, nullptr);
        QTRY_VERIFY_WITH_TIMEOUT(!api.online(), 6000);

        QVERIFY(lan->listen(QHostAddress::LocalHost, port));
        bool again = false;
        api.whenReady([&]() { again = true; });
        QTRY_VERIFY_WITH_TIMEOUT(again, 3000);
        QVERIFY(api.onLan());
        QVERIFY(api.online());
    }
};

QTEST_GUILESS_MAIN(TestApi)
#include "tst_api.moc"
