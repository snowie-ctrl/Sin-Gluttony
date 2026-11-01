#include <QJsonDocument>
#include <QTemporaryDir>
#include <QTest>
#include <QUrlQuery>

#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/AccountStore.h"
#include "services/RecipeStore.h"
#include "services/Recipes.h"

static const QByteArray eggs = R"({"status":"ok","data":{"id":4,"title":"Stub Spinach Eggs","servings":2,
  "ingredients":[],"steps":[],"versions":[]}})";
static const QByteArray noServings = R"json({"status":"ok","data":{"id":2,"title":"Coq au Vin (slow cooker)",
  "servings":null,"ingredients":[],"steps":[],"versions":[]}})json";


class TestRecipes : public QObject
{
    Q_OBJECT

    std::unique_ptr<FakeServer> server;
    std::unique_ptr<Api> api;
    std::unique_ptr<QTemporaryDir> dir;
    std::unique_ptr<AccountStore> accounts;
    std::unique_ptr<RecipeStore> copies;
    std::unique_ptr<Recipes> recipes;

    int requestsTo(const QString &path) const
    {
        int n = 0;
        for (const QUrl &url : server->requests)
            n += url.path() == path;
        return n;
    }

    // A copy of recipe 4 kept on this device, as cook mode or a list would leave it.
    void keepEggs(const QString &title = QStringLiteral("Stub Spinach Eggs (kept)"))
    {
        dir = std::make_unique<QTemporaryDir>();
        accounts = std::make_unique<AccountStore>(dir->path());
        accounts->open(7, "ann");
        copies = std::make_unique<RecipeStore>(*api);
        copies->setStore(accounts.get());
        copies->keepForCooking(QVariantMap{{"id", 4}, {"title", title}, {"servings", 2}, {"hasImage", false},
                                           {"ingredients", QVariantList()}, {"steps", QVariantList()}});
        recipes->setStore(copies.get());
    }

    void goOffline()
    {
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:1/api/gluttony"));
        api->setPingDelays(60000, 60000);
        api->get("/ping", QUrlQuery(), nullptr);
        QTRY_VERIFY_WITH_TIMEOUT(!api->online(), 10000);
    }

private slots:
    void init()
    {
        recipes.reset();
        copies.reset();
        accounts.reset();
        dir.reset();
        server = std::make_unique<FakeServer>();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server->serverPort()));
        recipes = std::make_unique<Recipes>(*api);
    }

    void openingLoadsItAndStartsFromItsOwnServings()
    {
        server->responses["/api/gluttony/recipes/4"] = eggs;
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
        server->responses["/api/gluttony/recipes/2"] = noServings;
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
        server->responses["/api/gluttony/recipes/999"] = R"({"status":"error","message":"no such recipe"})";
        server->statuses["/api/gluttony/recipes/999"] = 404;
        recipes->open(999);
        QTRY_VERIFY(recipes->gone());
        QVERIFY(!recipes->loading());
        QVERIFY(recipes->error().isEmpty());
        QVERIFY(recipes->recipe().isEmpty());
    }

    void aFailureSaysWhyAndRetryAsksAgain()
    {
        server->responses["/api/gluttony/recipes/4"] = R"({"status":"error","message":"server error"})";
        server->statuses["/api/gluttony/recipes/4"] = 500;
        recipes->open(4);
        QTRY_COMPARE(recipes->error(), QStringLiteral("server error"));
        QVERIFY(!recipes->gone());
        server->statuses.clear();
        server->responses["/api/gluttony/recipes/4"] = eggs;
        recipes->reload();
        QTRY_COMPARE(recipes->servings(), 2);
        QVERIFY(recipes->error().isEmpty());
    }

    void aLateAnswerForTheLastRecipeIsDropped()
    {
        server->responses["/api/gluttony/recipes/4"] = eggs;
        server->responses["/api/gluttony/recipes/2"] = noServings;
        server->holdNext["/api/gluttony/recipes/4"] = 1;
        recipes->open(4);
        QTRY_COMPARE(requestsTo("/api/gluttony/recipes/4"), 1);
        recipes->open(2);
        QTRY_VERIFY(!recipes->recipe().isEmpty());
        server->releaseHeld();
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

    void offlineTheCopyOpensWithoutAsking()
    {
        api->setSessionToken("tok");
        keepEggs();
        goOffline();
        recipes->open(4);
        QVERIFY(!recipes->loading());
        QVERIFY(recipes->fromCopy());
        QCOMPARE(recipes->recipe().value("title").toString(), QStringLiteral("Stub Spinach Eggs (kept)"));
        QCOMPARE(recipes->servings(), 2);
        QCOMPARE(requestsTo("/api/gluttony/recipes/4"), 0);
    }

    void anOfflineStartHasNoTokenAndOpensTheCopy()
    {
        keepEggs();
        recipes->open(4);
        QVERIFY(recipes->fromCopy());
        QCOMPARE(requestsTo("/api/gluttony/recipes/4"), 0);
    }

    void aLostConnectionOpensTheSavedCopy()
    {
        // The app still thinks it is online; the request meets no answer, and the copy stands in.
        api->setSessionToken("tok");
        keepEggs();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:1/api/gluttony"));
        recipes->open(4);
        QTRY_VERIFY_WITH_TIMEOUT(recipes->fromCopy(), 10000);
        QVERIFY(recipes->error().isEmpty());
        QCOMPARE(recipes->recipe().value("title").toString(), QStringLiteral("Stub Spinach Eggs (kept)"));
    }

    void aTunnelAnsweringForADownServerOpensTheSavedCopy()
    {
        // The tunnel answers 530 with a page of its own while the origin is down; Api reads that as unreachable.
        api->setSessionToken("tok");
        keepEggs();
        server->statuses["/api/gluttony/recipes/4"] = 530;
        server->responses["/api/gluttony/recipes/4"] = "<html>origin down</html>";
        recipes->open(4);
        QTRY_VERIFY_WITH_TIMEOUT(recipes->fromCopy(), 10000);
        QVERIFY(recipes->error().isEmpty());
        QVERIFY(!recipes->loading());
        QCOMPARE(recipes->recipe().value("title").toString(), QStringLiteral("Stub Spinach Eggs (kept)"));
    }

    void reopeningTheSameRecipeAfterReconnectAsksTheServer()
    {
        api->setSessionToken("tok");
        keepEggs();
        goOffline();
        recipes->open(4);
        QVERIFY(recipes->fromCopy());
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server->serverPort()));
        api->checkNow();
        QTRY_VERIFY(api->online());
        server->responses["/api/gluttony/recipes/4"] = eggs;
        recipes->open(4);
        QTRY_VERIFY(!recipes->fromCopy() && !recipes->loading());
        QCOMPARE(requestsTo("/api/gluttony/recipes/4"), 1);
    }

    void withNoCopyAnOutageSaysSo()
    {
        api->setSessionToken("tok");
        keepEggs();
        goOffline();
        recipes->open(2);
        QTRY_VERIFY_WITH_TIMEOUT(!recipes->loading(), 10000);
        QCOMPARE(recipes->error(), QStringLiteral("Could not reach the server"));
        QVERIFY(!recipes->fromCopy());
    }

    void aLoadedRecipeRefreshesItsCopy()
    {
        api->setSessionToken("tok");
        keepEggs();
        server->responses["/api/gluttony/recipes/4"] = eggs;
        recipes->open(4);
        QTRY_VERIFY(!recipes->loading());
        QVERIFY(!recipes->fromCopy());
        QCOMPARE(copies->recipe(4).value("title").toString(), QStringLiteral("Stub Spinach Eggs"));
        // A recipe with no copy is not kept by being looked at.
        server->responses["/api/gluttony/recipes/2"] = noServings;
        recipes->open(2);
        QTRY_VERIFY(!recipes->loading());
        QVERIFY(!copies->has(2));
    }

    void aGoneAnswerIsNotHiddenByACopy()
    {
        api->setSessionToken("tok");
        keepEggs();
        server->statuses["/api/gluttony/recipes/4"] = 404;
        server->responses["/api/gluttony/recipes/4"] = R"({"status":"error","message":"no such recipe"})";
        recipes->open(4);
        QTRY_VERIFY(!recipes->loading());
        QVERIFY(recipes->gone());
        QVERIFY(!recipes->fromCopy());
    }
};

QTEST_GUILESS_MAIN(TestRecipes)
#include "tst_recipes.moc"
