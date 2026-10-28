"""
Which known ingredient a line is about. Names are normalised (lower case, no
accents or punctuation, preparation words dropped, plurals made singular) and
looked up in the aliases; failing that, the longest known name inside the line
wins, so "boneless skinless chicken thighs" is a chicken thigh. What an
ingredient contains is its own facts plus its ancestors' (cheddar is a cheese,
cheese is dairy).
"""
import re
import unicodedata

_KEEP_S = {"asparagus", "couscous", "hummus", "molasses", "swiss", "grits", "citrus", "bass", "watercress",
           "cress", "schnapps", "octopus", "lemongrass", "hibiscus", "haggis", "gas", "glass", "bitters", "brussels"}
# "butter or margarine", "and/or", then "salt and pepper": on plain text, where "/" and "&" are gone.
# "or" splits first, so "cream or half and half" keeps half and half whole.
_OR = re.compile(r"\s+(?:and\s+)?or\s+")
_AND = re.compile(r"\s+and\s+")


def plainText(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text).split())


def singular(word):
    if word in _KEEP_S or len(word) <= 3:
        return word
    if word.endswith(("leaves", "loaves", "halves")):
        return word[:-3] + "f"
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    if word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if word.endswith(("ss", "us")):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def normaliseName(text, prepWords):
    """Numbers go too: "juice of 1 lemon" is lemon juice whatever the count."""
    return " ".join(singular(w) for w in plainText(text).split() if w not in prepWords and not w.isdigit())


class IngredientTable:
    def __init__(self, rows, aliases, prepWords, modifierWords=()):
        self.rows = rows                    # id -> {"id", "name", "parentId", "category", "contains": set}
        self.aliases = dict(aliases)        # normalised alias -> id
        self.prepWords = set(prepWords)
        self.modifierWords = set(modifierWords)
        # Each alias filed under its first word, so a line is checked only
        # against aliases that could start inside it.
        self._byFirstWord = {}
        for alias in self.aliases:
            if alias:
                self._byFirstWord.setdefault(alias.split()[0], []).append(alias)

    @classmethod
    def fromSeed(cls, seed, prepWords, modifierWords=()):
        rows, byName = {}, {}
        for n, entry in enumerate(seed, start=1):
            rows[n] = {"id": n, "name": entry["name"], "parentId": None, "category": entry.get("category"),
                       "contains": set(entry.get("contains", []))}
            byName[entry["name"]] = n
        for n, entry in enumerate(seed, start=1):
            rows[n]["parentId"] = byName.get(entry.get("parent"))
        aliases = {}
        for n, entry in enumerate(seed, start=1):
            for text in [entry["name"], *entry.get("aliases", [])]:
                key = normaliseName(text, prepWords)
                if key:
                    aliases.setdefault(key, n)
        return cls(rows, aliases, prepWords, modifierWords)

    @classmethod
    def fromServer(cls, payload, prepWords, modifierWords=()):
        rows = {r["id"]: {"id": r["id"], "name": r["name"], "parentId": r.get("parentId"),
                          "category": r.get("category"), "contains": set(r.get("contains", []))}
                for r in payload["ingredients"]}
        aliases = {a["alias"]: a["ingredientId"] for a in payload["aliases"] if a["ingredientId"] in rows}
        return cls(rows, aliases, prepWords, modifierWords)

    def lineage(self, ingredientId):
        """The ingredient and its ancestors, nearest first; a parent loop stops at the first repeat."""
        chain = []
        while ingredientId in self.rows and ingredientId not in chain:
            chain.append(ingredientId)
            ingredientId = self.rows[ingredientId]["parentId"]
        return chain

    def containsOf(self, ingredientId):
        return set().union(*(self.rows[i]["contains"] for i in self.lineage(ingredientId)))

    def categoriesOf(self, ingredientId):
        return {self.rows[i]["category"] for i in self.lineage(ingredientId) if self.rows[i]["category"]}

    def match(self, name):
        key = normaliseName(name, self.prepWords)
        if not key:
            return None, key
        if key in self.aliases:
            return self.aliases[key], key
        words = key.split()
        # An alias counts when every word outside its run is a modifier, so
        # "cashew butter" is not butter. Among the counting runs: longest alias,
        # then earliest position, then alphabetical, so the answer never depends
        # on set or hash order.
        found = []
        for position, word in enumerate(words):
            for alias in self._byFirstWord.get(word, ()):
                aliasWords = alias.split()
                end = position + len(aliasWords)
                if words[position:end] != aliasWords:
                    continue
                if all(w in self.modifierWords for w in words[:position] + words[end:]):
                    found.append((alias, position))
        if not found:
            return None, key
        alias, _ = min(found, key=lambda c: (-len(c[0]), c[1], c[0]))
        return self.aliases[alias], key

    def matchOptions(self, name):
        """
        ([ids], key) for a line that names several ingredients: "butter or
        margarine" and "salt and pepper" are both of theirs. An option of
        modifiers alone takes the last option's noun ("white or brown sugar").
        Every option has to be known. When some are, the line is unknown under
        the first that isn't, so curating fixes the right word; when none is,
        under its whole name.
        """
        return self._options(name, (_OR, _AND))

    def _options(self, name, splitters):
        ingredientId, key = self.match(name)
        if ingredientId:
            return [ingredientId], key
        text = plainText(name)
        while splitters:
            options = [o for o in splitters[0].split(text) if o]
            splitters = splitters[1:]
            if len(options) > 1:
                break
        else:
            return [], key
        noun = " ".join(options[-1].split()[1:])
        ids, unknown = [], []
        for option in options:
            optionIds, optionKey = self._options(option, splitters)
            words = optionKey.split()
            if not optionIds and noun and words and all(w in self.modifierWords for w in words):
                optionIds, optionKey = self._options(f"{option} {noun}", splitters)
            if not optionIds:
                unknown.append(optionKey)
            ids += [i for i in optionIds if i not in ids]
        if unknown:
            return [], (unknown[0] or key) if ids else key
        return ids, key


def seedPayload(seed, prepWords):
    """The seed as POST /ingredients/seed takes it: aliases normalised here, so plutus never has to."""
    payload = []
    for entry in seed:
        aliases = []
        for text in [entry["name"], *entry.get("aliases", [])]:
            key = normaliseName(text, prepWords)
            if key and key not in aliases:
                aliases.append(key)
        payload.append({"name": entry["name"], "parent": entry.get("parent"), "category": entry.get("category"),
                        "contains": sorted(set(entry.get("contains", []))), "aliases": aliases})
    return payload
