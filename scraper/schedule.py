"""
The weekly pass: Sunday at 03:00 America/Chicago, when nobody is browsing.
A pass is due when none has finished since the latest such time, so a pass
missed while the VM was off runs as soon as it is back. A failed pass is tried
again after FAILED_RETRY_HOURS, not every few seconds.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo

import config

TZ = ZoneInfo("America/Chicago")
WEEKDAY = 6         # Sunday
HOUR = 3


def lastDue(now):
    local = now.astimezone(TZ)
    due = (local - timedelta(days=(local.weekday() - WEEKDAY) % 7)).replace(hour=HOUR, minute=0, second=0,
                                                                              microsecond=0)
    if due > local:
        due -= timedelta(days=7)
    return due


def nextDue(now):
    return lastDue(now) + timedelta(days=7)


def isDue(now, state):
    failedAt = state.get("failedAt")
    if failedAt and now.timestamp() - failedAt < config.FAILED_RETRY_HOURS * 3600:
        return False
    last = state.get("lastFullAt")
    return last is None or last < lastDue(now).timestamp()
