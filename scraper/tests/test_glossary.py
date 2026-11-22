import json
import sys
from pathlib import Path

import pytest

import config
import glossary
from models import IngredientLine, Recipe, Step

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import glossaryCandidates  # noqa: E402

ENTRIES = [
    {"term": "fold", "forms": ["fold", "folds", "folding", "folded"], "kind": "technique", "text": "x"},
    {"term": "blind bake", "forms": ["blind bake", "blind baked", "blind baking"], "kind": "technique", "text": "x"},
    {"term": "caster sugar", "forms": ["caster sugar"], "kind": "word", "text": "x", "same": "superfine sugar"},
    {"term": "hob", "forms": ["hob"], "kind": "word", "text": "x"},
    {"term": "bake", "forms": ["bake"], "kind": "technique", "text": "never shown: a stop word"},
]


def spans(text):
    return [(text[s:e], term) for s, e, term in glossary.marks(text, ENTRIES)]


def test_wholeWordsOnly():
    assert spans("Unfold the hobnob, then fold.") == [("fold", "fold")]


def test_theLongestFormWins():
    assert spans("Blind bake the case.") == [("Blind bake", "blind bake")]


def test_theFirstOccurrenceOfATermPerText():
    assert spans("Fold in half the flour, then keep folding.") == [("Fold", "fold")]


def test_formsAndCase():
    assert spans("Gently FOLDED with CASTER SUGAR on the hob") == [
        ("FOLDED", "fold"), ("CASTER SUGAR", "caster sugar"), ("hob", "hob")]


def test_theStopListIsNeverMarked():
    assert spans("Bake for 20 minutes.") == []


def test_seedTermsReadPipedForms():
    terms = glossary.seedTerms({"technique": ["fold|folds|folded"], "word": ["hob"]})
    assert terms == [{"term": "fold", "forms": ["fold", "folds", "folded"], "kind": "technique"},
                     {"term": "hob", "forms": ["hob"], "kind": "word"}]


def recipe(key, steps, lines, hidden=None):
    return Recipe(source="site", sourceId=key, kind="food", title=key, steps=[Step(text=s) for s in steps],
                  ingredients=[IngredientLine(line=line, name=line) for line in lines], hiddenReason=hidden)


def test_countsCoverShownRecipesStepsAndLinesOnly():
    recipes = [recipe("a", ["Fold it in, fold again."], ["100 g caster sugar"]),
               recipe("b", ["Put on the hob."], ["caster sugar"]),
               recipe("c", ["Fold the hidden one."], [], hidden="no-photo")]
    counts = glossary.counts(recipes, glossary.seedTerms({"technique": ["fold|folded"], "word": ["caster sugar", "hob", "ramekin"]}))
    assert counts == {"fold": {"recipes": 1, "uses": 1}, "caster sugar": {"recipes": 2, "uses": 2},
                      "hob": {"recipes": 1, "uses": 1}}


def test_gapsAreSeedTermsThatAppearWithNoEntry():
    seed = {"technique": ["fold|folded", "deglaze|deglazed"], "word": ["hob", "ramekin"]}
    recipes = [recipe(str(i), ["Deglaze the pan on the hob, then fold."], []) for i in range(3)]
    recipes.append(recipe("x", ["Butter a ramekin."], []))
    assert glossary.gaps(recipes, seed, ENTRIES, minRecipes=3) == [{"term": "deglaze", "recipes": 3}]


def test_aSeedTermIsCoveredByAnEntrysForms():
    seed = {"technique": ["folded"], "word": []}
    recipes = [recipe(str(i), ["Folded in."], []) for i in range(3)]
    assert glossary.gaps(recipes, seed, ENTRIES, minRecipes=1) == []


def test_aMissingGlossaryFileGivesNone(tmp_path):
    assert glossary.loadEntries(tmp_path / "nope.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert glossary.loadEntries(broken) is None


def test_theCandidateCountPrintsNoRecipeText(tmp_path, capsys, monkeypatch):
    secret = "Zanzibarflump the quorbletted caster sugar on the hob, then fold softly."
    normalised = tmp_path / "normalised.jsonl"
    normalised.write_text("\n".join(json.dumps(r.toDict()) for r in [
        recipe("a", [secret], ["200 g xylophant caster sugar"]),
        recipe("b", [secret], ["1 secretive ramekin"])]) + "\n", encoding="utf-8")
    seedFile = tmp_path / "seed.json"
    seedFile.write_text(json.dumps({"technique": ["fold|folded"], "word": ["caster sugar", "hob", "ramekin"]}),
                        encoding="utf-8")
    monkeypatch.setattr(config, "GLOSSARY_FILE", tmp_path / "glossary.json")
    (tmp_path / "glossary.json").write_text(json.dumps(ENTRIES[:3]), encoding="utf-8")
    assert glossaryCandidates.main(["--normalised", str(normalised), "--seed", str(seedFile)]) == 0
    out = capsys.readouterr().out
    allowed = {"fold", "folded", "caster", "sugar", "hob", "ramekin", "technique", "word", "entry", "new",
               "recipes", "uses", "shown", "seed", "terms", "of", "that", "appear", "with", "no", "kind", "term", "status"}
    for word in out.replace("|", " ").replace(":", " ").replace(",", " ").replace(";", " ").split():
        assert word.isdigit() or word.lower() in allowed, word
    assert "caster sugar" in out and "hob" in out and "ramekin" in out


def test_theSeedLoadsAndHasNoStopWords():
    seed = json.loads((config.RULES_DIR / "glossarySeed.json").read_text(encoding="utf-8"))
    terms = glossary.seedTerms(seed)
    assert set(seed) == {"technique", "word"}
    names = [t["term"] for t in terms]
    assert len(names) == len(set(names))
    for t in terms:
        assert not set(t["forms"]) & glossary.STOP, t["term"]


def test_theGlossaryIsConsistent():
    entries = glossary.loadEntries(config.GLOSSARY_FILE)
    assert entries is not None, "app/assets/glossary.json is missing or broken"
    assert 150 <= len(entries) <= 200
    seen = {}
    for e in entries:
        assert set(e) <= {"term", "forms", "kind", "text", "same"}, e["term"]
        assert e["kind"] in ("technique", "word"), e["term"]
        assert e["term"] in e["forms"], e["term"]
        assert e["text"].strip() and len(e["text"]) <= 280, e["term"]
        for form in e["forms"]:
            assert form == form.lower().strip(), (e["term"], form)
            assert form not in glossary.STOP, (e["term"], form)
            assert seen.setdefault(form, e["term"]) == e["term"], f"{form!r} is in {seen[form]!r} and {e['term']!r}"


def test_theStopListIsTheAppsStopList():
    import re
    source = (config.BASE_DIR.parent / "app" / "qml" / "logic" / "glossary.mjs").read_text(encoding="utf-8")
    block = re.search(r"export const STOP = \[(.*?)\]", source, re.S).group(1)
    assert set(re.findall(r'"([^"]+)"', block)) == glossary.STOP


def test_digitsAndAccentedLettersArePartOfAWord():
    assert spans("hob2 and 2fold") == []
    assert spans("foldé, then fold") == [("fold", "fold")]
    assert spans("İ fold") == [("fold", "fold")]


@pytest.mark.parametrize("text", [
    "Cut in half lengthways.", "Cut in two and serve.", "A knob of ginger, grated.", "100 g unpitted olives",
    "Clarify the stock with egg whites.", "Roast until the skin crisps.", "Shape into a rounded loaf.",
    "Serve in a frosted glass.", "50 ml 100-proof rum", "Add to the salt shaker.", "Char siu pork",
])
def test_theRealGlossaryNeverMarksCommonPhrasesWrongly(text):
    """Everyday phrases that a careless form would explain with the wrong definition."""
    entries = glossary.loadEntries(config.GLOSSARY_FILE)
    wrong = {"cut in the butter", "knob of butter", "pitted", "clarified butter", "packet of crisps", "heaped",
             "frosting", "prove", "cocktail shaker", "charred", "crisps"}
    assert not {term for _, _, term in glossary.marks(text, entries)} & wrong, text
