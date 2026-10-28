# Gluttony part 1: the catalog

Status: design approved in conversation 2026-10-19; awaiting the owner's review of this file.

## Gluttony as a whole

Gluttony answers "what should I eat (or drink)?". A person opens it with a
vague idea (quick and easy, something to impress at a party, sweet and
Japanese), narrows a large tagged catalog in a few taps, and lands on a recipe
they would actually make. Results are browsed by picture; a recipe page shows
general information at the top and the recipe itself underneath.

The catalog is the owner's own database, filled by a scraper, because no
single source has everything. Users are the owner and friends, with Gluttony
accounts of their own (login keys, like Pageturner), on desktop first and then
iOS. Pride, a sibling health app, will later read from Gluttony; nutrition
facts describe food, so they will live in Gluttony's catalog, while what a
person ate and their goals belong to Pride. Gluttony never shows a tracker.

The project is split into parts, each with its own spec, plan and build:

1. **Catalog** (this spec): database, scraper, admin routes, read API, Surrogate page.
2. App core: accounts, browse, filters, search, recipe page, saved lists (desktop).
3. Enrichment: nutrition, cooking-word glossary, "goes with" pairings, packaged drinks (Coca-Cola).
4. Pantry and grocery lists.
5. Grocery store prices.
6. Restaurants and fast food menus.
7. iOS.

## Decisions

| Topic | Decision |
|---|---|
| Sources | TheMealDB, TheCocktailDB (official APIs, free key only), Wikibooks Cookbook (database dump). |
| Cost | Every source and service the scraper uses is free. No premium keys, no paid APIs, no LLM. |
| Missing metadata | Rules only: ingredient table, parsed times, scored difficulty, keyword flavour and occasion. |
| Filters in part 1 | Time and effort; cuisine and course; taste and diet; ingredients (include and exclude). |
| Recipes without an image | Kept everywhere, shown with a placeholder chosen by course. |
| Same dish from several sources | Separate recipes, linked by a dish key ("other ways to make this"). |
| Upkeep | A Gluttony page in Surrogate (run control, unknown ingredients, skipped recipes). |
| Cadence | Weekly full pass plus Run now / Re-tag from Surrogate. |
| Code | One private repo, `Code-Development/Gluttony`: `scraper/`, `server/`, `app/` (later), `docs/`. |
| Structure | Staged pipeline with a local raw copy (fetch, normalise, tag, link, publish). |
| Machine | A new VM of its own, created by Claude when the rollout reaches it. |

### What the sources hold (checked 2026-10-19)

- **TheMealDB**: 793 meals. Category, area, loose tags, up to 20 ingredient/measure pairs, instructions, thumbnail, YouTube, source URL, a Creative Commons flag per image. No time, servings, difficulty or nutrition. The free key "1" is for development and educational use; paying is required only to publish to an app store. "Please do not scrape our website": use the API only. Credit: "Recipe data and imagery: TheMealDB".
- **TheCocktailDB**: 637 drinks (58 non-alcoholic), 489 ingredients with description, type, alcohol flag and ABV. Category, alcoholic flag, glass, up to 15 ingredients. Coca-Cola exists only as an ingredient. Same key model and terms as TheMealDB.
- **Wikibooks Cookbook**: about 3,830 pages in Category:Recipes, some of them topic pages. `{{recipe summary}}` holds cuisine, origin, servings, yield, free-text time, difficulty 1 to 5 and image; `==Ingredients==` bullets and `==Procedure==` steps. CC BY-SA 4.0 (older revisions 3.0): credit by linking the page; share-alike applies to modified text. Dump `enwikibooks-latest-pages-articles.xml.bz2` is about 204 MB, published on the 1st and 20th of each month; images are on Commons with their own licences.

The free key's use here (a private app for the owner and friends, not on any
store) is the owner's reading of the terms, not something the sources have
confirmed. The scraper calls each API about 100 times a week.

## 1. Data model (`gluttonyDB` on plutus)

**`Recipes`**: one row per recipe from any source.

- `RecipeID`, `Kind` (`food`, `drink`; part 3 adds `product`), `Title`, `DishKey`.
- `Course`. Food: breakfast, starter, main, side, dessert, snack, bread, sauce. Drinks: cocktail, mocktail, shot, coffee/tea, shake, punch.
- `Cuisine` (from a fixed list, e.g. Japanese, Mexican), `Servings`, `PrepMinutes`, `CookMinutes`, `TotalMinutes`, `Difficulty` (1 easy, 2 medium, 3 involved).
- Drinks only: `Alcohol` (alcoholic, non-alcoholic, optional), `Glass`.
- `ServingsFrom`, `TimeFrom`, `DifficultyFrom`: `source` or `rule`, so the app can say "about 30 min" for a guessed value.
- `ImagePath` (null means the placeholder), `ImageCredit`, `VideoUrl`.
- `Source`, `SourceID`, `SourceUrl`, `Licence`, `Credit`.
- `ContentHash`, `FirstSeen`, `UpdatedAt`, `RemovedAt`. A recipe that leaves its source is hidden (`RemovedAt` set), never deleted.

`DishKey` is the title lower-cased with filler words removed ("easy",
"classic", "best", "homemade", "simple", "quick", articles) and the rest
singularised; recipes sharing it are versions of one dish.

**`RecipeIngredients`**: `RecipeID`, `Position`, `Line` (the original text, verbatim), `Quantity`, `QuantityMax` (ranges), `Unit`, `IngredientID` (null when unknown), `UnknownName` (the cleaned text when unknown), `Note`, `Optional`, `GroupHeading`.

**`RecipeSteps`**: `RecipeID`, `Position`, `Text`, `GroupHeading`.

**`Ingredients`**: `IngredientID`, `Name`, `ParentID` (cheddar under cheese), `Category`, `Origin` (`seed` or `owner`).

**`IngredientContains`**: `IngredientID`, `Item`, one row per item from meat, poultry, fish, shellfish, dairy, egg, gluten, tree-nut, peanut, soy, sesame, alcohol, honey. An ingredient also contains what its ancestors contain.

Multi-valued facts live in child tables, never SET, ENUM or JSON columns, as in Pageturner's schema.

**`IngredientAliases`**: `Alias` (normalised, unique), `IngredientID`, `Origin`.

**`RecipeFacts`**: `RecipeID`, `Complete` (every ingredient is known, optional ones included, since a reader may add them). **`RecipeContains`**: `RecipeID`, `Item` (the union over its ingredients). **`RecipeDiets`**: `RecipeID`, `Diet` (vegetarian, vegan, gluten-free, dairy-free).

`Recipes.SearchText` holds the title and ingredient names together, so one FULLTEXT index covers the text search.

Safety rule: a recipe that is not `Complete` is never listed as meeting a diet
or as free of an allergen. It does not appear under those filters until its
unknown ingredients are mapped.

**`RecipeTags`**: `RecipeID`, `Type` (flavour, occasion, source), `Tag`, `Origin` (`source` or `rule`). Flavours: sweet, savoury, spicy, sour, bitter. Occasions: weeknight, party, holiday, brunch.

Not in part 1: nutrition, packaged products, accounts and saved lists. Later
parts add their own tables beside these without changing them.

## 2. Pipeline

`scraper/` runs on the VM with its working files in `data/` (raw copies,
normalised records, published state) and run state in `run/`.

### 2.1 Fetch

- **TheMealDB, TheCocktailDB**: full enumeration with `search.php?f=<letter>` for every letter and digit, cross-checked with `list.php` plus `filter.php` by category and area (meals) or category, alcohol and glass (drinks). Filtering by each of the several hundred ingredients would add about 600 calls a pass, so it is left out. An id seen only through a filter gets `lookup.php?i=`. At most one request per second, a named User-Agent, free key only. Each record is saved as `data/raw/<source>/<id>.json`. TheCocktailDB's ingredient records (type, alcohol, ABV) are fetched only when the seed script asks for them, and cached for 30 days; the weekly pass doesn't need them.
- **Wikibooks**: download the dump only when a newer one is listed, then extract Cookbook-namespace pages to `data/raw/wikibooks/<page>.wikitext` with their revision id and timestamp.
- **Images**: downloaded once per source image URL and kept in `data/images/`. Wikibooks images are resolved through the Commons API (`imageinfo` with URL and `extmetadata` licence and artist) so the credit is correct.

### 2.2 Normalise

One adapter per source turns raw records into one shape: title, kind, ingredient lines, steps, servings, times, difficulty, cuisine, course hints, source tags, image, source, licence, credit.

- Wikibooks pages are parsed as wikitext (mwparserfromhell): the summary template, the ingredient bullets and the procedure steps, with sub-headings kept as group headings. Pages are skipped, with a recorded reason, when they are redirects, `{{cookdp}}` topic pages, or lack either ingredients or steps.
- The ingredient-line parser handles quantities (integers, decimals, fractions, unicode fractions, mixed numbers, ranges), units (a fixed table with spellings and abbreviations), notes after a comma or in brackets, "(optional)" and "to taste". TheMealDB and TheCocktailDB already separate measure and ingredient; their measure goes through the same quantity and unit parser.

### 2.3 Tag

The rules are data files in `scraper/rules/` (cuisine map, course map, units,
flavour keywords, technique words, filler words), except the ingredient table,
whose live copy is on plutus (see section 4).

- **Ingredient matching**: normalise (lower case, singular, strip preparation and size words such as fresh, chopped, diced, large), look up the aliases, then try the longest alias contained in the line. Unmatched lines keep `UnknownName`.
- **Time**: the Wikibooks time field (prep, cook, total), otherwise the sum of durations stated in the steps. `TimeFrom = rule` when derived. No time when neither exists.
- **Difficulty**: the Wikibooks rating mapped 1–2 to easy, 3 to medium, 4–5 to involved; otherwise a score from the step count, the ingredient count and hard-technique words, with thresholds tuned during the dry run.
- **Course and cuisine**: mapped from source categories, areas and Wikibooks categories; drink course from TheCocktailDB category and alcohol flag.
- **Flavour**: spicy when an ingredient is in the chilli group; sweet for dessert courses or when sugar-family ingredients are a large share; savoury for mains and sides that are not sweet; source tags mapped where they match.
- **Occasion**: weeknight for a main of at most 45 minutes and difficulty at most 2; party for starters, punches, or 8 or more servings; holiday and brunch from source tags and categories.
- **Facts**: `Contains`, `Diets` and `Complete` from the matched ingredients.
- **Calibration**: Wikibooks recipes that state both time and difficulty are the reference set. Each run reports how often the rules (applied as if the stated values were missing) agree with the stated values.

### 2.4 Link

Compute `DishKey` for every recipe.

### 2.5 Publish

- Compare each recipe's content hash with the last published state and send only new or changed recipes to the admin routes, in batches.
- Resize images with Pillow to a large copy (longest side 1200 px) and a thumbnail (400 px), and rsync them to `/pool/appFiles/gluttony/images/` on plutus.
- Mark recipes removed when they are missing from a complete fetch of their source (section 5).
- `PUBLISH=dry` runs every stage except sending and writes what it would send to the report.

**Re-tag** runs 2.2 to 2.5 over the raw copies without fetching.

## 3. Server

`server/` in the repo; deployed to plutus `/database/API/util/` the way
Pageturner's pieces are. The owner runs the schema and restarts Caduceus;
Claude never does either.

- `schema.sql`, and `gluttonySmoke.py`, which runs every route against a scratch database the owner creates and drops before `gluttonyDB` exists.
- `gluttonyAdminConfig.example.json` (the real one is never committed, `chmod 600`).

### Admin routes: `gluttonyAdminRoutes.py` at `/api/gluttony-admin` (LAN only)

- `POST /recipes/batch`: upsert recipes with their ingredients, steps, facts and tags; one transaction per recipe; returns which recipes were stored.
- `POST /recipes/removed`: set `RemovedAt` for the given recipes.
- `GET /state`: content hash per published recipe, so the scraper can rebuild its published state if the local file is lost.
- `GET /ingredients`: the live ingredient table and aliases.
- `POST /ingredients/seed`: upsert seed rows only; rows with `Origin = owner` are never changed.
- `GET /ingredients/unknown`: unknown names ranked by the number of recipes they block.
- `POST /ingredients/map`: add an alias to an existing ingredient, or create a new ingredient (name, parent, category, contains) with that alias; `Origin = owner`.

### Read API: `gluttonyRoutes.py` at `/api/gluttony`

- `GET /recipes`: filtered and paged results. Filters: kind, course, cuisine, maximum total minutes, difficulty, flavour, occasion, diets (all must be met), allergens to avoid, ingredients to include (all must be present, children count), ingredients to exclude, and text search over titles and ingredient lines (MySQL FULLTEXT). A filter that needs a value a recipe does not have leaves that recipe out. Diet and allergen filters only match `Complete` recipes. Sort: relevance, quickest, or a daily shuffle. Removed recipes never appear.
- `GET /recipes/<id>`: the full recipe, its other versions (same `DishKey`) and its credit.
- `GET /filters`: every filter's options with counts.
- `GET /images/<id>`, `GET /thumbs/<id>`.

In part 1 the read API is LAN only and has no accounts. Part 2 adds
Pageturner's session hook (`requireSession`, `requestUID()`) and only then lets
`/api/gluttony/` through the tunnel.

## 4. Running, schedule and Surrogate

- **VM**: a new VM for Gluttony, created by Claude when the rollout reaches it. `./run.sh` starts tmux session `gluttony` with the scraper loop and the control API. No qBittorrent; well under 1 GB of disk.
- **Schedule**: one full pass a week, Sunday 03:00 America/Chicago. A pass missed while the VM was off runs at startup.
- **One run at a time**: a lock file in `run/`.

### Control API (`controlApi.py`, its own `CONTROL_PORT`, header `X-Control-Token`)

- `GET /status`: current stage and progress, last run summary.
- `POST /run`: a full pass now; refused while one is running.
- `POST /retag`: stages 2.2 to 2.5 only.
- `POST /stop`: stop at the next safe point, never in the middle of publishing.
- `GET /report`: the last run's counts per source (new, changed, removed, skipped), skipped pages with reasons, unknown ingredients ranked by recipes blocked, and calibration agreement.

### Ingredient table

plutus's `Ingredients` and `IngredientAliases` are the live table; the
scraper reads them at the start of every tag stage. `scraper/rules/ingredients.json`
is the seed, built during development from the scraped data and TheCocktailDB
ingredient records, and loaded with `POST /ingredients/seed`. Tests use the
seed file. Mappings made in Surrogate are `owner` rows and are never
overwritten by the seed.

### Surrogate

A Gluttony page in Surrogate, backed by one `Gluttony` class that holds two
API clients: the scraper's control API and plutus's admin routes. (Surrogate's
shared `ScraperClient` expects Showtime-shaped routes such as a queue and
downloads, which Gluttony does not have.) Surrogate is its own git repo: the
work goes on a branch there, and the owner rebuilds it.

- **Run**: status, last run, Run now, Re-tag, Stop.
- **Catalog**: counts by kind and source; what the last run added, changed and removed.
- **Unknown ingredients**: ranked by recipes blocked; map to an existing ingredient (search), or create one with its parent, category and contains boxes. Takes effect on the next Re-tag.
- **Skipped recipes**: each with its reason; read only.

## 5. Errors

- **Source down or slow**: 3 tries with backoff, then that source is marked failed for the run and the others continue. A failed or incomplete source never marks anything removed.
- **Sudden drop**: if a source returns more than 5% fewer records than last run (for example a cap on the free key), nothing is removed and the report says why.
- **Parse failure**: the recipe is skipped with a reason; the run never stops for one recipe.
- **Publish**: one transaction per recipe; the local published state records only recipes the server confirmed, so failures are sent again next pass. A failed image publishes the recipe without it and retries the image next pass.
- **plutus unreachable**: publish retries, then the run ends with an error; raw and normalised data are kept so nothing is fetched again.

## 6. Testing

pytest, test first.

- Fixtures: saved records from both DBs and about 30 Wikibooks pages, with their credit in `tests/fixtures/README.md`.
- Table tests for the quantity, unit and ingredient-line parser and the matcher; a test for each tagging rule, the facts and the safety rule, the dish key, the content hash, and the removal guard.
- Calibration test: agreement with Wikibooks' stated time and difficulty must stay at or above a floor set after the dry run.
- Server routes tested against a fake connection, then the smoke test on a scratch database.
- Tests never reach the live sources or plutus: `conftest.py` blanks the source and admin base URLs.

## 7. Rollout

1. Claude creates the VM and installs the scraper.
2. Dry run on the VM with `PUBLISH=dry`; the owner and Claude review the report (counts, skipped pages, unknown ingredients, calibration). Claude extends the seed ingredient table and sets the calibration floor.
3. The owner runs the smoke test on a scratch database, creates `gluttonyDB`, runs `schema.sql`, registers both blueprints in Caduceus, creates `/pool/appFiles/gluttony`, and restarts Caduceus.
4. First real publish. Check counts and every filter kind through `/api/gluttony/recipes`.
5. The owner rebuilds Surrogate; the weekly schedule is switched on.

## Done when

- `gluttonyDB` holds about 5,000 recipes from the three sources, each with its credit.
- Every filter kind returns sensible results through `/api/gluttony/recipes`.
- A weekly pass runs unattended and only sends what changed.
- Surrogate shows the run, the unknown ingredients and the skipped recipes, and mapping an ingredient fixes its recipes on the next Re-tag.
