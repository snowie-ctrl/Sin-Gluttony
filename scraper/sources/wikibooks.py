"""
Wikibooks' Cookbook comes from the public database dump rather than page by
page: about 200 MB twice a month, against thousands of API calls. A dump is
downloaded only when the feed lists a newer one, read as a stream (the whole
wiki is in it; only the Cookbook's recipe pages are kept) and then deleted.
"""
import bz2
import re
import xml.etree.ElementTree as ET

import config
import net
import store

COOKBOOK_NS = "102"
_DUMP_DATE = re.compile(r"/enwikibooks/(\d{8})")
_RECIPE_MARK = re.compile(r"\{\{\s*recipe[ _]?summary|\[\[\s*category\s*:\s*recipes", re.IGNORECASE)


def latestDumpDate():
    match = _DUMP_DATE.search(net.getText(config.WIKIBOOKS_DUMP_RSS))
    if not match:
        raise net.HttpError("the dump feed names no date")
    return match.group(1)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def extractPages(dumpPath, onProgress=None):
    """Yield (title, revisionId, timestamp, wikitext) for each recipe page in the Cookbook namespace."""
    with bz2.open(dumpPath, "rb") as stream:
        context = ET.iterparse(stream, events=("start", "end"))
        _, root = next(context)
        count = 0
        for event, elem in context:
            if event != "end" or _local(elem.tag) != "page":
                continue
            title = elem.findtext("{*}title") or ""
            ns = elem.findtext("{*}ns") or ""
            redirect = elem.find("{*}redirect") is not None
            revision = elem.find("{*}revision")
            text = (revision.findtext("{*}text") if revision is not None else "") or ""
            revisionId = revision.findtext("{*}id") if revision is not None else None
            stamp = revision.findtext("{*}timestamp") if revision is not None else None
            # Clearing the root as well as the page keeps memory flat across the whole wiki.
            root.clear()
            count += 1
            if onProgress and count % 5000 == 0:
                onProgress(count)
            if ns != COOKBOOK_NS and not title.startswith("Cookbook:"):
                continue
            if redirect or text.lstrip().upper().startswith("#REDIRECT") or not _RECIPE_MARK.search(text):
                continue
            yield title, revisionId, stamp, text


def fetch(previous=None, log=print):
    previous = previous or {}
    kept = {"source": "wikibooks", "ok": False, "ids": list(previous.get("ids", [])),
            "dumpDate": previous.get("dumpDate")}
    try:
        date = latestDumpDate()
    except net.HttpError as e:
        log(f"wikibooks: the dump feed failed, keeping last pass's pages ({e})")
        return {**kept, "error": str(e)}
    if date == previous.get("dumpDate") and previous.get("ids"):
        log(f"wikibooks: dump {date} was already read")
        return {**previous, "ok": True, "error": None}

    dump = config.DATA_DIR / "wikibooks-dump.xml.bz2"
    ids = []
    try:
        net.downloadLarge(config.WIKIBOOKS_DUMP_URL, dump,
                          onProgress=lambda done: None)
        for title, revisionId, stamp, text in extractPages(dump):
            store.writeJson(store.rawPath("wikibooks", title),
                            {"source": "wikibooks", "sourceId": title, "revision": revisionId,
                             "timestamp": stamp, "wikitext": text})
            ids.append(title)
    except (net.HttpError, OSError, EOFError, ET.ParseError) as e:
        log(f"wikibooks: the dump could not be read, keeping last pass's pages ({e})")
        return {**kept, "error": f"{type(e).__name__}: {e}"}
    finally:
        dump.unlink(missing_ok=True)
    if not ids:
        log(f"wikibooks: dump {date} held no recipe pages, keeping last pass's pages")
        return {**kept, "error": "the dump held no recipe pages"}
    log(f"wikibooks: dump {date}, {len(ids)} recipe pages")
    return {"source": "wikibooks", "ok": True, "ids": sorted(ids), "error": None, "dumpDate": date}
