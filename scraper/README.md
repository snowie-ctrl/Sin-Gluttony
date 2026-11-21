# Gluttony scraper

Builds Gluttony's recipe catalog from the recipe sites in `rules/sites.json`, tags it with the rules in `rules/`,
works out nutrition from USDA FoodData Central, and publishes it to `gluttonyDB` on plutus. Design:
`../docs/superpowers/specs/2026-11-13-new-catalog-design.md`.

## A pass

crawl (full passes only; `POST /crawl/<site>` crawls one site) → read the cached pages → pictures → tag, FDC
mappings, nutrition, the completeness gate, then the basics → site health (`run/sites.json`) and the FDC queue
(`run/fdc-queue.json`) → publish, removing pages that are gone or missing from a complete sitemap listing (guarded by
`REMOVAL_GUARD` against the last complete listing's size, `siteCounts` in `run/state.json`). With `PUBLISH=on` the FDC
mappings are sent to `Ingredients.FdcID`. `PUBLISH=dry` (the default) runs every stage except sending. A re-tag
(`POST /retag` or `POST /regate`) crawls nothing and removes nothing: it runs everything after the crawl over the
pages already cached in `data/raw/`, in minutes.

**Kinds and courses.** A site's own category decides two things when a page is read (`siteCourse.py`, words in
`rules/siteCourses.json`): a page on a food site whose category says Drink, Cocktails, Beverage or Smoothie is a
drink, and the category's most specific word names the course ("Dinner, Side dish" is a side). A drink's course
comes from its category, then its title (smoothie → shake, latte → coffee/tea), then cocktail or mocktail by its
alcohol. The dry-run report's "Kinds and courses" lists, per site, the drinks and the recipes with no course;
a category word missing from the file shows there.

**Pairings.** After the recipes are published, `pairing.py` suggests what goes with each shown recipe, in slots
chosen by its course (a main gets a side, a sauce, a dessert and a drink; a side goes on mains; a cocktail gets a
snack). Every rule is in `rules/pairings.json`: the slot table, what the recipe says to serve it with (+10), cuisine
(+3 same, +1 same family, −2 different families), effort and time for sides and sauces, flavour balance (rich with
fresh, spicy with cooling, sweet with bitter or sour) and shared occasions. The top 8 per slot with a score above 0
go to plutus's `POST /pairings` with a why ("same cuisine"); a recipe's set is sent only when it changed (its hash
in `data/published.json`), and pairings are not part of a recipe's content hash. The report's `pairings` gives
pairings per slot and how many recipes found none.

## Running

```bash
py -3.12 -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # Windows dev
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe main.py --once full --no-images      # a dry pass on a dev machine; never for publishing (no-photo)
.venv/Scripts/python.exe main.py --dry-run --pages 200          # the dry run: crawl, gate, report; never publishes
```

On the VM (`~/Gluttony`): `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, `cp .env.example .env`
and fill it in, then `./run.sh`. Surrogate's Gluttony page drives it through `controlApi.py`.

M4's full trial, with publishing off, is the dry run at full scale reading plutus's ingredient table (read only):

```bash
.venv/bin/python main.py --dry-run --pages 0 --server-table
```

The USDA FDC CSVs must be in `data/fdc/` on the VM before the first pass (`python fdc.py import`), or no recipe gets
an estimate.

## The old catalog is retired

The first catalog (TheMealDB, TheCocktailDB and the Wikibooks Cookbook) was retired at the catalog switch (the
runbook in `server/README.md`, "The catalog switch"), and its code is gone. `CATALOG` in `.env` defaults to `new`.
With `CATALOG=old`, `main.py` prints "the old catalog was retired at the switch; set CATALOG=new" and exits with
status 1 before it takes the lock or touches a file (any other value but `new` is refused the same way), and the
control API answers every pass request (`/run`, `/retag`, `/regate`, `/crawl/<site>`) with 409 and that message. The old recipes' rows stay on plutus,
retired; a pass never sends or removes them. Their raw records and pictures on the VM are left where they are.

## Files it keeps

`data/raw/` (the page cache and each site's sitemap listing), `data/images/` (pictures), `data/normalised.jsonl`
(the last pass's recipes), `data/published.json` (what plutus confirmed: recipe and pairing hashes), `run/` (state, requests, progress, the last
report, site health, the FDC queue), `reports/` (the last 30 reports), `logs/scraper.log`.

## Growing the ingredient table

`scripts/seedCandidates.py` shows coverage, the most common unknown ingredients and the allergen audit, from the last
pass's `data/normalised.jsonl`. Add entries to `rules/ingredients.json`; mappings made in Surrogate live on plutus and
are never overwritten by the seed.

## Nutrition (USDA FoodData Central)

Nutrition per serving is estimated from USDA FoodData Central (FDC) when a recipe's site gives none. Free, rules only,
no API key and no calls to USDA.

**Getting the data.** Download the SR Legacy (and, when a complete release exists, Foundation Foods) CSV zips from
the FoodData Central download page (fdc.nal.usda.gov/download-datasets) and unzip each into its own folder under
`data/fdc/` (for example `data/fdc/sr/`). These files are git-ignored and are never committed. Each folder must hold
`food.csv`, `food_nutrient.csv` and `food_portion.csv`; folders without them are logged as incomplete and skipped.
Then build the cache:

```bash
.venv/Scripts/python.exe fdc.py import
```

The "newer USDA release" monthly check is left to milestone 4 (on the VM, with the owner).

**How a mapping is chosen.** Mappings are keyed by ingredient name. Precedence: the owner's pick
(`run/fdc-picks.json`), then a curated override (`rules/fdcMap.json`), then a settled rule match (exact name, raw,
Foundation before SR Legacy). A pick of `null` means no FDC food fits. Milestone 3 copies the result into
`Ingredients.FdcID`.

**Control API, the contract for Surrogate's FDC mapping and Sites pages.** The FDC page sits beside ingredient mapping, lists the
queue by unlocks, shows each ingredient's candidates with a search box, and offers a "no FDC food fits" button (a
`null` pick). All routes need the `X-Control-Token` header. A pick takes effect on the next pass or dry run; the API
never starts one.

- `GET /fdc/queue` returns `{"status": "ok", "generatedAt": iso | null, "queue": [{"ingredient", "unlocks", "blocks",
  "candidates": [{"fdcId", "description", "dataType", "score"}]}], "picks": {name: fdcId | null}}`. The queue is the
  dry run's `run/fdc-queue.json`; without it, `queue` is `[]`.
- `GET /fdc/search?q=<text>&limit=10` returns `{"status": "ok", "results": [{"fdcId", "description", "dataType",
  "score"}]}`. `q` is 2 to 80 characters (else 400); `limit` is clamped to 1 to 25. 503 `"FDC data not imported"`
  when no foods are imported.
- `POST /fdc/pick` with `{"ingredient": str, "fdcId": int | null}` returns `{"status": "ok"}`. 400 for a missing,
  empty or over-100-character `ingredient` or an `fdcId` that is not a whole number or null; 404 when `fdcId` is not
  an imported food.

The Sites page uses three more routes. `/status` also carries `"catalog"`, the `CATALOG` setting (`"new"`).

- `POST /regate` queues a re-tag (read, tag, nutrition, gate and publish over the cache) and returns 202
  `{"status": "ok", "message": "a re-gate starts within a few seconds"}`.
- `POST /crawl/<site>` queues a full pass of that one site (`{"kind": "run", "site": site}`) and returns 202. 404 for a
  site that is not enabled in `rules/sites.json`.
- Both answer 409 `"a pass is already running or waiting"` when busy. Under any `CATALOG` but `new`, they, `/run`
  and `/retag` answer 409 `"the old catalog was retired at the switch; set CATALOG=new"` (checked first).
- `GET /sites` returns `{"status": "ok", "catalog", "generatedAt": iso | null, "mode": "pass" | "dryrun" | null,
  "sites": [row]}` from `run/sites.json`, written by the pass and the dry run; empty when the file is missing or
  unreadable. Each row is as `siteHealth.py` writes it.
