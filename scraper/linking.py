"""
Dish keys: recipes that share one are versions of the same dish ("other ways
to make this"). The key is the title in plain lower case, with words like
"easy" and "classic" dropped and plurals made singular. Wikibooks numbers its
variations ("Banana Bread II"), so a trailing roman numeral is dropped too.
"""
from matching import plainText, singular

_NUMERALS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}


def dishKey(title, fillerWords):
    plain = plainText(title)
    words = [singular(w) for w in plain.split() if w not in fillerWords]
    if len(words) > 1 and words[-1] in _NUMERALS:
        words.pop()
    return " ".join(words) or plain
