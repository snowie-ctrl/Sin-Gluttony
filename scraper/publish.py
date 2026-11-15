"""
Turns tagged recipes into the payload plutus stores and sends only what
changed: each recipe's content hash is compared with the last one plutus
confirmed. Pictures go first, so no recipe ever names a picture plutus doesn't
have.

Removals come only from a complete fetch of a source. If a source failed, or
returned more than REMOVAL_GUARD fewer records than last pass (a capped free
key, a broken dump), nothing of it is removed and the report says why.

A recipe site removes a page that answered gone (404/410) on enough passes in
a row, and, when this pass read the site's whole sitemap listing, every page
missing from it. A listing that shrank by more than REMOVAL_GUARD since last
time removes nothing that way. Gone pages are removed even when the pass
stopped the site early, since each gone answer was seen directly. The old
sources (OLD_SOURCES) are skipped by construction, whatever is passed in.
Once plutus confirms a site removal, the page leaves the page cache, so no
later pass reads it and sends it again; a key being removed is never also
sent in the same pass.

A site recipe also carries its description, the gate's hidden reason, its
picture's width and its per-serving nutrition. Each goes in only when it has a
value, and never for an old-source recipe (whose picture does get a width), so
an old-source recipe's payload and hash are what they were.
"""
import hashlib
import json

import adminApi
import config
import pagecache
import store

OLD_SOURCES = config.OLD_SOURCES
MAX_NUTRIENT = 100000      # plutus refuses a per-serving nutrient above this, or below 0
NUTRIENTS = ("calories", "proteinG", "carbsG", "fatG", "satFatG", "fibreG", "sugarG", "sodiumMg")


def searchText(recipe):
    return " ".join([recipe.title] + [line.name for line in recipe.ingredients if line.name])[:4000]


def contentHash(payload):
    body = {k: v for k, v in payload.items() if k != "contentHash"}
    return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _storable(value):
    """A nutrient plutus can store (0 to 100,000, Ruling S10), else None: one wild number never refuses the recipe."""
    return value if value is not None and 0 <= value <= MAX_NUTRIENT else None


def nutritionFor(recipe):
    """The per-serving nutrition plutus stores, or None when there are no storable calories to show."""
    values = recipe.nutrition or {}
    if _storable(values.get("calories")) is None:
        return None
    return dict({name: _storable(values.get(name)) for name in NUTRIENTS},
                **{"from": recipe.nutritionFrom, "flagged": bool(recipe.nutritionFlagged)})


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
    if recipe.source not in OLD_SOURCES:     # an old-source payload and hash stay exactly as they were (Ruling P1)
        extras = {"description": recipe.description, "hiddenReason": recipe.hiddenReason,
                  "imageWidth": recipe.imageWidth, "nutrition": nutritionFor(recipe)}
        payload.update({name: value for name, value in extras.items() if value is not None})
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


def siteRemovals(publishedKeys, crawled, lastCounts, guard):
    """(keys to mark removed, a note per site the guard held back, those sites) for the recipe sites crawled."""
    keys, notes, guarded = set(), [], []
    for site, result in sorted(crawled.items()):
        if site in OLD_SOURCES:
            continue
        bySourceId = {k.split(":", 1)[1]: k for k in publishedKeys if k.split(":", 1)[0] == site}
        for url in result.get("goneUrls", []):
            key = bySourceId.get(pagecache.sourceIdFor(url))
            if key:
                keys.add(key)
        if not result.get("complete"):
            continue
        listed = {pagecache.sourceIdFor(url) for url, _ in pagecache.listing(site)}
        last = lastCounts.get(site)
        if not listed:
            notes.append(f"{site}: the sitemap listing is empty, nothing removed for missing pages")
            guarded.append(site)
            continue
        if last and len(listed) < last * (1 - guard):
            notes.append(f"{site}: {len(listed)} pages listed against {last} last time, more than {guard:.0%} fewer, "
                         "nothing removed for missing pages")
            guarded.append(site)
            continue
        keys.update(key for sourceId, key in bySourceId.items() if sourceId not in listed)
    return sorted(keys), notes, guarded


def publishedState(dry):
    """{key: contentHash} of what plutus holds: run's published file, else (publishing on) plutus's /state."""
    state = store.readJson(config.PUBLISHED_FILE, None)
    if state is not None:
        return dict(state.get("recipes", {}))
    if dry or not adminApi.configured():
        return {}
    # The local file was lost: plutus knows what it holds.
    return {row["key"]: row["hash"] for row in adminApi.get("/state")["recipes"]}


def _save(published):
    store.writeJson(config.PUBLISHED_FILE, {"recipes": published})


def _dropCached(keys, urlMaps):
    """Drop each removed recipe-site page from the page cache once plutus has its removal, so no later pass or
    re-tag reads it again and re-sends it (which would clear its RemovedAt). Old sources have no page cache."""
    for key in keys:
        site, sourceId = key.split(":", 1)
        if site in OLD_SOURCES:
            continue
        if site not in urlMaps:
            urlMaps[site] = pagecache.urlsBySourceId(site)
        url = urlMaps[site].get(sourceId)
        if url:
            pagecache.drop(site, url)


def publish(recipes, fetchResults, lastCounts, log=print, removals=None):
    """removals, when given, is a (keys, notes, guarded) already worked out (the recipe sites' siteRemovals)."""
    dry = config.PUBLISH != "on"
    if not dry and not adminApi.configured():
        raise adminApi.AdminError("ADMIN_TOKEN and ADMIN_HOST must be set in .env")
    payloads = [payloadFor(r) for r in recipes]
    published = publishedState(dry)
    if removals is not None:
        removeKeys, notes, guarded = sorted(removals[0]), list(removals[1]), list(removals[2])
    else:
        removeKeys, notes, guarded = removalsFor(list(published), fetchResults, lastCounts, config.REMOVAL_GUARD)
    removing = set(removeKeys)      # a page this pass removes is never also sent (it would clear RemovedAt)
    changed = [p for p in payloads if published.get(p["key"]) != p["contentHash"] and p["key"] not in removing]
    perSource = {}
    for p in changed:
        counts = perSource.setdefault(p["source"], {"new": 0, "changed": 0})
        counts["changed" if p["key"] in published else "new"] += 1
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
    urlMaps = {}
    for start in range(0, len(removeKeys), 1000):
        chunk = removeKeys[start:start + 1000]
        answer = adminApi.post("/recipes/removed", {"keys": chunk})
        summary["removed"] += answer.get("removed", 0)
        for key in chunk:
            published.pop(key, None)
        _save(published)
        _dropCached(chunk, urlMaps)
    if not changed and not removeKeys:
        _save(published)
    log(f"publish: {summary['stored']} stored, {len(summary['failed'])} refused, {summary['removed']} removed")
    return summary
