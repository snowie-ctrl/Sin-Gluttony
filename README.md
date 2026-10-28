# Gluttony

*"What should I eat, or drink?"*

Gluttony is a recipe app themed on the sin it is named after. Open it with a vague craving ("quick and easy",
"something to feed a crowd", "sweet"), narrow a catalog of thousands of recipes and drinks in a few taps, and land on
a recipe you would actually make, scaled to your table and in the units you cook in.

It is a personal project in several parts. Everything here is built and tested; parts marked *live* run on the
author's home server.

| Part | What it is | State |
|---|---|---|
| 1. Catalog | A scraper that builds and tags the recipe catalog weekly, and a Flask API over it | Live |
| 2. App core | The desktop app: accounts, diet profile, browsing, search, the recipe page; later saved recipes, cook mode, offline | Milestone 1 of 4 built |
| 3–7 | Enrichment (nutrition, glossary, pairings), pantry and grocery lists, store prices, restaurants, iOS | Planned |

## What it does today

- **A catalog of about 5,000 recipes and drinks** from TheMealDB, TheCocktailDB and the Wikibooks Cookbook,
  normalised to one shape and tagged by rules: course, cuisine, effort, time, flavour, occasion, diets met, allergens
  contained. No paid APIs and no machine learning: every tag comes from a readable rule in `scraper/rules/`.
- **A diet profile that applies everywhere.** Save "vegetarian, no peanuts" once and every search, Home's daily pick
  and "Go on, then" respect it, unless you switch it off for one search. A recipe is only ever listed as meeting a
  diet or free of an allergen when every one of its ingredients is known.
- **Home**: today's temptation (one pick a day per person and time zone), mood tiles that open the results with
  filters already set, and "Go on, then" for a random pick.
- **Browse**: a filter side panel (kind, course, cuisine, time, effort, flavour, occasion, alcohol, ingredients to
  include or leave out) that asks again at once, and Ctrl+K search across recipes and ingredients.
- **The recipe page**: servings that rescale every amount into kitchen fractions (⅔ cup, 1⅛ cups, never
  0.6666), metric and US units, both temperature scales in the steps, other versions of the same dish
  ("Seconds?"), and the source's credit and licence.

## Repository layout

```
scraper/   Python: fetch → normalise → pictures → tag → link → publish; rules in rules/*.json
server/    Flask blueprints: the read API (sessions, filters, /home, /random), accounts, the admin API; MySQL schema
app/       Qt 6 / QML desktop app with small C++ services; QML logic modules in qml/logic/*.mjs
  tests/   C++ (Qt Test), QML (qmltestrunner), and a stub server that imitates the API for development
docs/      api.md (the app/server contract) and the design specs
```

## Building and testing

**Server and scraper** (Python 3.12):

```bash
cd server && python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
```

The scraper is the same, from `scraper/`; `main.py --once full --no-images` runs a dry pass that sends nothing.

**App** (Windows, Qt 6.11 with MSVC 2022): see [`app/README.md`](app/README.md). In short:

```powershell
powershell -File app\tests\build.ps1     # set GLUTTONY_QT / GLUTTONY_QT_TOOLS / GLUTTONY_VCVARS to your Qt and MSVC
powershell -File app\tests\run.ps1       # C++ tests, then the QML logic tests
```

The app runs against the stub server in `app/tests/stub/` (sign in as `stub` / `stub-password`), so no real
server is needed to try it. The stub serves four fixture recipes unless you take your own snapshot.

## The look

Gula: molten orange to crimson on dark chocolate, Playfair Display headings over Tahoma, and a voice with a wink
("Cravings", "Devoured", "Go on, then", "Seconds?"). Every word the app shows lives in `app/qml/logic/words.mjs`.

## Data and credits

- Recipe data and pictures come from [TheMealDB](https://www.themealdb.com) and
  [TheCocktailDB](https://www.thecocktaildb.com) (through their free APIs) and the
  [Wikibooks Cookbook](https://en.wikibooks.org/wiki/Cookbook:Table_of_Contents) (CC BY-SA 4.0). The catalog
  itself is not in this repository; every recipe page shows its source, credit and licence.
- [Playfair Display](https://github.com/google/fonts/tree/main/ofl/playfairdisplay) is bundled under the SIL Open
  Font License (`app/assets/fonts/PlayfairDisplay/OFL.txt`).
- Parts of the app's foundations (the API layer, session handling and test harness) are adapted from the author's
  other Qt apps; each adapted file says where it came from.
