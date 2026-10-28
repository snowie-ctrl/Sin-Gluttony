"""
Where a Wikibooks recipe's picture lives and who to credit. Wikibooks' own API
answers for its local files and for Commons files alike, with the licence and
the author, which the app shows beside the picture.
"""
import html
import re
from urllib.parse import urlsplit

import config
import net

# The only widths Wikimedia serves. Anything else, the original file included,
# is refused with "too many requests" (https://w.wiki/GHai). The large copy is
# 1200 px, so nothing wider is asked for.
WIDTHS = (20, 40, 60, 120, 250, 330, 500, 960, 1280)


def fileName(value):
    """The bare file name from a summary's Image field: "[[File:Toast.jpg|200px]]", "Image:Toast.jpg" or "Toast.jpg"."""
    text = (value or "").strip().strip("[]").split("|", 1)[0].strip()
    text = re.sub(r"^(file|image)\s*:\s*", "", text, flags=re.IGNORECASE)
    return text or None


def _plain(markup):
    return html.unescape(re.sub(r"<[^>]+>", "", markup or "")).strip()


def isOriginal(url):
    """True for the address of the file itself rather than of a resized copy."""
    return "/thumb/" not in urlsplit(url).path


def _ask(name, width):
    data = net.getJson(config.WIKIBOOKS_API, params={
        "action": "query", "format": "json", "titles": f"File:{name}", "prop": "imageinfo",
        "iiprop": "url|size|extmetadata", "iiurlwidth": str(width)}, cacheHours=24 * 30)
    for page in ((data.get("query") or {}).get("pages") or {}).values():
        return (page.get("imageinfo") or [None])[0]
    return None


def imageInfo(name):
    """
    {"url", "credit"} for a file, or None when it doesn't exist or is too small
    for any width Wikimedia serves. Cached 30 days; raises net.HttpError.
    """
    info = _ask(name, WIDTHS[-1])
    if not info:
        return None
    url = info.get("thumburl") or info.get("url")
    if isOriginal(url):
        # Asked for its own width or more, the API gives the original back:
        # ask again for the widest listed size below it.
        smaller = [w for w in WIDTHS if w < (info.get("width") or 0)]
        info = _ask(name, smaller[-1]) if smaller else None
        url = info and info.get("thumburl")
        if not url or isOriginal(url):
            return None
    meta = info.get("extmetadata") or {}
    parts = [p for p in (_plain((meta.get("Artist") or {}).get("value")),
                         _plain((meta.get("LicenseShortName") or {}).get("value"))) if p]
    credit = ", ".join(parts + ["via Wikimedia Commons"]) if parts else "Wikimedia Commons"
    return {"url": url, "credit": credit}
