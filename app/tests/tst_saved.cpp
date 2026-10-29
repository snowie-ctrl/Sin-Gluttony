#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDate>
#include <QRegularExpression>
#include <QSignalSpy>
#include <QTest>
#include <QUrlQuery>

#include <memory>
#include <string>

#include "FakeServer.h"
#include "api/Api.h"
#include "services/Saved.h"

static QString path(const char *route)
{
    return QStringLiteral("/api/gluttony") + QLatin1String(route);
}

static const QByteArray twoLists = R"({"status":"ok","data":[
  {"id":3,"title":"Cravings","kind":"cravings","count":2},{"id":11,"title":"Weeknights","kind":"custom","count":0},
  {"id":12,"title":"Parties","kind":"custom","count":1}]})";

static QByteArray listPage(const QList<int> &ids)
{
    QJsonArray tiles;
    for (const int id : ids)
        tiles.append(QJsonObject{{"id", id}, {"kind", "food"}, {"title", QStringLiteral("Stub %1").arg(id)}});
    const QJsonObject data{{"total", int(ids.size())}, {"page", 1}, {"pageSize", 24}, {"recipes", tiles},
                           {"list", QJsonObject{{"id", 11}, {"title", "Weeknights"}, {"kind", "custom"},
                                                {"count", int(ids.size())}}}};
    return QJsonDocument(QJsonObject{{"status", "ok"}, {"data", data}}).toJson();
}


class TestSaved : public QObject
{
    Q_OBJECT

    // A new server for every case, so a request still on its way never lands in the next one.
    std::unique_ptr<FakeServer> server;
    std::unique_ptr<Api> api;
    std::unique_ptr<Saved> saved;

    QList<QUrl> requestsTo(const char *route) const
    {
        QList<QUrl> found;
        for (const QUrl &url : server->requests)
            if (url.path() == path(route))
                found << url;
        return found;
    }

    QList<QJsonObject> bodiesTo(const char *route) const
    {
        QList<QJsonObject> found;
        for (int i = 0; i < server->requests.size(); ++i)
            if (server->requests[i].path() == path(route))
                found << QJsonDocument::fromJson(server->bodies[i]).object();
        return found;
    }

    void loadLists()
    {
        server->responses[path("/lists")] = twoLists;
        saved->load();
        QTRY_VERIFY(saved->listsLoaded());
    }

    RecipeQuery *open() const { return qobject_cast<RecipeQuery *>(saved->listRecipes()); }

    void openWeeknights(const QList<int> &ids)
    {
        server->responses[path("/lists/11/recipes")] = listPage(ids);
        saved->openList(11);
        QTRY_COMPARE(open()->count(), int(ids.size()));
    }

private slots:
    void init()
    {
        saved.reset();
        api.reset();
        server = std::make_unique<FakeServer>();
        api = std::make_unique<Api>();
        api->setBases(QString(), QStringLiteral("http://127.0.0.1:%1/api/gluttony").arg(server->serverPort()));
        saved = std::make_unique<Saved>(*api);
    }

    void theListsComeCravingsFirst()
    {
        loadLists();
        QCOMPARE(saved->lists().size(), 3);
        QCOMPARE(saved->cravingsId(), 3);
        QVERIFY(saved->canCreateList());
        QCOMPARE(saved->listTitle(12), QStringLiteral("Parties"));
    }

    void aListsLoadThatFailsSaysWhy()
    {
        server->responses[path("/lists")] = R"({"status":"error","message":"lists are down"})";
        server->statuses[path("/lists")] = 500;
        saved->load();
        QTRY_COMPARE(saved->listsError(), QStringLiteral("lists are down"));
        QVERIFY(!saved->listsLoaded());
    }

    void aNewListIsTrimmedAndJoinsTheLists()
    {
        loadLists();
        server->responses[path("/lists/create")] = R"({"status":"ok","data":{"id":13,"title":"Fridays","kind":"custom","count":0}})";
        QSignalSpy created(saved.get(), &Saved::listCreated);
        saved->createList(QStringLiteral("  Fridays  "));
        QTRY_COMPARE(created.count(), 1);
        QCOMPARE(created.first().at(0).toInt(), 13);
        QCOMPARE(bodiesTo("/lists/create").last().value("title").toString(), QStringLiteral("Fridays"));
        QCOMPARE(saved->lists().size(), 4);
    }

    void aTitleIsCountedInCharactersAsTheServerCountsThem()
    {
        // Sixty cakes are sixty characters to the server, though Qt holds each as two UTF-16 units.
        const QString cakes = QString::fromUcs4(std::u32string(60, U'\U0001F370').c_str());
        QCOMPARE(cakes.size(), 120);
        QCOMPARE(Saved::cleanTitle(cakes), cakes);
        QCOMPARE(Saved::cleanTitle(cakes + QStringLiteral("x")), QString());
        QCOMPARE(Saved::cleanTitle(QStringLiteral("   ")), QString());
        QCOMPARE(Saved::cleanTitle(QString(61, QLatin1Char('x'))), QString());
    }

    void aTitleTheServerWouldRefuseIsNeverSent()
    {
        loadLists();
        QSignalSpy failed(saved.get(), &Saved::failed);
        saved->createList(QStringLiteral("   "));
        saved->renameList(11, QString(61, QLatin1Char('x')));
        QCOMPARE(failed.count(), 2);
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("A list title is 1 to 60 characters"));
        QTest::qWait(100);
        QVERIFY(requestsTo("/lists/create").isEmpty() && requestsTo("/lists/rename").isEmpty());
    }

    void theNewListButtonRestsAtFifty()
    {
        QJsonArray fifty;
        fifty.append(QJsonObject{{"id", 1}, {"title", "Cravings"}, {"kind", "cravings"}, {"count", 0}});
        for (int i = 2; i <= 50; ++i)
            fifty.append(QJsonObject{{"id", i}, {"title", QStringLiteral("List %1").arg(i)}, {"kind", "custom"},
                                     {"count", 0}});
        server->responses[path("/lists")] = QJsonDocument(QJsonObject{{"status", "ok"}, {"data", fifty}}).toJson();
        saved->load();
        QTRY_VERIFY(saved->listsLoaded());
        QVERIFY(!saved->canCreateList());
        QSignalSpy failed(saved.get(), &Saved::failed);
        saved->createList(QStringLiteral("One more"));
        QCOMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("You can have at most 50 lists"));
        QTest::qWait(100);
        QVERIFY(requestsTo("/lists/create").isEmpty());
    }

    void aRefusedNewListSaysWhyInTheServersWords()
    {
        loadLists();
        server->responses[path("/lists/create")] = R"({"status":"error","message":"you can have at most 50 lists"})";
        server->statuses[path("/lists/create")] = 400;
        QSignalSpy failed(saved.get(), &Saved::failed);
        saved->createList(QStringLiteral("One more"));
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("list"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("you can have at most 50 lists"));
        QCOMPARE(saved->lists().size(), 3);
        QVERIFY(!saved->busy());
    }

    void aRenameAndADeleteChangeTheLists()
    {
        loadLists();
        server->responses[path("/lists/rename")] = R"({"status":"ok","data":{"id":11,"title":"Fridays","kind":"custom","count":0}})";
        saved->renameList(11, QStringLiteral("Fridays"));
        QTRY_COMPARE(saved->listTitle(11), QStringLiteral("Fridays"));
        server->responses[path("/lists/delete")] = R"({"status":"ok"})";
        saved->deleteList(12);
        QTRY_COMPARE(saved->lists().size(), 2);
        QCOMPARE(bodiesTo("/lists/delete").last().value("id").toInt(), 12);
    }

    void movingAListSendsWhatItFollows()
    {
        loadLists();
        server->responses[path("/lists/reorder")] = R"({"status":"ok"})";
        saved->moveList(12, -1);
        QCOMPARE(saved->lists().at(1).toMap().value("id").toInt(), 12);
        QTRY_COMPARE(requestsTo("/lists/reorder").size(), 1);
        QVERIFY(bodiesTo("/lists/reorder").last().value("after").isNull());
        saved->moveList(12, 1);
        QTRY_COMPARE(requestsTo("/lists/reorder").size(), 2);
        QCOMPARE(bodiesTo("/lists/reorder").last().value("after").toInt(), 11);
        saved->moveList(3, 1);          // Cravings never moves
        saved->moveList(12, 1);         // already last
        QTest::qWait(100);
        QCOMPARE(requestsTo("/lists/reorder").size(), 2);
    }

    void aSecondListMoveWaitsForTheFirst()
    {
        loadLists();
        server->responses[path("/lists/reorder")] = R"({"status":"ok"})";
        server->holdNext[path("/lists/reorder")] = 1;
        saved->moveList(12, -1);        // 3 12 11: 12 first after Cravings
        saved->moveList(12, 1);         // 3 11 12: 12 after 11
        QTRY_COMPARE(requestsTo("/lists/reorder").size(), 1);
        QTest::qWait(150);
        QCOMPARE(requestsTo("/lists/reorder").size(), 1);
        server->releaseHeld();
        QTRY_COMPARE(requestsTo("/lists/reorder").size(), 2);
        const QList<QJsonObject> sent = bodiesTo("/lists/reorder");
        QCOMPARE(sent[0].value("id").toInt(), 12);
        QVERIFY(sent[0].value("after").isNull());
        QCOMPARE(sent[1].value("id").toInt(), 12);
        QCOMPARE(sent[1].value("after").toInt(), 11);
    }

    void aRefusedListMoveReloadsTheLists()
    {
        loadLists();
        server->responses[path("/lists/reorder")] = R"({"status":"error","message":"that list is gone"})";
        server->statuses[path("/lists/reorder")] = 404;
        QSignalSpy failed(saved.get(), &Saved::failed);
        saved->moveList(12, -1);
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("lists"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("that list is gone"));
        QTRY_COMPARE(requestsTo("/lists").size(), 2);
        QTRY_COMPARE(saved->lists().at(1).toMap().value("id").toInt(), 11);
    }

    void aCravingAddsToTheCravingsListAndFlagsEveryTile()
    {
        loadLists();
        server->responses[path("/lists/items/add")] = R"({"status":"ok","data":{"listId":3,"recipeId":7,"count":3}})";
        QSignalSpy kept(saved.get(), &Saved::keptChanged);
        const QVariantMap tile{{"id", 7}, {"craving", false}, {"devouredCount", 2}, {"stars", 4}};
        QCOMPARE(saved->flagsOf(tile).value("craving").toBool(), false);
        saved->setCraving(7, true);
        QTRY_VERIFY(saved->flagsOf(tile).value("craving").toBool());
        QCOMPARE(saved->flagsOf(tile).value("devouredCount").toInt(), 2);
        QCOMPARE(saved->flagsOf(tile).value("stars").toInt(), 4);
        QCOMPARE(bodiesTo("/lists/items/add").last().value("listId").toInt(), 3);
        QCOMPARE(saved->lists().first().toMap().value("count").toInt(), 3);
        QCOMPARE(kept.count(), 1);
    }

    void theOpenRecipesMineFollowsWhatIsChanged()
    {
        loadLists();
        saved->showMine(7, QVariantMap{{"craving", false}, {"lists", QVariantList{12}}, {"devoured", QVariantList()},
                                       {"stars", QVariant()}, {"note", QVariant()}});
        QCOMPARE(saved->mineId(), 7);
        server->responses[path("/lists/items/add")] = R"({"status":"ok","data":{"listId":11,"recipeId":7,"count":1}})";
        saved->setInList(11, 7, true);
        QTRY_COMPARE(saved->mine().value("lists").toList().size(), 2);
        server->responses[path("/lists/items/remove")] = R"({"status":"ok","data":{"listId":12,"recipeId":7,"count":0}})";
        saved->setInList(12, 7, false);
        QTRY_COMPARE(saved->mine().value("lists").toList().size(), 1);
        QCOMPARE(saved->mine().value("lists").toList().first().toInt(), 11);
        // Another recipe's answer never changes this one's mine.
        saved->showMine(8, QVariantMap{{"craving", false}, {"lists", QVariantList()}});
        saved->setInList(11, 7, true);
        QTRY_COMPARE(requestsTo("/lists/items/add").size(), 2);
        QTest::qWait(50);
        QVERIFY(saved->mine().value("lists").toList().isEmpty());
    }

    void removingFromTheOpenListDropsTheTile()
    {
        loadLists();
        openWeeknights({1, 2, 3});
        server->responses[path("/lists/items/remove")] = R"({"status":"ok","data":{"listId":11,"recipeId":2,"count":2}})";
        saved->setInList(11, 2, false);
        QTRY_COMPARE(open()->count(), 2);
        QCOMPARE(open()->rowAt(1).value("id").toInt(), 3);
    }

    void anAddedRecipeShowsTheNextTimeTheListOpens()
    {
        loadLists();
        openWeeknights({1});
        server->responses[path("/lists/items/add")] = R"({"status":"ok","data":{"listId":11,"recipeId":2,"count":2}})";
        saved->setInList(11, 2, true);
        // Once its answer is in, the open list is out of date.
        QTRY_COMPARE(saved->lists().at(1).toMap().value("count").toInt(), 2);
        server->responses[path("/lists/11/recipes")] = listPage({2, 1});
        saved->openList(11);
        QTRY_COMPARE(open()->count(), 2);
        QCOMPARE(requestsTo("/lists/11/recipes").size(), 2);
        saved->openList(11);            // nothing changed since: nothing is asked
        QTest::qWait(100);
        QCOMPARE(requestsTo("/lists/11/recipes").size(), 2);
    }

    void aMoveSendsTheRecipeAndWhatItNowFollows()
    {
        loadLists();
        openWeeknights({1, 2, 3});
        server->responses[path("/lists/items/reorder")] = R"({"status":"ok"})";
        saved->moveItem(2, 0);
        QCOMPARE(open()->rowAt(0).value("id").toInt(), 3);
        QTRY_COMPARE(requestsTo("/lists/items/reorder").size(), 1);
        const QJsonObject sent = bodiesTo("/lists/items/reorder").last();
        QCOMPARE(sent.value("listId").toInt(), 11);
        QCOMPARE(sent.value("recipeId").toInt(), 3);
        QVERIFY(sent.value("after").isNull());
    }

    void aSecondMoveWaitsForTheFirst()
    {
        loadLists();
        openWeeknights({1, 2, 3});
        server->responses[path("/lists/items/reorder")] = R"({"status":"ok"})";
        server->holdNext[path("/lists/items/reorder")] = 1;
        saved->moveItem(0, 2);          // 2 3 1: 1 after 3
        saved->moveItem(0, 1);          // 3 2 1: 2 after 3
        QTRY_COMPARE(requestsTo("/lists/items/reorder").size(), 1);
        QTest::qWait(150);
        QCOMPARE(requestsTo("/lists/items/reorder").size(), 1);
        server->releaseHeld();
        QTRY_COMPARE(requestsTo("/lists/items/reorder").size(), 2);
        const QList<QJsonObject> sent = bodiesTo("/lists/items/reorder");
        QCOMPARE(sent[0].value("recipeId").toInt(), 1);
        QCOMPARE(sent[0].value("after").toInt(), 3);
        QCOMPARE(sent[1].value("recipeId").toInt(), 2);
        QCOMPARE(sent[1].value("after").toInt(), 3);
    }

    void aRefusedMoveReloadsTheList()
    {
        loadLists();
        openWeeknights({1, 2, 3});
        server->responses[path("/lists/items/reorder")] = R"({"status":"error","message":"that recipe is not on this list"})";
        server->statuses[path("/lists/items/reorder")] = 404;
        QSignalSpy failed(saved.get(), &Saved::failed);
        saved->moveItem(0, 1);
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("move"));
        QTRY_COMPARE(requestsTo("/lists/11/recipes").size(), 2);
        QTRY_COMPARE(open()->rowAt(0).value("id").toInt(), 1);
    }

    void clearingForgetsEverything()
    {
        loadLists();
        openWeeknights({1});
        saved->showMine(7, QVariantMap{{"craving", true}});
        saved->clear();
        QVERIFY(saved->lists().isEmpty() && !saved->listsLoaded());
        QCOMPARE(saved->cravingsId(), 0);
        QCOMPARE(saved->openListId(), 0);
        QCOMPARE(open()->count(), 0);
        QCOMPARE(saved->mineId(), 0);
        QVERIFY(!saved->flagsOf(QVariantMap{{"id", 7}}).value("craving").toBool());
        QCOMPARE(qobject_cast<RecipeQuery *>(saved->devouredHistory())->count(), 0);
        QCOMPARE(saved->devouredSort(), QStringLiteral("recent"));
    }

    void devouredSendsTheChosenLocalDay()
    {
        loadLists();
        server->responses[path("/devoured/add")] =
            R"({"status":"ok","data":{"id":41,"recipeId":7,"on":"2026-10-27","count":2,"already":false}})";
        saved->showMine(7, QVariantMap{{"craving", false}, {"lists", QVariantList()},
                                       {"devoured", QVariantList{QVariantMap{{"id", 40}, {"on", "2026-09-01"}}}}});
        QSignalSpy kept(saved.get(), &Saved::keptChanged);
        // Today is the device's own calendar day, never the UTC one.
        QCOMPARE(saved->today(), QDate::currentDate().toString(Qt::ISODate));
        saved->devour(7, QStringLiteral("2026-10-27"));
        QVERIFY(saved->devouring());
        QTRY_VERIFY(!saved->devouring());
        const QJsonObject sent = bodiesTo("/devoured/add").last();
        QCOMPARE(sent.value("recipeId").toInt(), 7);
        QCOMPARE(sent.value("on").toString(), QStringLiteral("2026-10-27"));
        QVERIFY(QRegularExpression("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
                    .match(sent.value("clientId").toString()).hasMatch());
        const QVariantList marks = saved->mine().value("devoured").toList();
        QCOMPARE(marks.size(), 2);
        QCOMPARE(marks.first().toMap().value("id").toInt(), 41);
        QCOMPARE(saved->flagsOf(QVariantMap{{"id", 7}}).value("devouredCount").toInt(), 2);
        QCOMPARE(kept.count(), 1);
    }

    void eachMarkHasItsOwnClientIdAndADoubleTapSendsOne()
    {
        server->responses[path("/devoured/add")] =
            R"({"status":"ok","data":{"id":41,"recipeId":7,"on":"2026-10-27","count":1,"already":false}})";
        saved->devour(7, QStringLiteral("2026-10-27"));
        saved->devour(7, QStringLiteral("2026-10-27"));     // still on its way: ignored
        QTRY_VERIFY(!saved->devouring());
        saved->devour(7, QStringLiteral("2026-10-27"));
        QTRY_COMPARE(requestsTo("/devoured/add").size(), 2);
        const QList<QJsonObject> sent = bodiesTo("/devoured/add");
        QVERIFY(sent[0].value("clientId").toString() != sent[1].value("clientId").toString());
    }

    void aDayThatHasNotComeIsNeverSent()
    {
        QSignalSpy failed(saved.get(), &Saved::failed);
        saved->devour(7, QDate::currentDate().addDays(1).toString(Qt::ISODate));
        saved->devour(7, QStringLiteral("2026-02-30"));
        QCOMPARE(failed.count(), 2);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("devoured"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("Pick a day that has already come"));
        QTest::qWait(100);
        QVERIFY(requestsTo("/devoured/add").isEmpty());
    }

    void aMarkIsTakenBackOff()
    {
        saved->showMine(7, QVariantMap{{"devoured", QVariantList{QVariantMap{{"id", 41}, {"on", "2026-10-27"}},
                                                                 QVariantMap{{"id", 40}, {"on", "2026-09-01"}}}}});
        server->responses[path("/devoured/remove")] = R"({"status":"ok","data":{"id":41,"recipeId":7,"count":1}})";
        saved->undevour(41);
        QTRY_COMPARE(saved->mine().value("devoured").toList().size(), 1);
        QCOMPARE(saved->mine().value("devoured").toList().first().toMap().value("id").toInt(), 40);
        QCOMPARE(saved->flagsOf(QVariantMap{{"id", 7}}).value("devouredCount").toInt(), 1);
    }

    void starsAreSetAndClearedWithNull()
    {
        saved->showMine(7, QVariantMap{{"stars", QVariant()}});
        server->responses[path("/rating")] = R"({"status":"ok","data":{"recipeId":7,"stars":4}})";
        saved->setStars(7, 4);
        QTRY_COMPARE(saved->mine().value("stars").toInt(), 4);
        QCOMPARE(bodiesTo("/rating").last().value("stars").toInt(), 4);
        QCOMPARE(saved->flagsOf(QVariantMap{{"id", 7}}).value("stars").toInt(), 4);
        server->responses[path("/rating")] = R"({"status":"ok","data":{"recipeId":7,"stars":null}})";
        saved->setStars(7, 0);
        QTRY_VERIFY(saved->mine().value("stars").isNull() || saved->mine().value("stars").toInt() == 0);
        QVERIFY(bodiesTo("/rating").last().value("stars").isNull());
        saved->setStars(7, 9);          // past five: nothing is sent
        QTest::qWait(100);
        QCOMPARE(requestsTo("/rating").size(), 2);
    }

    void aStarRequestMarksItsRecipeBusyUntilItIsAnswered()
    {
        saved->showMine(7, QVariantMap{{"stars", QVariant()}});
        QSignalSpy changed(saved.get(), &Saved::savingChanged);
        QVERIFY(saved->starsSaving().isEmpty());
        server->responses[path("/rating")] = R"({"status":"ok","data":{"recipeId":7,"stars":4}})";
        server->holdNext[path("/rating")] = 1;
        saved->setStars(7, 4);
        // Only that recipe, and only its stars: the note and other recipes are free.
        QVERIFY(saved->starsSaving().contains(7));
        QVERIFY(!saved->starsSaving().contains(8));
        QVERIFY(saved->noteSaving().isEmpty());
        QCOMPARE(changed.count(), 1);
        QTRY_COMPARE(requestsTo("/rating").size(), 1);
        server->releaseHeld();
        QTRY_VERIFY(saved->starsSaving().isEmpty());
        QCOMPARE(saved->mine().value("stars").toInt(), 4);

        // A refusal frees it too, so the person can try again.
        server->responses[path("/rating")] = R"({"status":"error","message":"no such recipe"})";
        server->statuses[path("/rating")] = 404;
        server->holdNext[path("/rating")] = 1;
        saved->setStars(7, 2);
        QVERIFY(saved->starsSaving().contains(7));
        QTRY_COMPARE(requestsTo("/rating").size(), 2);
        server->releaseHeld();
        QTRY_VERIFY(saved->starsSaving().isEmpty());

        // Signing out forgets it, and the answer that comes late changes nothing.
        server->holdNext[path("/rating")] = 1;
        saved->setStars(7, 1);
        QVERIFY(saved->starsSaving().contains(7));
        QTRY_COMPARE(requestsTo("/rating").size(), 3);
        saved->clear();
        QVERIFY(saved->starsSaving().isEmpty());
        server->releaseHeld();
        QTest::qWait(100);
        QVERIFY(saved->starsSaving().isEmpty());
    }

    void aNoteRequestMarksItsRecipeBusyUntilItIsAnswered()
    {
        saved->showMine(7, QVariantMap{{"note", QVariant()}});
        QVERIFY(saved->noteSaving().isEmpty());
        server->responses[path("/note")] = R"({"status":"ok","data":{"recipeId":7,"note":"less salt"}})";
        server->holdNext[path("/note")] = 1;
        saved->setNote(7, QStringLiteral("less salt"));
        QVERIFY(saved->noteSaving().contains(7));
        QVERIFY(!saved->noteSaving().contains(8));
        QVERIFY(saved->starsSaving().isEmpty());
        QTRY_COMPARE(requestsTo("/note").size(), 1);
        server->releaseHeld();
        QTRY_VERIFY(saved->noteSaving().isEmpty());
        QCOMPARE(saved->mine().value("note").toString(), QStringLiteral("less salt"));

        server->responses[path("/note")] = R"({"status":"error","message":"no such recipe"})";
        server->statuses[path("/note")] = 404;
        server->holdNext[path("/note")] = 1;
        saved->setNote(7, QStringLiteral("more"));
        QVERIFY(saved->noteSaving().contains(7));
        QTRY_COMPARE(requestsTo("/note").size(), 2);
        server->releaseHeld();
        QTRY_VERIFY(saved->noteSaving().isEmpty());

        server->holdNext[path("/note")] = 1;
        saved->setNote(7, QStringLiteral("again"));
        QVERIFY(saved->noteSaving().contains(7));
        QTRY_COMPARE(requestsTo("/note").size(), 3);
        saved->clear();
        QVERIFY(saved->noteSaving().isEmpty());
        server->releaseHeld();
        QTest::qWait(100);
        QVERIFY(saved->noteSaving().isEmpty());

        // A note too long to send is never marked: nothing is on its way.
        saved->setNote(7, QString::fromUcs4(std::u32string(2001, U'x').c_str()));
        QVERIFY(saved->noteSaving().isEmpty());
    }

    void aNoteIsCappedInCodePointsNotUtf16Units()
    {
        // Two thousand cakes are 2,000 characters to the server and 4,000 UTF-16 units to Qt.
        const QString full = QString::fromUcs4(std::u32string(2000, U'\U0001F370').c_str());
        QCOMPARE(saved->noteLength(full), 2000);
        QCOMPARE(Saved::cleanNote(QStringLiteral("  less salt \n")), QStringLiteral("less salt"));
        server->responses[path("/note")] = QJsonDocument(QJsonObject{{"status", "ok"},
            {"data", QJsonObject{{"recipeId", 7}, {"note", full}}}}).toJson();
        saved->showMine(7, QVariantMap{{"note", QVariant()}});
        QSignalSpy done(saved.get(), &Saved::done);
        saved->setNote(7, full);
        QTRY_COMPARE(done.count(), 1);
        QCOMPARE(done.first().at(0).toString(), QStringLiteral("note"));
        QCOMPARE(bodiesTo("/note").last().value("text").toString(), full);
        QCOMPARE(saved->mine().value("note").toString(), full);
        QSignalSpy failed(saved.get(), &Saved::failed);
        saved->setNote(7, full + QString::fromUcs4(U"\U0001F370"));
        QCOMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("A note is at most 2000 characters"));
        QTest::qWait(100);
        QCOMPARE(requestsTo("/note").size(), 1);
    }

    void anEmptyNoteDeletesIt()
    {
        saved->showMine(7, QVariantMap{{"note", "less salt"}});
        server->responses[path("/note")] = R"({"status":"ok","data":{"recipeId":7,"note":null}})";
        saved->setNote(7, QStringLiteral("   "));
        QTRY_VERIFY(saved->mine().value("note").toString().isEmpty());
        QCOMPARE(bodiesTo("/note").last().value("text").toString(), QString());
    }

    void aRefusedNoteSaysWhy()
    {
        server->responses[path("/note")] = R"({"status":"error","message":"no such recipe"})";
        server->statuses[path("/note")] = 404;
        QSignalSpy failed(saved.get(), &Saved::failed);
        saved->setNote(7, QStringLiteral("x"));
        QTRY_COMPARE(failed.count(), 1);
        QCOMPARE(failed.first().at(0).toString(), QStringLiteral("note"));
        QCOMPARE(failed.first().at(1).toString(), QStringLiteral("no such recipe"));
    }

    void theHistoryIsAskedBySortAndAgainAfterAMark()
    {
        auto *history = qobject_cast<RecipeQuery *>(saved->devouredHistory());
        server->responses[path("/devoured")] = R"({"status":"ok","data":{"total":1,"page":1,"pageSize":24,
          "recipes":[{"id":7,"title":"Stub","devouredId":41,"on":"2026-10-27"}]}})";
        saved->openDevoured(QStringLiteral("recent"));
        QTRY_COMPARE(history->count(), 1);
        QVERIFY(!QUrlQuery(requestsTo("/devoured").last()).hasQueryItem("sort"));
        saved->openDevoured(QStringLiteral("stars"));
        QTRY_COMPARE(requestsTo("/devoured").size(), 2);
        QCOMPARE(QUrlQuery(requestsTo("/devoured").last()).queryItemValue("sort"), QStringLiteral("stars"));
        QCOMPARE(saved->devouredSort(), QStringLiteral("stars"));
        saved->openDevoured(QStringLiteral("stars"));       // unchanged: nothing is asked
        QTest::qWait(100);
        QCOMPARE(requestsTo("/devoured").size(), 2);
        server->responses[path("/rating")] = R"({"status":"ok","data":{"recipeId":7,"stars":5}})";
        saved->setStars(7, 5);
        // Once its answer is in (a loaded machine is slow), the history is out of date.
        QTRY_COMPARE(saved->flagsOf(QVariantMap{{"id", 7}}).value("stars").toInt(), 5);
        saved->openDevoured(QStringLiteral("stars"));       // a star changed the order: asked again
        QTRY_COMPARE(requestsTo("/devoured").size(), 3);
    }

    void theOpenTabIsRememberedForTheNextVisit()
    {
        loadLists();
        QVERIFY(!saved->devouredOpen());
        saved->openDevoured(QStringLiteral("recent"));
        QVERIFY(saved->devouredOpen());
        openWeeknights({1});
        QVERIFY(!saved->devouredOpen());
        saved->openDevoured(QStringLiteral("recent"));
        saved->clear();
        QVERIFY(!saved->devouredOpen());
    }
};

QTEST_GUILESS_MAIN(TestSaved)
#include "tst_saved.moc"
