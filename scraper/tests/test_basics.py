import basics
from models import Recipe

A, B, C = "https://x.test/a/", "https://x.test/b/", "https://x.test/c/"
RULES = {"basics": [{"name": "eggs", "url": A, "urls": [A, B, C]}, {"name": "toast", "url": None, "urls": []},
                    {"name": "old", "url": "https://x.test/old/"}]}


def made(url, hidden=None):
    return Recipe(source="testsite", sourceId=url[-3:], kind="food", title=url, ingredients=[], steps=[],
                  sourceUrl=url, hiddenReason=hidden, tags=[])


def tagged(recipe):
    return [t for t in recipe.tags if t["tag"] == "basic"]


def test_priorityUrlsHoldEveryCandidateAndTheOlderSingleUrl():
    assert basics.priorityUrls(RULES) == {A, B, C, "https://x.test/old/"}


def test_theFirstCandidateThatPassesWinsAndOnlyItIsTagged():
    recipes = [made(A, "small-photo"), made(B), made(C)]
    row = basics.resolve(RULES, recipes)[0]
    assert (row["url"], row["candidate"], row["status"]) == (B, 2, "listed via candidate 2")
    basics.applyTags(recipes, RULES)
    assert [bool(tagged(r)) for r in recipes] == [False, True, False]


def test_aFirstCandidateThatPassesIsListedPlain():
    row = basics.resolve(RULES, [made(A), made(B)])[0]
    assert (row["url"], row["status"]) == (A, "listed")


def test_whenNoneArePassingTheFirstReasonShowsAndNothingIsTagged():
    recipes = [made(A, "small-photo"), made(B, "no-time")]
    row = basics.resolve(RULES, recipes)[0]
    assert (row["url"], row["status"], row["candidate"]) == (A, "hidden: small-photo", None)
    basics.applyTags(recipes, RULES)
    assert not any(tagged(r) for r in recipes)


def test_aBasicWithNoCandidatesIsMissing():
    row = basics.resolve(RULES, [])[1]
    assert (row["url"], row["status"]) == (None, "missing: no site has it")


def test_aSecondCandidateNotFetchedStillLeavesTheFirstReason():
    state = {"testsite": {"notRecipe": {A: "2026-11-14"}}}
    assert basics.resolve(RULES, [], [], state)[0]["status"] == "not a recipe page"
    assert basics.resolve(RULES, [], [], None)[0]["status"] == "not fetched"
