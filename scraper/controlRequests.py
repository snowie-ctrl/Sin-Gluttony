"""
Surrogate's Run now and Re-tag. The control API runs in its own process and
only appends to run/control-requests.json; the loop claims the whole file
between passes (requestFiles.claim), so a request made during a pass lands in
a fresh file instead of being lost, and done() clears the claim once the pass
it asked for has ended.

    {"kind": "run"}      a full pass
    {"kind": "run", "site": s}   a full pass of one recipe site (CATALOG=new)
    {"kind": "retag"}    stages after fetch, over the raw copies
"""
import time

import config
import requestFiles

KINDS = ("run", "retag")


def ask(kind, site=None):
    path = config.CONTROL_REQUESTS_FILE
    request = {"kind": kind, "at": time.time()}
    if site is not None:
        request["site"] = site
    requestFiles.write(requestFiles.read(path) + [request], path)


def pending():
    path = config.CONTROL_REQUESTS_FILE
    return requestFiles.read(requestFiles.claimedPath(path)) + requestFiles.read(path)


def take():
    return requestFiles.claim(config.CONTROL_REQUESTS_FILE)


def done():
    requestFiles.claimedPath(config.CONTROL_REQUESTS_FILE).unlink(missing_ok=True)
