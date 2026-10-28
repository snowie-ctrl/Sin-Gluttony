#include <QTest>

#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/Recipes.h"

static const QByteArray eggs = R"({"status":"ok","data":{"id":4,"title":"Stub Spinach Eggs","servings":2,
  "ingredients":[],"steps":[],"versions":[]}})";
static const QByteArray noServings = R"json({"status":"ok","data":{"id":2,"title":"Coq au Vin (slow cooker)",
  "servings":null,"ingredients":[],"steps":[],"versions":[]}})json";


class TestRecipes : public QObject
{
    Q_OBJECT

    FakeServer server;
    std::unique_ptr<Api> api;
    std::unique_ptr<Recipes> recipes;

    int requestsTo(const QString &path) const
    {
        int n = 0;
        for (const QUrl &url : server.requests)
            n += url.path() == path;
        return n;
    }

private slots:
    void init()
    {
        server.responses.clear();
        server.statuses.clear();
        server.requests.clear();
        server.holdNext.clear();
        recipes.reset();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server.serverPort()));
        recipes = std::make_unique<Recipes>(*api);
    }

    void openingLoadsItAndStartsFromItsOwnServings()
    {
        server.responses["/api/gluttony/recipes/4"] = eggs;
        recipes->open(4);
        QVERIFY(recipes->loading());
        QTRY_VERIFY(!recipes->loading());
        QCOMPARE(recipes->recipe().value("title").toString(), QStringLiteral("Stub Spinach Eggs"));
        QCOMPARE(recipes->servings(), 2);
        QCOMPARE(recipes->multiplier(), 1.0);
        recipes->setServings(6);
        QCOMPARE(recipes->servings(), 6);
        recipes->setServings(500);
        QCOMPARE(recipes->servings(), 99);
        recipes->open(4);       // the same recipe, already loaded: nothing is asked
        QTest::qWait(100);
        QCOMPARE(requestsTo("/api/gluttony/recipes/4"), 1);
    }

    void withoutStatedServingsTheMultiplierScales()
    {
        server.responses["/api/gluttony/recipes/2"] = noServings;
        recipes->open(2);
        QTRY_VERIFY(!recipes->recipe().isEmpty());
        QCOMPARE(recipes->servings(), 0);
        recipes->setServings(4);
        QCOMPARE(recipes->servings(), 0);
        recipes->setMultiplier(2);
        QCOMPARE(recipes->multiplier(), 2.0);
        recipes->setMultiplier(0);
        QCOMPARE(recipes->multiplier(), 0.25);
    }

    void aGoneRecipeSaysSo()
    {
        server.responses["/api/gluttony/recipes/999"] = R"({"status":"error","message":"no such recipe"})";
        server.statuses["/api/gluttony/recipes/999"] = 404;
        recipes->open(999);
        QTRY_VERIFY(recipes->gone());
        QVERIFY(!recipes->loading());
        QVERIFY(recipes->error().isEmpty());
        QVERIFY(recipes->recipe().isEmpty());
    }

    void aFailureSaysWhyAndRetryAsksAgain()
    {
        server.responses["/api/gluttony/recipes/4"] = R"({"status":"error","message":"server error"})";
        server.statuses["/api/gluttony/recipes/4"] = 500;
        recipes->open(4);
        QTRY_COMPARE(recipes->error(), QStringLiteral("server error"));
        QVERIFY(!recipes->gone());
        server.statuses.clear();
        server.responses["/api/gluttony/recipes/4"] = eggs;
        recipes->reload();
        QTRY_COMPARE(recipes->servings(), 2);
        QVERIFY(recipes->error().isEmpty());
    }

    void aLateAnswerForTheLastRecipeIsDropped()
    {
        server.responses["/api/gluttony/recipes/4"] = eggs;
        server.responses["/api/gluttony/recipes/2"] = noServings;
        server.holdNext["/api/gluttony/recipes/4"] = 1;
        recipes->open(4);
        QTRY_COMPARE(requestsTo("/api/gluttony/recipes/4"), 1);
        recipes->open(2);
        QTRY_VERIFY(!recipes->recipe().isEmpty());
        server.releaseHeld();
        QTest::qWait(200);
        QCOMPARE(recipes->recipeId(), 2);
        QCOMPARE(recipes->recipe().value("id").toInt(), 2);
    }

    void picturesHaveTheirAddresses()
    {
        QVERIFY(recipes->thumbUrl(4).endsWith(QStringLiteral("/api/gluttony/thumbs/4")));
        QVERIFY(recipes->imageUrl(4).endsWith(QStringLiteral("/api/gluttony/images/4")));
        QVERIFY(recipes->thumbUrl(0).isEmpty());
    }
};

QTEST_GUILESS_MAIN(TestRecipes)
#include "tst_recipes.moc"
