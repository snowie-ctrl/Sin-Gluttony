"""Pairings (spec 2026-11-19 part 3, 2.1 and 2.2): the slot table, "serve with", each score part, the cut and the why.
Every recipe here is made up."""
import config
import pairing
import rulesData
from models import IngredientLine, Recipe, Step

RULES = rulesData.load(config.RULES_DIR)


def made(sourceId, course, title=None, kind=None, cuisine=None, difficulty=None, minutes=None, flavours=(),
         occasions=(), ingredients=(), description=None, steps=(), dishKey=None, hidden=None, source="madeup"):
    title = title or f"Dish {sourceId}"
    drink = course in ("cocktail", "mocktail", "shot", "coffee/tea", "shake", "punch")
    r = Recipe(source=source, sourceId=str(sourceId), kind=kind or ("drink" if drink else "food"), title=title,
               ingredients=[IngredientLine(line=n, name=n) for n in ingredients],
               steps=[Step(text=t) for t in steps], course=course, cuisine=cuisine, difficulty=difficulty,
               totalMinutes=minutes, description=description)
    r.tags = ([{"type": "flavour", "tag": f, "origin": "rule"} for f in flavours]
              + [{"type": "occasion", "tag": o, "origin": "rule"} for o in occasions])
    r.dishKey = dishKey or title.lower()
    r.hiddenReason = hidden
    return r


def slotKeys(result, key, slot):
    return [p["key"] for p in result.get(key, []) if p["slot"] == slot]


# ---- 2.1 the slot table ----

def test_aMainGetsASideASauceADessertAndADrink():
    main = made(1, "main", description="Serve with rice and gravy and cake and mojito.")
    others = [made(2, "side", "Rice"), made(3, "sauce", "Gravy"), made(4, "dessert", "Cake"),
              made(5, "cocktail", "Mojito"), made(6, "starter", "Rice soup")]
    result = pairing.pairAll([main, *others], RULES)
    assert {p["slot"]: p["key"] for p in result["madeup:1"]} == {"side": "madeup:2", "sauce": "madeup:3",
                                                                   "dessert": "madeup:4", "drink": "madeup:5"}


def test_aDessertsDrinkIsCoffeeTeaACocktailOrAMocktailOnly():
    dessert = made(1, "dessert", "Tart", cuisine="French")
    drinks = [made(n, course, cuisine="French") for n, course in
              ((2, "coffee/tea"), (3, "cocktail"), (4, "mocktail"), (5, "shot"), (6, "shake"), (7, "punch"))]
    result = pairing.pairAll([dessert, *drinks], RULES)
    assert sorted(slotKeys(result, "madeup:1", "drink")) == ["madeup:2", "madeup:3", "madeup:4"]


def test_aStartersDrinkMayBeAnyDrink():
    starter = made(1, "starter", cuisine="French")
    drinks = [made(n, course, cuisine="French") for n, course in ((2, "shot"), (3, "shake"), (4, "punch"))]
    assert sorted(slotKeys(pairing.pairAll([starter, *drinks], RULES), "madeup:1", "drink")) == \
        ["madeup:2", "madeup:3", "madeup:4"]


def test_aSideGoesOnMainsAndACocktailGetsSnacksAndStarters():
    side, main = made(1, "side", cuisine="Thai"), made(2, "main", cuisine="Thai")
    cocktail = made(3, "cocktail", cuisine="Thai")
    snack, starter, dessert = made(4, "snack", cuisine="Thai"), made(5, "starter", cuisine="Thai"), \
        made(6, "dessert", cuisine="Thai")
    result = pairing.pairAll([side, main, cocktail, snack, starter, dessert], RULES)
    assert slotKeys(result, "madeup:1", "goes-on") == ["madeup:2"]
    assert sorted(slotKeys(result, "madeup:3", "snack")) == ["madeup:4", "madeup:5"]


def test_aShakeAndCoffeeGetNothing():
    shake, coffee = made(1, "shake", cuisine="Thai"), made(2, "coffee/tea", cuisine="Thai")
    snack = made(3, "snack", cuisine="Thai")
    result = pairing.pairAll([shake, coffee, snack], RULES)
    assert "madeup:1" not in result and "madeup:2" not in result


def test_theSlotTableLivesInTheRulesFile():
    assert RULES["pairings"]["slots"]["main"] == ["side", "sauce", "dessert", "drink"]
    assert RULES["pairings"]["rowCourses"]["dessert"]["drink"] == ["coffee/tea", "cocktail", "mocktail"]


# ---- "serve with" ----

def test_serveWithNaanAndRaitaMatchesBoth():
    main = made(1, "main", steps=["Simmer for 20 minutes.", "Serve with warm naans and raita. Enjoy the rice."])
    naan, raita, rice = made(2, "side", "Naan"), made(3, "sauce", "Raita"), made(4, "side", "Rice")
    result = pairing.pairAll([main, naan, raita, rice], RULES)
    assert slotKeys(result, "madeup:1", "side") == ["madeup:2"]       # "rice" is after the full stop
    assert slotKeys(result, "madeup:1", "sauce") == ["madeup:3"]


def test_theDescriptionCountsAndCommasOrAndSplitTheParts():
    main = made(1, "main", description="Lovely served alongside garlic bread, slaw or a green salad.")
    parts = pairing.servedWithParts(main, RULES)
    assert [sorted(p) for p in parts] == [["bread", "garlic"], ["slaw"], ["a", "green", "salad"]]


def test_aDishMatchesOnlyWhenAllItsWordsAreInOnePart():
    main = made(1, "main", description="Serve with garlic bread and a green salad.")
    garlicBread, salad, greenBeans = made(2, "side", "Garlic bread"), made(3, "side", "Green salad"), \
        made(4, "side", "Green beans")
    result = pairing.pairAll([main, garlicBread, salad, greenBeans], RULES)
    assert slotKeys(result, "madeup:1", "side") == ["madeup:2", "madeup:3"]


def test_garnishOnlyPhrasesMatchNothing():
    main = made(1, "main", description="Serve with chopped parsley, grated parmesan and a squeeze of lime.")
    parsley, parmesan, lime = made(2, "side", "Parsley"), made(3, "sauce", "Parmesan"), made(4, "side", "Lime")
    result = pairing.pairAll([main, parsley, parmesan, lime], RULES)
    assert "madeup:1" not in result


def test_yourFavouriteAnythingMatchesNothing():
    main = made(1, "main", description="Serve with your favourite salsa.")
    assert "madeup:1" not in pairing.pairAll([main, made(2, "sauce", "Salsa")], RULES)


def test_aGarnishWordInADishKeyStillNeedsItsOtherWords():
    main = made(1, "main", description="Serve with soy sauce.")
    hot = made(2, "sauce", "Hot sauce")
    assert "madeup:1" not in pairing.pairAll([main, hot], RULES)


# ---- 2.2 the score parts ----

def score(r, c, slot="side"):
    return pairing.score(r, c, slot, RULES)


def test_cuisine():
    assert score(made(1, "main", cuisine="Italian"), made(2, "side", cuisine="Italian"))[0] == 3
    assert score(made(1, "main", cuisine="Italian"), made(2, "side", cuisine="Greek"))[0] == 1
    assert score(made(1, "main", cuisine="Italian"), made(2, "side", cuisine="Thai"))[0] == -2
    assert score(made(1, "main", cuisine="Italian"), made(2, "side"))[0] == 0
    assert score(made(1, "main"), made(2, "side", cuisine="Thai"))[0] == 0


def test_aHarderOrLongerSideCostsPointsButADrinkDoesNot():
    r = made(1, "main", cuisine="Thai", difficulty=1, minutes=30)
    harder = made(2, "side", cuisine="Thai", difficulty=2, minutes=30)
    longer = made(3, "side", cuisine="Thai", difficulty=1, minutes=45)
    assert score(r, harder)[0] == 1 and score(r, longer)[0] == 2
    assert score(r, harder, "sauce")[0] == 1
    assert score(r, made(4, "cocktail", cuisine="Thai", difficulty=3, minutes=90), "drink")[0] == 3
    assert score(r, made(5, "side", cuisine="Thai"))[0] == 3            # unknown effort and time cost nothing


def test_flavourPairsWorkEitherWayRound():
    rich = made(1, "main", ingredients=["double cream", "butter"])
    fresh = made(2, "side", ingredients=["cucumber", "lemon juice"])
    plain = made(3, "side", ingredients=["rice"])
    points, why = score(rich, fresh)
    assert points == 2 and why == ["a fresh side for a rich main"]
    assert score(fresh, rich, "goes-on")[0] == 2
    assert score(rich, plain)[0] == 0
    assert score(made(4, "dessert", flavours=["sweet"]), made(5, "coffee/tea", flavours=["bitter"]), "drink")[0] == 2
    assert score(made(6, "main", flavours=["spicy"]), made(7, "sauce", ingredients=["greek yogurt"]), "sauce")[0] == 2


def test_eachSharedOccasionAddsOne():
    r = made(1, "main", occasions=["party", "holiday", "weeknight"])
    assert score(r, made(2, "side", occasions=["party", "holiday"]))[0] == 2
    assert score(r, made(3, "side", occasions=["brunch"]))[0] == 0


def test_servedWithIsTheStrongest():
    r = made(1, "main", cuisine="Italian", description="Serve with focaccia.")
    points, why = score(r, made(2, "side", "Focaccia", cuisine="Thai"))
    assert points == 8 and why == ["the recipe says to serve it with focaccia"]


# ---- never paired, ties, the cut, the why ----

def test_neverItselfItsOwnDishOrAHiddenRecipe():
    r = made(1, "main", "Chilli", cuisine="Mexican", description="Serve with rice.")
    sameDish = made(2, "side", "Chilli", cuisine="Mexican")
    hidden = made(3, "side", "Rice", cuisine="Mexican", hidden="no-photo")
    result = pairing.pairAll([r, sameDish, hidden], RULES)
    assert "madeup:1" not in result
    assert "madeup:3" not in result                    # a hidden recipe gets no pairings either


def test_scoresOfZeroOrLessAreDropped():
    r = made(1, "main", cuisine="Italian")
    result = pairing.pairAll([r, made(2, "side", cuisine="Thai"), made(3, "side")], RULES)
    assert "madeup:1" not in result


def test_theTopEightByScoreThenKey():
    r = made(1, "main", cuisine="Italian", description="Serve with polenta.")
    sides = [made(n, "side", f"Side {n}", cuisine="Italian", source="b") for n in range(10, 22)]
    best = made(99, "side", "Polenta", cuisine="Italian", source="z")
    result = pairing.pairAll([r, *sides, best], RULES)
    picked = result["madeup:1"]
    assert [p["key"] for p in picked] == ["z:99"] + [f"b:{n}" for n in range(10, 17)]
    assert [p["rank"] for p in picked] == list(range(1, 9))
    assert pairing.pairAll([r, *reversed(sides), best], RULES) == result


def test_theWhyIsTheOneOrTwoLargestPartsInOrder():
    r = made(1, "main", cuisine="Italian", occasions=["party"], ingredients=["cream"],
             description="Serve with salad.")
    c = made(2, "side", "Salad", cuisine="Italian", occasions=["party"], ingredients=["rocket"])
    picked = pairing.pairAll([r, c], RULES)["madeup:1"][0]
    assert picked["why"] == "the recipe says to serve it with salad; same cuisine"
    alone = made(3, "side", "Beans", cuisine="Greek")
    assert pairing.pairAll([r, alone], RULES)["madeup:1"][0]["why"] == "both Mediterranean"


def test_theWhyFitsWhatPlutusStores():
    r = made(1, "main", description="Serve with " + " ".join(["very"] * 40) + " long thing.")
    c = made(2, "side", " ".join(["very"] * 40) + " long thing")
    assert len(pairing.pairAll([r, c], RULES)["madeup:1"][0]["why"]) <= 120


def test_theGroupedScoringPicksWhatScoringEveryPairWould():
    """pairAll groups candidates to stay fast over a whole catalog; it must keep exactly what scoring every pair
    (pairing.score) and sorting by score, then key, would keep."""
    import random
    rng = random.Random(7)
    cuisines = ["Italian", "Greek", "Thai", "Indian", None]
    courses = ["main", "main", "side", "sauce", "dessert", "cocktail", "coffee/tea", "snack", "starter"]
    words = ["rice", "salad", "naan", "slaw", "bread", "beans"]
    recipes = []
    for n in range(90):
        title = f"{rng.choice(words)} {n % 7}" if rng.random() < 0.5 else rng.choice(words)
        recipes.append(made(n, rng.choice(courses), title, cuisine=rng.choice(cuisines),
                            difficulty=rng.choice([None, 1, 2, 3]), minutes=rng.choice([None, 20, 40, 90]),
                            flavours=rng.sample(["sweet", "spicy", "sour", "bitter"], rng.randint(0, 2)),
                            occasions=rng.sample(["party", "holiday", "weeknight"], rng.randint(0, 2)),
                            ingredients=rng.sample(["cream", "lemon", "yogurt", "rice", "onion"], 2),
                            description=f"Serve with {rng.choice(words)} and {rng.choice(words)}."
                            if rng.random() < 0.4 else None))
    result = pairing.pairAll(recipes, RULES)
    p = RULES["pairings"]
    for r in recipes:
        expected = []
        for slot in p["slots"].get(r.course, []):
            allowed = p["rowCourses"].get(r.course, {}).get(slot) or p["slotCourses"][slot]
            scored = sorted((-pairing.score(r, c, slot, RULES)[0], c.key) for c in recipes
                            if c.course in allowed and c.key != r.key and c.dishKey != r.dishKey)
            expected += [(slot, key) for points, key in scored if points < 0][:p["perSlot"]]
        assert [(x["slot"], x["key"]) for x in result.get(r.key, [])] == expected, r.key
