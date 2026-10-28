"""
Each pass's report: counts per source, what was skipped and why, which
unknown ingredients block the most recipes, how well the rules agree with
Wikibooks, and what publishing did. The latest is run/last-report.json
(Surrogate reads it); the last 30 stay in reports/; run/runs.jsonl keeps one
line per pass.
"""
import json
import time

import config
import store

KEEP_REPORTS = 30


def unknownIngredients(recipes, limit=200):
    counts, examples = {}, {}
    for recipe in recipes:
        for line in recipe.ingredients:
            if line.unknownName and line.unknownName not in examples:
                examples[line.unknownName] = line.line
        for name in {line.unknownName for line in recipe.ingredients if line.unknownName}:
            counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [{"name": name, "recipes": n, "example": examples[name]} for name, n in ranked]


def summariseSkipped(skipped, keep=500):
    byReason = {}
    for entry in skipped:
        byReason[entry["reason"]] = byReason.get(entry["reason"], 0) + 1
    return {"skipped": skipped[:keep], "skippedCount": len(skipped), "skippedByReason": byReason}


def write(report):
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["startedAt"]))
    store.writeJson(config.REPORT_DIR / f"run-{stamp}.json", report)
    store.writeJson(config.LAST_REPORT_FILE, report)
    for old in sorted(config.REPORT_DIR.glob("run-*.json"))[:-KEEP_REPORTS]:
        old.unlink(missing_ok=True)
    published = report.get("publish") or {}
    line = {key: report.get(key) for key in ("mode", "outcome", "error", "startedAt", "endedAt", "recipes")}
    line.update({"changed": published.get("changed", 0), "removed": published.get("removed", 0),
                 "dry": published.get("dry")})
    config.RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.RUNS_FILE, "a", encoding="utf-8") as out:
        out.write(json.dumps(line) + "\n")


def lastRun():
    try:
        lines = config.RUNS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None
