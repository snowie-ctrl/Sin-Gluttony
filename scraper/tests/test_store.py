import config
import store


def test_jsonRoundTripsAndLeavesNoTemporaryFile(tmp_path):
    path = tmp_path / "a" / "b.json"
    store.writeJson(path, {"title": "Crème brûlée", "n": 2})
    assert store.readJson(path) == {"title": "Crème brûlée", "n": 2}
    assert [p.name for p in path.parent.iterdir()] == ["b.json"]


def test_aMissingOrBrokenFileGivesTheDefault(tmp_path):
    assert store.readJson(tmp_path / "missing.json", {"x": 1}) == {"x": 1}
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert store.readJson(broken) is None


def test_rawPathKeepsPlainIdsAndHashesTitles():
    assert store.rawPath("mealdb", "52772") == config.RAW_DIR / "mealdb" / "52772.json"
    hashed = store.rawPath("wikibooks", "Cookbook:Grilled Cheese/Sandwich")
    assert hashed.parent == config.RAW_DIR / "wikibooks"
    assert hashed.name == store.safeName("Cookbook:Grilled Cheese/Sandwich") + ".json"


def test_writeLinesWritesOneObjectPerLine(tmp_path):
    path = tmp_path / "x.jsonl"
    store.writeLines(path, [{"a": 1}, {"b": 2}])
    assert path.read_text(encoding="utf-8").splitlines() == ['{"a": 1}', '{"b": 2}']
