"""
Reading schema.org Recipe data out of a page: the JSON-LD block, and helpers
that turn its loosely typed fields (ISO durations, yields as text or lists,
pictures as text, lists or objects) into plain values.
"""
import html
import json
import re
from urllib.parse import unquote, urlsplit, urlunsplit, parse_qsl, urlencode

from models import Step

_LD = re.compile(r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)


def _isRecipe(node):
    kind = node.get("@type")
    return kind == "Recipe" or (isinstance(kind, list) and "Recipe" in kind)


def _walk(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity"):
            if key in node:
                yield from _walk(node[key])


def recipeJsonLd(html):
    """The page's schema.org Recipe object (from a plain block, a list or a Yoast @graph), or None."""
    for block in _LD.findall(html or ""):
        try:
            data = json.loads(block.strip(), strict=False)
        except ValueError:
            continue
        for node in _walk(data):
            if _isRecipe(node):
                return node
    return None


def hasRecipe(html):
    return recipeJsonLd(html) is not None


_OG_TYPE = re.compile(r"<meta[^>]+(?:property|name)\s*=\s*[\"']og:type[\"']", re.I)


def hasPageMetadata(html):
    """True when a page without a Recipe still carries ordinary page metadata: JSON-LD of another @type, or og:type."""
    if _OG_TYPE.search(html or ""):
        return True
    for block in _LD.findall(html or ""):
        try:
            data = json.loads(block.strip(), strict=False)
        except ValueError:
            continue
        if any("@type" in node for node in _walk(data)):
            return True
    return False


_TAG = re.compile(r"<[^>]+>")
_ISO = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$", re.IGNORECASE)
_AMOUNT = re.compile(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)")
NUTRIENTS = {"calories": "calories", "proteinContent": "proteinG", "carbohydrateContent": "carbsG",
             "fatContent": "fatG", "saturatedFatContent": "satFatG", "fiberContent": "fibreG",
             "sugarContent": "sugarG", "sodiumContent": "sodiumMg"}
SALT_TO_SODIUM_MG = 393     # 1 g of salt holds 393 mg of sodium (BBC Good Food gives salt, not sodium)


def clean(text):
    """Page text as plain words: entities decoded, tags dropped, spaces collapsed."""
    if not isinstance(text, str):
        return ""
    return " ".join(html.unescape(_TAG.sub(" ", html.unescape(text))).split())


def isoMinutes(value):
    """'PT1H30M' -> 90. A bare number counts as minutes. None for nothing, zero or nonsense."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        minutes = round(value)
    else:
        text = str(value).strip()
        if text.isdigit():
            minutes = int(text)
        else:
            match = _ISO.match(text)
            if not match:
                return None
            days, hours, mins, secs = (float(group) if group else 0.0 for group in match.groups())
            minutes = round(days * 1440 + hours * 60 + mins + secs / 60)
    return minutes or None


_SERVES = re.compile(r"\b(?:serves|servings?|portions?|people|persons?|feeds)\b", re.I)
_MAKES = re.compile(r"\b(?:makes|pieces?|cookies?|biscuits?|muffins?|cupcakes?|bars?|squares?|slices?|loaf|loaves|"
                    r"rolls?|buns?|balls?|bites?|pancakes?|scones?|cakes?|pies?|tarts?|jars?|cups?|litres?|ml)\b", re.I)


def _number(text):
    match = re.search(r"\d+", text)
    return int(match.group()) if match and int(match.group()) > 0 else None


def yieldOf(value):
    """(servings, pieces): a value that states servings wins over a count of pieces ("Makes 12"); a bare number
    is servings. pieces is True when the only count given is of pieces, so per serving means per piece."""
    values = value if isinstance(value, list) else [value]
    texts = [str(int(v)) if isinstance(v, (int, float)) else str(v) for v in values if v not in (None, "")]
    for text in texts:
        if _SERVES.search(text) and _number(text):
            return _number(text), False
    for text in texts:
        number = _number(text)
        if number:
            return number, bool(_MAKES.search(text)) and not _SERVES.search(text)
    return None, False


def servingsOf(value):
    """'4 servings', 4 or ['4', '4 servings'] -> 4: the servings given, else the first whole number. None if none."""
    return yieldOf(value)[0]


def imageOf(value):
    """A picture's address from text, a list, or an ImageObject."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for item in value:
            found = imageOf(item)
            if found:
                return found
        return None
    if isinstance(value, dict):
        return imageOf(value.get("url") or value.get("contentUrl"))
    return None


_OG_IMAGE = re.compile(r"<meta\b[^>]*?(?:property|name)\s*=\s*[\"']og:image(?::width)?[\"'][^>]*>", re.I)
_META_CONTENT = re.compile(r"content\s*=\s*[\"']([^\"']*)[\"']", re.I)
_HINTS = (re.compile(r"[?&](?:resize|fit)=(\d+)(?:,|;)\d+", re.I),          # ?resize=900,836  ?fit=225%2C225
          re.compile(r"[?&](?:w|width)=(\d+)", re.I),                         # ?w=1200
          re.compile(r"(?<![\d.])(\d{3,4})x(?:\d{3,4})?(?=[./?]|$)", re.I),    # -1200x800.jpg  /1024x.webp
          re.compile(r"(\d{3,4})px", re.I))                                   # _680px_1.jpg


_ORIGINAL_HOST = "images.immediate.co.uk"
_ORIGINAL_WIDTH = 4000      # nominal: an original is at least as wide as any rendition; images.py measures the real width


def originalPicture(url):
    """An images.immediate.co.uk address without its `resize` parameter (other parameters, such as quality, stay),
    which asks the CDN for the original picture. Other hosts are returned untouched.
    The owner approved this on 2026-11-14: BBC Good Food only offers 440 px renditions on its pages, and the
    completeness gate needs a picture at least 800 px wide."""
    if not url:
        return url
    parts = urlsplit(html.unescape(url))
    if (parts.hostname or "").lower() != _ORIGINAL_HOST or not re.search(r"(?:^|&)resize=", parts.query):
        return url
    kept = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "resize"]
    return urlunsplit(parts._replace(query=urlencode(kept, safe=",")))


def _width(url, stated=None):
    """The width a picture's address or its own markup says; 0 when neither does."""
    if stated:
        try:
            return int(float(stated))
        except (TypeError, ValueError):
            pass
    text = unquote(url)
    for hint in _HINTS:
        found = hint.search(text)
        if found:
            return int(found.group(1))
    return 0


def bestImage(html, recipe):
    """The widest picture the page itself offers: every schema.org image (text, list, ImageObject with a width),
    the og:image with its og:image:width, and size hints in the addresses. The first wins a tie; None for no image.
    The real width is still measured on the downloaded file (images.py), so a wrong hint only costs a worse pick."""
    found = {}      # address -> widest width known for it

    def add(url, stated=None):
        url = (url or "").strip()
        if url:
            original = originalPicture(url)
            if original != url:
                url, stated = original, _ORIGINAL_WIDTH
            found[url] = max(found.get(url, 0), _width(url, stated))

    def walk(value):
        if isinstance(value, str):
            add(value)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            add(value.get("url") or value.get("contentUrl"), value.get("width"))

    walk((recipe or {}).get("image"))
    last = None
    for tag in _OG_IMAGE.findall(html or ""):
        content = _META_CONTENT.search(tag)
        if not content:
            continue
        if re.search(r"og:image:width", tag, re.I):
            if last:
                add(last, content.group(1))
        else:
            last = content.group(1).strip()
            add(last)
    return max(found, key=found.get, default=None)     # max keeps the first of equal widths


def stepsOf(value):
    """recipeInstructions in any of its shapes (text, HowToStep list, HowToSection list) as Steps."""
    steps = []

    def add(node, group):
        if isinstance(node, str):
            for part in re.split(r"[\r\n]+", node):
                text = clean(part)
                if text:
                    steps.append(Step(text=text, group=group))
        elif isinstance(node, list):
            for item in node:
                add(item, group)
        elif isinstance(node, dict):
            if "itemListElement" in node:
                add(node["itemListElement"], clean(node.get("name")) or group)
            elif node.get("text"):
                add(node["text"], group)

    add(value, None)
    return steps


def keywordsOf(value):
    parts = value if isinstance(value, list) else str(value or "").split(",")
    return [clean(part) for part in parts if clean(part)]


def joined(value):
    """A field that may be text or a list (recipeCategory, recipeCuisine) as one text, or None."""
    parts = keywordsOf(value) if isinstance(value, list) else [clean(value)] if value else []
    return ", ".join(part for part in parts if part) or None


def _amount(value):
    """(number, unit) from '1,250 kcal', '6.5g', 300; None when there is no number."""
    match = _AMOUNT.search(str(value))
    if not match:
        return None
    number = match.group(1)
    number = number.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", number) else number.replace(",", ".")
    return float(number), match.group(2).lower()


_KCAL = re.compile(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)\s*(?:kcal|cal(?:ories)?)\b", re.I)
_KJ = re.compile(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)\s*kj\b", re.I)
KJ_PER_KCAL = 4.184


def caloriesOf(value):
    """kcal from a site's calories text: a kcal number wins, a kJ-only number is converted."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "")
    for pattern, divide in ((_KCAL, 1), (_KJ, KJ_PER_KCAL)):
        match = pattern.search(text)
        if match:
            return round(_amount(match.group(1))[0] / divide, 1)
    amount = _amount(text)
    return amount[0] if amount and not amount[1] else None


def nutritionOf(nutrients):
    """A site's per-serving nutrition in Gluttony's eight fields, or None when it gives no calories."""
    if not isinstance(nutrients, dict):
        return None
    found = {field: None for field in NUTRIENTS.values()}
    for key, field in NUTRIENTS.items():
        if field == "calories":
            calories = caloriesOf(nutrients.get(key)) if nutrients.get(key) is not None else None
            found[field] = round(calories, 1) if calories is not None else None
            continue
        amount = _amount(nutrients[key]) if nutrients.get(key) is not None else None
        if amount is None:
            continue
        number, unit = amount
        if field == "sodiumMg" and unit == "g":
            number *= 1000
        found[field] = round(number, 1)
    if found["sodiumMg"] is None and nutrients.get("saltContent") is not None:
        salt = _amount(nutrients["saltContent"])
        if salt is not None:
            found["sodiumMg"] = round(salt[0] * SALT_TO_SODIUM_MG, 1)
    return found if found["calories"] is not None else None
