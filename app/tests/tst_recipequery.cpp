#include <QAbstractListModel>
#include <QSignalSpy>
#include <QTest>
#include <QUrlQuery>

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

    FakeServer server;
    std::unique_ptr<Api> api;
    std::unique_ptr<RecipeQuery> query;

    QList<QUrl> recipeRequests() const
    {
        QList<QUrl> found;
        for (const QUrl &url : server.requests)
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
        server.responses.clear();
        server.queued.clear();
        server.statuses.clear();
        server.queuedStatuses.clear();
        server.requests.clear();
        server.holdNext.clear();
        query.reset();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server.serverPort()));
        query = std::make_unique<RecipeQuery>(*api);
    }

    void theFirstPageThenTheNext()
    {
        server.queued[recipesPath] = {page(30, 1, 24), page(30, 25, 6)};
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
        server.responses[recipesPath] = page(1, 1, 1);
        query->run(kind("food"));
        query->run(kind("food"));
        QTRY_VERIFY(query->answered());
        query->run(kind("food"));
        QTest::qWait(100);
        QCOMPARE(recipeRequests().size(), 1);
    }

    void anOlderAnswerNeverLandsInANewerList()
    {
        server.queued[recipesPath] = {page(1, 100, 1), page(1, 200, 1)};
        server.holdNext[recipesPath] = 1;
        query->run(kind("food"));
        QTRY_COMPARE(recipeRequests().size(), 1);
        query->run(kind("drink"));
        QTRY_COMPARE(query->count(), 1);
        server.releaseHeld();
        QTest::qWait(200);
        auto *model = qobject_cast<QAbstractListModel *>(query->tiles());
        QCOMPARE(model->data(model->index(0), Qt::UserRole + 1).toMap().value("id").toInt(), 200);
    }

    void aFailedPageKeepsTheRowsAndMoreAsksForItAgain()
    {
        server.queued[recipesPath] = {page(30, 1, 24), R"({"status":"error","message":"busy"})", page(30, 25, 6)};
        server.queuedStatuses[recipesPath] = {200, 500, 200};
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
};

QTEST_GUILESS_MAIN(TestRecipeQuery)
#include "tst_recipequery.moc"
