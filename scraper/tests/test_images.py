import shutil

from PIL import Image

import config
import images
import net
import store
from models import IngredientLine, Recipe, Step


def recipe(**fields):
    base = dict(source="madeupsite", sourceId="1", kind="food", title="x",
                ingredients=[IngredientLine(line="salt", name="salt")], steps=[Step(text="Cook.")])
    base.update(fields)
    return Recipe(**base)


def fakeDownloads(monkeypatch, tmp_path, mode="RGB", size=(2400, 1600)):
    picture = tmp_path / "picture.png"
    Image.new(mode, size, (200, 100, 50, 128) if mode == "RGBA" else (200, 100, 50)).save(picture)
    calls = []
    def download(url, dest, timeout=30, refusals=False):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(picture, dest)
        return True
    monkeypatch.setattr(net, "download", download)
    return calls


def test_aPictureIsDownloadedOnceAndResized(monkeypatch, tmp_path):
    calls = fakeDownloads(monkeypatch, tmp_path)
    r = recipe(imageUrl="https://www.example-recipes.test/a.jpg", imageCredit="Made-up Site")
    assert images.ensureImages([r], allowDownload=True, log=lambda *a: None) == {"made": 1, "failed": 0, "pictureStops": {}}
    name = images.imageName("https://www.example-recipes.test/a.jpg")
    assert r.imagePath == name and r.imageCredit == "Made-up Site"
    with Image.open(config.IMAGE_DIR / "images" / name) as large, Image.open(config.IMAGE_DIR / "thumbs" / name) as thumb:
        assert large.size == (1200, 800) and thumb.size == (400, 267) and large.format == "JPEG"
    again = recipe(imageUrl="https://www.example-recipes.test/a.jpg", imageCredit="Made-up Site")
    images.ensureImages([again], allowDownload=True, log=lambda *a: None)
    assert calls == ["https://www.example-recipes.test/a.jpg"] and again.imagePath == name


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
    def download(url, dest, timeout=30, refusals=False):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"not a picture")
        return True
    monkeypatch.setattr(net, "download", download)
    r = recipe(imageUrl="https://x/broken.jpg")
    assert images.ensureImages([r], allowDownload=True, log=lambda *a: None) == {"made": 0, "failed": 1, "pictureStops": {}}
    assert r.imagePath is None


def test_aPictureWithoutAnAddressIsSkipped(monkeypatch, tmp_path):
    calls = fakeDownloads(monkeypatch, tmp_path)
    blankUrl = recipe(imageUrl="")
    noAddress = recipe(sourceId="2", imageUrl=None)
    assert images.ensureImages([blankUrl, noAddress], allowDownload=True, log=lambda *a: None) == {"made": 0, "failed": 0, "pictureStops": {}}
    assert blankUrl.imagePath is None and noAddress.imagePath is None and calls == []


def test_aDecompressionBombGivesNoPicture(monkeypatch, tmp_path):
    fakeDownloads(monkeypatch, tmp_path)
    def resize(original, dest, size):
        raise Image.DecompressionBombError("too big")
    monkeypatch.setattr(images, "_resize", resize)
    r = recipe(imageUrl="https://x/bomb.jpg")
    assert images.ensureImages([r], allowDownload=True, log=lambda *a: None) == {"made": 0, "failed": 1, "pictureStops": {}}
    assert r.imagePath is None
    assert not (config.IMAGE_DIR / "original" / images.imageName("https://x/bomb.jpg")[:-4]).exists()


def test_anOlderIndexsOtherEntriesAreWrittenBackUntouched(monkeypatch, tmp_path):
    fakeDownloads(monkeypatch, tmp_path)
    older = {"file:Made-up.jpg": {"url": "https://pictures.example.test/made-up.jpg", "credit": "Jo"}}
    store.writeJson(config.IMAGE_DIR / "index.json", {"files": older})
    r = recipe(imageUrl="https://www.example-recipes.test/new.jpg")
    images.ensureImages([r], allowDownload=True, log=lambda *a: None)
    index = store.readJson(config.IMAGE_DIR / "index.json")
    assert index["files"] == older and index["widths"] == {r.imagePath: 2400}


def test_progressIsReportedEveryFiftyRecipes():
    seen = []
    images.ensureImages([recipe(sourceId=str(n)) for n in range(120)], allowDownload=False,
                        log=lambda *a: None, onProgress=seen.append)
    assert seen == [50, 100]


def test_theOriginalWidthIsRecorded(monkeypatch, tmp_path):
    calls = fakeDownloads(monkeypatch, tmp_path, size=(2400, 1600))
    r = recipe(imageUrl="https://www.example-recipes.test/made-up.jpg")
    images.ensureImages([r], allowDownload=True, log=lambda *a: None)
    assert r.imageWidth == 2400
    again = recipe(imageUrl="https://www.example-recipes.test/made-up.jpg")
    images.ensureImages([again], allowDownload=False, log=lambda *a: None)
    assert again.imageWidth == 2400 and len(calls) == 1


def test_aSmallPictureKeepsItsSmallWidth(monkeypatch, tmp_path):
    fakeDownloads(monkeypatch, tmp_path, size=(600, 400))
    r = recipe(imageUrl="https://www.example-recipes.test/small.jpg")
    images.ensureImages([r], allowDownload=True, log=lambda *a: None)
    assert r.imageWidth == 600


def test_aPictureMadeBeforeWidthsWereKeptIsMeasured(monkeypatch, tmp_path):
    fakeDownloads(monkeypatch, tmp_path, size=(1000, 700))
    images.ensureImages([recipe(imageUrl="https://x.test/old.jpg")], allowDownload=True, log=lambda *a: None)
    index = store.readJson(config.IMAGE_DIR / "index.json")
    del index["widths"]
    store.writeJson(config.IMAGE_DIR / "index.json", index)
    r = recipe(imageUrl="https://x.test/old.jpg")
    images.ensureImages([r], allowDownload=False, log=lambda *a: None)
    assert r.imageWidth == 1000


def _refusing(monkeypatch, tmp_path, status, refuseSource="budgetbytes"):
    fakeDownloads(monkeypatch, tmp_path)
    attempts = []
    def download(url, dest, timeout=30, refusals=False):
        attempts.append(url)
        if "bb" in url and status:
            raise net.HttpError("refused", status=status)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(tmp_path / "picture.png", dest)
        return True
    monkeypatch.setattr(net, "download", download)
    recipes = [recipe(source="budgetbytes", sourceId=str(i), imageUrl=f"https://bb/{i}.jpg") for i in range(3)]
    recipes.append(recipe(source="difford", sourceId="d", imageUrl="https://df/d.jpg"))
    return recipes, attempts


def test_a403OnAPictureStopsThatSitesDownloads(monkeypatch, tmp_path):
    recipes, attempts = _refusing(monkeypatch, tmp_path, 403)
    result = images.ensureImages(recipes, allowDownload=True, log=lambda *a: None)
    assert [u for u in attempts if "bb" in u] == ["https://bb/0.jpg"]
    assert "https://df/d.jpg" in attempts
    assert result["pictureStops"] == {"budgetbytes": "pictures blocked (403)"}
    assert recipes[3].imagePath is not None and recipes[0].imagePath is None


def test_a429GivesARateLimitStop(monkeypatch, tmp_path):
    recipes, attempts = _refusing(monkeypatch, tmp_path, 429)
    result = images.ensureImages(recipes, allowDownload=True, log=lambda *a: None)
    assert result["pictureStops"] == {"budgetbytes": "pictures rate limited (429)"}


def test_a404IsNotAStop(monkeypatch, tmp_path):
    recipes, attempts = _refusing(monkeypatch, tmp_path, 404)
    result = images.ensureImages(recipes, allowDownload=True, log=lambda *a: None)
    assert result["pictureStops"] == {}
    assert len([u for u in attempts if "bb" in u]) == 3 and result["failed"] == 3


def test_aStoppedSiteKeepsPicturesAlreadyMade(monkeypatch, tmp_path):
    recipes, attempts = _refusing(monkeypatch, tmp_path, 0)
    images.ensureImages(recipes, allowDownload=True, log=lambda *a: None)
    again, attempts2 = _refusing(monkeypatch, tmp_path, 403)
    again.append(recipe(source="budgetbytes", sourceId="new", imageUrl="https://bb/new.jpg"))
    result = images.ensureImages(again, allowDownload=True, log=lambda *a: None)
    assert all(r.imagePath for r in again[:4])
    assert [u for u in attempts2 if "bb" in u] == ["https://bb/new.jpg"]
    assert result["pictureStops"] == {"budgetbytes": "pictures blocked (403)"}


def test_everyPictureDownloadAsksForRefusals(monkeypatch, tmp_path):
    fakeDownloads(monkeypatch, tmp_path)
    seen = {}
    def download(url, dest, timeout=30, **kw):
        seen[url] = kw
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(tmp_path / "picture.png", dest)
        return True
    monkeypatch.setattr(net, "download", download)
    rs = [recipe(source="budgetbytes", imageUrl="https://bb/1.jpg"),
          recipe(source="difford", imageUrl="https://df/1.jpg")]
    images.ensureImages(rs, allowDownload=True, log=lambda *a: None)
    assert seen == {"https://bb/1.jpg": {"refusals": True}, "https://df/1.jpg": {"refusals": True}}
