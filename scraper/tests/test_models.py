from models import IngredientLine, Recipe, Step


def test_aRecipeRoundTripsThroughADict():
    recipe = Recipe(source="madeupsite", sourceId="1", kind="food", title="Toast",
                    ingredients=[IngredientLine(line="1 slice bread", name="bread", quantity=1.0, unit="slice")],
                    steps=[Step(text="Toast it.")], hints={"tags": ["Breakfast"]})
    again = Recipe.fromDict(recipe.toDict())
    assert again == recipe
    assert again.key == "madeupsite:1"


def test_theRecipeSiteFieldsRoundTripAndOldRecordsStillLoad():
    recipe = Recipe(source="recipetineats", sourceId="abc", kind="food", title="Made-up Stew", ingredients=[],
                    steps=[], description="Made-up.", nutrition={"calories": 400.0}, imageWidth=1200,
                    hiddenReason="no-time")
    assert Recipe.fromDict(recipe.toDict()) == recipe
    old = recipe.toDict()
    for field in ("description", "nutrition", "imageWidth", "hiddenReason"):
        del old[field]
    again = Recipe.fromDict(old)
    assert (again.description, again.nutrition, again.imageWidth, again.hiddenReason) == (None, None, None, None)
