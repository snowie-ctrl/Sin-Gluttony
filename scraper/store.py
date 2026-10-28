"""
The scraper's own files: raw records as fetched, and small JSON state files.
Every write goes through a temporary file and os.replace, so a crash never
leaves a half-written record that a later stage would read as real.
"""
import hashlib, json, os, re
from pathlib import Path

import config

_PLAIN_ID = re.compile(r"[A-Za-z0-9_-]{1,60}")


def writeJson(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def readJson(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def writeLines(path, lines):
    """One JSON object per line, written whole or not at all."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as out:
        for line in lines:
            out.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)


def safeName(text):
    """A file name for any source id: Wikibooks page titles hold slashes, colons and spaces."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def rawPath(source, sourceId):
    sourceId = str(sourceId)
    name = sourceId if _PLAIN_ID.fullmatch(sourceId) else safeName(sourceId)
    return config.RAW_DIR / source / f"{name}.json"
