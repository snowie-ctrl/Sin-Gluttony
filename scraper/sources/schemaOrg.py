"""
Reading schema.org Recipe data out of a page: the JSON-LD block, and helpers
that turn its loosely typed fields (ISO durations, yields as text or lists,
pictures as text, lists or objects) into plain values.
"""
import json
import re

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
