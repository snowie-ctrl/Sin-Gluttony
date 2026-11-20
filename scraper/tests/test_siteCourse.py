import pytest

import rulesData
import siteCourse
from models import IngredientLine, Recipe, Step

TABLE = rulesData.load()["siteCourses"]


def made(category, kind="food", title="Made-up thing"):
    return Recipe(source="testsite", sourceId="x", kind=kind, title=title,
                  ingredients=[IngredientLine(line="salt", name="salt")], steps=[Step(text="Mix.")],
                  hints={"category": category})


def test_aCategoryIsSplitIntoLowercaseParts():
    assert siteCourse.parts("Cocktails, Drink") == ["cocktails", "drink"]
    assert siteCourse.parts(None) == [] and siteCourse.parts("") == []


@pytest.mark.parametrize("category", ["Cocktails, Drink", "Drink", "Drinks, Party food", "Beverage"])
def test_aDrinkWordMakesAFoodADrink(category):
    assert siteCourse.classify(made(category), TABLE).kind == "drink"


@pytest.mark.parametrize("category", ["Dinner", "drinks party food", "Afternoon tea, Treat", None])
def test_noWholeDrinkPartLeavesItFood(category):
    assert siteCourse.classify(made(category), TABLE).kind == "food"


def test_aDrinkSiteRecipeStaysADrinkWhateverItsCategory():
    assert siteCourse.classify(made("Dessert", kind="drink"), TABLE).kind == "drink"


@pytest.mark.parametrize("category, course", [
    ("Dinner, Main course", "main"), ("Dessert, Dinner", "dessert"), ("Dinner, Side dish", "side"),
    ("Lunch, Starter", "starter"), ("Breakfast, Brunch", "breakfast"), ("Condiment", "sauce"),
    ("Afternoon tea, Snack, Treat", "dessert"), ("Snack", "snack"), ("Side dish, Snack", "side"),
    ("Buffet", None), (None, None),
    # an explicit "main course" beats weaker words, but not a sauce (final review, 88 such recipes)
    ("Dinner, Lunch, Main course, Pasta, Starter, Supper", "main"), ("Main course, Salad, Side dish", "main"),
    ("Appetiser, Main", "main"), ("Mains, Sauces", "sauce"), ("Dinner, Lunch, Side dish", "side"),
])
def test_aFoodCourseIsTheMostSpecificWordInTheCategory(category, course):
    assert siteCourse.classify(made(category), TABLE).hints["course"] == course


@pytest.mark.parametrize("category, title, course", [
    ("Cocktails, Drink", "Espresso martini", "cocktail"),       # the category wins over the title
    ("Drink", "Mango lassi", "shake"),
    ("Drink", "Iced chai latte", "coffee/tea"),
    ("Drink", "Appleberry mulled wine", "punch"),
    ("Drink", "Homemade lemonade", None),                      # tagging decides cocktail or mocktail
    ("Mocktails", "Virgin mojito", "mocktail"),
])
def test_aDrinkCourseComesFromItsCategoryThenItsTitle(category, title, course):
    assert siteCourse.classify(made(category, title=title), TABLE).hints["course"] == course


def test_titleWordsMatchWholeWordsOnly():
    # "teacake" is not "tea", "shotgun" is not "shot"
    assert siteCourse.drinkCourse("Teacake fizz", [], TABLE) is None
    assert siteCourse.drinkCourse("Shotgun punch", [], TABLE) == "punch"
