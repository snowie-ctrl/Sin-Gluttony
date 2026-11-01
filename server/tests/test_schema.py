import pathlib
import re

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "schema.sql").read_text(encoding="utf-8")
TABLES = {"Recipes", "RecipeIngredients", "RecipeSteps", "RecipeFacts", "RecipeContains", "RecipeDiets",
          "RecipeTags", "Ingredients", "IngredientContains", "IngredientAliases"}


def test_everyTableIsThere():
    assert set(re.findall(r"CREATE TABLE (\w+)", SCHEMA)) == TABLES


def test_everyTableUsesTheHouseEngineAndCollation():
    bodies = re.findall(r"CREATE TABLE \w+ \((.*?)\n\)(.*?);", SCHEMA, re.S)
    assert len(bodies) == len(TABLES)
    for _, tail in bodies:
        assert tail.strip() == "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"


def test_noSetEnumOrJsonColumns():
    body = "\n".join(line for line in SCHEMA.splitlines() if not line.startswith("--"))
    assert not re.search(r"\b(SET|ENUM)\s*\(|\bJSON\b", body)


def test_sourceIdsAreComparedExactly():
    """Source ids are exact identifiers: two pages differing only in case or accents must stay two recipes."""
    assert "SourceID VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL," in SCHEMA


PART2 = (pathlib.Path(__file__).resolve().parent.parent / "schema-part2.sql").read_text(encoding="utf-8")
PART2_TABLES = {"Users", "Devices", "Sessions", "LoginKeys", "UserDiets", "UserAvoids",
                "Lists", "ListItems", "Devoured", "Ratings", "Notes"}


def test_part2AddsItsTablesAndTouchesNoCatalogTable():
    assert set(re.findall(r"CREATE TABLE (\w+)", PART2)) == PART2_TABLES
    assert not re.search(r"\b(ALTER|DROP)\s+TABLE\b", PART2)


def test_part2UsesTheHouseEngineAndCollation():
    bodies = re.findall(r"CREATE TABLE \w+ \((.*?)\n\)(.*?);", PART2, re.S)
    assert len(bodies) == len(PART2_TABLES)
    for _, tail in bodies:
        assert tail.strip() == "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"


def test_part2HasNoSetEnumOrJsonColumns():
    body = "\n".join(line for line in PART2.splitlines() if not line.startswith("--"))
    assert not re.search(r"\b(SET|ENUM)\s*\(|\bJSON\b", body)


def test_aUserGoesWithEverythingTheirs():
    for table in ("Devices", "Sessions", "UserDiets", "UserAvoids"):
        block = re.search(rf"CREATE TABLE {table} \((.*?)\n\)", PART2, re.S).group(1)
        assert "REFERENCES Users (UserID) ON DELETE CASCADE" in block, table
    keys = re.search(r"CREATE TABLE LoginKeys \((.*?)\n\)", PART2, re.S).group(1)
    assert "REFERENCES Users (UserID) ON DELETE SET NULL" in keys


def test_usernamesAreUniqueAndSessionsAreFoundByUser():
    assert "UNIQUE KEY ux_users_username (Username)" in PART2
    assert "KEY ix_sessions_user (UserID)" in PART2


def block(table):
    return re.search(rf"CREATE TABLE {table} \((.*?)\n\)", PART2, re.S).group(1)


def test_whatAPersonKeepsGoesWithThemAndWithTheRecipe():
    for table in ("Lists", "Devoured", "Ratings", "Notes"):
        assert "REFERENCES Users (UserID) ON DELETE CASCADE" in block(table), table
    for table in ("ListItems", "Devoured", "Ratings", "Notes"):
        assert "REFERENCES Recipes (RecipeID) ON DELETE CASCADE" in block(table), table
    assert "REFERENCES Lists (ListID) ON DELETE CASCADE" in block("ListItems")


def test_theSpecsIndexesAndKeysAreThere():
    assert "KEY ix_devoured_user_made (UserID, MadeOn)" in block("Devoured")
    assert "UNIQUE KEY ux_devoured_client (ClientID)" in block("Devoured")
    assert "ClientID CHAR(36) NOT NULL" in block("Devoured")
    assert "KEY ix_listitems_recipe (RecipeID)" in block("ListItems")
    assert "PRIMARY KEY (ListID, RecipeID)" in block("ListItems")
    assert "PRIMARY KEY (UserID, RecipeID)" in block("Ratings")
    assert "PRIMARY KEY (UserID, RecipeID)" in block("Notes")


def test_theLimitsAreInTheColumns():
    assert "Title VARCHAR(60) NOT NULL" in block("Lists")
    assert "Text VARCHAR(2000) NOT NULL" in block("Notes")
    assert "CHECK (Stars IS NULL OR Stars BETWEEN 1 AND 5)" in block("Ratings")
    assert "CHECK (Kind IN ('cravings', 'custom'))" in block("Lists")


def test_anAccountCanHoldOnlyOneCravingsList():
    # CravingsOf is a plain column the sign-up fills, not a generated one: MySQL refuses ON DELETE CASCADE on the
    # foreign key over the base column of a stored generated column.
    lists = block("Lists")
    assert "CravingsOf INT NULL," in lists
    assert "GENERATED" not in lists
    assert "UNIQUE KEY ux_lists_cravings (CravingsOf)" in lists


def test_cravingsOfIsSetExactlyOnCravings():
    # A list is Cravings exactly when it names its owner in CravingsOf, so the unique key can't be sidestepped.
    assert "CONSTRAINT ck_lists_cravingsof CHECK ((Kind = 'cravings') = (CravingsOf IS NOT NULL))" in block("Lists")


def test_starsAndNotesKeepWhenTheyChangedEvenWhenCleared():
    # A cleared rating or note stays as a row (Stars NULL, Text ''), holding when it was cleared: /sync/batch
    # compares a queued change with it, so a change made offline before the clearing never brings it back.
    assert "Stars TINYINT NULL," in block("Ratings")
    for table in ("Ratings", "Notes"):
        assert "UpdatedAt DATETIME(3) NOT NULL," in block(table), table
        assert "ON UPDATE" not in block(table), table
        assert "DEFAULT" not in block(table).split("UpdatedAt", 1)[1].split(",", 1)[0], table
