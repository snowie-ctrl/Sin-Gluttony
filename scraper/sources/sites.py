"""
The recipe sites in rules/sites.json: what each one's robots.txt allows and
which recipe pages its sitemaps list, with lastmod. Every request goes through
net.crawl (GluttonyPersonalCrawler, one request per 5 s per host), and a 403
or 429 stops the site for the pass as SiteStopped. The crawl takes the sites in
turn and keeps each recipe page in pagecache.
"""
import gzip
import re
import time
import xml.etree.ElementTree as ET
import zlib
from urllib.parse import urlsplit
from datetime import datetime, timezone
from urllib.robotparser import RobotFileParser

import config
import net
import pagecache
import store
from sources import schemaOrg

AGENT = "GluttonyPersonalCrawler"       # the name robots.txt groups are matched against
MAX_SITEMAPS = 300                      # a runaway sitemap index stops here
# A bare page (no recipe, no page metadata) whose <title> or first 2 KB of body holds one of these is a bot
# challenge or a "Simple Page" wall. Not looked for in ordinary pages: Cloudflare scripts and reCAPTCHA sit in those.
WALL_MARKERS = re.compile(r"cf-challenge|are you a robot|access denied|just a moment|simple page", re.IGNORECASE)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_BODY = re.compile(r"<body[^>]*>", re.I)
BODY_SCAN = 2048
NOT_RECIPE_RUN = 10     # this many bare pages (no JSON-LD, no og:type) in a row is a wall too
UNREACHABLE_RUN = 5     # this many failed requests in a row stops the site
RECHECK_EVERY = 4       # a site without lastmod is fetched in full every fourth pass
GONE_AFTER = 2          # a page answering 404 or 410 this many passes in a row is gone

FIELDS = ("site", "name", "host", "sitemaps", "recipeUrl", "parser", "kind", "enabled")
PARSERS = ("schema", "difford")


def loadSites(rules):
    """The enabled entries of rules/sites.json. A malformed entry stops the run: the file is reviewed config."""
    enabled = []
    for entry in rules.get("sites", []):
        name = entry.get("site", "?")
        missing = [field for field in FIELDS if field not in entry]
        if missing:
            raise ValueError(f"sites.json: {name} lacks {', '.join(missing)}")
        if entry["parser"] not in PARSERS:
            raise ValueError(f"sites.json: {name}: parser must be one of {', '.join(PARSERS)}")
        if entry["kind"] not in ("food", "drink"):
            raise ValueError(f"sites.json: {name}: kind must be food or drink")
        try:
            re.compile(entry["recipeUrl"])
        except re.error as e:
            raise ValueError(f"sites.json: {name}: recipeUrl is not a pattern ({e})")
        for url in entry["sitemaps"]:
            if (urlsplit(url).hostname or "").lower() != entry["host"]:
                raise ValueError(f"sites.json: {name}: sitemap {url} is not on host {entry['host']}")
        if entry["enabled"]:
            enabled.append(entry)
    return enabled


class SiteStopped(Exception):
    """A site that refused, walled us off or says no in robots.txt: nothing more is asked of it this pass."""
    def __init__(self, reason, retryAfter=None):
        super().__init__(reason)
        self.reason = reason
        self.retryAfter = retryAfter


def refusal(error):
    """The stop for a 403 or 429 answer; a 429's Retry-After is kept for the next pass."""
    if error.status == 429:
        return SiteStopped("rate limited (429)", error.retryAfter)
    return SiteStopped(f"blocked ({error.status})")


def robotsFor(site):
    """
    The site's robots.txt. A missing one (404 and other 4xx) allows everything,
    as the robots convention says; a refusal stops the site; an unreachable one
    stops it too, because rules we could not read cannot be obeyed.
    """
    url = f"https://{site['host']}/robots.txt"
    robots = RobotFileParser(url)
    try:
        text = net.crawl(url)
    except net.HttpError as e:
        if e.status in (403, 429):
            raise refusal(e)
        if e.status is not None and 400 <= e.status < 500:
            robots.parse([])
            return robots
        raise SiteStopped(f"robots.txt unreachable ({e})")
    robots.parse(text.splitlines())
    return robots


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parseSitemap(data):
    """('sitemapindex' or 'urlset', [(loc, lastmod or None)]) from a sitemap's bytes, gzipped or not."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    root = ET.fromstring(data)
    entries = []
    for item in root:
        fields = {_local(child.tag): (child.text or "").strip() for child in item}
        if fields.get("loc"):
            entries.append((fields["loc"], fields.get("lastmod") or None))
    return _local(root.tag), entries


def parseLastmod(text):
    if not text:
        return None
    try:
        when = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _iso(when):
    """One text form for every lastmod, so newer compares as greater."""
    return when.astimezone(timezone.utc).isoformat() if when else None


def sitemapEntries(site, robots, log=print):
    """
    Every recipe page the site's sitemaps list (indexes followed) and robots.txt
    allows, as (url, lastmod or None): newest first, pages without lastmod last.
    """
    pattern = re.compile(site["recipeUrl"])
    queue, seen, found = list(site["sitemaps"]), set(), {}
    while queue and len(seen) < MAX_SITEMAPS:
        url = queue.pop(0)
        if url in seen:
            continue
        if urlsplit(url).hostname != site["host"]:
            # this host's robots.txt cannot vouch for another host
            log(f"{site['site']}: sitemap {url} skipped (other host)")
            continue
        if not robots.can_fetch(AGENT, url):
            continue
        seen.add(url)
        try:
            kind, entries = parseSitemap(net.crawl(url, binary=True))
        except net.HttpError as e:
            if e.status in (403, 429):
                raise refusal(e)
            log(f"{site['site']}: sitemap {url} skipped ({e})")
            continue
        except (ET.ParseError, OSError, EOFError, zlib.error) as e:
            log(f"{site['site']}: sitemap {url} unreadable ({type(e).__name__})")
            continue
        if kind == "sitemapindex":
            queue += [loc for loc, _ in entries]
            continue
        for loc, lastmod in entries:
            if pattern.match(loc):
                when = _iso(parseLastmod(lastmod))
                if loc not in found or (when or "") > (found[loc] or ""):
                    found[loc] = when
    if not found:
        raise SiteStopped("no recipe pages in the sitemaps")
    allowed = sorted((url, when) for url, when in found.items() if robots.can_fetch(AGENT, url))
    if not allowed:
        raise SiteStopped("robots.txt disallows the recipe pages")
    allowed.sort(key=lambda entry: entry[1] or "", reverse=True)   # stable: URL order within the same lastmod
    return allowed


def isDue(lastmod, cached, recheck=False):
    """A page is fetched when it is new, newer than its cached copy, or (recheck) its site gives no lastmod."""
    if cached is None or recheck:
        return True
    if lastmod is None:
        return False
    old = parseLastmod(cached.get("lastmod"))
    return old is None or parseLastmod(lastmod) > old


def choose(entries, pages, priority=frozenset()):
    """The first `pages` entries (None: all), priority URLs (the basics) first, then in listing order."""
    ordered = [e for e in entries if e[0] in priority] + [e for e in entries if e[0] not in priority]
    return ordered if pages is None else ordered[:pages]


def _newResult(name):
    return {"site": name, "ok": True, "stopReason": None, "listed": 0, "planned": 0, "due": 0, "fetched": 0,
            "notRecipe": 0, "gone": 0, "errors": 0}


def _stopped(result, siteState, stop, now):
    result["ok"], result["stopReason"] = False, stop.reason
    siteState["lastStop"] = stop.reason
    if stop.retryAfter:
        siteState["notBefore"] = now() + stop.retryAfter


def _plan(site, siteState, pages, priority, log, now):
    """(listing, chosen, due) for this pass, or SiteStopped."""
    notBefore = siteState.get("notBefore")
    if notBefore and now() < notBefore:
        raise SiteStopped("waiting for the Retry-After a 429 asked for")
    siteState.pop("notBefore", None)
    robots = robotsFor(site)
    delay = robots.crawl_delay(AGENT)
    if delay and float(delay) > net.CRAWL_INTERVAL:
        net.MIN_INTERVAL[site["host"]] = float(delay)       # robots.txt asks for more room than 5 s: it gets it
    entries = sitemapEntries(site, robots, log)
    pagecache.saveListing(site["site"], entries)
    passes = siteState.get("passes", 0)
    siteState["passes"] = passes + 1
    recheck = not any(lastmod for _, lastmod in entries) and passes % RECHECK_EVERY == 0
    # pages known not to be recipes (blog posts) wait for a changed lastmod and take no slot from the limit
    known = siteState.get("notRecipe", {})
    eligible = [(url, lastmod) for url, lastmod in entries
                if url not in known or isDue(lastmod, {"lastmod": known[url]}, recheck)]
    chosen = choose(eligible, pages, priority)
    due = [(url, lastmod) for url, lastmod in chosen if isDue(lastmod, pagecache.meta(site["site"], url), recheck)]
    return entries, chosen, due


def _challenge(html):
    title = _TITLE.search(html)
    body = _BODY.search(html)
    start = body.end() if body else 0
    return bool(WALL_MARKERS.search((title.group(1) if title else "") + " " + html[start:start + BODY_SCAN]))


def _fetchOne(site, url, lastmod, result, siteState, run, now, log):
    try:
        html = net.crawl(url)
    except net.HttpError as e:
        if e.status in (403, 429):
            raise refusal(e)
        if e.status in (404, 410):
            missing = siteState.setdefault("missing", {})
            missing[url] = missing.get(url, 0) + 1
            if missing[url] >= GONE_AFTER:
                result["gone"] += 1         # milestone 3 marks these RemovedAt; here they are counted
            return
        result["errors"] += 1
        run["failures"] += 1
        if run["failures"] >= UNREACHABLE_RUN:
            raise SiteStopped(f"unreachable ({UNREACHABLE_RUN} failed requests in a row: {e})")
        return
    run["failures"] = 0
    siteState.get("missing", {}).pop(url, None)
    if not schemaOrg.hasRecipe(html):
        result["notRecipe"] += 1
        if schemaOrg.hasPageMetadata(html):
            siteState.setdefault("notRecipe", {})[url] = lastmod
            return      # an ordinary blog post or article: skipped, but no sign of a wall either way
        if _challenge(html):
            result["notRecipe"] -= 1        # a wall is not a page of the site
            raise SiteStopped(f"walled (a bot challenge instead of the recipe at {url})")
        run["notRecipe"] += 1
        if run["notRecipe"] >= NOT_RECIPE_RUN:
            raise SiteStopped(f"walled ({NOT_RECIPE_RUN} pages in a row without recipe markup)")
        return
    run["notRecipe"] = 0
    siteState.get("notRecipe", {}).pop(url, None)
    pagecache.save(site["site"], url, html, lastmod, fetchedAt=now())
    result["fetched"] += 1
    if result["fetched"] % 25 == 0:
        log(f"{site['site']}: {result['fetched']} of {result['due']} pages fetched")


def crawl(siteList, pages, log=print, priority=frozenset(), now=time.time):
    """
    One pass over the sites. For each: robots.txt, the sitemaps, then the first
    `pages` recipe URLs (priority ones first, then newest; None: all), fetched
    when due. The sites take turns, so with net's 5 s per host no site waits
    for another. Returns {site: result}. Stops, Retry-After, 404 counts and pass
    counts are kept in config.SITE_STATE_FILE, saved even if the pass breaks.
    """
    state = store.readJson(config.SITE_STATE_FILE, {}) or {}
    bySite = {site["site"]: site for site in siteList}
    results, queues, runs = {}, {}, {}
    try:
        for site in siteList:
            name = site["site"]
            siteState = state.setdefault(name, {})
            result = results[name] = _newResult(name)
            try:
                entries, chosen, due = _plan(site, siteState, pages, priority, log, now)
            except SiteStopped as stop:
                _stopped(result, siteState, stop, now)
                log(f"{name}: stopped ({stop.reason})")
                continue
            siteState.pop("lastStop", None)
            result.update(listed=len(entries), planned=len(chosen), due=len(due))
            log(f"{name}: {len(entries)} recipe pages listed, {len(due)} of the first {len(chosen)} due")
            if due:
                queues[name], runs[name] = list(due), {"notRecipe": 0, "failures": 0}
        while queues:
            for name in list(queues):
                url, lastmod = queues[name].pop(0)
                try:
                    _fetchOne(bySite[name], url, lastmod, results[name], state[name], runs[name], now, log)
                except SiteStopped as stop:
                    _stopped(results[name], state[name], stop, now)
                    log(f"{name}: stopped ({stop.reason})")
                    queues[name] = []
                if not queues[name]:
                    del queues[name]
    finally:
        store.writeJson(config.SITE_STATE_FILE, state)
    return results
