#include <QSignalSpy>
#include <QTest>
#include <QUrlQuery>

#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/Diet.h"
#include "services/Home.h"

static const QString homePath = QStringLiteral("/api/gluttony/home");
static const QString randomPath = QStringLiteral("/api/gluttony/random");
static const QString dietPath = QStringLiteral("/api/gluttony/me/diet");
static const QByteArray homeJson = R"({"status":"ok","data":{"date":"2026-10-27",
  "pick":{"id":1,"title":"Stub Coq au Vin","hasImage":true},
  "picks":[{"id":4,"title":"Stub Spinach Eggs"}]}})";


class TestHome : public QObject
{
    Q_OBJECT

    FakeServer server;
    std::unique_ptr<Api> api;
    std::unique_ptr<Diet> diet;
    std::unique_ptr<Home> home;

    QList<QUrl> to(const QString &path) const
    {
        QList<QUrl> found;
        for (const QUrl &url : server.requests)
            if (url.path() == path)
                found << url;
        return found;
    }

private slots:
    void init()
    {
        server.responses.clear();
        server.statuses.clear();
        server.requests.clear();
        server.holdNext.clear();
        home.reset();
        diet.reset();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server.serverPort()));
        diet = std::make_unique<Diet>(*api);
        home = std::make_unique<Home>(*api, *diet);
        home->setTimeZone("America/Chicago");
    }

    void homeAsksWithTheZoneAndShowsThePick()
    {
        server.responses[homePath] = homeJson;
        home->load();
        QVERIFY(home->loading());
        QTRY_VERIFY(home->answered());
        QCOMPARE(QUrlQuery(to(homePath).last()).queryItemValue("tz"), QStringLiteral("America/Chicago"));
        QVERIFY(!QUrlQuery(to(homePath).last()).hasQueryItem("profile"));
        QVERIFY(home->hasPick());
        QCOMPARE(home->pick().value("title").toString(), QStringLiteral("Stub Coq au Vin"));
        QCOMPARE(home->picks().size(), 1);
        QCOMPARE(home->date(), QStringLiteral("2026-10-27"));
    }

    void nothingFittingIsAnAnswerNotAnError()
    {
        server.responses[homePath] = R"({"status":"ok","data":{"date":"2026-10-27","pick":null,"picks":[]}})";
        home->load();
        QTRY_VERIFY(home->answered());
        QVERIFY(!home->hasPick());
        QVERIFY(home->pick().isEmpty() && home->picks().isEmpty() && home->error().isEmpty());
    }

    void aFailureSaysWhyAndKeepsWhatWasShown()
    {
        server.responses[homePath] = homeJson;
        home->load();
        QTRY_VERIFY(home->hasPick());
        server.responses[homePath] = R"({"status":"error","message":"home is down"})";
        server.statuses[homePath] = 500;
        home->load();
        QTRY_COMPARE(home->error(), QStringLiteral("home is down"));
        QVERIFY(home->hasPick());
    }

    void aDietChangeDropsWhatTheOldProfileFound()
    {
        server.responses[dietPath] = R"({"status":"ok","data":{"diets":["vegan"],"avoid":[]}})";
        server.responses[homePath] = homeJson;
        diet->load();
        QTRY_VERIFY(diet->loaded());
        home->load();
        QTRY_VERIFY(home->hasPick());
        server.responses[homePath] = R"({"status":"error","message":"home is down"})";
        server.statuses[homePath] = 500;
        diet->setEnabled(false);
        QVERIFY(!home->hasPick() && home->picks().isEmpty());
        QTRY_COMPARE(home->error(), QStringLiteral("home is down"));
        QVERIFY(!home->hasPick());
    }

    void switchingTheDietOffAsksAgainWithProfileOff()
    {
        server.responses[dietPath] = R"({"status":"ok","data":{"diets":["vegan"],"avoid":[]}})";
        server.responses[homePath] = homeJson;
        diet->load();
        QTRY_VERIFY(diet->loaded());
        home->load();
        QTRY_VERIFY(home->answered());
        diet->setEnabled(false);
        QTRY_COMPARE(to(homePath).size(), 2);
        QCOMPARE(QUrlQuery(to(homePath).last()).queryItemValue("profile"), QStringLiteral("off"));
    }

    void goOnThenPicksOneOrSaysNothingFits()
    {
        server.responses[randomPath] = R"({"status":"ok","data":{"recipe":{"id":3,"title":"Stub Mojito"}}})";
        QSignalSpy picked(home.get(), &Home::picked);
        home->goOnThen();
        QVERIFY(home->rolling());
        home->goOnThen();
        QTRY_COMPARE(picked.count(), 1);
        QCOMPARE(picked.first().first().toInt(), 3);
        QCOMPARE(to(randomPath).size(), 1);
        QVERIFY(!home->rolling());

        server.responses[randomPath] = R"({"status":"ok","data":{"recipe":null}})";
        QSignalSpy nothing(home.get(), &Home::nothingFits);
        home->goOnThen();
        QTRY_COMPARE(nothing.count(), 1);
    }

    void goOnThenFailsInPlainWords()
    {
        server.responses[randomPath] = R"({"status":"error","message":"server error"})";
        server.statuses[randomPath] = 500;
        QSignalSpy failed(home.get(), &Home::rollFailed);
        home->goOnThen();
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().first().toString(), QStringLiteral("server error"));
    }

    void aLoadMeanwhileNeverStrandsARoll()
    {
        server.responses[homePath] = homeJson;
        server.responses[randomPath] = R"({"status":"ok","data":{"recipe":{"id":3}}})";
        QSignalSpy picked(home.get(), &Home::picked);
        home->goOnThen();
        home->load();
        QTRY_COMPARE(picked.count(), 1);
        QVERIFY(!home->rolling());
    }

    void clearingDropsALateAnswer()
    {
        server.responses[homePath] = homeJson;
        server.holdNext[homePath] = 1;
        home->load();
        QTRY_COMPARE(to(homePath).size(), 1);
        home->clear();
        server.releaseHeld();
        QTest::qWait(200);
        QVERIFY(!home->answered() && !home->hasPick());
    }
};

QTEST_GUILESS_MAIN(TestHome)
#include "tst_home.moc"
