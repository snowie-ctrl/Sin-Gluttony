#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUrlQuery>

#include <memory>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/AccountStore.h"
#include "services/SyncQueue.h"

static QString path(const char *route)
{
    return QStringLiteral("/api/gluttony") + QLatin1String(route);
}

static const QString deadBase = QStringLiteral("http://127.0.0.1:1/api/gluttony");
static const QString clientA = QStringLiteral("11111111-2222-4333-8444-555555555555");

static QJsonObject mark(int recipeId = 1, const QString &clientId = clientA)
{
    return QJsonObject{{"op", "devoured"}, {"recipeId", recipeId}, {"on", "2026-10-28"}, {"clientId", clientId},
                       {"title", "Stub Coq au Vin"}};
}

static QJsonObject stars(int recipeId, const QJsonValue &value)
{
    return QJsonObject{{"op", "stars"}, {"recipeId", recipeId}, {"stars", value}, {"title", "Stub"}};
}

// /sync/batch's answer: each change's result in turn.
static QByteArray answer(const QList<QJsonObject> &results)
{
    QJsonArray list;
    for (const QJsonObject &result : results)
        list.append(result);
    return QJsonDocument(QJsonObject{{"status", "ok"}, {"data", QJsonObject{{"results", list}}}}).toJson();
}


class TestSyncQueue : public QObject
{
    Q_OBJECT

    std::unique_ptr<QTemporaryDir> dir;
    std::unique_ptr<FakeServer> server;
    std::unique_ptr<Api> api;
    std::unique_ptr<AccountStore> accounts;
    std::unique_ptr<SyncQueue> queue;

    QString live() const { return QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server->serverPort()); }

    QList<QJsonObject> batches() const
    {
        QList<QJsonObject> found;
        for (int i = 0; i < server->requests.size(); ++i)
            if (server->requests[i].path() == path("/sync/batch"))
                found << QJsonDocument::fromJson(server->bodies[i]).object();
        return found;
    }

    // The server stops answering: Api finds out on its next call.
    void goOffline()
    {
        api->setBases(QString(), deadBase);
        api->setPingDelays(60000, 60000);
        api->get("/ping", QUrlQuery(), nullptr);
        QTRY_VERIFY_WITH_TIMEOUT(!api->online(), 10000);
    }

    void comeBack()
    {
        api->setBases(QString(), live());
        api->checkNow();
        QTRY_VERIFY(api->online());
    }

    // The server refuses whatever is sent until the change waiting is stuck.
    // (A helper, not a test: it needs a change already waiting.)
    void refuseUntilStuck()
    {
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "refused"}, {"message", "no"}}});
        for (int i = 0; i < 10 && queue->stuck().isEmpty(); ++i) {
            QTRY_VERIFY(!queue->sending());
            if (queue->stuck().isEmpty())
                queue->flush();
        }
        QTRY_COMPARE(queue->stuck().size(), 1);
    }

private slots:
    void init()
    {
        queue.reset();
        dir = std::make_unique<QTemporaryDir>();
        server = std::make_unique<FakeServer>();
        api = std::make_unique<Api>();
        api->setBases(QString(), live());
        api->setSessionToken("tok");
        accounts = std::make_unique<AccountStore>(dir->path());
        accounts->open(7, "ann");
        queue = std::make_unique<SyncQueue>(*api);
        queue->setStore(accounts.get());
        queue->setRetryDelay(60000);
    }

    void cleanup()
    {
        queue.reset();
    }

    void aChangeMadeOfflineWaitsOnDisk()
    {
        goOffline();
        queue->add(mark());
        QCOMPARE(queue->count(), 1);
        const QJsonObject kept = queue->changes().first();
        QCOMPARE(kept.value("op").toString(), QStringLiteral("devoured"));
        QCOMPARE(kept.value("failures").toInt(), 0);
        QVERIFY(QRegularExpression(R"(^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$)").match(kept.value("at").toString()).hasMatch());
        QVERIFY(!kept.value("id").toString().isEmpty());
        QVERIFY(batches().isEmpty());
        // Another start of the app finds it.
        SyncQueue again(*api);
        again.setStore(accounts.get());
        QCOMPARE(again.count(), 1);
        QCOMPARE(again.changes().first().value("clientId").toString(), clientA);
    }

    void itIsSentWhenTheServerAnswersAgain()
    {
        goOffline();
        queue->add(mark());
        queue->add(stars(1, 4));
        server->responses[path("/sync/batch")] = answer({
            QJsonObject{{"result", "applied"}, {"id", 41}, {"recipeId", 1}, {"on", "2026-10-28"}, {"count", 1}},
            QJsonObject{{"result", "applied"}, {"recipeId", 1}, {"stars", 4}}});
        QSignalSpy taken(queue.get(), &SyncQueue::taken);
        comeBack();
        QTRY_COMPARE(queue->count(), 0);
        QCOMPARE(batches().size(), 1);
        const QJsonArray ops = batches().first().value("ops").toArray();
        QCOMPARE(ops.size(), 2);
        QCOMPARE(ops.at(0).toObject().value("clientId").toString(), clientA);
        QCOMPARE(ops.at(1).toObject().value("stars").toInt(), 4);
        QCOMPARE(taken.count(), 2);
        QCOMPARE(taken.at(0).at(1).toJsonObject().value("id").toInt(), 41);
        QCOMPARE(AccountStore::readJson(dir->path() + "/accounts/7/sync-queue.json").value("changes").toArray().size(), 0);
    }

    void waitsNamesTheRecipesWithAChangeWaiting()
    {
        goOffline();
        queue->add(stars(1, 4));
        QVERIFY(queue->waits(1));
        QVERIFY(!queue->waits(2));
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 1}, {"stars", 4}}});
        comeBack();
        QTRY_COMPARE(queue->count(), 0);
        QVERIFY(!queue->waits(1));
    }

    void addingWhileTheServerAnswersSendsAtOnce()
    {
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 1}, {"stars", 4}}});
        queue->add(stars(1, 4));
        QTRY_COMPARE(queue->count(), 0);
        QCOMPARE(batches().size(), 1);
    }

    void aNewerStarOrNoteReplacesTheOneWaiting()
    {
        goOffline();
        queue->add(stars(1, 3));
        queue->add(stars(1, 4));
        queue->add(stars(2, QJsonValue()));
        queue->add(QJsonObject{{"op", "note"}, {"recipeId", 1}, {"text", "a"}});
        queue->add(QJsonObject{{"op", "note"}, {"recipeId", 1}, {"text", "b"}});
        QCOMPARE(queue->count(), 3);
        QCOMPARE(queue->changes().at(0).value("stars").toInt(), 4);
        QVERIFY(queue->changes().at(1).value("stars").isNull());
        QCOMPARE(queue->changes().at(2).value("text").toString(), QStringLiteral("b"));
    }

    void everyMarkIsKept()
    {
        goOffline();
        queue->add(mark(1, clientA));
        queue->add(mark(1, QStringLiteral("22222222-2222-4333-8444-555555555555")));
        QCOMPARE(queue->count(), 2);
        QCOMPARE(queue->pendingMarks(1).size(), 2);
        QCOMPARE(queue->pendingMarks(1).at(0).toMap(), (QVariantMap{{"clientId", clientA}, {"on", "2026-10-28"}}));
        QVERIFY(queue->pendingMarks(2).isEmpty());
    }

    void aMarkTakenBackBeforeItIsSentGoes()
    {
        goOffline();
        queue->add(mark());
        QVERIFY(queue->dropMark(clientA));
        QCOMPARE(queue->count(), 0);
        QVERIFY(!queue->dropMark(clientA));
    }

    void aRefusedChangeIsStuckAfterFiveRefusals()
    {
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "refused"}, {"message", "no such recipe"}}});
        queue->add(stars(99, 4));
        for (int sent = 1; sent < 5; ++sent) {
            QTRY_COMPARE(batches().size(), sent);
            QTRY_VERIFY(!queue->sending());
            QCOMPARE(queue->changes().first().value("failures").toInt(), sent);
            QVERIFY(queue->stuck().isEmpty());
            queue->flush();
        }
        QTRY_COMPARE(batches().size(), 5);
        QTRY_COMPARE(queue->stuck().size(), 1);
        const QVariantMap stuck = queue->stuck().first().toMap();
        QCOMPARE(stuck.value("message").toString(), QStringLiteral("no such recipe"));
        QCOMPARE(stuck.value("title").toString(), QStringLiteral("Stub"));
        // A stuck change is never sent by itself again.
        queue->flush();
        QTest::qWait(100);
        QCOMPARE(batches().size(), 5);
        QCOMPARE(queue->count(), 1);
    }

    // Spec §8: a refused change is tried again on each reconnect, not whenever something else is added.
    void aRefusedChangeIsNotSentAgainByNewChangesButByAReconnect()
    {
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "refused"}, {"message", "no such recipe"}}});
        queue->add(stars(99, 4));
        QTRY_COMPARE(batches().size(), 1);
        QTRY_VERIFY(!queue->sending());
        QCOMPARE(queue->changes().first().value("failures").toInt(), 1);
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 1}, {"stars", 4}}});
        for (int recipe = 1; recipe <= 3; ++recipe) {
            queue->add(stars(recipe, 4));
            QTRY_COMPARE(batches().size(), 1 + recipe);
            QTRY_COMPARE(queue->count(), 1);
            const QJsonArray ops = batches().last().value("ops").toArray();
            QCOMPARE(ops.size(), 1);
            QCOMPARE(ops.first().toObject().value("recipeId").toInt(), recipe);
        }
        // Nothing counted against the refused change.
        QCOMPARE(queue->changes().first().value("recipeId").toInt(), 99);
        QCOMPARE(queue->changes().first().value("failures").toInt(), 1);
        // A reconnect (flush) is what sends it again.
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "refused"}, {"message", "no such recipe"}}});
        queue->flush();
        QTRY_COMPARE(batches().size(), 5);
        QCOMPARE(batches().last().value("ops").toArray().first().toObject().value("recipeId").toInt(), 99);
        QTRY_COMPARE(queue->changes().first().value("failures").toInt(), 2);
    }

    void tryingAStuckChangeAgainDoesNotRetryAnotherRefusedOne()
    {
        queue->add(stars(99, 4));
        refuseUntilStuck();
        // Another change, refused once: it waits for the next reconnect.
        queue->add(stars(98, 2));
        QTRY_COMPARE(queue->changes().last().value("failures").toInt(), 1);
        QTRY_VERIFY(!queue->sending());
        const int sent = batches().size();
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 99}, {"stars", 4}}});
        queue->retry(queue->stuck().first().toMap().value("id").toString());
        QTRY_COMPARE(batches().size(), sent + 1);
        const QJsonArray ops = batches().last().value("ops").toArray();
        QCOMPARE(ops.size(), 1);
        QCOMPARE(ops.first().toObject().value("recipeId").toInt(), 99);
        QTRY_COMPARE(queue->count(), 1);
        QCOMPARE(queue->changes().first().value("failures").toInt(), 1);
    }

    void aStuckChangeIsTriedAgainOrDiscarded()
    {
        queue->add(stars(99, 4));
        refuseUntilStuck();
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 99}, {"stars", 4}}});
        queue->retry(queue->stuck().first().toMap().value("id").toString());
        QTRY_COMPARE(queue->count(), 0);

        queue->add(stars(98, 2));
        refuseUntilStuck();
        queue->discard(queue->stuck().first().toMap().value("id").toString());
        QCOMPARE(queue->count(), 0);
    }

    void noAnswerOrABusyServerCountsNothing()
    {
        server->queuedStatuses[path("/sync/batch")] = {503};
        server->queued[path("/sync/batch")] = {R"({"status":"error","message":"busy"})"};
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 1}, {"stars", 4}}});
        queue->setRetryDelay(50);
        queue->add(stars(1, 4));
        QTRY_COMPARE(queue->count(), 0);
        QCOMPARE(batches().size(), 2);
    }

    void aBatchWhoseAnswerIsLostIsSentAgainHarmlessly()
    {
        // The server applied the mark, but its answer never arrived (here: a 503 in its place). The same change,
        // with the same clientId and moment, goes again, and the server's "already" lets it go once.
        server->queuedStatuses[path("/sync/batch")] = {503};
        server->queued[path("/sync/batch")] = {R"({"status":"error","message":"server error"})"};
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "already"}, {"id", 41}, {"recipeId", 1},
                                                                     {"on", "2026-10-28"}, {"count", 1}}});
        QSignalSpy taken(queue.get(), &SyncQueue::taken);
        queue->setRetryDelay(50);
        queue->add(mark());
        QTRY_COMPARE(queue->count(), 0);
        QCOMPARE(batches().size(), 2);
        const QJsonObject first = batches().at(0).value("ops").toArray().first().toObject();
        const QJsonObject second = batches().at(1).value("ops").toArray().first().toObject();
        QCOMPARE(second.value("clientId"), first.value("clientId"));
        QCOMPARE(second.value("at"), first.value("at"));
        QCOMPARE(taken.count(), 1);
        QCOMPARE(queue->changes().size(), 0);
    }

    void aWholeBatchRefusedCountsAFailureForEach()
    {
        server->statuses[path("/sync/batch")] = 400;
        server->responses[path("/sync/batch")] = R"({"status":"error","message":"ops must be a list of 1 to 500 changes"})";
        queue->add(stars(1, 4));
        QTRY_COMPARE(queue->changes().first().value("failures").toInt(), 1);
        QCOMPARE(queue->changes().first().value("message").toString(),
                 QStringLiteral("ops must be a list of 1 to 500 changes"));
    }

    void aBatchTooBigForTheServerCountsAFailureForEach()
    {
        // nginx refuses a body over its limit with its own page, before Flask sees it.
        server->statuses[path("/sync/batch")] = 413;
        server->responses[path("/sync/batch")] = "<html><center><h1>413 Request Entity Too Large</h1></center></html>";
        queue->add(stars(1, 4));
        QTRY_COMPARE(queue->changes().first().value("failures").toInt(), 1);
        QCOMPARE(queue->changes().first().value("message").toString(), QStringLiteral("Too much to send at once."));
    }

    void anotherAccountNeverSendsTheLastOnesChanges()
    {
        goOffline();
        queue->add(mark());
        accounts->open(8, "bea");
        QCOMPARE(queue->count(), 0);
        server->responses[path("/sync/batch")] = answer({});
        comeBack();
        QTest::qWait(200);
        QVERIFY(batches().isEmpty());
        // The first account finds its change again when it signs in.
        accounts->open(7, "ann");
        QCOMPARE(queue->count(), 1);
    }

    void anAnswerForTheLastAccountIsDropped()
    {
        server->holdNext[path("/sync/batch")] = 1;
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 1}, {"stars", 4}}});
        queue->add(stars(1, 4));
        QTRY_COMPARE(batches().size(), 1);
        accounts->open(8, "bea");
        server->releaseHeld();
        QTest::qWait(200);
        QCOMPARE(queue->count(), 0);
        // The first account's file still holds it; sent again, the server answers "already".
        QCOMPARE(AccountStore::readJson(dir->path() + "/accounts/7/sync-queue.json").value("changes").toArray().size(), 1);
    }

    void aFullBatchIsFollowedByTheNext()
    {
        goOffline();
        for (int i = 1; i <= 501; ++i)
            queue->add(stars(i, 3));
        QList<QJsonObject> applied;
        for (int i = 0; i < 500; ++i)
            applied << QJsonObject{{"result", "applied"}, {"recipeId", i + 1}, {"stars", 3}};
        server->queued[path("/sync/batch")] = {answer(applied)};
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 501}, {"stars", 3}}});
        comeBack();
        QTRY_COMPARE(queue->count(), 0);
        QCOMPARE(batches().size(), 2);
        QCOMPARE(batches().at(0).value("ops").toArray().size(), 500);
        QCOMPARE(batches().at(1).value("ops").toArray().size(), 1);
    }

    void theTokensArrivalSends()
    {
        api->setSessionToken(QString());
        queue->add(stars(1, 4));
        QTest::qWait(100);
        QVERIFY(batches().isEmpty());
        server->responses[path("/sync/batch")] = answer({QJsonObject{{"result", "applied"}, {"recipeId", 1}, {"stars", 4}}});
        api->setSessionToken("tok");
        QTRY_COMPARE(queue->count(), 0);
    }
};

QTEST_GUILESS_MAIN(TestSyncQueue)
#include "tst_syncqueue.moc"
