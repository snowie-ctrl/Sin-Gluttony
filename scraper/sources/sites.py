"""
The recipe sites in rules/sites.json: what each one's robots.txt allows and
which recipe pages its sitemaps list, with lastmod. Every request goes through
net.crawl (GluttonyPersonalCrawler, one request per 5 s per host), and a 403
or 429 stops the site for the pass as SiteStopped.
"""
import gzip
import re
import xml.etree.ElementTree as ET
import zlib
from urllib.parse import urlsplit
from datetime import datetime, timezone
from urllib.robotparser import RobotFileParser

import net

AGENT = "GluttonyPersonalCrawler"       # the name robots.txt groups are matched against
MAX_SITEMAPS = 300                      # a runaway sitemap index stops here

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
