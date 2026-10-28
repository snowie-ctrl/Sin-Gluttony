from models import IngredientLine, Recipe, Step


def test_aRecipeRoundTripsThroughADict():
    recipe = Recipe(source="mealdb", sourceId="1", kind="food", title="Toast",
                    ingredients=[IngredientLine(line="1 slice bread", name="bread", quantity=1.0, unit="slice")],
                    steps=[Step(text="Toast it.")], hints={"tags": ["Breakfast"]})
    again = Recipe.fromDict(recipe.toDict())
    assert again == recipe
    assert again.key == "mealdb:1"
