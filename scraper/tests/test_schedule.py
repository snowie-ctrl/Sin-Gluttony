from datetime import datetime, timedelta

import schedule

TZ = schedule.TZ


def test_lastDueIsTheMostRecentSundayAtThree():
    wednesday = datetime(2026, 10, 21, 12, 0, tzinfo=TZ)
    assert schedule.lastDue(wednesday) == datetime(2026, 10, 18, 3, 0, tzinfo=TZ)
    assert schedule.lastDue(datetime(2026, 10, 18, 2, 59, tzinfo=TZ)) == datetime(2026, 10, 11, 3, 0, tzinfo=TZ)
    assert schedule.lastDue(datetime(2026, 10, 18, 3, 0, tzinfo=TZ)) == datetime(2026, 10, 18, 3, 0, tzinfo=TZ)
    assert schedule.nextDue(wednesday) == datetime(2026, 10, 25, 3, 0, tzinfo=TZ)


def test_aPassIsDueUntilOneRanAfterTheLastDueTime():
    now = datetime(2026, 10, 21, 12, 0, tzinfo=TZ)
    due = schedule.lastDue(now).timestamp()
    assert schedule.isDue(now, {})
    assert schedule.isDue(now, {"lastFullAt": due - 60})          # missed while the VM was off
    assert not schedule.isDue(now, {"lastFullAt": due + 60})


def test_aFailedPassWaitsSixHours():
    now = datetime(2026, 10, 21, 12, 0, tzinfo=TZ)
    assert not schedule.isDue(now, {"failedAt": (now - timedelta(hours=5)).timestamp()})
    assert schedule.isDue(now, {"failedAt": (now - timedelta(hours=7)).timestamp()})
