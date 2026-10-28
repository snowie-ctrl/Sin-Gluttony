import shutil

from PIL import Image

import config
import images
import net
import store
from models import IngredientLine, Recipe, Step
from sources import wikiImages


def recipe(**fields):
    base = dict(source="mealdb", sourceId="1", kind="food", title="x",
                ingredients=[IngredientLine(line="salt", name="salt")], steps=[Step(text="Cook.")])
    base.update(fields)
    return Recipe(**base)


def fakeDownloads(monkeypatch, tmp_path, mode="RGB", size=(2400, 1600)):
    picture = tmp_path / "picture.png"
    Image.new(mode, size, (200, 100, 50, 128) if mode == "RGBA" else (200, 100, 50)).save(picture)
    calls = []
    def download(url, dest, timeout=30):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(picture, dest)
        return True
    monkeypatch.setattr(net, "download", download)
    return calls


def test_aPictureIsDownloadedOnceAndResized(monkeypatch, tmp_path):
    calls = fakeDownloads(monkeypatch, tmp_path)
    r = recipe(imageUrl="https://www.themealdb.com/images/a.jpg", imageCredit="TheMealDB")
    assert images.ensureImages([r], allowDownload=True, log=lambda *a: None) == {"made": 1, "failed": 0}
    name = images.imageName("https://www.themealdb.com/images/a.jpg")
    assert r.imagePath == name and r.imageCredit == "TheMealDB"
    with Image.open(config.IMAGE_DIR / "images" / name) as large, Image.open(config.IMAGE_DIR / "thumbs" / name) as thumb:
        assert large.size == (1200, 800) and thumb.size == (400, 267) and large.format == "JPEG"
    again = recipe(imageUrl="https://www.themealdb.com/images/a.jpg", imageCredit="TheMealDB")
    images.ensureImages([again], allowDownload=True, log=lambda *a: None)
    assert calls == ["https://www.themealdb.com/images/a.jpg"] and again.imagePath == name


def test_aTransparentPictureBecomesAJpeg(monkeypatch, tmp_path):
    fakeDownloads(monkeypatch, tmp_path, mode="RGBA", size=(300, 300))
    r = recipe(imageUrl="https://x/b.png")
    images.ensureImages([r], allowDownload=True, log=lambda *a: None)
    assert r.imagePath is not None


def test_withoutDownloadsOnlyReadyPicturesAreUsed(monkeypatch, tmp_path):
    calls = fakeDownloads(monkeypatch, tmp_path)
    r = recipe(imageUrl="https://x/new.jpg")
    images.ensureImages([r], allowDownload=False, log=lambda *a: None)
    assert r.imagePath is None and calls == []


def test_aBrokenFileGivesNoPicture(monkeypatch):
    def download(url, dest, timeout=30):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"not a picture")
        return True
    monkeypatch.setattr(net, "download", download)
    r = recipe(imageUrl="https://x/broken.jpg")
    assert images.ensureImages([r], allowDownload=True, log=lambda *a: None) == {"made": 0, "failed": 1}
    assert r.imagePath is None


def test_aPictureWithoutAnAddressIsSkipped(monkeypatch, tmp_path):
    calls = fakeDownloads(monkeypatch, tmp_path)
    monkeypatch.setattr(wikiImages, "imageInfo", lambda name: {"url": None, "credit": "x"})
    blankUrl = recipe(imageUrl="")
    noAddress = recipe(source="wikibooks", sourceId="2", hints={"imageFile": "Gone.jpg"})
    assert images.ensureImages([blankUrl, noAddress], allowDownload=True, log=lambda *a: None) == {"made": 0, "failed": 0}
    assert blankUrl.imagePath is None and noAddress.imagePath is None and calls == []


def test_aDecompressionBombGivesNoPicture(monkeypatch, tmp_path):
    fakeDownloads(monkeypatch, tmp_path)
    def resize(original, dest, size):
        raise Image.DecompressionBombError("too big")
    monkeypatch.setattr(images, "_resize", resize)
    r = recipe(imageUrl="https://x/bomb.jpg")
    assert images.ensureImages([r], allowDownload=True, log=lambda *a: None) == {"made": 0, "failed": 1}
    assert r.imagePath is None
    assert not (config.IMAGE_DIR / "original" / images.imageName("https://x/bomb.jpg")[:-4]).exists()


def test_aWikibooksFileIsLookedUpOnceEvenWhenMissing(monkeypatch, tmp_path):
    fakeDownloads(monkeypatch, tmp_path)
    asked = []
    def imageInfo(name):
        asked.append(name)
        return {"url": "https://upload.wikimedia.org/t.jpg", "credit": "Jo, CC BY-SA 4.0, via Wikimedia Commons"} \
            if name == "Toast.jpg" else None
    monkeypatch.setattr(wikiImages, "imageInfo", imageInfo)
    found = recipe(source="wikibooks", hints={"imageFile": "Toast.jpg"})
    missing = recipe(source="wikibooks", sourceId="2", hints={"imageFile": "Nope.jpg"})
    images.ensureImages([found, missing], allowDownload=True, log=lambda *a: None)
    images.ensureImages([recipe(source="wikibooks", sourceId="3", hints={"imageFile": "Nope.jpg"})],
                        allowDownload=True, log=lambda *a: None)
    assert found.imageCredit.startswith("Jo") and missing.imagePath is None
    assert asked == ["Toast.jpg", "Nope.jpg"]


def test_aSavedOriginalAddressIsAskedAgainUntilItsPictureIsMade(monkeypatch, tmp_path):
    calls = fakeDownloads(monkeypatch, tmp_path)
    original = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Old.jpg"
    made = "https://upload.wikimedia.org/wikipedia/commons/c/cd/Kept.jpg"
    thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Old.jpg/500px-Old.jpg"
    store.writeJson(config.IMAGE_DIR / "index.json", {"files": {
        "file:Old.jpg": {"url": original, "credit": "Jo"},
        "file:Kept.jpg": {"url": made, "credit": "Al"}}})
    for folder in ("images", "thumbs"):
        (config.IMAGE_DIR / folder).mkdir(parents=True, exist_ok=True)
        (config.IMAGE_DIR / folder / images.imageName(made)).write_bytes(b"x")
    asked = []
    def imageInfo(name):
        asked.append(name)
        return {"url": thumb, "credit": "Jo"}
    monkeypatch.setattr(wikiImages, "imageInfo", imageInfo)
    old = recipe(source="wikibooks", hints={"imageFile": "Old.jpg"})
    kept = recipe(source="wikibooks", sourceId="2", hints={"imageFile": "Kept.jpg"})
    images.ensureImages([old, kept], allowDownload=False, log=lambda *a: None)
    assert asked == []
    images.ensureImages([old, kept], allowDownload=True, log=lambda *a: None)
    assert asked == ["Old.jpg"] and calls == [thumb]
    assert old.imagePath == images.imageName(thumb) and kept.imagePath == images.imageName(made)


def test_progressIsReportedEveryFiftyRecipes():
    seen = []
    images.ensureImages([recipe(sourceId=str(n)) for n in range(120)], allowDownload=False,
                        log=lambda *a: None, onProgress=seen.append)
    assert seen == [50, 100]
