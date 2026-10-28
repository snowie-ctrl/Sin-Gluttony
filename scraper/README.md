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
