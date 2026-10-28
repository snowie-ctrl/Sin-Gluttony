import pytest

import adaptTheDb
import rulesData
from models import Skipped

UNITS = rulesData.load()["unitMap"]


def mealRaw(**fields):
    record = {"idMeal": "52772", "strMeal": "Teriyaki  Chicken", "strCategory": "Chicken", "strArea": "Japanese",
              "strInstructions": "STEP 1\r\nPreheat the oven.\r\n\r\nSTEP 2\r\n2. Mix the sauce.",
              "strMealThumb": "https://www.themealdb.com/images/media/meals/abc.jpg",
              "strTags": "Meat,Casserole", "strYoutube": "https://www.youtube.com/watch?v=x"}
    for n in range(1, 21):
        record[f"strIngredient{n}"] = ""
        record[f"strMeasure{n}"] = ""
    record.update(fields)
    return {"source": "mealdb", "sourceId": "52772", "record": record}


def test_aMealBecomesARecipe():
    recipe = adaptTheDb.adaptMeal(mealRaw(strIngredient1="soy sauce", strMeasure1="3/4 cup "), UNITS)
    assert (recipe.key, recipe.kind, recipe.title) == ("mealdb:52772", "food", "Teriyaki Chicken")
    assert [s.text for s in recipe.steps] == ["Preheat the oven.", "Mix the sauce."]
    line = recipe.ingredients[0]
    assert (line.line, line.name, line.quantity, line.unit) == ("3/4 cup soy sauce", "soy sauce", 0.75, "cup")
    assert recipe.hints == {"category": "Chicken", "area": "Japanese", "tags": ["Meat", "Casserole"]}
    assert recipe.sourceUrl == "https://www.themealdb.com/meal/52772"
    assert recipe.credit == "Recipe data and imagery: TheMealDB"
    assert recipe.imageUrl.endswith("abc.jpg") and recipe.videoUrl


def test_emptyAndNullSlotsAreSkipped():
    raw = mealRaw(strIngredient1="Eggs", strMeasure1="2", strIngredient2="  ", strMeasure2="1 cup",
                  strIngredient3=None, strMeasure3=None, strIngredient4="Lemon", strMeasure4="Juice of 1")
    recipe = adaptTheDb.adaptMeal(raw, UNITS)
    assert [(i.name, i.note) for i in recipe.ingredients] == [("Eggs", None), ("Lemon", "Juice of 1")]


def test_aSingleParagraphSplitsIntoSentences():
    steps = adaptTheDb.splitSteps("Shake with ice. Strain into a glass. Serve.")
    assert [s.text for s in steps] == ["Shake with ice.", "Strain into a glass.", "Serve."]


def test_aDrinkKeepsAlcoholAndGlass():
    record = {"idDrink": "11007", "strDrink": "Margarita", "strCategory": "Ordinary Drink",
              "strAlcoholic": "Alcoholic", "strGlass": "Cocktail glass", "strIBA": "Contemporary Classics",
              "strInstructions": "Shake and strain.", "strDrinkThumb": "https://x/m.jpg", "strTags": "IBA,Classic",
              "strIngredient1": "Tequila", "strMeasure1": "1 1/2 oz "}
    recipe = adaptTheDb.adaptDrink({"source": "cocktaildb", "sourceId": "11007", "record": record}, UNITS)
    assert (recipe.kind, recipe.alcohol, recipe.glass) == ("drink", "alcoholic", "Cocktail glass")
    assert recipe.ingredients[0].quantity == 1.5 and recipe.ingredients[0].unit == "oz"
    assert recipe.hints["iba"] == "Contemporary Classics"


def test_aMealWithNoIngredientsIsSkipped():
    with pytest.raises(Skipped, match="no ingredients"):
        adaptTheDb.adaptMeal(mealRaw(), UNITS)
