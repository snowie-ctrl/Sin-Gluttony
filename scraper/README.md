# Gluttony scraper

Builds Gluttony's recipe catalog from TheMealDB, TheCocktailDB (official APIs, free key) and the Wikibooks Cookbook
(the database dump), tags it with the rules in `rules/`, and publishes it to `gluttonyDB` on plutus. Design:
`../docs/superpowers/specs/2026-10-19-catalog-design.md`.

## A pass

fetch (full passes only) → normalise → pictures → tag → link → publish. `PUBLISH=dry` (the default) runs every stage
except sending. A re-tag runs everything after fetch over the raw copies in `data/raw/`, in minutes.

## Running

```bash
py -3.12 -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # Windows dev
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe main.py --once full --no-images      # a dry pass on a dev machine; never for publishing (no-photo)
.venv/Scripts/python.exe main.py --dry-run --pages 200          # the new catalog's dry run: crawl, gate, report
```

On the VM (`~/Gluttony`): `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, `cp .env.example .env`
and fill it in, then `./run.sh`. Surrogate's Gluttony page drives it through `controlApi.py`.

## The new catalog

`CATALOG` in `.env` picks the pass:

- `CATALOG=old` (the default) is the pass above over TheMealDB, TheCocktailDB and Wikibooks, unchanged.
- `CATALOG=new` runs the recipe sites in `rules/sites.json` only: crawl (full passes; `POST /crawl/<site>` crawls one
  site) → read the cached pages → pictures → tag, FDC mappings, nutrition, the completeness gate, then the basics →
  site health (`run/sites.json`) and the FDC queue (`run/fdc-queue.json`) → publish, removing pages that are gone or
  missing from a complete sitemap listing (guarded by `REMOVAL_GUARD` against the last complete listing's size,
  `siteCounts` in `run/state.json`). With `PUBLISH=on` the FDC mappings are sent to `Ingredients.FdcID`. A re-tag
  (`POST /regate`) crawls nothing and removes nothing.

M4's full trial, with publishing off, is the dry run at full scale reading plutus's ingredient table (read only):

```bash
.venv/bin/python main.py --dry-run --pages 0 --server-table
```

The USDA FDC CSVs must be in `data/fdc/` on the VM before the first new pass (`python fdc.py import`), or no recipe
gets an estimate. Switching the live catalog over (publishing, retiring the old sources, moving saved items) follows
the runbook in `server/README.md`, "The catalog switch"; until then the VM stays on `CATALOG=old`.

## Files it keeps

`data/raw/` (source records), `data/images/` (pictures), `data/normalised.jsonl` (the last pass's recipes),
`data/published.json` (what plutus confirmed), `run/` (state, requests, progress, the last report), `reports/`
(the last 30 reports), `logs/scraper.log`.

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

The Sites page (new catalog) uses three more routes. `/status` also carries `"catalog": "old" | "new"`.

- `POST /regate` queues a re-tag (read, tag, nutrition, gate and publish over the cache) and returns 202
  `{"status": "ok", "message": "a re-gate starts within a few seconds"}`.
- `POST /crawl/<site>` queues a full pass of that one site (`{"kind": "run", "site": site}`) and returns 202. 404 for a
  site that is not enabled in `rules/sites.json`.
- Both answer 409 `"a pass is already running or waiting"` when busy, and 409
  `"the new catalog is not on (CATALOG=old)"` under `CATALOG=old` (checked first).
- `GET /sites` returns `{"status": "ok", "catalog", "generatedAt": iso | null, "mode": "pass" | "dryrun" | null,
  "sites": [row]}` from `run/sites.json`, written by the pass and the dry run; empty when the file is missing or
  unreadable. Each row is as `siteHealth.py` writes it.
