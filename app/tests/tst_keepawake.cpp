// Copied from Showtime Showtime/tests/tst_keepawake.cpp at 6e44e7a; the include path.
#include <QSignalSpy>
#include <QTest>

#include "services/KeepAwake.h"

#ifdef Q_OS_WIN
#include <windows.h>
#endif


class TestKeepAwake : public QObject
{
    Q_OBJECT

private slots:
    void togglesAndSignalsOnlyOnChange()
    {
        KeepAwake keepAwake;
        QSignalSpy changed(&keepAwake, &KeepAwake::activeChanged);
        keepAwake.setActive(true);
        keepAwake.setActive(true);
        QCOMPARE(int(changed.count()), 1);
        QVERIFY(keepAwake.active());
        keepAwake.setActive(false);
        QCOMPARE(int(changed.count()), 2);
    }

#ifdef Q_OS_WIN
    // SetThreadExecutionState returns the state it replaces, so setting it
    // again reveals what KeepAwake left in place, with no admin rights needed.
    void holdsTheExecutionStateWhileActive()
    {
        KeepAwake keepAwake;
        keepAwake.setActive(true);
        const EXECUTION_STATE held = SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED);
        QVERIFY(held & ES_SYSTEM_REQUIRED);
        QVERIFY(held & ES_DISPLAY_REQUIRED);

        keepAwake.setActive(false);
        const EXECUTION_STATE released = SetThreadExecutionState(ES_CONTINUOUS);
        QVERIFY(!(released & ES_SYSTEM_REQUIRED));
        QVERIFY(!(released & ES_DISPLAY_REQUIRED));
    }

    void releasesWhenDestroyed()
    {
        {
            KeepAwake keepAwake;
            keepAwake.setActive(true);
        }
        const EXECUTION_STATE left = SetThreadExecutionState(ES_CONTINUOUS);
        QVERIFY(!(left & ES_SYSTEM_REQUIRED));
    }
#endif
};

QTEST_GUILESS_MAIN(TestKeepAwake)
#include "tst_keepawake.moc"
