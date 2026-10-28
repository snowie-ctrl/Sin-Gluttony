// Copied from Pageturner Pageturner/tests/tst_sessionauth.cpp at ad9342e; Gluttony paths.
#include <QNetworkReply>
#include <QSignalSpy>
#include <QTest>

#include <memory>

#include "FakeServer.h"
#include "api/AuthNetworkFactory.h"
#include "api/SessionAuth.h"


class TestSessionAuth : public QObject
{
    Q_OBJECT

    FakeServer server;

private slots:
    void init()
    {
        SessionAuth::instance().setToken(QString());
        SessionAuth::instance().setOrigins({});
    }

    void aMatchingOriginGetsTheToken()
    {
        auto &auth = SessionAuth::instance();
        auth.setOrigins({QUrl("https://api.example/api/gluttony")});
        auth.setToken("tok");
        QCOMPARE(auth.headerFor(QUrl("https://api.example/api/gluttony/media/1/cover.webp")),
                 QByteArray("tok"));
        QCOMPARE(auth.headerFor(QUrl("https://api.example:443/anything")), QByteArray("tok"));
    }

    void otherOriginsGetNothing()
    {
        auto &auth = SessionAuth::instance();
        auth.setOrigins({QUrl("https://api.example/api/gluttony")});
        auth.setToken("tok");
        QVERIFY(auth.headerFor(QUrl("https://other.example/x")).isEmpty());
        QVERIFY(auth.headerFor(QUrl("http://api.example/x")).isEmpty());
        QVERIFY(auth.headerFor(QUrl("https://api.example:8443/x")).isEmpty());
    }

    void bothConfiguredOriginsGetTheToken()
    {
        auto &auth = SessionAuth::instance();
        auth.setOrigins({QUrl("http://home.lan:5000/api/gluttony"), QUrl("https://api.example/api/gluttony")});
        auth.setToken("tok");
        QCOMPARE(auth.headerFor(QUrl("http://home.lan:5000/api/gluttony/ping")), QByteArray("tok"));
        QCOMPARE(auth.headerFor(QUrl("https://api.example/api/gluttony/ping")), QByteArray("tok"));
        QVERIFY(auth.headerFor(QUrl("http://home.lan/api/gluttony/ping")).isEmpty());
    }

    void noTokenMeansNoHeader()
    {
        auto &auth = SessionAuth::instance();
        auth.setOrigins({QUrl("https://api.example/api/gluttony")});
        QVERIFY(auth.headerFor(QUrl("https://api.example/x")).isEmpty());
        auth.setToken("tok");
        auth.setToken(QString());
        QVERIFY(auth.headerFor(QUrl("https://api.example/x")).isEmpty());
    }

    void factoryManagersSendTheHeader()
    {
        QVERIFY(server.isListening());
        const QString base = QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server.serverPort());
        SessionAuth::instance().setOrigins({QUrl(base)});
        SessionAuth::instance().setToken("tok");

        AuthNetworkFactory factory;
        std::unique_ptr<QNetworkAccessManager> manager(factory.create(nullptr));
        QNetworkReply *reply = manager->get(QNetworkRequest(QUrl(base + "/media/1/cover.webp")));
        QSignalSpy finished(reply, &QNetworkReply::finished);
        QVERIFY(finished.wait(3000));
        reply->deleteLater();

        QVERIFY(!server.heads.isEmpty());
        QVERIFY(server.heads.last().contains("X-Session-Token: tok"));
        QCOMPARE(reply->request().attribute(QNetworkRequest::RedirectPolicyAttribute).toInt(),
                 int(QNetworkRequest::SameOriginRedirectPolicy));
    }

    void factoryManagersKeepTheTokenFromOtherOrigins()
    {
        FakeServer stranger;
        QVERIFY(server.isListening());
        QVERIFY(stranger.isListening());
        const QString base = QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server.serverPort());
        SessionAuth::instance().setOrigins({QUrl(base)});
        SessionAuth::instance().setToken("tok");

        AuthNetworkFactory factory;
        std::unique_ptr<QNetworkAccessManager> manager(factory.create(nullptr));
        const QUrl other(QStringLiteral("http://127.0.0.1:%1/x").arg(stranger.serverPort()));
        QNetworkReply *reply = manager->get(QNetworkRequest(other));
        QSignalSpy finished(reply, &QNetworkReply::finished);
        QVERIFY(finished.wait(3000));
        reply->deleteLater();

        QVERIFY(!stranger.heads.isEmpty());
        QVERIFY(!stranger.heads.last().toLower().contains("x-session-token"));
    }
};

QTEST_GUILESS_MAIN(TestSessionAuth)
#include "tst_sessionauth.moc"
