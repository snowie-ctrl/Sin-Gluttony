"""
The Gluttony scraper's loop. It waits for Surrogate's requests (Run now,
Re-tag) and, with SCHEDULE=on, runs the weekly pass. `--once full|retag` runs
one pass and exits; the dry run and manual checks use it, and `--no-images`
skips pictures when building the seed on a dev machine.
`--dry-run [--pages N] [--no-fetch] [--server-table]` is the dry run over the recipe sites; it never
publishes. `--pages 0` means every page, and `--server-table` reads plutus's ingredient table (read only):
together they are M4's full trial. A run request naming a site (Surrogate's crawl of one site, CATALOG=new)
is a full pass of that site alone.
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
    """
    (mode, site): mode is "full", "retag" or None; site is the one recipe site a run request named, or None for
    all. Run requests naming different sites, or one naming none, make a full pass of every site.
    """
    runs = [r for r in requests if r.get("kind") == "run"]
    if runs:
        named = {r.get("site") for r in runs}
        return "full", (named.pop() if len(named) == 1 else None)   # a full pass covers a re-tag asked for too
    if any(r.get("kind") == "retag" for r in requests):
        return "retag", None
    if config.SCHEDULE == "on" and schedule.isDue(now, state):
        return "full", None
    return None, None


def handle(requests, now):
    """One turn of the loop: the pass the requests (or the schedule) ask for, if any; returns its mode."""
    state = store.readJson(config.STATE_FILE, {}) or {}
    mode, site = chooseMode(requests, now, state)
    if mode:
        runOnce(mode, site=site)
    return mode


def runOnce(mode, log=print, images=True, site=None):
    config.STOP_FILE.unlink(missing_ok=True)
    report = pipeline.runPass(mode, log, stopRequested=lambda: config.STOP_FILE.exists(), images=images, site=site)
    config.STOP_FILE.unlink(missing_ok=True)
    state = store.readJson(config.STATE_FILE, {}) or {}
    if mode == "full" and site is None:     # a pass of one site does not stand in for the weekly pass
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
    parser.add_argument("--dry-run", action="store_true",
                        help="crawl the recipe sites, run the gate and write reports/dryrun-<date>/; never publishes")
    parser.add_argument("--pages", type=int, default=200, help="with --dry-run: recipe pages per site (0: all)")
    parser.add_argument("--no-fetch", action="store_true",
                        help="with --dry-run: report over the cached pages without asking the sites")
    parser.add_argument("--server-table", action="store_true",
                        help="with --dry-run: read plutus's ingredient table (read only) instead of the repo's seed")
    args = parser.parse_args(argv)
    lock = acquireLock()  # noqa: F841 -- held for the life of the process
    progress.idle()
    if args.dry_run:
        import dryrun   # here, not at the top: only the dry run needs recipe-scrapers
        dryrun.run(pages=args.pages or None, crawl=not args.no_fetch, serverTable=args.server_table)
        return 0
    if args.once:
        return 0 if runOnce(args.once, images=not args.no_images)["outcome"] == "ok" else 1
    try:
        while True:
            requests = controlRequests.take()
            mode = handle(requests, datetime.now(timezone.utc))
            if requests:
                controlRequests.done()
            if not mode:
                progress.idle()
                time.sleep(config.POLL_SECONDS)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
