"""
One recipe shape for every source. Adapters fill it from raw records, the tag
stage adds what the sources lack, and publish turns it into the payload plutus
stores. Plain dataclasses, so a recipe round-trips through JSON for the
normalised file and the tests.
"""
from dataclasses import asdict, dataclass, field


class Skipped(Exception):
    """A source record that is not a usable recipe (a topic page, no steps...). The reason goes in the report."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@dataclass
class IngredientLine:
    line: str                       # the original text, as the source wrote it
    name: str                       # the ingredient words, without amount, unit and notes
    quantity: float | None = None
    quantityMax: float | None = None
    unit: str | None = None
    note: str | None = None
    optional: bool = False
    group: str | None = None        # "For the sauce"
    ingredientId: int | None = None # set by matching
    unknownName: str | None = None  # the normalised name when nothing matched
    # "butter or margarine", "salt and pepper": ingredientId is the first named, the rest are here. Facts
    # count every option; plutus only ever stores the first.
    alternativeIds: list = field(default_factory=list)


@dataclass
class Step:
    text: str
    group: str | None = None


@dataclass
class Recipe:
    source: str
    sourceId: str
    kind: str                       # food | drink
    title: str
    ingredients: list
    steps: list
    sourceUrl: str | None = None
    licence: str = ""
    credit: str = ""
    imageUrl: str | None = None     # where the source keeps the picture
    imageCredit: str | None = None
    videoUrl: str | None = None
    servings: int | None = None
    servingsFrom: str | None = None
    prepMinutes: int | None = None
    cookMinutes: int | None = None
    totalMinutes: int | None = None
    timeFrom: str | None = None
    difficulty: int | None = None   # 1 easy, 2 medium, 3 involved
    difficultyFrom: str | None = None
    course: str | None = None
    cuisine: str | None = None
    alcohol: str | None = None
    glass: str | None = None
    # What the source said that rules read later: category, area, tags,
    # categories, timeText, difficultyRating, cuisineText, imageFile, iba.
    hints: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)        # [{"type", "tag", "origin"}]
    facts: dict | None = None                       # {"complete", "contains", "diets"}
    dishKey: str | None = None
    imagePath: str | None = None                    # the picture's name on plutus, or None

    @property
    def key(self):
        return f"{self.source}:{self.sourceId}"

    def toDict(self):
        return asdict(self)

    @classmethod
    def fromDict(cls, data):
        data = dict(data)
        data["ingredients"] = [IngredientLine(**i) for i in data.get("ingredients", [])]
        data["steps"] = [Step(**s) for s in data.get("steps", [])]
        return cls(**data)
