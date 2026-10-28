import pytest

import net
from sources import wikiImages


@pytest.mark.parametrize("value, expected", [
    ("[[File:Grilled cheese.jpg|300px]]", "Grilled cheese.jpg"),
    ("Image:Toast.png", "Toast.png"),
    ("Toast.png", "Toast.png"),
    ("  ", None),
    (None, None),
])
def test_fileNameStripsLinkSyntax(value, expected):
    assert wikiImages.fileName(value) == expected


def test_imageInfoGivesTheAddressAndACredit(monkeypatch):
    answer = {"query": {"pages": {"5": {"imageinfo": [{
        "url": "https://upload.wikimedia.org/a/Toast.jpg",
        "thumburl": "https://upload.wikimedia.org/thumb/a/Toast.jpg/1280px-Toast.jpg",
        "extmetadata": {"Artist": {"value": "<a href='x'>Jo Baker</a>"},
                        "LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}}}}
    monkeypatch.setattr(net, "getJson", lambda url, params=None, **kw: answer)
    assert wikiImages.imageInfo("Toast.jpg") == {
        "url": "https://upload.wikimedia.org/thumb/a/Toast.jpg/1280px-Toast.jpg",
        "credit": "Jo Baker, CC BY-SA 4.0, via Wikimedia Commons"}


def answerFor(width):
    """The API's answer for a file `width` pixels wide, asked at each width."""
    original = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Toast.jpg"
    def getJson(url, params=None, **kw):
        asked = int(params["iiurlwidth"])
        thumb = original if asked >= width else \
            f"https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Toast.jpg/{asked}px-Toast.jpg"
        return {"query": {"pages": {"5": {"imageinfo": [{
            "url": original, "thumburl": thumb, "width": width, "extmetadata": {}}]}}}}
    return getJson


@pytest.mark.parametrize("width, expected", [
    (4000, "1280px-Toast.jpg"),
    (1280, "960px-Toast.jpg"),
    (900, "500px-Toast.jpg"),
    (331, "330px-Toast.jpg"),
    (21, "20px-Toast.jpg"),
])
def test_aFileIsAskedForAtAWidthWikimediaServes(monkeypatch, width, expected):
    # Wikimedia refuses the original file and any width not on its list.
    monkeypatch.setattr(net, "getJson", answerFor(width))
    url = wikiImages.imageInfo("Toast.jpg")["url"]
    assert url.endswith("/" + expected) and not wikiImages.isOriginal(url)


def test_aFileTooSmallForAnyWidthHasNoPicture(monkeypatch):
    monkeypatch.setattr(net, "getJson", answerFor(20))
    assert wikiImages.imageInfo("Toast.jpg") is None


def test_onlyAThumbnailAddressIsNotAnOriginal():
    assert wikiImages.isOriginal("https://upload.wikimedia.org/wikipedia/commons/a/ab/Toast.jpg")
    assert not wikiImages.isOriginal(
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Toast.jpg/1280px-Toast.jpg?utm_source=x")


def test_aMissingFileHasNoInfo(monkeypatch):
    monkeypatch.setattr(net, "getJson", lambda url, params=None, **kw: {"query": {"pages": {"-1": {"missing": ""}}}})
    assert wikiImages.imageInfo("Nope.jpg") is None
