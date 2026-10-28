"""
Copies up to 30 Wikibooks pages that state both a time and a difficulty into
tests/fixtures/calibration/, with their credit, so the calibration floor is
tested on real pages. CC BY-SA 4.0: each page's title and address go in the
README beside them.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import store  # noqa: E402
from models import Recipe  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "calibration"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    picked = []
    for line in config.NORMALISED_FILE.read_text(encoding="utf-8").splitlines():
        recipe = Recipe.fromDict(json.loads(line))
        if recipe.source == "wikibooks" and recipe.hints.get("difficultyRating") and recipe.timeFrom == "source":
            picked.append(recipe)
        if len(picked) == 30:
            break
    credits = ["# Calibration pages", "",
               "Real Wikibooks Cookbook pages, CC BY-SA 4.0, by their contributors:", ""]
    for recipe in picked:
        source = store.rawPath("wikibooks", recipe.sourceId)
        shutil.copy(source, OUT / source.name)
        credits.append(f"- [{recipe.title}]({recipe.sourceUrl}) — `{source.name}`")
    (OUT / "README.md").write_text("\n".join(credits) + "\n", encoding="utf-8")
    print(f"{len(picked)} pages saved to {OUT}")


if __name__ == "__main__":
    main()
