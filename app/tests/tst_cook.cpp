#include <QFile>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>

#include <memory>

#include "services/AccountStore.h"
#include "services/Cook.h"

#ifdef Q_OS_WIN
#include <windows.h>
#endif


static QVariantMap recipe(int id = 1)
{
    QVariantList steps, lines;
    for (int i = 0; i < 4; ++i)
        steps << QVariantMap{{"text", QStringLiteral("Step %1").arg(i + 1)}, {"group", QVariant()}};
    for (int i = 0; i < 3; ++i)
        lines << QVariantMap{{"line", QStringLiteral("Line %1").arg(i + 1)}};
    return {{"id", id}, {"title", "Stub Coq au Vin"}, {"steps", steps}, {"ingredients", lines}};
}

static const qint64 hour = 60LL * 60 * 1000;


class TestCook : public QObject
{
    Q_OBJECT

    std::unique_ptr<QTemporaryDir> dir;
    std::unique_ptr<AccountStore> store;
    std::unique_ptr<Cook> cook;
    qint64 now = 1'700'000'000'000;

    std::unique_ptr<Cook> makeCook()
    {
        auto made = std::make_unique<Cook>();
        made->setStore(store.get());
        made->setClock([this]() { return now; });
        return made;
    }

private slots:
    void init()
    {
        dir = std::make_unique<QTemporaryDir>();
        store = std::make_unique<AccountStore>(dir->path());
        store->open(7, "ann");
        now = 1'700'000'000'000;
        cook = makeCook();
    }

    void cleanup()
    {
        cook.reset();
    }

    void anEndedSessionKeepsTheTimers()
    {
        cook->open(recipe());
        cook->startTimer(60, "a");
        // An ended session or a device forgotten elsewhere closes the folder, nothing more.
        store->close();
        QCOMPARE(cook->timers().size(), 1);
        QVERIFY(cook->awake());
        store->open(7, "ann");
        QCOMPARE(cook->timers().size(), 1);
    }

    void anotherAccountDoesNotInheritTheTimers()
    {
        cook->startTimer(60, "a");
        store->close();
        store->open(8, "bob");
        QVERIFY(cook->timers().isEmpty());
        QVERIFY(!cook->awake());
    }

    void signingOutWipesTheTimers()
    {
        cook->open(recipe());
        cook->startTimer(60, "a");
        store->wipe();
        QVERIFY(cook->timers().isEmpty());
        QVERIFY(!cook->active());
    }

    void aSignOutTheServerEndedFirstWipesTheTimersToo()
    {
        cook->startTimer(60, "a");
        store->close();
        store->wipeAccount(7);
        QVERIFY(cook->timers().isEmpty());
    }

    void openingShowsTheFirstStepAndKeepsTheScreenOn()
    {
        QSignalSpy opened(cook.get(), &Cook::opened);
        cook->open(recipe());
        QVERIFY(cook->active());
        QCOMPARE(cook->recipeId(), 1);
        QCOMPARE(cook->step(), 0);
        QCOMPARE(cook->stepCount(), 4);
        QVERIFY(cook->awake());
        QCOMPARE(opened.count(), 1);
        QCOMPARE(opened.at(0).at(0).toMap().value("id").toInt(), 1);
        cook->close();
        QVERIFY(!cook->active());
        QVERIFY(!cook->awake());
    }

    void aRecipeWithoutAnIdDoesNotOpen()
    {
        cook->open(QVariantMap{{"title", "nothing"}});
        QVERIFY(!cook->active());
        QVERIFY(!cook->awake());
    }

    void theStepsMoveWithinTheRecipe()
    {
        cook->open(recipe());
        QSignalSpy moved(cook.get(), &Cook::stepChanged);
        cook->previous();
        QCOMPARE(cook->step(), 0);
        QCOMPARE(moved.count(), 0);
        cook->next();
        cook->next();
        QCOMPARE(cook->step(), 2);
        cook->goTo(9);
        QCOMPARE(cook->step(), 3);
        cook->next();
        QCOMPARE(cook->step(), 3);
        cook->goTo(1);
        QCOMPARE(cook->step(), 1);
        QCOMPARE(moved.count(), 4);
    }

    void linesAreTickedAndUnticked()
    {
        cook->open(recipe());
        cook->toggleTick(2);
        cook->toggleTick(0);
        QCOMPARE(cook->ticks(), (QVariantList{2, 0}));
        cook->toggleTick(2);
        QCOMPARE(cook->ticks(), (QVariantList{0}));
        cook->toggleTick(3);    // there are three lines
        cook->toggleTick(-1);
        QCOMPARE(cook->ticks(), (QVariantList{0}));
    }

    void thePlaceIsKeptForTheSameRecipe()
    {
        cook->open(recipe());
        cook->goTo(2);
        cook->toggleTick(1);
        cook->close();
        now += 11 * hour;
        auto again = makeCook();
        again->open(recipe());
        QCOMPARE(again->step(), 2);
        QCOMPARE(again->ticks(), (QVariantList{1}));
        // Another recipe starts at the top.
        again->open(recipe(2));
        QCOMPARE(again->step(), 0);
        QVERIFY(again->ticks().isEmpty());
    }

    void aPlaceKeptThirteenHoursAgoStartsAtTheTop()
    {
        cook->open(recipe());
        cook->goTo(3);
        cook->toggleTick(0);
        cook->close();
        now += 13 * hour;
        auto again = makeCook();
        again->open(recipe());
        QCOMPARE(again->step(), 0);
        QVERIFY(again->ticks().isEmpty());
    }

    void aKeptPlaceBeyondAShorterRecipeIsBroughtInRange()
    {
        cook->open(recipe());
        cook->goTo(3);
        cook->close();
        QVariantMap shorter = recipe();
        shorter.insert("steps", QVariantList{QVariantMap{{"text", "Only step"}}});
        auto again = makeCook();
        again->open(shorter);
        QCOMPARE(again->step(), 0);
    }

    void anotherAccountKeepsItsOwnPlace()
    {
        cook->open(recipe());
        cook->goTo(2);
        cook->close();
        store->open(8, "bea");
        auto theirs = makeCook();
        theirs->open(recipe());
        QCOMPARE(theirs->step(), 0);
        QVERIFY(QFile::exists(dir->path() + "/accounts/7/cook.json"));
    }

    void aTimerCountsDownAndSaysDoneOnce()
    {
        QSignalSpy done(cook.get(), &Cook::timerDone);
        const int id = cook->startTimer(60, "Stub Coq au Vin · step 2");
        QVERIFY(id > 0);
        QCOMPARE(cook->timers().size(), 1);
        QCOMPARE(cook->timers().at(0).toMap().value("remaining").toInt(), 60);
        now += 30'000;
        cook->update();
        QCOMPARE(cook->timers().at(0).toMap().value("remaining").toInt(), 30);
        QCOMPARE(done.count(), 0);
        now += 30'000;
        cook->update();
        QCOMPARE(done.count(), 1);
        QCOMPARE(done.at(0).at(0).toInt(), id);
        QCOMPARE(done.at(0).at(1).toString(), QStringLiteral("Stub Coq au Vin · step 2"));
        QVERIFY(cook->timers().at(0).toMap().value("done").toBool());
        QCOMPARE(cook->timers().at(0).toMap().value("remaining").toInt(), 0);
        now += 30'000;
        cook->update();
        QCOMPARE(done.count(), 1);
    }

    void aTimerKeepsRunningAfterCookModeCloses()
    {
        QSignalSpy done(cook.get(), &Cook::timerDone);
        cook->open(recipe());
        cook->startTimer(120, "step 1");
        cook->close();
        QCOMPARE(cook->timers().size(), 1);
        now += 121'000;
        cook->update();
        QCOMPARE(done.count(), 1);
        // A finished timer stays until it is dismissed.
        QCOMPARE(cook->timers().size(), 1);
        cook->dismissTimer(cook->timers().at(0).toMap().value("id").toInt());
        QVERIFY(cook->timers().isEmpty());
    }

    // A laptop that sleeps would not chime: the machine stays awake while a timer runs, with cook mode open or not.
    void aRunningTimerKeepsTheMachineAwakeAfterCookModeCloses()
    {
        QSignalSpy changed(cook.get(), &Cook::awakeChanged);
        cook->open(recipe());
        QCOMPARE(changed.count(), 1);
        cook->startTimer(120, "step 1");
        cook->close();
        QVERIFY(cook->awake());
        // Already awake the whole time: nothing to announce.
        QCOMPARE(changed.count(), 1);
        now += 121'000;
        cook->update();
        QVERIFY(!cook->awake());
        QCOMPARE(changed.count(), 2);
    }

    void aTimerStartedWithCookModeClosedKeepsTheMachineAwakeUntilDismissed()
    {
        QVERIFY(!cook->awake());
        const int id = cook->startTimer(120, "step 1");
        QVERIFY(cook->awake());
        cook->dismissTimer(id);
        QVERIFY(!cook->awake());
    }

    void aFinishedTimerAloneDoesNotKeepTheMachineAwake()
    {
        cook->startTimer(60, "a");
        const int running = cook->startTimer(120, "b");
        now += 61'000;
        cook->update();
        QVERIFY(cook->awake());
        cook->dismissTimer(running);
        QVERIFY(!cook->awake());
    }

    void withNoTimerClosingCookModeLetsTheMachineSleep()
    {
        cook->open(recipe());
        const int id = cook->startTimer(60, "a");
        cook->dismissTimer(id);
        QVERIFY(cook->awake());
        cook->close();
        QVERIFY(!cook->awake());
    }

    void twoTimersEndingTogetherEachSayDone()
    {
        QSignalSpy done(cook.get(), &Cook::timerDone);
        const int first = cook->startTimer(60, "a");
        const int second = cook->startTimer(60, "b");
        now += 60'000;
        cook->update();
        QCOMPARE(done.count(), 2);
        QCOMPARE(done.at(0).at(0).toInt(), first);
        QCOMPARE(done.at(1).at(0).toInt(), second);
    }

    void aStoppedTimerNeverSaysDone()
    {
        QSignalSpy done(cook.get(), &Cook::timerDone);
        const int id = cook->startTimer(60, "a");
        cook->dismissTimer(id);
        now += 61'000;
        cook->update();
        QCOMPARE(done.count(), 0);
        QVERIFY(cook->timers().isEmpty());
        QCOMPARE(cook->startTimer(0, "nothing"), 0);
        QVERIFY(cook->timers().isEmpty());
    }

    void theTimersTickOnTheirOwn()
    {
        // The real clock and Cook's own tick: a one-second timer says done without anyone calling update().
        Cook real;
        QSignalSpy done(&real, &Cook::timerDone);
        real.startTimer(1, "a");
        QTRY_COMPARE(done.count(), 1);
    }

    void signingOutEndsEverything()
    {
        cook->open(recipe());
        cook->startTimer(60, "a");
        cook->clear();
        QVERIFY(!cook->active());
        QVERIFY(!cook->awake());
        QVERIFY(cook->timers().isEmpty());
        QVERIFY(cook->recipe().isEmpty());
    }

#ifdef Q_OS_WIN
    void theScreenIsLetGoWhenCookModeCloses()
    {
        cook->open(recipe());
        cook->close();
        const EXECUTION_STATE left = SetThreadExecutionState(ES_CONTINUOUS);
        QVERIFY(!(left & ES_DISPLAY_REQUIRED));
    }
#endif
};

QTEST_GUILESS_MAIN(TestCook)
#include "tst_cook.moc"
