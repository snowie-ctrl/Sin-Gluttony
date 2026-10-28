from conftest import REAL_SESSION_UID


def test_everyReadRouteNeedsASession(anonReadClient):
    for path in ("/recipes", "/recipes/7", "/filters", "/ingredients?q=ch", "/images/7", "/thumbs/7"):
        answer = anonReadClient.get(f"/api/gluttony{path}")
        assert answer.status_code == 401, path
        assert answer.get_json() == {"status": "error", "message": "not signed in"}


def test_pingNeedsNoSessionAndNoDatabase(anonReadClient):
    # isolated() refuses every connection, so this also proves ping opens none.
    assert anonReadClient.get("/api/gluttony/ping").get_json() == {"status": "ok"}


def test_aTunnelRequestWithASessionIsAnswered(tunnelClient, useDb):
    useDb(fetchall=[[{"IngredientID": 1, "Name": "cheese"}]])
    assert tunnelClient.get("/api/gluttony/ingredients?q=che").status_code == 200


def test_aTunnelRequestWithoutASessionIs401(anonReadClient):
    anonReadClient.environ_base["HTTP_CF_CONNECTING_IP"] = "203.0.113.9"
    assert anonReadClient.get("/api/gluttony/filters").status_code == 401


def test_aSessionIsLookedUpByTokenAndExpiry(useDb):
    conn = useDb(fetchone=[{"UserID": 7}])
    assert REAL_SESSION_UID("abc") == 7
    sql, params = conn.cur.executed[0]
    assert sql == "SELECT UserID FROM Sessions WHERE Token = %s AND ExpiresAt > NOW()" and params == ("abc",)
    assert conn.closed


def test_aMissingTokenNeedsNoDatabase():
    assert REAL_SESSION_UID("") is None and REAL_SESSION_UID(None) is None


def test_theRateLimiterRefusesPastTheLimitUntilTheWindowMoves(sessions):
    clock = [0.0]
    limiter = sessions.RateLimiter(clock=lambda: clock[0])
    assert all(limiter.allow("k", 3, 60) for _ in range(3))
    assert not limiter.allow("k", 3, 60)
    clock[0] = 61.0
    assert limiter.allow("k", 3, 60)


def test_ipv6CallersAreCountedByTheirSlash64(sessions):
    assert sessions.limiterKey("2001:db8::1") == sessions.limiterKey("2001:db8::ffff") == "2001:db8::/64"
    assert sessions.limiterKey("203.0.113.9") == "203.0.113.9"


def test_aServerErrorThroughTheTunnelSaysNothingInside(tunnelClient, useDb):
    useDb(failOn="FROM Ingredients")
    answer = tunnelClient.get("/api/gluttony/ingredients?q=che")
    assert answer.status_code == 500
    assert answer.get_json() == {"status": "error", "message": "server error"}


def test_aServerErrorAtHomeKeepsItsDetail(readClient, useDb):
    useDb(failOn="FROM Ingredients")
    answer = readClient.get("/api/gluttony/ingredients?q=che")
    assert answer.status_code == 500 and "RuntimeError" in answer.get_json()["message"]


def test_theProfileIsReadInOneQuery(sessions, useDb):
    conn = useDb(fetchall=[[{"Kind": "diet", "Value": "vegetarian"}, {"Kind": "avoid", "Value": "peanut"},
                            {"Kind": "avoid", "Value": "sesame"}]])
    with sessions.database() as (_, cur):
        assert sessions.profileOf(cur, 7) == (["vegetarian"], ["peanut", "sesame"])
    sql, params = conn.cur.executed[0]
    assert "FROM UserDiets WHERE UserID = %s" in sql and "FROM UserAvoids WHERE UserID = %s" in sql
    assert params == (7, 7)
