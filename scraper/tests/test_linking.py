import linking
import rulesData

FILLER = set(rulesData.load()["fillerWords"])


def test_dishKeyIgnoresAccentsAndFillerWords():
    assert linking.dishKey("The Best Classic Grilled Cheese Sandwiches", FILLER) == "grilled cheese sandwich"
    assert linking.dishKey("Crème Brûlée", FILLER) == linking.dishKey("creme brulee", FILLER) == "creme brulee"
    assert linking.dishKey("Piña Colada", FILLER) == "pina colada"


def test_numberedPagesAreVersionsOfOneDish():
    # Wikibooks numbers its variations: "Banana Bread", "Banana Bread II", "Banana Bread III".
    keys = {linking.dishKey(t, FILLER) for t in ("Banana Bread", "Banana Bread I", "Banana Bread II",
                                                 "Banana Bread III", "Banana Bread IV", "Banana Bread X")}
    assert keys == {"banana bread"}
    assert linking.dishKey("Loukoumas (Greek Donuts with Honey) II", FILLER) == \
        linking.dishKey("Loukoumas (Greek Donuts with Honey)", FILLER)


def test_onlyATrailingNumeralIsDropped():
    assert linking.dishKey("Vitamin C Smoothie", FILLER) == "vitamin c smoothie"
    assert linking.dishKey("Chex Mix", FILLER) == "chex mix"
    assert linking.dishKey("V", FILLER) == "v"


def test_aTitleOfOnlyFillerWordsKeepsItsWords():
    assert linking.dishKey("The Best", FILLER) == "the best"
