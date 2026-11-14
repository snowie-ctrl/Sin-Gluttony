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
.venv/Scripts/python.exe main.py --once full --no-images      # a dry pass on a dev machine
.venv/Scripts/python.exe main.py --dry-run --pages 200          # the new catalog's dry run: crawl, gate, report
```

On the VM (`~/Gluttony`): `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, `cp .env.example .env`
and fill it in, then `./run.sh`. Surrogate's Gluttony page drives it through `controlApi.py`.

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

**Control API, the contract for Surrogate's FDC mapping page.** The page sits beside ingredient mapping, lists the
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
