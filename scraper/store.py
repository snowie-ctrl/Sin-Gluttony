"""
The scraper's own JSON and JSON-lines files (state, reports, the last pass's
recipes). Every write goes through a temporary file and os.replace, so a
crash never leaves a half-written record that a later stage would read as real.
"""
import json, os
from pathlib import Path


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
