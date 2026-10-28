#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/Diet.h"

static const QString dietPath = QStringLiteral("/api/gluttony/me/diet");
static const QByteArray vegetarian = R"({"status":"ok","data":{"diets":["vegetarian"],"avoid":["peanut","sesame"]}})";


class TestDiet : public QObject
{
    Q_OBJECT

    FakeServer server;
    std::unique_ptr<Api> api;
    std::unique_ptr<Diet> diet;

private slots:
    void init()
    {
        server.responses.clear();
        server.statuses.clear();
        server.requests.clear();
        server.bodies.clear();
        server.holdNext.clear();
        diet.reset();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server.serverPort()));
        diet = std::make_unique<Diet>(*api);
    }

    void loadingReadsTheProfile()
    {
        server.responses[dietPath] = vegetarian;
        diet->load();
        QTRY_VERIFY(diet->loaded());
        QCOMPARE(diet->diets(), QStringList{"vegetarian"});
        QCOMPARE(diet->avoid(), (QStringList{"peanut", "sesame"}));
        QVERIFY(diet->hasProfile());
        QVERIFY(diet->enabled());
        QCOMPARE(diet->profileParam(), QString());
    }

    void switchedOffWithAProfileAsksForProfileOff()
    {
        server.responses[dietPath] = vegetarian;
        diet->load();
        QTRY_VERIFY(diet->loaded());
        QSignalSpy enabled(diet.get(), &Diet::enabledChanged);
        diet->setEnabled(false);
        diet->setEnabled(false);
        QCOMPARE(enabled.count(), 1);
        QCOMPARE(diet->profileParam(), QStringLiteral("off"));
    }

    void withoutAProfileNothingIsSentEvenWhenOff()
    {
        server.responses[dietPath] = R"({"status":"ok","data":{"diets":[],"avoid":[]}})";
        diet->load();
        QTRY_VERIFY(diet->loaded());
        diet->setEnabled(false);
        QVERIFY(!diet->hasProfile());
        QCOMPARE(diet->profileParam(), QString());
    }

    void savingSendsTheListsAndSwitchesItBackOn()
    {
        server.responses[dietPath] = R"({"status":"ok","data":{"diets":["vegan"],"avoid":["peanut"]}})";
        diet->setEnabled(false);
        QSignalSpy saved(diet.get(), &Diet::saved);
        diet->save({"vegan"}, {"peanut"});
        QVERIFY(diet->saving());
        QTRY_COMPARE(saved.count(), 1);
        const QJsonObject sent = QJsonDocument::fromJson(server.bodies.last()).object();
        QCOMPARE(sent.value("diets").toArray().first().toString(), QStringLiteral("vegan"));
        QCOMPARE(sent.value("avoid").toArray().first().toString(), QStringLiteral("peanut"));
        QVERIFY(!diet->saving());
        QVERIFY(diet->enabled());
        QCOMPARE(diet->diets(), QStringList{"vegan"});
    }

    void aRefusedSaveKeepsTheOldProfileAndSaysWhy()
    {
        server.responses[dietPath] = vegetarian;
        diet->load();
        QTRY_VERIFY(diet->loaded());
        server.responses[dietPath] = R"({"status":"error","message":"unknown diet: keto"})";
        server.statuses[dietPath] = 400;
        diet->save({"keto"}, {});
        QTRY_VERIFY(!diet->saving());
        QCOMPARE(diet->error(), QStringLiteral("unknown diet: keto"));
        QCOMPARE(diet->diets(), QStringList{"vegetarian"});
    }

    void clearingDropsALateAnswerAndSwitchesItOn()
    {
        server.responses[dietPath] = vegetarian;
        server.holdNext[dietPath] = 1;
        diet->load();
        QTRY_COMPARE(server.requests.size(), 1);
        diet->setEnabled(false);
        diet->clear();
        server.releaseHeld();
        QTest::qWait(200);
        QVERIFY(!diet->loaded());
        QVERIFY(!diet->hasProfile());
        QVERIFY(diet->enabled());
    }
};

QTEST_GUILESS_MAIN(TestDiet)
#include "tst_diet.moc"
