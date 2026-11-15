"""
The raw record of every recipe page: data/raw/<site>/<sha1(url)>.html.gz, with
<sha1(url)>.json beside it holding the url, when it was fetched and the
sitemap's lastmod, and listing.json holding the site's last sitemap listing.
Better parsing later reads these again and never asks the site. data/ is
git-ignored: no page is ever committed.
"""
import gzip
import hashlib
import os
import time
import zlib

import config
import store

LISTING = "listing.json"


def sourceIdFor(url):
    """A recipe site page's source id (its key is "<site>:<id>"): the first 20 hex digits of sha1(url)."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def _paths(site, url):
    folder = config.RAW_DIR / site
    name = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return folder / f"{name}.html.gz", folder / f"{name}.json"


def save(site, url, html, lastmod, fetchedAt=None):
    """The page first, then its sidecar: a sidecar never names a page that is not whole on disk."""
    page, meta = _paths(site, url)
    page.parent.mkdir(parents=True, exist_ok=True)
    tmp = page.with_name(f"{page.name}.{os.getpid()}.tmp")
    tmp.write_bytes(gzip.compress(html.encode("utf-8")))
    os.replace(tmp, page)
    store.writeJson(meta, {"url": url, "fetchedAt": time.time() if fetchedAt is None else fetchedAt,
                           "lastmod": lastmod})


def meta(site, url):
    return store.readJson(_paths(site, url)[1])


def load(site, url):
    page, _ = _paths(site, url)
    try:
        return gzip.decompress(page.read_bytes()).decode("utf-8", errors="replace")
    except (OSError, EOFError, zlib.error):     # missing, cut short by a killed run, or damaged
        return None


def pages(site):
    """(meta, html) for every whole cached page of a site, in URL order, one at a time (a full site is gigabytes)."""
    folder = config.RAW_DIR / site
    metas = [store.readJson(path) for path in folder.glob("*.json") if path.name != LISTING]
    for info in sorted((m for m in metas if isinstance(m, dict) and m.get("url")), key=lambda m: m["url"]):
        html = load(site, info["url"])
        if html is not None:
            yield info, html


def urlsBySourceId(site):
    """{source id: url} for every page of a site with a sidecar on disk."""
    folder = config.RAW_DIR / site
    metas = [store.readJson(path) for path in folder.glob("*.json") if path.name != LISTING]
    return {sourceIdFor(m["url"]): m["url"] for m in metas if isinstance(m, dict) and m.get("url")}


def drop(site, url):
    """Forget a page: its .html.gz and its sidecar. A page plutus was told is removed must not be read again
    from here (it would be published anew); if it comes back in the sitemap it is due and fetched afresh."""
    for path in _paths(site, url):
        path.unlink(missing_ok=True)


def saveListing(site, entries):
    store.writeJson(config.RAW_DIR / site / LISTING, [[url, lastmod] for url, lastmod in entries])


def listing(site):
    return [(url, lastmod) for url, lastmod in store.readJson(config.RAW_DIR / site / LISTING, []) or []]
