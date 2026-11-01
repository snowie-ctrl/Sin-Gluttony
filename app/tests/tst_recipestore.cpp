#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUrlQuery>

#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/AccountStore.h"
#include "services/RecipeStore.h"

static QString path(const QString &route)
{
    return QStringLiteral("/api/gluttony") + route;
}

static const qint64 day = 24LL * 60 * 60 * 1000;

// A recipe's detail as GET /recipes/<id> answers it.
static QByteArray detail(int id, const QString &title, bool hasImage = true, const QJsonObject &mine = {})
{
    QJsonObject recipe{{"id", id}, {"kind", "food"}, {"title", title}, {"course", "main"}, {"hasImage", hasImage},
                       {"steps", QJsonArray{QJsonObject{{"text", "Cook it."}}}}, {"ingredients", QJsonArray()},
                       {"mine", mine.isEmpty() ? QJsonObject{{"craving", false}, {"lists", QJsonArray()},
                                                             {"devoured", QJsonArray()}, {"stars", QJsonValue()},
                                                             {"note", QJsonValue()}} : mine}};
    return QJsonDocument(QJsonObject{{"status", "ok"}, {"data", recipe}}).toJson();
}

// A manifest: Cravings with `cravings`, a list "Weeknights" (11) with `weeknights`, and every one with `stamp`.
static QByteArray manifest(const QList<int> &cravings, const QList<int> &weeknights = {},
                           const QString &stamp = "2026-10-20T08:30:15", const QList<int> &extra = {})
{
    QJsonArray recipes, first, second;
    QList<int> all = cravings + weeknights + extra;
    std::sort(all.begin(), all.end());
    all.erase(std::unique(all.begin(), all.end()), all.end());
    for (const int id : all)
        recipes.append(QJsonObject{{"id", id}, {"updatedAt", stamp}, {"removed", false}});
    for (const int id : cravings)
        first.append(id);
    for (const int id : weeknights)
        second.append(id);
    const QJsonObject data{{"lists", QJsonArray{QJsonObject{{"id", 3}, {"title", "Cravings"}, {"kind", "cravings"},
                                                            {"recipeIds", first}},
                                                QJsonObject{{"id", 11}, {"title", "Weeknights"}, {"kind", "custom"},
                                                            {"recipeIds", second}}}},
                           {"recipes", recipes}};
    return QJsonDocument(QJsonObject{{"status", "ok"}, {"data", data}}).toJson();
}

// A `mine` block as the server sends it.
static QJsonObject mineWith(const QJsonValue &stars, const QJsonValue &note, const QJsonArray &devoured = {},
                            bool craving = true)
{
    return QJsonObject{{"craving", craving}, {"lists", QJsonArray()}, {"devoured", devoured}, {"stars", stars},
                       {"note", note}};
}

// The manifest `body` with `mine` set on recipe `id`, as the server sends what the person keeps on each recipe.
static QByteArray withMine(const QByteArray &body, int id, const QJsonObject &mine)
{
    QJsonObject root = QJsonDocument::fromJson(body).object();
    QJsonObject data = root.value("data").toObject();
    QJsonArray recipes = data.value("recipes").toArray();
    for (int i = 0; i < recipes.size(); ++i) {
        QJsonObject entry = recipes.at(i).toObject();
        if (entry.value("id").toInt() == id) {
            entry.insert("mine", mine);
            recipes.replace(i, entry);
        }
    }
    data.insert("recipes", recipes);
    root.insert("data", data);
    return QJsonDocument(root).toJson();
}


class TestRecipeStore : public QObject
{
    Q_OBJECT

    std::unique_ptr<QTemporaryDir> dir;
    std::unique_ptr<FakeServer> server;
    std::unique_ptr<Api> api;
    std::unique_ptr<AccountStore> accounts;
    std::unique_ptr<RecipeStore> store;
    qint64 now = 1'700'000'000'000;

    QList<QUrl> requestsTo(const QString &route) const
    {
        QList<QUrl> found;
        for (const QUrl &url : server->requests)
            if (url.path() == path(route))
                found << url;
        return found;
    }

    QString copyFile(int id, const char *suffix = ".json") const
    {
        return dir->path() + QStringLiteral("/accounts/7/recipes/%1").arg(id) + QLatin1String(suffix);
    }

    void serve(int id, const QString &title, bool hasImage = true)
    {
        server->responses[path(QStringLiteral("/recipes/%1").arg(id))] = detail(id, title, hasImage);
        server->responses[path(QStringLiteral("/images/%1").arg(id))] = "JPEG-" + QByteArray::number(id);
    }

    // Refreshes and waits until it has finished.
    void refreshed()
    {
        store->refresh();
        QTRY_VERIFY(!store->refreshing());
    }

private slots:
    void init()
    {
        store.reset();
        dir = std::make_unique<QTemporaryDir>();
        server = std::make_unique<FakeServer>();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server->serverPort()));
        // The token is set before the store exists, so only the tests that ask for it see a refresh on its arrival.
        api->setSessionToken("tok");
        accounts = std::make_unique<AccountStore>(dir->path());
        accounts->open(7, "ann");
        now = 1'700'000'000'000;
        store = std::make_unique<RecipeStore>(*api);
        store->setClock([this]() { return now; });
        store->setStore(accounts.get());
    }

    void cleanup()
    {
        store.reset();
    }

    void aStarGivenOnAnotherDeviceReachesTheCopyWithoutFetchingIt()
    {
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(QJsonValue(), QJsonValue()));
        server->responses[path("/recipes/5")] = detail(5, "Stub Coq au Vin", true, mineWith(QJsonValue(), QJsonValue()));
        server->responses[path("/images/5")] = "JPEG-" + QByteArray::number(5);
        refreshed();
        QCOMPARE(requestsTo("/recipes/5").size(), 1);
        QCOMPARE(requestsTo("/images/5").size(), 1);

        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(4, "less salt"));
        refreshed();
        const QVariantMap mine = store->recipe(5).value("mine").toMap();
        QCOMPARE(mine.value("stars").toInt(), 4);
        QCOMPARE(mine.value("note").toString(), QStringLiteral("less salt"));
        // The tiles read the copy's flags.
        QCOMPARE(store->cravings().first().toMap().value("stars").toInt(), 4);
        // Neither the recipe nor its picture was asked for again.
        QCOMPARE(requestsTo("/recipes/5").size(), 1);
        QCOMPARE(requestsTo("/images/5").size(), 1);
    }

    void aMarkRemovedElsewhereLeavesTheCopy()
    {
        const QJsonArray made{QJsonObject{{"id", 41}, {"on", "2026-10-20"}}};
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(QJsonValue(), QJsonValue(), made));
        server->responses[path("/recipes/5")] = detail(5, "Stub Coq au Vin", false,
                                                       mineWith(QJsonValue(), QJsonValue(), made));
        refreshed();
        QCOMPARE(store->again().size(), 1);

        // The mark is taken back on another device: no row is left to date, but the manifest's mine says so.
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(QJsonValue(), QJsonValue()));
        refreshed();
        QVERIFY(store->again().isEmpty());
        QVERIFY(store->recipe(5).value("mine").toMap().value("devoured").toList().isEmpty());
        QCOMPARE(requestsTo("/recipes/5").size(), 1);
    }

    void aChangeStillWaitingKeepsTheCopysValue()
    {
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(QJsonValue(), QJsonValue()));
        server->responses[path("/recipes/5")] = detail(5, "Stub Coq au Vin", false, mineWith(QJsonValue(), QJsonValue()));
        refreshed();
        // Two stars given offline: the queue holds them and Saved has patched the copy.
        bool waiting = true;
        store->setWaiting([&waiting](int recipeId) { return waiting && recipeId == 5; });
        store->patchMine(5, mineWith(2, QJsonValue()).toVariantMap());

        // The manifest is read before the queued stars reach the server: it still says none.
        refreshed();
        QCOMPARE(store->recipe(5).value("mine").toMap().value("stars").toInt(), 2);

        // Once the queue has nothing for it, the server's word stands.
        waiting = false;
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(2, QJsonValue()));
        refreshed();
        QCOMPARE(store->recipe(5).value("mine").toMap().value("stars").toInt(), 2);
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(5, QJsonValue()));
        refreshed();
        QCOMPARE(store->recipe(5).value("mine").toMap().value("stars").toInt(), 5);
    }

    void aManifestWithoutMineLeavesTheCopysMineAlone()
    {
        // An older server (or a half-deployed one) sends no mine: the copy keeps its own.
        server->responses[path("/saved/manifest")] = manifest({5});
        server->responses[path("/recipes/5")] = detail(5, "Stub Coq au Vin", false);
        refreshed();
        store->patchMine(5, mineWith(3, QJsonValue()).toVariantMap());
        refreshed();
        QCOMPARE(store->recipe(5).value("mine").toMap().value("stars").toInt(), 3);
    }

    void aManifestReadBeforeTheQueuesBatchDoesNotRollTheCopyBack()
    {
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(QJsonValue(), QJsonValue()));
        server->responses[path("/recipes/5")] = detail(5, "Stub Coq au Vin", false, mineWith(QJsonValue(), QJsonValue()));
        refreshed();
        bool waiting = true;
        store->setWaiting([&waiting](int recipeId) { return waiting && recipeId == 5; });
        store->patchMine(5, mineWith(2, QJsonValue()).toVariantMap());

        // The manifest is asked for while the change waits, and its answer (read before the batch was applied, so
        // stars still none) is held back.
        server->holdNext[path("/saved/manifest")] = 1;
        store->refresh();
        QTRY_COMPARE(requestsTo("/saved/manifest").size(), 2);
        // The batch's answer comes first: the queue has nothing for the recipe by the time the manifest arrives.
        waiting = false;
        server->releaseHeld();
        QTRY_VERIFY(!store->refreshing());
        QCOMPARE(store->recipe(5).value("mine").toMap().value("stars").toInt(), 2);

        // A refresh asked for with nothing waiting takes the server's word.
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(5, QJsonValue()));
        refreshed();
        QCOMPARE(store->recipe(5).value("mine").toMap().value("stars").toInt(), 5);
    }

    void aDetailFetchedWhileAChangeWaitsKeepsTheCopysMine()
    {
        // A copy whose picture is missing is fetched whole again at the next refresh.
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, mineWith(QJsonValue(), QJsonValue()));
        server->responses[path("/recipes/5")] = detail(5, "Stub Coq au Vin", true, mineWith(QJsonValue(), QJsonValue()));
        server->responses[path("/images/5")] = "JPEG-" + QByteArray::number(5);
        server->statuses[path("/images/5")] = 500;
        refreshed();
        QVERIFY(store->has(5));
        QVERIFY(!QFile::exists(copyFile(5, ".jpg")));
        store->setWaiting([](int recipeId) { return recipeId == 5; });
        store->patchMine(5, mineWith(2, QJsonValue()).toVariantMap());

        server->statuses.remove(path("/images/5"));
        refreshed();
        QCOMPARE(requestsTo("/recipes/5").size(), 2);
        QCOMPARE(store->recipe(5).value("mine").toMap().value("stars").toInt(), 2);
        QTRY_VERIFY(QFile::exists(copyFile(5, ".jpg")));
    }

    void anEmptyMineInTheManifestLeavesTheCopysMineAlone()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        server->responses[path("/recipes/5")] = detail(5, "Stub Coq au Vin", false);
        refreshed();
        store->patchMine(5, mineWith(3, "keep it").toVariantMap());
        server->responses[path("/saved/manifest")] = withMine(manifest({5}), 5, QJsonObject());
        refreshed();
        const QVariantMap mine = store->recipe(5).value("mine").toMap();
        QCOMPARE(mine.value("stars").toInt(), 3);
        QCOMPARE(mine.value("note").toString(), QStringLiteral("keep it"));
    }

    void aSavedRecipeIsKeptWithItsPicture()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Stub Coq au Vin");
        refreshed();
        QVERIFY(store->has(5));
        QVERIFY(QFile::exists(copyFile(5)));
        QFile picture(copyFile(5, ".jpg"));
        QVERIFY(picture.open(QIODevice::ReadOnly));
        QCOMPARE(picture.readAll(), QByteArray("JPEG-5"));
        QCOMPARE(store->recipe(5).value("title").toString(), QStringLiteral("Stub Coq au Vin"));
        // Thumbnails come from the large picture (spec §6), on disk, online or not.
        QVERIFY(store->pictureUrl(5, false).startsWith("file:"));
        QCOMPARE(store->pictureUrl(5, false), store->pictureUrl(5, true));
        QCOMPARE(AccountStore::readJson(copyFile(5)).value("updatedAt").toString(), QStringLiteral("2026-10-20T08:30:15"));
        // The picture request carried the session (SessionAuth), as every Image's does.
        bool signedRequest = false;
        for (int i = 0; i < server->requests.size(); ++i)
            if (server->requests[i].path() == path("/images/5"))
                signedRequest = server->heads[i].contains("X-Session-Token: tok");
        QVERIFY(signedRequest);
    }

    void aRecipeWithoutAPictureAsksForNone()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Plain", false);
        refreshed();
        QVERIFY(store->has(5));
        QVERIFY(requestsTo("/images/5").isEmpty());
        // No copy of the picture: the server's address, as before.
        QVERIFY(store->pictureUrl(5, false).endsWith("/thumbs/5"));
        QVERIFY(store->pictureUrl(5, true).endsWith("/images/5"));
    }

    void theListsAndTheirTilesComeFromTheManifest()
    {
        server->responses[path("/saved/manifest")] = manifest({5, 6}, {6});
        serve(5, "Five");
        serve(6, "Six");
        refreshed();
        const QVariantList lists = store->lists();
        QCOMPARE(lists.size(), 2);
        QCOMPARE(lists.at(0).toMap(), (QVariantMap{{"id", 3}, {"title", "Cravings"}, {"kind", "cravings"}, {"count", 2}}));
        QCOMPARE(lists.at(1).toMap().value("count").toInt(), 1);
        const QVariantList tiles = store->tilesOf(3);
        QCOMPARE(tiles.size(), 2);
        QCOMPARE(tiles.at(0).toMap().value("title").toString(), QStringLiteral("Five"));
        QCOMPARE(tiles.at(1).toMap().value("id").toInt(), 6);
        QCOMPARE(store->cravings().size(), 2);
        QVERIFY(QFile::exists(dir->path() + "/accounts/7/manifest.json"));
    }

    void anUnchangedCopyIsNotFetchedAgain()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        refreshed();
        QCOMPARE(requestsTo("/recipes/5").size(), 1);
        QCOMPARE(requestsTo("/images/5").size(), 1);
    }

    void aChangedRecipeIsFetchedAgain()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        server->responses[path("/saved/manifest")] = manifest({5}, {}, "2026-10-28T09:00:00");
        serve(5, "Five, better");
        refreshed();
        QCOMPARE(requestsTo("/recipes/5").size(), 2);
        QCOMPARE(store->recipe(5).value("title").toString(), QStringLiteral("Five, better"));
    }

    void aRecipeThatLeftTheListsGoes()
    {
        server->responses[path("/saved/manifest")] = manifest({5, 6});
        serve(5, "Five");
        serve(6, "Six");
        refreshed();
        server->responses[path("/saved/manifest")] = manifest({6});
        refreshed();
        QVERIFY(!store->has(5));
        QVERIFY(!QFile::exists(copyFile(5)));
        QVERIFY(!QFile::exists(copyFile(5, ".jpg")));
        QVERIFY(store->has(6));
    }

    void aFailedManifestDeletesNothing()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        server->statuses[path("/saved/manifest")] = 500;
        server->responses[path("/saved/manifest")] = R"({"status":"error","message":"down"})";
        refreshed();
        QVERIFY(store->has(5));
        QVERIFY(QFile::exists(copyFile(5)));
        QCOMPARE(store->lists().size(), 2);
    }

    // A 200 that is not a manifest (a proxy's or a half-deployed server's answer) says nothing about what to keep.
    void aManifestWithoutItsListsOrRecipesDeletesNothing()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        const QJsonObject kept = AccountStore::readJson(dir->path() + "/accounts/7/manifest.json");
        for (const QByteArray &answer : {QByteArray(R"({"status":"ok","data":{}})"),
                                         QByteArray(R"({"status":"ok","data":{"lists":[]}})"),
                                         QByteArray(R"({"status":"ok","data":{"recipes":[]}})"),
                                         QByteArray(R"({"status":"ok","data":{"lists":"none","recipes":[]}})"),
                                         QByteArray(R"({"status":"ok"})")}) {
            server->responses[path("/saved/manifest")] = answer;
            refreshed();
            QVERIFY2(store->has(5), answer.constData());
            QVERIFY2(QFile::exists(copyFile(5)), answer.constData());
            QCOMPARE(store->lists().size(), 2);
            QCOMPARE(AccountStore::readJson(dir->path() + "/accounts/7/manifest.json"), kept);
        }
    }

    void aDetailThatIsNotTheServersOwn404LeavesTheCopy()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        // A proxy's page, not the server saying the recipe is gone.
        server->responses[path("/saved/manifest")] = manifest({5}, {}, "2026-10-28T09:00:00");
        server->statuses[path("/recipes/5")] = 404;
        server->responses[path("/recipes/5")] = "<html><body>Not Found</body></html>";
        refreshed();
        QVERIFY(store->has(5));
        QVERIFY(QFile::exists(copyFile(5)));
        // The server's own 404 still takes the copy away (aRecipeThatHasGoneIsDeleted).
    }

    void aRecipeThatHasGoneIsDeleted()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        server->responses[path("/saved/manifest")] = manifest({5}, {}, "2026-10-28T09:00:00");
        server->statuses[path("/recipes/5")] = 404;
        server->responses[path("/recipes/5")] = R"({"status":"error","message":"no such recipe"})";
        refreshed();
        QVERIFY(!store->has(5));
    }

    void aCookedRecipeIsKeptAndNamedToTheServer()
    {
        serve(9, "Cooked");
        store->keepForCooking(QJsonDocument::fromJson(detail(9, "Cooked")).object().value("data").toObject().toVariantMap());
        QVERIFY(store->has(9));
        QTRY_VERIFY(QFile::exists(copyFile(9, ".jpg")));
        QCOMPARE(qint64(AccountStore::readJson(copyFile(9)).value("cookedAt").toDouble()), now);
        server->responses[path("/saved/manifest")] = manifest({}, {}, "2026-10-20T08:30:15", {9});
        now += 29 * day;
        refreshed();
        QCOMPARE(QUrlQuery(requestsTo("/saved/manifest").last()).queryItemValue("extra"), QStringLiteral("9"));
        QVERIFY(store->has(9));
    }

    void aRecipeCookedWhileARefreshIsOnItsWayStays()
    {
        server->responses[path("/saved/manifest")] = manifest({});
        server->holdNext[path("/saved/manifest")] = 1;
        store->refresh();
        QTRY_COMPARE(requestsTo("/saved/manifest").size(), 1);
        now += 1000;
        store->keepForCooking(QJsonDocument::fromJson(detail(9, "Cooked", false)).object().value("data").toObject().toVariantMap());
        server->releaseHeld();
        QTRY_VERIFY(!store->refreshing());
        QVERIFY(store->has(9));
    }

    void aCookedPictureArrivingMidRefreshDoesNotEndIt()
    {
        server->responses[path("/saved/manifest")] = manifest({});
        server->holdNext[path("/saved/manifest")] = 1;
        serve(9, "Cooked");
        store->refresh();
        QTRY_COMPARE(requestsTo("/saved/manifest").size(), 1);
        store->keepForCooking(QJsonDocument::fromJson(detail(9, "Cooked")).object().value("data").toObject().toVariantMap());
        QTRY_VERIFY(QFile::exists(copyFile(9, ".jpg")));
        QTest::qWait(50);
        // The manifest has not answered yet: the refresh is still on its way, and the cooked copy is not undone.
        QVERIFY(store->refreshing());
        server->releaseHeld();
        QTRY_VERIFY(!store->refreshing());
        QVERIFY(store->has(9));
    }

    void aCookCopyOlderThanThirtyDaysGoes()
    {
        serve(9, "Cooked");
        store->keepForCooking(QJsonDocument::fromJson(detail(9, "Cooked", false)).object().value("data").toObject().toVariantMap());
        server->responses[path("/saved/manifest")] = manifest({});
        now += 31 * day;
        refreshed();
        QVERIFY(!QUrlQuery(requestsTo("/saved/manifest").last()).hasQueryItem("extra"));
        QVERIFY(!store->has(9));
        QVERIFY(!QFile::exists(copyFile(9)));
    }

    void cookingASavedRecipeKeepsItsStamp()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        store->keepForCooking(store->recipe(5));
        QCOMPARE(AccountStore::readJson(copyFile(5)).value("updatedAt").toString(), QStringLiteral("2026-10-20T08:30:15"));
        refreshed();
        QCOMPARE(requestsTo("/recipes/5").size(), 1);
    }

    void atMostFourAreFetchedAtOnce()
    {
        QList<int> ids{1, 2, 3, 4, 5, 6};
        server->responses[path("/saved/manifest")] = manifest(ids);
        for (const int id : ids) {
            serve(id, QStringLiteral("R%1").arg(id), false);
            // Only the first four are parked: the fifth and sixth must wait for a free slot, not for the server.
            if (id <= 4)
                server->holdNext[path(QStringLiteral("/recipes/%1").arg(id))] = 1;
        }
        store->refresh();
        QTRY_COMPARE(server->requests.size(), 5);   // the manifest and four details
        QTest::qWait(100);
        QCOMPARE(server->requests.size(), 5);
        server->releaseHeld();
        QTRY_VERIFY(store->has(6));
        QTRY_VERIFY(!store->refreshing());
    }

    void anotherAccountHasItsOwnCopies()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        accounts->open(8, "bea");
        QVERIFY(!store->has(5));
        QVERIFY(store->lists().isEmpty());
        accounts->open(7, "ann");
        QVERIFY(store->has(5));
        QCOMPARE(store->lists().size(), 2);
    }

    void anAnswerForTheLastAccountIsDropped()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        server->holdNext[path("/saved/manifest")] = 1;
        store->refresh();
        QTRY_COMPARE(requestsTo("/saved/manifest").size(), 1);
        accounts->open(8, "bea");
        server->releaseHeld();
        QTest::qWait(200);
        QVERIFY(!store->has(5));
        QVERIFY(!QDir(dir->path() + "/accounts/8/recipes").exists("5.json"));
        QVERIFY(!store->refreshing());
    }

    void theTokensArrivalRefreshes()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        api->setSessionToken(QString());
        api->setSessionToken("tok2");
        QTRY_VERIFY(store->has(5));
    }

    void nothingIsAskedWithNoAccount()
    {
        accounts->close();
        store->refresh();
        QTest::qWait(100);
        QVERIFY(requestsTo("/saved/manifest").isEmpty());
    }

    void offlineRowsAndSearchReadTheCopies()
    {
        server->responses[path("/saved/manifest")] = manifest({5}, {6});
        serve(5, "Stub Coq au Vin");
        serve(6, "Stub Spinach Eggs");
        refreshed();
        QCOMPARE(store->search("coq").size(), 1);
        QCOMPARE(store->search("STUB").size(), 2);
        QCOMPARE(store->search("STUB").at(0).toMap().value("title").toString(), QStringLiteral("Stub Coq au Vin"));
        QVERIFY(store->search("  ").isEmpty());
        QVERIFY(store->again().isEmpty());
        store->patchMine(6, QVariantMap{{"craving", false}, {"devoured", QVariantList{QVariantMap{{"id", 3}, {"on", "2026-10-27"}}}},
                                         {"stars", 4}});
        store->patchMine(5, QVariantMap{{"craving", true}, {"devoured", QVariantList{QVariantMap{{"id", 4}, {"on", "2026-10-28"}}}}});
        const QVariantList again = store->again();
        QCOMPARE(again.size(), 2);
        QCOMPARE(again.at(0).toMap().value("id").toInt(), 5);
        QCOMPARE(again.at(1).toMap().value("stars").toInt(), 4);
        QCOMPARE(again.at(1).toMap().value("devouredCount").toInt(), 1);
        QCOMPARE(store->recipe(6).value("mine").toMap().value("stars").toInt(), 4);
        QVERIFY(store->tilesOf(3).at(0).toMap().value("craving").toBool());
    }

    void aFresherDetailReplacesTheCopyAndKeepsItsStamps()
    {
        server->responses[path("/saved/manifest")] = manifest({5});
        serve(5, "Five");
        refreshed();
        QSignalSpy changed(store.get(), &RecipeStore::changed);
        store->update(QJsonDocument::fromJson(detail(5, "Five again")).object().value("data").toObject().toVariantMap());
        QVERIFY(changed.count() >= 1);
        QCOMPARE(store->recipe(5).value("title").toString(), QStringLiteral("Five again"));
        QCOMPARE(AccountStore::readJson(copyFile(5)).value("updatedAt").toString(), QStringLiteral("2026-10-20T08:30:15"));
        // A recipe with no copy is not kept by update().
        store->update(QJsonDocument::fromJson(detail(77, "Not saved")).object().value("data").toObject().toVariantMap());
        QVERIFY(!store->has(77));
    }
};

QTEST_GUILESS_MAIN(TestRecipeStore)
#include "tst_recipestore.moc"
