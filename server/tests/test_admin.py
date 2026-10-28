import samples


def post(client, path, body):
    return client.post(f"/api/gluttony-admin{path}", json=body)


def test_everyRouteNeedsTheToken(anonClient):
    assert anonClient.get("/api/gluttony-admin/state").status_code == 401


def test_aBatchStoresARecipeWithItsChildren(client, useDb):
    conn = useDb(lastrowids={"Recipes": [31]})
    answer = post(client, "/recipes/batch", {"recipes": [samples.recipe()]})
    assert answer.status_code == 200
    assert answer.get_json() == {"status": "ok", "stored": ["mealdb:1"], "failed": []}
    insert = conn.cur.statements("INSERT INTO Recipes")[0]
    assert "ON DUPLICATE KEY UPDATE RecipeID = LAST_INSERT_ID(RecipeID)" in insert[0]
    assert insert[1][:3] == ("mealdb", "1", "food")
    assert conn.cur.statements("INSERT INTO RecipeIngredients")[0][1] == \
        (31, 1, "2 slices bread", 2, None, "slice", 1, None, None, 0, None)
    assert conn.cur.statements("INSERT INTO RecipeFacts") == [("INSERT INTO RecipeFacts (RecipeID, Complete) VALUES (%s, %s)", (31, 1))]
    assert [p for _, p in conn.cur.statements("INSERT INTO RecipeContains")] == [(31, "dairy"), (31, "gluten")]
    assert [p for _, p in conn.cur.statements("INSERT INTO RecipeDiets")] == [(31, "vegetarian")]
    assert conn.commits == 1


def test_resendingReplacesChildrenAndClearsRemoved(client, useDb):
    conn = useDb(lastrowids={"Recipes": [31]})
    changed = samples.recipe(imagePath=None, ingredients=samples.recipe()["ingredients"][:1])
    post(client, "/recipes/batch", {"recipes": [changed]})
    sqls = [sql for sql, _ in conn.cur.executed]
    assert "RemovedAt = NULL" in sqls[0]
    for table in ("RecipeIngredients", "RecipeSteps", "RecipeTags", "RecipeFacts", "RecipeContains", "RecipeDiets"):
        delete = sqls.index(f"DELETE FROM {table} WHERE RecipeID = %s")
        inserts = [n for n, sql in enumerate(sqls) if sql.startswith(f"INSERT INTO {table} ")]
        assert all(delete < n for n in inserts), table
    assert len(conn.cur.statements("INSERT INTO RecipeIngredients")) == 1


def test_aBadRecipeIsReportedAndTheRestStored(client, useDb):
    useDb(lastrowids={"Recipes": [31]})
    answer = post(client, "/recipes/batch", {"recipes": [samples.recipe(), samples.recipe("2", kind="soup")]}).get_json()
    assert answer["stored"] == ["mealdb:1"]
    assert answer["failed"][0]["key"] == "mealdb:2" and "kind" in answer["failed"][0]["message"]


def test_aDatabaseFailureRollsBackOnlyThatRecipe(client, useDb):
    conn = useDb(lastrowids={"Recipes": [31, 32]},
                 failOn=lambda sql, params: sql.startswith("INSERT INTO RecipeSteps") and params[0] == 32)
    answer = post(client, "/recipes/batch", {"recipes": [samples.recipe("1"), samples.recipe("2")]}).get_json()
    assert answer["stored"] == ["mealdb:1"]
    assert answer["failed"] == [{"key": "mealdb:2", "message": "database write failed: RuntimeError"}]
    assert conn.commits == 1 and conn.rollbacks >= 1


def test_anEmptyBatchIsRefused(client, useDb):
    useDb()
    assert post(client, "/recipes/batch", {"recipes": []}).status_code == 400


def test_removedMarksOnlyRecipesStillShown(client, useDb):
    conn = useDb(rowcounts=[1, 0])
    answer = post(client, "/recipes/removed", {"keys": ["mealdb:1", "wikibooks:Cookbook:A:B"]}).get_json()
    assert answer == {"status": "ok", "removed": 1}
    assert [p for _, p in conn.cur.statements("UPDATE Recipes")] == [("mealdb", "1"), ("wikibooks", "Cookbook:A:B")]
    assert "RemovedAt IS NULL" in conn.cur.statements("UPDATE Recipes")[0][0] and conn.commits == 1


def test_stateListsEveryShownRecipesHash(client, useDb):
    useDb(fetchall=[[{"Source": "mealdb", "SourceID": "1", "ContentHash": "a" * 40}]])
    assert client.get("/api/gluttony-admin/state").get_json() == \
        {"status": "ok", "recipes": [{"key": "mealdb:1", "hash": "a" * 40}]}


def test_ingredientsGivesTheWholeTable(client, useDb):
    useDb(fetchall=[[{"IngredientID": 1, "Name": "cheese", "ParentID": None, "Category": "dairy", "Origin": "seed"},
                     {"IngredientID": 2, "Name": "cheddar", "ParentID": 1, "Category": None, "Origin": "owner"}],
                    [{"IngredientID": 1, "Item": "dairy"}],
                    [{"Alias": "cheese", "IngredientID": 1}, {"Alias": "cheddar", "IngredientID": 2}]])
    answer = client.get("/api/gluttony-admin/ingredients").get_json()
    assert answer["ingredients"] == [
        {"id": 1, "name": "cheese", "parentId": None, "category": "dairy", "origin": "seed", "contains": ["dairy"]},
        {"id": 2, "name": "cheddar", "parentId": 1, "category": None, "origin": "owner", "contains": []}]
    assert answer["aliases"] == [{"alias": "cheese", "ingredientId": 1}, {"alias": "cheddar", "ingredientId": 2}]


def test_theSeedNeverChangesTheOwnersRows(client, useDb):
    conn = useDb(fetchone=[None, {"IngredientID": 5, "Origin": "seed"}, {"IngredientID": 9, "Origin": "owner"}],
                 lastrowids={"Ingredients": [4]})
    seed = [{"name": "cheese", "parent": None, "category": "dairy", "contains": ["dairy"], "aliases": ["cheese"]},
            {"name": "cheddar", "parent": "cheese", "category": None, "contains": [], "aliases": ["cheddar"]},
            {"name": "salt", "parent": None, "category": "spice", "contains": [], "aliases": ["salt"]}]
    answer = post(client, "/ingredients/seed", {"ingredients": seed}).get_json()
    assert answer == {"status": "ok", "added": 1, "updated": 1, "kept": 1}
    assert [p for _, p in conn.cur.statements("UPDATE Ingredients SET ParentID")] == [(None, 4), (4, 5)]
    aliasSql, aliasParams = conn.cur.statements("INSERT INTO IngredientAliases")[0]
    assert "IF(Origin = 'seed', VALUES(IngredientID), IngredientID)" in aliasSql and aliasParams == ("cheese", 4)
    writes = [params for sql, params in conn.cur.executed if sql.startswith(("UPDATE", "DELETE", "INSERT"))]
    assert not any(9 in params for params in writes)          # the owner's salt is never touched
    assert conn.commits == 1


def test_unknownIngredientsAreRankedByRecipes(client, useDb):
    useDb(fetchall=[[{"name": "dragon fruit", "recipes": 3, "example": "1 dragon fruit"}]], fetchone=[{"n": 1}])
    answer = client.get("/api/gluttony-admin/ingredients/unknown?limit=5").get_json()
    assert answer == {"status": "ok", "unknown": [{"name": "dragon fruit", "recipes": 3, "example": "1 dragon fruit"}],
                      "total": 1}


def test_unknownRefusesABadLimit(client, useDb):
    useDb()
    assert client.get("/api/gluttony-admin/ingredients/unknown?limit=lots").status_code == 400


def test_mapToAnExistingIngredient(client, useDb):
    conn = useDb(fetchone=[{"IngredientID": 5}])
    assert post(client, "/ingredients/map", {"alias": "dragon fruit", "ingredientId": 5}).get_json() == \
        {"status": "ok", "ingredientId": 5}
    sql, params = conn.cur.statements("INSERT INTO IngredientAliases")[0]
    assert params == ("dragon fruit", 5) and "Origin = 'owner'" in sql and conn.commits == 1


def test_mapToAMissingIngredientIs404(client, useDb):
    conn = useDb(fetchone=[None])
    assert post(client, "/ingredients/map", {"alias": "x", "ingredientId": 5}).status_code == 404
    assert conn.commits == 0


def test_mapByCreatingAnIngredient(client, useDb):
    conn = useDb(fetchone=[None, {"IngredientID": 3}], lastrowids={"Ingredients": [40]})
    body = {"alias": "dragon fruit", "create": {"name": "Dragon fruit", "parentId": 3, "category": "fruit",
                                               "contains": []}}
    assert post(client, "/ingredients/map", body).get_json() == {"status": "ok", "ingredientId": 40}
    assert conn.cur.statements("INSERT INTO Ingredients")[0][1] == ("Dragon fruit", 3, "fruit")
    assert conn.cur.statements("INSERT INTO IngredientAliases")[0][1] == ("dragon fruit", 40)


def test_creatingANameThatExistsIs409(client, useDb):
    useDb(fetchone=[{"IngredientID": 7}])
    body = {"alias": "x", "create": {"name": "cheese", "contains": []}}
    assert post(client, "/ingredients/map", body).status_code == 409


def test_searchFindsIngredientsByName(client, useDb):
    conn = useDb(fetchall=[[{"IngredientID": 1, "Name": "cheese", "Category": "dairy"}]])
    answer = client.get("/api/gluttony-admin/ingredients/search?q=che").get_json()
    assert answer == {"status": "ok", "ingredients": [{"id": 1, "name": "cheese", "category": "dairy"}]}
    assert conn.cur.executed[0][1][0] == "%che%"


def test_statsCountsByKindAndSource(client, useDb):
    useDb(fetchall=[[{"Source": "mealdb", "Kind": "food", "n": 790}]],
          fetchone=[{"total": 790, "removed": 3, "complete": 600}])
    assert client.get("/api/gluttony-admin/stats").get_json() == {
        "status": "ok", "total": 790, "removed": 3, "complete": 600,
        "bySource": [{"source": "mealdb", "kind": "food", "count": 790}]}


def test_tagsThatDifferOnlyByAccentOrCaseStoreOnce(client, useDb):
    conn = useDb(lastrowids={"Recipes": [31]})
    tags = [{"type": "source", "tag": "Café", "origin": "source"}, {"type": "source", "tag": "Cafe", "origin": "source"},
            {"type": "source", "tag": "CAFÉ", "origin": "source"}, {"type": "flavour", "tag": "sweet", "origin": "rule"}]
    answer = post(client, "/recipes/batch", {"recipes": [samples.recipe(tags=tags)]}).get_json()
    assert answer["stored"] == ["mealdb:1"]
    assert [p for _, p in conn.cur.statements("INSERT INTO RecipeTags")] ==         [(31, "source", "Café", "source"), (31, "flavour", "sweet", "rule")]


def test_aBatchThatIsAJsonListIsRefused(client, useDb):
    useDb()
    assert post(client, "/recipes/batch", [samples.recipe()]).status_code == 400

