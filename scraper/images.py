"""
Recipe pictures, kept on plutus so the app never depends on the sources being
up. Each picture is downloaded once, then a large copy and a thumbnail are
made. Names come from the picture's own address, so a recipe whose picture
changes gets a new name, and no app keeps showing the old one from its cache.
"""
import hashlib

from PIL import Image, UnidentifiedImageError

import config
import net
import store
from sources import wikiImages

LARGE = 1200
THUMB = 400
QUALITY = 85


def imageName(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + ".jpg"


def _indexPath():
    return config.IMAGE_DIR / "index.json"


def _resize(original, dest, size):
    with Image.open(original) as img:
        img.load()
        if img.mode in ("P", "LA", "RGBA"):
            img = img.convert("RGBA")
            # JPEG has no transparency: put the picture on white, as a page would show it.
            flat = Image.new("RGB", img.size, (255, 255, 255))
            flat.paste(img, mask=img.split()[3])
            img = flat
        else:
            img = img.convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG", quality=QUALITY, optimize=True)


def _made(name):
    return (config.IMAGE_DIR / "images" / name).exists() and (config.IMAGE_DIR / "thumbs" / name).exists()


def _source(recipe, index, allowDownload):
    """(address, credit) of a recipe's picture, or None."""
    if recipe.imageUrl is not None:
        return (recipe.imageUrl, recipe.imageCredit) if recipe.imageUrl else None
    fileName = recipe.hints.get("imageFile")
    if not fileName:
        return None
    key = f"file:{fileName}"
    saved = index["files"].get(key)
    # An original's address was saved before Wikimedia began refusing them;
    # one whose picture was never made is asked about again.
    stale = bool(saved and saved.get("url") and wikiImages.isOriginal(saved["url"])
                 and not _made(imageName(saved["url"])))
    if key not in index["files"] or stale:
        if not allowDownload:
            return None
        try:
            # None is remembered too, so a missing file isn't asked about every week.
            index["files"][key] = wikiImages.imageInfo(fileName)
        except net.HttpError:
            return None
    info = index["files"][key]
    return (info["url"], info["credit"]) if info and info["url"] else None


def ensureImages(recipes, allowDownload, log=print, onProgress=None):
    index = store.readJson(_indexPath(), None) or {"files": {}}
    made = failed = 0
    for done, recipe in enumerate(recipes, start=1):
        if onProgress and done % 50 == 0:
            onProgress(done)
        found = _source(recipe, index, allowDownload)
        if not found:
            continue
        url, credit = found
        name = imageName(url)
        large = config.IMAGE_DIR / "images" / name
        thumb = config.IMAGE_DIR / "thumbs" / name
        if not _made(name):
            if not allowDownload:
                continue
            original = config.IMAGE_DIR / "original" / name[:-4]
            if not original.exists() and not net.download(url, original):
                failed += 1
                continue
            try:
                _resize(original, large, LARGE)
                _resize(original, thumb, THUMB)
            except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
                original.unlink(missing_ok=True)
                large.unlink(missing_ok=True)
                failed += 1
                continue
            made += 1
        recipe.imagePath = name
        recipe.imageCredit = credit
    store.writeJson(_indexPath(), index)
    if made or failed:
        log(f"pictures: {made} made, {failed} failed")
    return {"made": made, "failed": failed}
