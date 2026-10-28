import controlRequests


def test_askedRequestsAreTakenThenDone():
    controlRequests.ask("run")
    assert [r["kind"] for r in controlRequests.pending()] == ["run"]
    taken = controlRequests.take()
    assert [r["kind"] for r in taken] == ["run"]
    controlRequests.ask("retag")                     # asked while the first is being carried out
    assert [r["kind"] for r in controlRequests.pending()] == ["run", "retag"]
    controlRequests.done()
    assert [r["kind"] for r in controlRequests.pending()] == ["retag"]
