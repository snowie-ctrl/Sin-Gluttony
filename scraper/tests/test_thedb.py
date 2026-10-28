import config
import net
import store
from sources import thedb


def fakeApi(monkeypatch, answers, calls=None):
    """answers: {(endpoint, (("f", "a"),)): json}. Anything not listed answers null, as the API does for no results."""
    def getJson(url, params=None, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        key = (endpoint, tuple(sorted((params or {}).items())))
        if calls is not None:
            calls.append(key)
        answer = answers.get(key, {"meals": None, "drinks": None})
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(net, "getJson", getJson)


def meal(mealId, name):
    return {"idMeal": mealId, "strMeal": name}


def test_letterSearchGivesFullRecords(monkeypatch):
    fakeApi(monkeypatch, {("search.php", (("f", "a"),)): {"meals": [meal("1", "Apple Pie")]},
                          ("search.php", (("f", "b"),)): {"meals": [meal("2", "Beef Stew")]}})
    assert set(thedb.allRecords(thedb.MEALDB)) == {"1", "2"}


def test_anIdSeenOnlyThroughAFilterIsLookedUp(monkeypatch):
    # The free key may cap a letter search; the category filter still names the id.
    calls = []
    fakeApi(monkeypatch, {
        ("search.php", (("f", "a"),)): {"meals": [meal("1", "Apple Pie")]},
        ("list.php", (("c", "list"),)): {"meals": [{"strCategory": "Dessert"}]},
        ("filter.php", (("c", "Dessert"),)): {"meals": [{"idMeal": "1"}, {"idMeal": "9"}]},
        ("lookup.php", (("i", "9"),)): {"meals": [meal("9", "Apple Crumble")]},
    }, calls)
    records = thedb.allRecords(thedb.MEALDB)
    assert records["9"]["strMeal"] == "Apple Crumble"
    assert ("lookup.php", (("i", "1"),)) not in calls


def test_noneFoundAndNullMeanNothing(monkeypatch):
    fakeApi(monkeypatch, {("search.php", (("f", "q"),)): {"drinks": "None Found"},
                          ("list.php", (("g", "list"),)): {"drinks": None}})
    assert thedb.allRecords(thedb.COCKTAILDB) == {}


def test_rawRecordsAreWrittenAndIdsListed(monkeypatch):
    fakeApi(monkeypatch, {("search.php", (("f", "a"),)): {"meals": [meal("1", "Apple Pie")]}})
    result = thedb.fetchSource(thedb.MEALDB, log=lambda *a: None)
    assert result == {"source": "mealdb", "ok": True, "ids": ["1"], "error": None}
    raw = store.readJson(store.rawPath("mealdb", "1"))
    assert raw["record"]["strMeal"] == "Apple Pie" and raw["sourceId"] == "1"


def test_aFailedFetchKeepsLastPassIdsAndIsNotOk(monkeypatch):
    fakeApi(monkeypatch, {("search.php", (("f", "a"),)): net.HttpError("GET ... failed after 3 attempt(s)")})
    result = thedb.fetchSource(thedb.MEALDB, previous={"ids": ["1", "2"]}, log=lambda *a: None)
    assert result["ok"] is False and result["ids"] == ["1", "2"] and "failed" in result["error"]
    assert not (config.RAW_DIR / "mealdb").exists()
