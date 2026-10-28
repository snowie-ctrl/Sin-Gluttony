import pytest

import net


class FakeStream:
    def __init__(self, status, chunks):
        self.status_code = status
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, size):
        yield from self._chunks


def test_testsCannotReachTheNetwork():
    with pytest.raises(RuntimeError, match="must not touch the network"):
        net.getJson("https://www.themealdb.com/api/json/v1/1/search.php", params={"f": "a"})


def test_downloadLargeStreamsToTheFileAndLeavesNoPart(tmp_path, monkeypatch):
    monkeypatch.setattr(net._session, "get", lambda url, **kw: FakeStream(200, [b"ab", b"cd"]))
    seen = []
    dest = tmp_path / "dump.xml.bz2"
    net.downloadLarge("https://dumps.wikimedia.org/x", dest, onProgress=seen.append)
    assert dest.read_bytes() == b"abcd"
    assert seen == [2, 4]
    assert not (tmp_path / "dump.xml.bz2.part").exists()


def test_downloadLargeGivesUpOnA404WithoutAFile(tmp_path, monkeypatch):
    monkeypatch.setattr(net._session, "get", lambda url, **kw: FakeStream(404, []))
    dest = tmp_path / "dump.xml.bz2"
    with pytest.raises(net.HttpError, match="404"):
        net.downloadLarge("https://dumps.wikimedia.org/x", dest)
    assert not dest.exists()
