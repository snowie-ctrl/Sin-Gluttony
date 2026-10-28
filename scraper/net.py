# Copied from Artemis/Pageturner/net.py at 7acc9ec; changes: Gluttony's hosts and User-Agent, 1 s default interval,
# 3 tries, config read at call time, downloadLarge for the Wikibooks dump.
"""
Polite HTTP for every outside service: a per-host rate limit, retries with
backoff (honouring Retry-After on 429), and an optional on-disk cache so dry
runs can be repeated without asking the sources again.
"""
import hashlib, json, os, random, time
from urllib.parse import urlsplit

import requests

import config


# The sources are free services run by volunteers: a named agent lets them see
# who is asking, and nothing here needs to look like a browser.
USER_AGENT = "Gluttony-catalog/1.0 (private recipe catalog for a few friends)"
MIN_INTERVAL = {                # seconds between requests to the same host
    "www.themealdb.com": 1.0,
    "www.thecocktaildb.com": 1.0,
    "dumps.wikimedia.org": 1.0,
    "en.wikibooks.org": 1.0,
    "upload.wikimedia.org": 1.0,
}
DEFAULT_INTERVAL = 1.0
RETRIES = 3

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_lastCall = {}


class HttpError(Exception):
    pass


def _throttle(host):
    wait = MIN_INTERVAL.get(host, DEFAULT_INTERVAL) - (time.time() - _lastCall.get(host, 0))
    if wait > 0:
        time.sleep(wait + random.uniform(0, 0.3))
    _lastCall[host] = time.time()


def _cachePath(method, url, params, payload):
    key = json.dumps([method, url, params, payload], sort_keys=True)
    return config.CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".txt")


def request(method, url, *, params=None, payload=None, cacheHours=None, timeout=20, retries=RETRIES, cacheOnly=False, headers=None,
            refresh=False):
    """
    Return the response body as text. Raises HttpError once retries are exhausted.

    cacheOnly answers from the cache or fails, without touching the network.
    headers are sent but are not part of the cache key.
    refresh skips reading the cache for this one request and writes the answer back.
    """
    cacheFile = _cachePath(method, url, params, payload) if cacheHours else None
    if cacheFile and not refresh and cacheFile.exists() and time.time() - cacheFile.stat().st_mtime < cacheHours * 3600:
        return cacheFile.read_text(encoding="utf-8")
    if cacheOnly:
        raise HttpError(f"{method} {url} not cached")

    host = urlsplit(url).hostname
    lastError = None
    for attempt in range(retries):
        last = attempt == retries - 1
        _throttle(host)
        try:
            resp = _session.request(method, url, params=params, json=payload, timeout=timeout, headers=headers)
        except requests.RequestException as e:
            lastError = f"{type(e).__name__}: {e}"
            if not last:
                time.sleep(2 ** attempt)
            continue

        if resp.status_code == 429:
            lastError = "429 rate limited"
            if not last:
                time.sleep(float(resp.headers.get("Retry-After") or 2 ** (attempt + 2)))
            continue
        if resp.status_code >= 500:
            lastError = f"{resp.status_code} server error"
            if not last:
                time.sleep(2 ** attempt)
            continue
        if resp.status_code >= 400:
            raise HttpError(f"{method} {url} -> {resp.status_code}")

        if cacheFile:
            config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            # Through a temporary file: a half-written cache entry would be
            # served as a fresh (and broken) answer for hours.
            tmp = cacheFile.with_suffix(".tmp")
            tmp.write_text(resp.text, encoding="utf-8")
            os.replace(tmp, cacheFile)
        return resp.text

    raise HttpError(f"{method} {url} failed after {retries} attempt(s) ({lastError})")


def getText(url, params=None, cacheHours=None, retries=RETRIES, timeout=20, cacheOnly=False, headers=None):
    return request("GET", url, params=params, cacheHours=cacheHours, retries=retries, timeout=timeout,
                   cacheOnly=cacheOnly, headers=headers)


def getJson(url, params=None, cacheHours=None, retries=RETRIES, timeout=20, cacheOnly=False, headers=None):
    return json.loads(getText(url, params=params, cacheHours=cacheHours, retries=retries, timeout=timeout,
                              cacheOnly=cacheOnly, headers=headers))


def postJson(url, payload, cacheHours=None, refresh=False):
    return json.loads(request("POST", url, payload=payload, cacheHours=cacheHours, refresh=refresh))


def download(url, destPath, timeout=30):
    """Save a binary file (pictures). Returns True on success; failures are not fatal."""
    host = urlsplit(url).hostname
    for attempt in range(RETRIES):
        _throttle(host)
        try:
            resp = _session.get(url, timeout=timeout)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            destPath.parent.mkdir(parents=True, exist_ok=True)
            destPath.write_bytes(resp.content)
            return True
        if resp.status_code < 500 and resp.status_code != 429:
            return False
        time.sleep(2 ** attempt)
    return False


def downloadLarge(url, destPath, timeout=60, onProgress=None):
    """
    Stream a big file (the Wikibooks dump, about 200 MB) to disk without
    holding it in memory. It is written beside the target and moved into place
    at the end, so an interrupted download never looks finished.
    onProgress(bytesSoFar) is called after each chunk. Raises HttpError.
    """
    host = urlsplit(url).hostname
    partial = destPath.with_name(destPath.name + ".part")
    lastError = None
    for attempt in range(RETRIES):
        _throttle(host)
        try:
            with _session.get(url, stream=True, timeout=timeout) as resp:
                if resp.status_code != 200:
                    lastError = f"{resp.status_code}"
                    if resp.status_code < 500 and resp.status_code != 429:
                        break
                    time.sleep(2 ** attempt)
                    continue
                destPath.parent.mkdir(parents=True, exist_ok=True)
                done = 0
                with open(partial, "wb") as out:
                    for chunk in resp.iter_content(1 << 20):
                        out.write(chunk)
                        done += len(chunk)
                        if onProgress:
                            onProgress(done)
            os.replace(partial, destPath)
            return
        except requests.RequestException as e:
            lastError = f"{type(e).__name__}: {e}"
            time.sleep(2 ** attempt)
    partial.unlink(missing_ok=True)
    raise HttpError(f"GET {url} failed ({lastError})")
