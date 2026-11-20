# Gluttony

*"What should I eat, or drink?"*

Gluttony is a recipe app themed on the sin it is named after. Open it with a vague craving ("quick and easy",
"something to feed a crowd", "sweet"), narrow a catalog of thousands of recipes in a few taps, and land on a recipe
you would actually make, scaled to your table and in the units you cook in.

It is a personal project in several parts. Everything here is built and tested; parts marked *live* run on the
author's home server.

| Part | What it is | State |
|---|---|---|
| 1. Catalog | A crawler that reads recipe sites weekly, checks and tags every recipe, estimates nutrition, and a Flask API over it | Live (new catalog since 2026-11-19) |
| 2. App core | The desktop app: accounts, diet profile, browsing, search, the recipe page, saved recipes, cook mode, offline | Live (all 4 milestones) |
| 3. Enrichment | Glossary, pairings, packaged drinks (nutrition arrived early, with the new catalog) | Designing |
| 4–7 | Pantry and grocery lists, store prices, restaurants, iOS | Planned |

## What it does today

- **A catalog of about 6,200 recipes** from five recipe sites: BBC Good Food, RecipeTin Eats, Pinch of Yum,
  Budget Bytes and Love and Lemons, plus a short list of basics (eggs, porridge, pancakes and the like). The crawler
  names itself, obeys `robots.txt`, keeps to a slow pace and stops for a site that refuses it. A recipe is only shown
  when it is complete: a good photo, a time, servings, ingredients that all parse, and nutrition. Tags come from
  readable rules in `scraper/rules/` (course, cuisine, effort, time, flavour, occasion, diets met, allergens
  contained); no paid APIs and no machine learning.
- **Nutrition per serving**: the site's own figures when it gives them, otherwise an estimate from the ingredients
  (USDA FoodData Central), marked as estimated. Gluttony shows catalog facts only and never tracks what you ate.
- **A diet profile that applies everywhere.** Save "vegetarian, no peanuts" once and every search, Home's daily pick
  and "Go on, then" respect it, unless you switch it off for one search. A recipe is only ever listed as meeting a
  diet or free of an allergen when every one of its ingredients is known.
- **Home**: today's temptation (one pick a day per person and time zone), mood tiles that open the results with
  filters already set ("Quick fix" lists the basics), and "Go on, then" for a random pick.
- **Browse**: a filter side panel (kind, course, cuisine, time, effort, flavour, occasion, ingredients to include or
  leave out) that asks again at once, and Ctrl+K search across recipes and ingredients.
- **The recipe page**: the description, per-serving nutrition, servings that rescale every amount into kitchen
  fractions (⅔ cup, 1⅛ cups, never 0.6666), metric and US units, both temperature scales in the steps, other
  versions of the same dish ("Seconds?"), and "From <site> ↗" back to the original page.
- **Saved**: your own lists, Devoured (what you made, with dates), stars and notes.
- **Cook mode**: one step at a time, ingredients to tick off, timers from the steps, and it resumes where you left.
- **Offline**: recipes you saved or cooked stay readable, and changes made offline sync when the connection is back.
- **Site health**: each site's pass, pass rate and an alarm when a site's layout changes and its parsing breaks,
  shown in the owner's admin app.

Drinks are empty for now: the one drink site (Difford's Guide) refuses the crawler, and the old free drink database
left with the switch. "Bottoms up" fills again when a drink site can be read.

## Repository layout

```
scraper/   Python: crawl → read → pictures → tag → nutrition → gate → basics → publish; rules in rules/*.json
server/    Flask blueprints: the read API (sessions, filters, /home, /random), accounts, the admin API, the
           catalog switch; MySQL schema and migrations
app/       Qt 6 / QML desktop app with small C++ services; QML logic modules in qml/logic/*.mjs
  tests/   C++ (Qt Test), QML (qmltestrunner), and a stub server that imitates the API for development
docs/      api.md (the app/server contract) and the design specs and plans (docs/superpowers/)
```

## Building and testing

**Server and scraper** (Python 3.12):

```bash
cd server && python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
```

The scraper is the same, from `scraper/`; [`scraper/README.md`](scraper/README.md) covers the dry run, the weekly
pass and the control API. The server's deployment and the catalog switch are in [`server/README.md`](server/README.md).

**App** (Windows, Qt 6.11 with MSVC 2022): see [`app/README.md`](app/README.md). In short:

```powershell
powershell -File app\tests\build.ps1     # set GLUTTONY_QT / GLUTTONY_QT_TOOLS / GLUTTONY_VCVARS to your Qt and MSVC
powershell -File app\tests\run.ps1       # C++ tests, then the QML logic tests
```

The app finds its server in `config/secrets.json` (git-ignored; copy `app/config/secrets.example.json`). A build
without one cannot reach any server. To try it without the real server, run the stub server in `app/tests/stub/`
(sign in as `stub` / `stub-password`); it serves a few fixture recipes unless you take your own snapshot.

## The look

Ember: a neutral charcoal, near-monochrome dark theme where Gluttony lives only in the accents (the pig icon's orange
melting into crimson), so the food pictures keep their colour. Playfair Display headings over Tahoma, and a voice
with a wink ("Cravings", "Devoured", "Go on, then", "Seconds?"). Every word the app shows lives in
`app/qml/logic/words.mjs`.

## Data and credits

- Recipes and pictures come from [BBC Good Food](https://www.bbcgoodfood.com),
  [RecipeTin Eats](https://www.recipetineats.com), [Pinch of Yum](https://pinchofyum.com),
  [Budget Bytes](https://www.budgetbytes.com) and [Love and Lemons](https://www.loveandlemons.com). Every recipe page
  credits its site and links to the original. Nothing scraped is in this repository: the cache, pictures and reports
  stay on the author's machines, and the tests use hand-written fixtures.
- Nutrition estimates use [USDA FoodData Central](https://fdc.nal.usda.gov) (SR Legacy, public domain).
- [Playfair Display](https://github.com/google/fonts/tree/main/ofl/playfairdisplay) is bundled under the SIL Open
  Font License (`app/assets/fonts/PlayfairDisplay/OFL.txt`).
- Parts of the app's foundations (the API layer, session handling and test harness) are adapted from the author's
  other Qt apps; each adapted file says where it came from.
