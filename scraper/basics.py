"""
The basics (quick-mode staples) in rules/basics.json. Each has a short ranked
list of candidate pages, "urls"; the first candidate that passes the
completeness gate is the basic's page and the only one tagged `basic`. The
others stay ordinary recipes. A file with only "url" (the older shape) counts
as a list of one.
"""


def candidateUrls(basic):
    urls = basic.get("urls")
    if urls is None:
        urls = [basic["url"]] if basic.get("url") else []
    return [u for u in urls if u]


def priorityUrls(rules):
    """Every candidate of every basic: the crawl fetches these first."""
    return frozenset(u for basic in rules.get("basics", []) for u in candidateUrls(basic))


def _pageStatus(url, byUrl, notRead, rejected):
    if url in byUrl:
        reason = byUrl[url].hiddenReason
        return f"hidden: {reason}" if reason else "listed"
    if url in notRead:
        return f"not read: {notRead[url]}"
    if url in rejected:
        return "not a recipe page"
    return "not fetched"


def resolve(rules, recipes, skipped=(), siteState=None):
    """One row per basic: name, url (the chosen page, else the first candidate), status, candidate (1-based or None)."""
    byUrl = {r.sourceUrl: r for r in recipes}
    notRead = {s["url"]: s["reason"] for s in skipped}
    # pages the crawler fetched and found not to be recipes are not cached; the site state remembers them
    rejected = {url for state in (siteState or {}).values() if isinstance(state, dict)
                for url in state.get("notRecipe", {})}
    rows = []
    for basic in rules.get("basics", []):
        urls = candidateUrls(basic)
        row = {"name": basic["name"], "url": urls[0] if urls else None, "status": "missing: no site has it",
               "candidate": None}
        statuses = [_pageStatus(u, byUrl, notRead, rejected) for u in urls]
        if urls:
            row["status"] = statuses[0]
            for number, (url, status) in enumerate(zip(urls, statuses), 1):
                if status == "listed":
                    row.update(url=url, candidate=number,
                               status="listed" if number == 1 else f"listed via candidate {number}")
                    break
        rows.append(row)
    return rows


def applyTags(recipes, rules):
    """The `basic` occasion tag goes on each basic's chosen page only; call after the gate has run."""
    chosen = {row["url"] for row in resolve(rules, recipes) if row["candidate"]}
    for recipe in recipes:
        if recipe.sourceUrl in chosen:
            recipe.tags.append({"type": "occasion", "tag": "basic", "origin": "rule"})
