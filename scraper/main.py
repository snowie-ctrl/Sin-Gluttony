"""
The Gluttony scraper's loop. It waits for Surrogate's requests (Run now,
Re-tag) and, with SCHEDULE=on, runs the weekly pass. `--once full|retag` runs
one pass and exits; the dry run and manual checks use it, and `--no-images`
skips pictures when building the seed on a dev machine.
"""
import argparse
import sys
import time
from datetime import datetime, timezone

import config
import controlRequests
import pipeline
import progress
import schedule
import store


def acquireLock():
    """One scraper at a time: a second copy started by mistake would interleave writes to data/ and run/."""
    if sys.platform != "linux":
        return None
    import fcntl
    config.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = open(config.LOCK_FILE, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise SystemExit("another Gluttony scraper is already running")
    return handle


def chooseMode(requests, now, state):
    kinds = {r.get("kind") for r in requests}
    if "run" in kinds:
        return "full"              # a full pass covers a re-tag asked for at the same time
    if "retag" in kinds:
        return "retag"
    if config.SCHEDULE == "on" and schedule.isDue(now, state):
        return "full"
    return None


def runOnce(mode, log=print, images=True):
    config.STOP_FILE.unlink(missing_ok=True)
    report = pipeline.runPass(mode, log, stopRequested=lambda: config.STOP_FILE.exists(), images=images)
    config.STOP_FILE.unlink(missing_ok=True)
    state = store.readJson(config.STATE_FILE, {}) or {}
    if mode == "full":
        if report["outcome"] == "failed":
            state["failedAt"] = report["endedAt"]
        else:
            state["lastFullAt"] = report["startedAt"]
            state.pop("failedAt", None)
    store.writeJson(config.STATE_FILE, state)
    return report


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Gluttony's recipe scraper")
    parser.add_argument("--once", choices=("full", "retag"), help="run one pass and exit")
    parser.add_argument("--no-images", action="store_true", help="skip pictures (building the seed on a dev machine)")
    args = parser.parse_args(argv)
    lock = acquireLock()  # noqa: F841 -- held for the life of the process
    progress.idle()
    if args.once:
        return 0 if runOnce(args.once, images=not args.no_images)["outcome"] == "ok" else 1
    try:
        while True:
            requests = controlRequests.take()
            state = store.readJson(config.STATE_FILE, {}) or {}
            mode = chooseMode(requests, datetime.now(timezone.utc), state)
            if mode:
                runOnce(mode)
            if requests:
                controlRequests.done()
            if not mode:
                progress.idle()
                time.sleep(config.POLL_SECONDS)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
