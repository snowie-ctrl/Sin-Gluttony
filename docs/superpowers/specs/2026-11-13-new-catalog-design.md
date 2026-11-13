# Gluttony: the new catalog (recipe sites in, open databases out)

Status: designed with the owner 2026-11-13, section by section. Waiting for the owner's review of
this file.

Part 1 (`2026-10-19-catalog-design.md`) filled the catalog from TheMealDB, TheCocktailDB and the
Wikibooks Cookbook. They are community-maintained: times, servings and nutrition are missing or
inconsistent, the photos are often poor, and basics like scrambled eggs are missing. The app looks
less finished than it is because no two recipes carry the same information. This design replaces
those sources with well-kept recipe sites read through their schema.org markup, refuses to list a
recipe that lacks the core facts, and fills the one fact sites often skip (nutrition) from USDA
data.

The rest of the roadmap (part 3 onward) is on hold until this is live. Part 3 loses its nutrition
piece, which is done here; glossary, pairings and packaged drinks stay in part 3.

## Decisions

| Topic | Decision |
|---|---|
| Audience | The owner, and possibly family or close friends: a small private circle behind invite keys. Never public. Every read route already needs a session, pictures included. |
| Repo | Stays public (portfolio). Code is public; scraped text, photos, cached pages and dumps are never committed. |
| Sources | Meals: BBC Good Food, Budget Bytes, RecipeTin Eats, Pinch of Yum. Drinks: Difford's Guide. Plus about 50 basics (section 2.6). Love and Lemons and Imbibe are later config entries. |
| Rejected | AllRecipes, Serious Eats, Liquor.com, Simply Recipes, The Kitchn: they answer an honestly named crawler with a 403 bot wall (checked 2026-11-13). Gluttony never disguises itself to get past one. NYT Cooking: paywall. |
| Old catalog | Retired completely: every TheMealDB, TheCocktailDB and Wikibooks recipe leaves the app. Saved items move to a matching new recipe where one exists (section 4). |
| Approach | The existing scraper on VM 103 gets new source adapters; matching, tagging, facts, images, publish and Surrogate stay. MySQL `gluttonyDB` on plutus stays. (The handoff's Postgres and standalone-service ideas were weighed and dropped: they would rebuild what works.) |
| Must-haves | A recipe is listed only with a photo at least 800 px wide, total time, servings, every ingredient line parsed, and nutrition per serving. |
| Cost | Free only, rules only, no LLM, as before. `recipe-scrapers` (MIT) and USDA FoodData Central bulk files (public domain) fit. |

## 1. What the sites hold (checked 2026-11-13)

One sample page per site, fetched once with an honest User-Agent. robots.txt for all five allows a
generic crawler on recipe pages; the three Dotdash Meredith sites that were rejected disallow named
AI bots and also wall off any automated client.

| Site | Access | Times | Servings | Nutrition | Photo | Notes |
|---|---|---|---|---|---|---|
| BBC Good Food | 200 | prep, cook, total | yes | yes | yes | sitemap in robots.txt |
| Budget Bytes | 200 | prep, cook, total | yes | yes | yes | WordPress recipe card |
| RecipeTin Eats | 200 | prep, cook, total | yes | yes | yes | WordPress recipe card |
| Pinch of Yum | 200 | prep, cook, total | yes | yes | yes | WordPress recipe card |
| Difford's Guide | 200 | total only | yes | no (estimated) | yes | `sitemap/cocktail.xml`, about 7,000 to 8,000 recipe URLs with `lastmod`; glass and garnish read from the page |

## 2. Pipeline

### 2.1 Site config

`scraper/rules/sites.json`, one entry per site:

```json
{"site": "recipetineats", "name": "RecipeTin Eats", "host": "www.recipetineats.com",
 "sitemaps": ["https://www.recipetineats.com/sitemap_index.xml"],
 "recipeUrl": "^https://www\\.recipetineats\\.com/[a-z0-9-]+/$",
 "parser": "schema", "kind": "food", "enabled": true}
```

`parser` is `schema` (recipe-scrapers) or `difford`. `kind` is the default kind (`food` or
`drink`). The exact sitemap URLs and URL patterns are confirmed per site in milestone 1.

### 2.2 Discover and fetch (`sources/sites.py`)

- **robots.txt** is read at the start of every pass with `urllib.robotparser` and obeyed for every
  URL, sitemaps included. A site whose robots.txt disallows recipe pages is skipped with that reason.
- **Sitemaps:** sitemap indexes are followed, entries filtered by `recipeUrl`, and each URL's
  `lastmod` is kept. A page is fetched when it is new or its `lastmod` is newer than the cached copy.
  A site without `lastmod` is fully re-checked every fourth weekly pass.
- **Pace:** at most one request every 5 seconds per host. Sites are interleaved in one loop so the
  pass is not bound by the slowest site. The first full pass is roughly a day and a half; weekly
  passes after that are minutes.
- **Identity:** `GluttonyPersonalCrawler/1.0 (+https://github.com/snowie-ctrl/Sin-Gluttony)`. No
  browser User-Agent, no rotating identities, no headless browser.
- **Refusal:** a 403, a 429, or a page that is not the requested recipe (a challenge or "Simple
  Page" wall, detected by the missing recipe markup plus the status) stops that site for the rest of
  the pass. The reason is recorded and shown in Surrogate. A 429 with `Retry-After` is honoured on
  the next pass, not by retrying in this one.
- **Cache:** each page is stored gzipped as `scraper/data/raw/<site>/<sha1(url)>.html.gz` with its
  URL, fetch time and `lastmod` beside it. `scraper/data/` is git-ignored. The cache is the raw record, so better
  parsing later never needs a re-crawl.
- A URL that leaves the sitemap, or returns 404 or 410 twice in a row, gets `RemovedAt` (hidden,
  never deleted), as part 1 does for recipes that leave their source.

### 2.3 Extract

- **`schema` sites:** `recipe_scrapers.scrape_html(html, org_url=url, supported_only=False)` gives
  title, description, prep, cook and total minutes, yields, ingredient lines (and groups where the
  site has them), instruction steps, image URL, nutrients, category, cuisine and keywords. ISO 8601
  durations become integer minutes.
- **Difford's (`sources/difford.py`):** the page's schema.org Recipe JSON-LD gives title,
  description, total time, yield, ingredients, steps and image. Glass and garnish are read from the
  page's own markup. Method (shaken, stirred, built, blended, thrown) comes from the steps by
  keyword rules.
- Each adapter returns the same normalised shape the part 1 adapters return, plus `description`,
  `nutrition` (or none) and `imageUrl`.

### 2.4 Ingredients, tags, facts

Unchanged from part 1: the rule-based quantity, unit and matching code, the tag rules, `DishKey`,
`Contains`, `Diets` and `Complete`. The quantity parser and alias table are extended for the
patterns the new sites use (milestone 1 runs the parser over the dry-run pages and fixes what
fails). `ingredient-parser-nlp` from the handoff is not used: the existing parser is tested,
rules-only, and feeds the tags and diet facts.

Drink specifics: Difford's glass goes into `Recipes.Glass`. The garnish becomes ingredient lines
under a "Garnish" group heading, marked optional. Method becomes a `technique` tag. Drink time is
a rule by method (built 3, stirred 4, shaken 4, blended 5 minutes) with `TimeFrom = rule`, unless
the page states a different time. Servings default to 1 with `ServingsFrom = rule` when the page
gives none.

### 2.5 The completeness gate (`gate.py`)

A recipe is listed only when all five hold:

1. **Photo:** an image was downloaded and is at least 800 px wide. Thumbnail and full size are made
   as in part 1. `ImageWidth` is stored.
2. **Time:** total minutes known (from the site, or by rule for drinks). Prep and cook are shown
   when the site gives them.
3. **Servings:** servings or yield known (from the site, or by rule for drinks).
4. **Ingredients parsed:** every ingredient line splits into quantity, unit and name. "To taste",
   "for garnish" and lines without a quantity count as parsed when the name is found. The name does
   not have to match a known ingredient.
5. **Nutrition:** per-serving nutrition from the site, or a full estimate (section 3).

A recipe that fails is stored with `HiddenReason` set to the first failing check, in this order:
`no-photo`, `small-photo`, `no-time`, `no-servings`, `unparsed-line`, `no-nutrition`. It is
re-checked every pass, so mapping work in Surrogate brings recipes in without a re-crawl.

The part 1 safety rule is unchanged: a recipe whose ingredients are not all known is never listed
under a diet or as free of an allergen. Check 4 does not weaken it.

### 2.6 Basics

`scraper/rules/basics.json` lists about 50 recipe URLs from the four meal sites, chosen in
milestone 1 from their sitemaps: eggs (scrambled, fried, boiled, poached, omelette), toast, porridge,
pancakes, rice, pasta, mashed potatoes, roast chicken, grilled cheese, a simple salad and so on.
They pass the same gate and get a `basic` occasion tag, which drives the app's quick mode. A basic
that no site provides is listed in the report, and nothing is written by hand.

## 3. Nutrition

### 3.1 Data

- USDA FoodData Central bulk CSVs (Foundation Foods and SR Legacy), public domain, downloaded to
  `data/fdc/` on the VM. A newer release is fetched when USDA lists one, checked monthly. No API
  key and no API calls.
- `Ingredients.FdcID`: the FDC food each known ingredient maps to (null when unmapped).
- Gram conversion: by weight directly; by count and named portions ("1 large egg", "1 clove")
  through FDC's portion table; by volume through FDC's portion table or a density rule file
  (`rules/densities.json`) for ingredients without a volume portion.
- `rules/drinkNutrition.json`: typical per-100 ml values for categories USDA covers poorly
  (liqueurs by sweetness band, bitters, simple and flavoured syrups, vermouths).

### 3.2 Estimating (`nutrition.py`)

- For each required line: ingredient → FDC food → grams → nutrients. Sum, then divide by servings.
- Optional, "to taste" and garnish lines are skipped.
- If any required line cannot be converted (unknown ingredient, no `FdcID`, no gram rule), the
  recipe has no estimate.
- Stored per serving: calories, protein, carbohydrate, fat, saturated fat, fibre, sugar, sodium.
- The site's own nutrition wins when present (`NutritionFrom = source`). Otherwise the estimate is
  used (`NutritionFrom = estimate`) and the app says "estimated".

### 3.3 Mapping and trust

- Name rules propose an `FdcID` for each ingredient: exact and singular matches against FDC
  descriptions, preferring Foundation over SR Legacy and raw over prepared. Rules that cannot settle
  a match leave it for the owner.
- Surrogate gets an **FDC mapping** page beside the ingredient mapping page: ingredients ordered by
  how many hidden recipes they would unlock, with the top FDC candidates to pick from.
- **Calibration:** where a site publishes nutrition and an estimate can also be computed, each run
  reports the agreement (median and spread of the calorie ratio, per site). This is the measure of
  how far "estimated" can be trusted, like part 1's time calibration.
- **Range check:** a per-serving calorie range per course (for example 20 to 2,500 for food, 30 to
  600 for drinks) flags outliers in the report. A flagged estimate is still shown; a flagged
  estimate that is also over 3x the range limit is treated as no estimate.

## 4. Data model changes (`gluttonyDB`)

Added beside part 1's tables. No user table changes.

- `Recipes`: `Description` (TEXT, null), `HiddenReason` (VARCHAR, null means listed), `ImageWidth`
  (INT, null). `Source` takes the five site keys. `Licence` is `personal use` and `Credit` is the
  site's display name for every new recipe.
- `RecipeNutrition`: `RecipeID` (PK, FK cascade), `Calories`, `ProteinG`, `CarbsG`, `FatG`,
  `SatFatG`, `FibreG`, `SugarG`, `SodiumMg` (DECIMAL, per serving), `NutritionFrom` (`source` or
  `estimate`), `Flagged` (BOOL).
- `Ingredients`: `FdcID` (INT, null).
- A new tag value `basic` (occasion) and method values (technique) in `RecipeTags`.

The schema change is a migration file the owner runs (or Claude runs when asked), as in part 1.

## 5. Switchover

Nothing changes for the owner until the last step.

1. **PC dry run** (milestone 1): about 200 pages per site, publishing off. The report gives the pass
   rate per site and per gate reason, plus ten sample recipes per site. The owner reads it before
   any full crawl.
2. **Full crawl on VM 103**, publishing off. Same report at full scale. FDC mapping is worked down in
   Surrogate until the `no-nutrition` count is acceptable to the owner.
3. **Switch**, after a `mysqldump` of `gluttonyDB` and a copy of `/pool/appFiles/gluttony`:
   - New recipes are published.
   - Every TheMealDB, TheCocktailDB and Wikibooks recipe gets `RemovedAt`. **None is deleted**: the
     user tables (`ListItems`, `Devoured`, `Ratings`, `Notes`) cascade on delete.
   - **Moving what people kept:** for each retired recipe referenced by a user row, find listed new
     recipes with the same `DishKey` and kind. With exactly one, move the references to it. With
     several, pick the one with the most facts (nutrition from the source, prep and cook given, a
     larger photo), then the lowest `RecipeID`. Primary-key clashes (the person already has the new
     recipe) keep the higher rating, join the notes with a blank line, keep both Devoured dates,
     and keep one list entry.
   - References with no match stay in the database pointing at the retired recipe, which the app no
     longer shows. This is reversible. The switch reports how many moved and how many did not.
   - The old sources leave the weekly schedule. Their adapters (`adaptTheDb.py`, `adaptWikibooks.py`,
     `sources/thedb.py`, `sources/wikibooks.py`, `sources/wikiImages.py`) and tests are removed in a
     follow-up commit once the switch is confirmed. Old pictures stay on disk until a later cleanup.

## 6. Server and app

- **Server:** listings, search, `/home` and `/random` skip rows with `RemovedAt` or `HiddenReason`.
  `/recipe/<id>` adds `description`, `nutrition` (with `from`), `credit` and `sourceUrl`. A retired
  recipe is shown nowhere, Saved included, so an unmatched saved item simply disappears, as the
  owner chose.
- **Recipe page:** the description under the title; a per-serving nutrition panel (calories,
  protein, carbs, fat, then the rest on expand), marked "estimated" when it is; "From <site> ↗"
  opening the original page. It shows catalog facts only, with no intake tracking (Pride owns what a
  person ate). Servings scaling does not change per-serving values.
- **Quick mode** filters on the `basic` tag plus the existing quick rules.
- **Offline copies** of retired recipes drop out through the existing manifest. Moved ones fetch
  the new recipe.
- No layout changes and no new filters. The stub server's snapshot is regenerated from the new
  catalog for the app's tests.

## 7. Keeping it working

- Surrogate's Gluttony section gets a **Sites** page: per site, the last pass time, pages listed,
  fetched and cached, the stop reason if any (blocked, robots, 429), and gate counts by reason.
- **Breakage alarm:** a site turns red when its extraction success rate (pages fetched that yield a
  recipe) drops by more than 20 points from the previous pass, or to under 50%. That is the "layout
  changed, parser broke" signal. Other sites and the published catalog are unaffected.
- The control API (`:5057`) gains `POST /crawl/<site>` to re-run one site and `POST /regate` to
  re-run the gate and nutrition over the cache without fetching.

## 8. Testing

- **Fixtures are hand-written.** Unit tests use small HTML files that copy each site's structure
  (JSON-LD shape, recipe-card markup, Difford's glass and garnish markup) with made-up recipe text,
  so nothing scraped is committed to the public repo.
- Local regression tests run over the real cached pages in the git-ignored `data/raw/` when it
  exists, and are skipped otherwise.
- Covered: robots obedience, sitemap filtering and `lastmod` logic, the pace limiter, stop on
  403/429/wall, both extractors, each gate check and its order, gram conversion, the estimate
  (including the refuse-when-incomplete rule), the range flag, the switchover mapping and its
  clash rules (against the test MySQL fake, which already refuses unread SELECTs), and the server's
  hidden-row filtering.
- `scraper/data/` (cache, pictures, FDC files) and `scraper/reports/` (dry-run samples) are
  already git-ignored. The grep run before every push (LAN addresses, logins, tokens, emails) also
  checks that no tracked file is an `.html.gz`, sits under `scraper/data/`, or holds a site's
  recipe text.

## 9. Milestones

Each in a fresh session.

1. **Crawler, gate, dry run:** site config, fetching, both extractors, parser fixes, the gate
   without nutrition, the basics list, and the PC dry-run report.
2. **Nutrition:** FDC import, mapping rules, gram conversion, the estimate, calibration and range
   check, the Surrogate FDC mapping page.
3. **Server, app, Surrogate:** schema migration, publish changes, server fields and filtering, the
   recipe page additions, quick mode on `basic`, the Sites page and alarm, the stub snapshot.
4. **Rollout and switch:** VM 103 deploy, full crawl, mapping pass with the owner, backup, switch,
   live checks, then removing the old adapters.

## Done when

The app lists only recipes from the five sites and the basics. Every listed recipe has a good photo,
time, servings, parsed ingredients and per-serving nutrition (marked when estimated) and credits its
site. Saved items with a match have moved. Surrogate shows each site's health. The weekly pass runs
on its own. Nothing scraped is in the public repo.
