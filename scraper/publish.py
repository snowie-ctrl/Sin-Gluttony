"""
Turns tagged recipes into the payload plutus stores and sends only what
changed: each recipe's content hash is compared with the last one plutus
confirmed. Pictures go first, so no recipe ever names a picture plutus doesn't
have.

Removals come only from a complete fetch of a source. If a source failed, or
returned more than REMOVAL_GUARD fewer records than last pass (a capped free
key, a broken dump), nothing of it is removed and the report says why.
"""
import hashlib
import json

import adminApi
import config
import store


def searchText(recipe):
    return " ".join([recipe.title] + [line.name for line in recipe.ingredients if line.name])[:4000]


def contentHash(payload):
    body = {k: v for k, v in payload.items() if k != "contentHash"}
    return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def payloadFor(recipe):
    payload = {
        "key": recipe.key, "source": recipe.source, "sourceId": recipe.sourceId, "kind": recipe.kind,
        "title": recipe.title, "dishKey": recipe.dishKey, "course": recipe.course, "cuisine": recipe.cuisine,
        "servings": recipe.servings, "servingsFrom": recipe.servingsFrom, "prepMinutes": recipe.prepMinutes,
        "cookMinutes": recipe.cookMinutes, "totalMinutes": recipe.totalMinutes, "timeFrom": recipe.timeFrom,
        "difficulty": recipe.difficulty, "difficultyFrom": recipe.difficultyFrom, "alcohol": recipe.alcohol,
        "glass": recipe.glass, "imagePath": recipe.imagePath, "imageCredit": recipe.imageCredit,
        "videoUrl": recipe.videoUrl, "sourceUrl": recipe.sourceUrl, "licence": recipe.licence,
        "credit": recipe.credit, "searchText": searchText(recipe),
        "ingredients": [{"line": l.line, "quantity": l.quantity, "quantityMax": l.quantityMax, "unit": l.unit,
                         "ingredientId": l.ingredientId, "unknownName": l.unknownName, "note": l.note,
                         "optional": l.optional, "group": l.group} for l in recipe.ingredients],
        "steps": [{"text": s.text, "group": s.group} for s in recipe.steps],
        "tags": recipe.tags,
        "facts": recipe.facts,
    }
    payload["contentHash"] = contentHash(payload)
    return payload


def removalsFor(publishedKeys, fetchResults, lastCounts, guard):
    """(keys to mark removed, a note per source that removes nothing, the sources the guard held back)."""
    keys, notes, guarded = [], [], []
    for source, result in sorted(fetchResults.items()):
        if not result.get("ok"):
            notes.append(f"{source}: fetch failed, nothing removed")
            continue
        ids = set(result.get("ids", []))
        if not ids:
            notes.append(f"{source}: fetch returned no records, nothing removed")
            guarded.append(source)
            continue
        last = lastCounts.get(source)
        if last and len(ids) < last * (1 - guard):
            notes.append(f"{source}: {len(ids)} records against {last} last pass, more than {guard:.0%} fewer, "
                         "nothing removed")
            guarded.append(source)
            continue
        keys += [k for k in publishedKeys if k.split(":", 1)[0] == source and k.split(":", 1)[1] not in ids]
    return sorted(keys), notes, guarded


def _publishedState(dry):
    state = store.readJson(config.PUBLISHED_FILE, None)
    if state is not None:
        return dict(state.get("recipes", {}))
    if dry or not adminApi.configured():
        return {}
    # The local file was lost: plutus knows what it holds.
    return {row["key"]: row["hash"] for row in adminApi.get("/state")["recipes"]}


def _save(published):
    store.writeJson(config.PUBLISHED_FILE, {"recipes": published})


def publish(recipes, fetchResults, lastCounts, log=print):
    dry = config.PUBLISH != "on"
    if not dry and not adminApi.configured():
        raise adminApi.AdminError("ADMIN_TOKEN and ADMIN_HOST must be set in .env")
    payloads = [payloadFor(r) for r in recipes]
    published = _publishedState(dry)
    changed = [p for p in payloads if published.get(p["key"]) != p["contentHash"]]
    perSource = {}
    for p in changed:
        counts = perSource.setdefault(p["source"], {"new": 0, "changed": 0})
        counts["changed" if p["key"] in published else "new"] += 1
    removeKeys, notes, guarded = removalsFor(list(published), fetchResults, lastCounts, config.REMOVAL_GUARD)
    summary = {"dry": dry, "changed": len(changed), "perSource": perSource, "stored": 0, "failed": [],
               "removed": 0, "notes": notes, "guarded": guarded}
    if dry:
        summary.update({"wouldRemove": removeKeys[:50], "wouldRemoveCount": len(removeKeys)})
        log(f"publish (dry): {len(changed)} would be sent, {len(removeKeys)} would be removed")
        return summary

    if changed:
        for folder in ("images", "thumbs"):
            if (config.IMAGE_DIR / folder).exists():
                adminApi.rsync(config.IMAGE_DIR / folder, f"{config.MEDIA_ROOT}/{folder}")
    for start in range(0, len(changed), config.BATCH_SIZE):
        batch = changed[start:start + config.BATCH_SIZE]
        answer = adminApi.post("/recipes/batch", {"recipes": batch})
        hashes = {p["key"]: p["contentHash"] for p in batch}
        for key in answer.get("stored", []):
            published[key] = hashes[key]
        summary["stored"] += len(answer.get("stored", []))
        summary["failed"] += answer.get("failed", [])
        _save(published)                    # after every batch, so a failure later keeps this progress
    for start in range(0, len(removeKeys), 1000):
        chunk = removeKeys[start:start + 1000]
        answer = adminApi.post("/recipes/removed", {"keys": chunk})
        summary["removed"] += answer.get("removed", 0)
        for key in chunk:
            published.pop(key, None)
        _save(published)
    if not changed and not removeKeys:
        _save(published)
    log(f"publish: {summary['stored']} stored, {len(summary['failed'])} refused, {summary['removed']} removed")
    return summary
