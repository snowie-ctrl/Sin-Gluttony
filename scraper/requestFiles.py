# Copied from Artemis/Pageturner/requestFiles.py at 7acc9ec (itself from Artemis/Showtime at 9b6e9c7); unchanged.
"""
Requests a person made on Surrogate: asked for in the control API's process,
carried out by the scraper's loop (discovery's Queue anyway / Dismiss, the
curator's Set id). Only the scraper writes the files they change, so the
control API just appends to a requests file, and the scraper claims the whole
file before working on it: requests made meanwhile land in a fresh file
instead of being overwritten, and a claim left by a crash is worked on again.
"""
import json, os


def claimedPath(path):
    return path.with_suffix(".claimed.json")


def read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def write(requests, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")          # a writer of its own in each process
    tmp.write_text(json.dumps(requests), encoding="utf-8")
    os.replace(tmp, path)


def claim(path):
    """
    Take the requests file for ourselves: requests asked for while we work on
    these land in a fresh file, instead of being overwritten when we finish.
    A claimed file left by a crash is worked on too.
    """
    claimed = claimedPath(path)
    left = read(claimed)
    try:
        os.replace(path, claimed)
    except OSError:
        return left                         # nothing new was asked (or the file is already the crashed one)
    requests = left + read(claimed)
    if left:
        write(requests, claimed)
    return requests
