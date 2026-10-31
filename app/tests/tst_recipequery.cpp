#include <QAbstractListModel>
#include <QSignalSpy>
#include <QTest>
#include <QUrlQuery>

#include <algorithm>
#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/RecipeQuery.h"

static const QString recipesPath = QStringLiteral("/api/gluttony/recipes");

static QByteArray page(int total, int first, int count)
{
    QByteArray tiles;
    for (int i = 0; i < count; ++i)
        tiles += (i ? "," : "") + QByteArray(R"({"id":)") + QByteArray::number(first + i) + R"(,"title":"Dish"})";
    return R"({"status":"ok","data":{"total":)" + QByteArray::number(total) + R"(,"page":1,"pageSize":24,"recipes":[)"
           + tiles + "]}}";
}


class TestRecipeQuery : public QObject
{
    Q_OBJECT

    std::unique_ptr<FakeServer> server;
    std::unique_ptr<Api> api;
    std::unique_ptr<RecipeQuery> query;

    QList<QUrl> recipeRequests() const
    {
        QList<QUrl> found;
        for (const QUrl &url : server->requests)
            if (url.path() == recipesPath)
                found << url;
        return found;
    }

    static QUrlQuery kind(const QString &value)
    {
        QUrlQuery q;
        q.addQueryItem("kind", value);
        return q;
    }

private slots:
    void init()
    {
        query.reset();
        api.reset();
        // A new server for every case, listening before the last one goes, so a late request never reaches it.
        server = std::make_unique<FakeServer>();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server->serverPort()));
        query = std::make_unique<RecipeQuery>(*api);
    }

    void theFirstPageThenTheNext()
    {
        server->queued[recipesPath] = {page(30, 1, 24), page(30, 25, 6)};
        query->run(kind("food"));
        QTRY_COMPARE(query->count(), 24);
        QCOMPARE(query->total(), 30);
        QVERIFY(!query->exhausted());
        query->more();
        QTRY_COMPARE(query->count(), 30);
        QVERIFY(query->exhausted());
        const QUrlQuery second(recipeRequests().last());
        QCOMPARE(second.queryItemValue("page"), QStringLiteral("2"));
        QCOMPARE(second.queryItemValue("pageSize"), QStringLiteral("24"));
        QCOMPARE(second.queryItemValue("kind"), QStringLiteral("food"));
        query->more();
        QTest::qWait(100);
        QCOMPARE(recipeRequests().size(), 2);
    }

    void theSameQueryTwiceAsksOnce()
    {
        server->responses[recipesPath] = page(1, 1, 1);
        query->run(kind("food"));
        query->run(kind("food"));
        QTRY_VERIFY(query->answered());
        query->run(kind("food"));
        QTest::qWait(100);
        QCOMPARE(recipeRequests().size(), 1);
    }

    void anOlderAnswerNeverLandsInANewerList()
    {
        server->queued[recipesPath] = {page(1, 100, 1), page(1, 200, 1)};
        server->holdNext[recipesPath] = 1;
        query->run(kind("food"));
        QTRY_COMPARE(recipeRequests().size(), 1);
        query->run(kind("drink"));
        QTRY_COMPARE(query->count(), 1);
        server->releaseHeld();
        QTest::qWait(200);
        auto *model = qobject_cast<QAbstractListModel *>(query->tiles());
        QCOMPARE(model->data(model->index(0), Qt::UserRole + 1).toMap().value("id").toInt(), 200);
    }

    void aFailedPageKeepsTheRowsAndMoreAsksForItAgain()
    {
        server->queued[recipesPath] = {page(30, 1, 24), R"({"status":"error","message":"busy"})", page(30, 25, 6)};
        server->queuedStatuses[recipesPath] = {200, 500, 200};
        query->run(kind("food"));
        QTRY_COMPARE(query->count(), 24);
        query->more();
        QTRY_COMPARE(query->error(), QStringLiteral("busy"));
        QCOMPARE(query->count(), 24);
        QVERIFY(!query->exhausted());
        query->more();
        QTRY_COMPARE(query->count(), 30);
        QVERIFY(query->error().isEmpty());
    }

    void aQueryOfItsOwnAsksItsOwnPath()
    {
        const QString listPath = QStringLiteral("/api/gluttony/lists/11/recipes");
        server->responses[listPath] = page(2, 1, 2);
        RecipeQuery list(*api, QStringLiteral("/lists/11/recipes"));
        list.run(QUrlQuery());
        QTRY_COMPARE(list.count(), 2);
        QCOMPARE(server->requests.last().path(), listPath);
        QCOMPARE(QUrlQuery(server->requests.last()).queryItemValue("page"), QStringLiteral("1"));
    }

    void aNewPathDropsTheRowsAndAsksAgain()
    {
        server->responses["/api/gluttony/lists/11/recipes"] = page(2, 1, 2);
        server->responses["/api/gluttony/lists/12/recipes"] = page(1, 50, 1);
        RecipeQuery list(*api, QStringLiteral("/lists/11/recipes"));
        list.run(QUrlQuery());
        QTRY_COMPARE(list.count(), 2);
        list.setPath(QStringLiteral("/lists/12/recipes"));
        QCOMPARE(list.count(), 0);
        QVERIFY(!list.answered());
        list.run(QUrlQuery());
        QTRY_COMPARE(list.count(), 1);
        QCOMPARE(list.rowAt(0).value("id").toInt(), 50);
    }

    void droppingARowOfAWholeListTakesItOut()
    {
        server->responses[recipesPath] = page(3, 1, 3);
        query->run(kind("food"));
        QTRY_COMPARE(query->count(), 3);
        query->dropRecipe(2);
        QCOMPARE(query->count(), 2);
        QCOMPARE(query->total(), 2);
        QVERIFY(query->exhausted());
        QCOMPARE(query->rowAt(1).value("id").toInt(), 3);
        QTest::qWait(100);
        QCOMPARE(recipeRequests().size(), 1);
    }

    void droppingARowOfALongerListAsksAgainFromTheStart()
    {
        // The server's later pages have moved up by one, so asking for page 2 would skip a recipe.
        server->queued[recipesPath] = {page(30, 1, 24), page(29, 1, 24)};
        query->run(kind("food"));
        QTRY_COMPARE(query->count(), 24);
        query->dropRecipe(5);
        QTRY_COMPARE(recipeRequests().size(), 2);
        QCOMPARE(QUrlQuery(recipeRequests().last()).queryItemValue("page"), QStringLiteral("1"));
        QTRY_COMPARE(query->total(), 29);
    }

    void movingARowKeepsEveryOther()
    {
        server->responses[recipesPath] = page(3, 1, 3);
        query->run(kind("food"));
        QTRY_COMPARE(query->count(), 3);
        query->moveRecipe(0, 2);
        QCOMPARE(query->rowAt(0).value("id").toInt(), 2);
        QCOMPARE(query->rowAt(1).value("id").toInt(), 3);
        QCOMPARE(query->rowAt(2).value("id").toInt(), 1);
        query->moveRecipe(2, 0);
        QCOMPARE(query->rowAt(0).value("id").toInt(), 1);
        query->moveRecipe(0, 9);        // out of range: nothing moves
        QCOMPARE(query->rowAt(0).value("id").toInt(), 1);
    }

    void rowsFromElsewhereAreShownWholeAndTheNextRunAsksTheServer()
    {
        RecipeQuery listQuery(*api, QStringLiteral("/lists/3/recipes"));
        listQuery.showRows(QVariantList{QVariantMap{{"id", 5}}, QVariantMap{{"id", 6}}});
        QCOMPARE(listQuery.count(), 2);
        QCOMPARE(listQuery.total(), 2);
        QVERIFY(listQuery.answered());
        QVERIFY(listQuery.exhausted());
        QVERIFY(!listQuery.loading());
        listQuery.run(QUrlQuery());
        QTRY_VERIFY(std::any_of(server->requests.cbegin(), server->requests.cend(), [](const QUrl &url) {
            return url.path() == QLatin1String("/api/gluttony/lists/3/recipes");
        }));
    }
};

QTEST_GUILESS_MAIN(TestRecipeQuery)
#include "tst_recipequery.moc"
