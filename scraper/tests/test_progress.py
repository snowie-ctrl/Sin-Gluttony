import time

import progress


def test_aStageIsRunningUntilIdle():
    assert progress.read() == {"state": "idle"} and not progress.isRunning()
    progress.stage("full", "tag", "", startedAt=1.0)
    assert progress.isRunning() and progress.read()["stage"] == "tag"
    progress.idle()
    assert not progress.isRunning()


def test_aStaleRunningStateIsNotRunning():
    progress.stage("full", "fetch")
    assert not progress.isRunning(now=time.time() + progress.STALE_SECONDS + 1)
