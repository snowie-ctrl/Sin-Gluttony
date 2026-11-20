import adaptSites
import pagecache
import rulesData
from sources import difford, schemaSite
from conftest import FIXTURES

RULES = rulesData.load()
WPRM = (FIXTURES / "sites" / "schema-wprm.html").read_text(encoding="utf-8")
FOOD = {"site": "testsite", "name": "Test Site", "host": "www.example-recipes.test", "sitemaps": [],
        "recipeUrl": "^https://www\\.example-recipes\\.test/[a-z0-9-]+/$", "parser": "schema", "kind": "food",
        "enabled": True}
DRINK = dict(FOOD, site="testdrinks", parser="difford", kind="drink")


def test_eachSitesParserIsUsed(monkeypatch):
    from models import IngredientLine, Recipe, Step
    calls = []
    def fake(name):
        def parse(html, url, site, *rest):
            calls.append((name, url))
            return Recipe(source=site["site"], sourceId="x", kind=site["kind"], title="Made-up",
                          ingredients=[IngredientLine(line="salt", name="salt")], steps=[Step(text="Mix.")])
        return parse
    monkeypatch.setattr(schemaSite, "extractSchema", fake("schema"))
    monkeypatch.setattr(difford, "extractDifford", fake("difford"))
    adaptSites.adaptPage(FOOD, "https://x.test/a/", "<html>", RULES)
    adaptSites.adaptPage(DRINK, "https://x.test/b/", "<html>", RULES)
    assert calls == [("schema", "https://x.test/a/"), ("difford", "https://x.test/b/")]


def test_everyCachedPageIsReadAndWhatGivesNoRecipeIsRecorded():
    good = "https://www.example-recipes.test/made-up-lemon-test-chicken/"
    bad = "https://www.example-recipes.test/made-up-post/"
    pagecache.save("testsite", good, WPRM, None)
    pagecache.save("testsite", bad, "<html><body>Made-up post</body></html>", None)
    recipes, skipped = adaptSites.adaptCached([FOOD], RULES)
    assert [r.title for r in recipes] == ["Made-up Lemon Test Chicken"]
    assert [(s["site"], s["url"]) for s in skipped] == [("testsite", bad)] and skipped[0]["reason"]


def test_anUnexpectedErrorSkipsOnlyThatPage(monkeypatch):
    pagecache.save("testsite", "https://www.example-recipes.test/a/", "<a>", None)
    pagecache.save("testsite", "https://www.example-recipes.test/b/", WPRM, None)
    real = schemaSite.extractSchema
    def flaky(html, url, site, units):
        if html == "<a>":
            raise KeyError("recipeIngredient")
        return real(html, url, site, units)
    monkeypatch.setattr(schemaSite, "extractSchema", flaky)
    recipes, skipped = adaptSites.adaptCached([FOOD], RULES)
    assert len(recipes) == 1
    assert skipped[0]["reason"] == "could not be read" and "KeyError" in skipped[0]["detail"]


def test_corruptCacheEntriesAreSkippedAndTheRestStillAdapt():
    import gzip, zlib
    import config
    pagecache.save("testsite", "https://www.example-recipes.test/good/", WPRM, None)
    folder = config.RAW_DIR / "testsite"
    # a gzip whose deflate stream is damaged raises zlib.error, not OSError
    pagecache.save("testsite", "https://www.example-recipes.test/zbad/", "<html>made-up</html>", None)
    page, _ = pagecache._paths("testsite", "https://www.example-recipes.test/zbad/")
    raw = bytearray(gzip.compress(b"made-up " * 500))
    raw[12:20] = b"\xff" * 8
    page.write_bytes(bytes(raw))
    (folder / "listy.json").write_text('["not", "an", "object"]', encoding="utf-8")
    recipes, skipped = adaptSites.adaptCached([FOOD], RULES)
    assert [r.title for r in recipes] == ["Made-up Lemon Test Chicken"]


def test_aFoodSitesDrinkPageIsReadAsADrinkWithItsCourse(monkeypatch):
    from models import IngredientLine, Recipe, Step
    def page(html, url, site, units):
        return Recipe(source=site["site"], sourceId="x", kind=site["kind"], title="Made-up mango lassi",
                      ingredients=[IngredientLine(line="1 mango", name="mango")], steps=[Step(text="Blend.")],
                      hints={"category": "Drink"})
    monkeypatch.setattr(schemaSite, "extractSchema", page)
    recipe = adaptSites.adaptPage(FOOD, "https://x.test/a/", "<html>", RULES)
    assert (recipe.kind, recipe.hints["course"]) == ("drink", "shake")


def test_aFoodPageGetsItsCourseHint(monkeypatch):
    from models import IngredientLine, Recipe, Step
    def page(html, url, site, units):
        return Recipe(source=site["site"], sourceId="x", kind=site["kind"], title="Made-up slaw",
                      ingredients=[IngredientLine(line="1 cabbage", name="cabbage")], steps=[Step(text="Shred.")],
                      hints={"category": "Dinner, Side dish"})
    monkeypatch.setattr(schemaSite, "extractSchema", page)
    recipe = adaptSites.adaptPage(FOOD, "https://x.test/a/", "<html>", RULES)
    assert (recipe.kind, recipe.hints["course"]) == ("food", "side")
