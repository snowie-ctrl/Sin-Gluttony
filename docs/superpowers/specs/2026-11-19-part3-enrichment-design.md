# Gluttony part 3: enrichment (site drinks, pairings, glossary)

Status: designed with the owner 2026-11-19. Waiting for the owner's review of this file.

The roadmap's part 3 was "nutrition, cooking-word glossary, goes-with pairings, packaged drinks"
(`2026-10-19-catalog-design.md`). Nutrition shipped with the new catalog
(`2026-11-13-new-catalog-design.md`, live since 2026-11-19). That switch also left drinks empty:
the old free drink database is retired and the one drink site, Difford's Guide, refuses the
crawler (403). The recipe sites already hold drinks, filed as food. Part 3 is now three things:
put those drinks where they belong (with amounts a jigger can measure), suggest what goes with a
recipe, and explain the cooking words in the steps.

## Decisions

| Topic | Decision |
|---|---|
| Scope | Site drinks (with jigger amounts), pairings, glossary. Three milestones, each in a fresh session. |
| Out of scope | Packaged drinks (products), a new drink source, a glossary page, glossary terms in Ctrl+K search. |
| Drinks | A recipe whose site category says it is a drink becomes `kind = drink`. No new source. Difford's stays configured and joins if it ever lets the crawler in. |
| Jigger | A drink's liquid amounts up to 120 ml show in quarter ounces (US) or the nearest 5 ml (metric). |
| Pairings | Catalog recipes only, chosen by readable rules plus what the recipe itself says it is served with. Scored weekly by the scraper; the server filters by what is shown and the diet profile. |
| Glossary | About 150 to 200 terms written for Gluttony, bundled with the app (works offline and in cook mode). Techniques plus British/American kitchen words. The owner reviews the list before it ships. |
| Unchanged | Free and open data only, no machine learning, every rule readable in a file, nothing scraped in the public repo, no intake tracking. |

## Milestone 1: site drinks and jigger amounts

### 1.1 Which recipes are drinks (`scraper`)

- `rules/drinkCategories.json` lists the category words that make a recipe a drink: `drink`,
  `drinks`, `cocktail`, `cocktails`, `beverage`, `beverages`, `mocktail`, `mocktails`,
  `smoothie`, `smoothies`. Matching is per comma-separated part of the site's own category
  (`hints.category`, already read by `sources/schemaSite.py`), case-insensitive, whole part only:
  "Cocktails, Drink" and "Drink" match; "Drinks party food" does not.
- The kind is decided when the page is read (`adaptSites.py`, after `schemaSite` builds the
  recipe), before tagging, nutrition and the gate, so a drink gets the drink course rules
  (`tagging.applyCourse`: cocktail or mocktail by alcohol, then the other drink courses),
  `rules/drinkNutrition.json` and the drink nutrition ranges.
- A site whose config says `kind: drink` (Difford's) keeps it; the rule only turns food into drink,
  never the other way.
- The recipe keeps its source key and so its `RecipeID` on plutus: only its kind, course and tags
  change on the next publish. Saved items, Devoured marks, stars and notes stay on it. Nothing
  moves.
- Basics are unaffected (they are food courses).
- Expected size, from the 2026-11-19 cache: BBC Good Food has 297 "Cocktails, Drink" and 238
  "Drink" pages, of which 194 pass the gate today; the other sites add their smoothies and
  lemonades. The dry-run report gains a line per site: pages turned into drinks, and how many are
  shown.

### 1.2 Jigger amounts (`app/qml/logic/units.mjs`)

For a recipe with `kind === "drink"`, a liquid amount is shown for a jigger:

- **Which lines:** a volume unit (`ml`, `cl`, `dl`, `l`, `tsp`, `tbsp`, `fl oz`, `cup`, and a
  drink's bare `oz`, already read as `fl oz`) whose scaled amount is at least 7.5 ml and at most
  120 ml. Grams, counts and units with no conversion are unchanged ("2 lime wedges").
- **US:** ounces in quarter steps (¼, ½, ¾, 1, 1¼, 1½ …), written with the kitchen fractions the
  app already uses, unit `oz`. 1 tbsp shows ½ oz; 44 ml shows 1½ oz.
- **Metric:** the nearest 5 ml (10, 15, 20, 25, 30 …). 44 ml shows 45 ml; 1 tbsp shows 15 ml.
- **Below 7.5 ml** (under ¼ oz: a dash, a barspoon): teaspoons in kitchen fractions in both
  systems. Never rounded to nothing.
- **Above 120 ml** (a bottle of prosecco in a punch): the existing conversion (ml or l; cups or
  fl oz).
- **Scaling first:** the servings factor is applied before rounding, so 2 × 1¾ oz shows 3½ oz.
- **Food is unchanged.** A food recipe's spoons and cups keep today's behaviour.
- The original line is still one click away, as today.

### 1.3 Rollout

1. Re-gate on VM 103 (`main.py --once retag`); the report's per-site drink lines and
   `GET /api/gluttony-admin/stats` (`bySource` with `kind: drink`) show the drinks.
2. App build and release with jigger amounts. "Bottoms up" lists drinks again.

## Milestone 2: pairings

### 2.1 Slots (`scraper/rules/pairings.json`)

Each shown recipe gets suggestions in slots chosen by its course:

| Recipe's course | Slots |
|---|---|
| main | side, sauce, dessert, drink |
| starter, breakfast, snack | drink |
| dessert | drink (coffee/tea, cocktail, mocktail only) |
| side, sauce, bread | goes-on (mains) |
| cocktail, mocktail, punch, shot | snack (snacks and starters) |
| shake, coffee/tea | none |

A slot's candidates are shown recipes of the slot's course (a `drink` slot takes any drink course
the row allows). The slot table lives in the rules file, not in code.

### 2.2 Scoring (`scraper/pairing.py`)

For a recipe R and a candidate C in one of R's slots, the score adds:

1. **Served with** (strongest, +10): R's description or steps say "serve with …", "served with
   …" or "serve alongside …"; the phrase up to the next full stop is split on "and", "or" and
   commas, and a part matches C when C's `DishKey` words are all in it as whole words ("serve
   with warm naan and raita" matches a naan and a raita). Garnish words (herbs, cheese, a squeeze
   of something, "your favourite …") listed in the rules file never match on their own.
2. **Cuisine:** same cuisine +3; a cuisine in the same family (`cuisineFamilies` in the rules
   file, e.g. italian, greek, spanish, french in "mediterranean") +1; both set and in different
   families −2; either unset 0.
3. **Effort and time** (side and sauce slots): C's difficulty above R's −2; C's total time above
   R's −1.
4. **Flavour balance:** pairs in the rules file (`rich` with `fresh`, `spicy` with `cooling`,
   `sweet` with `bitter` or `sour`), +2 when R has one side and C the other. Uses the existing
   flavour tags.
5. **Occasion:** +1 per shared occasion tag (party, quick, weekend …).

Never paired: R itself, a recipe with R's `DishKey`, a hidden or removed recipe. Equal scores are
ordered by C's source key (`site:id`), so the result is the same from one pass to the next.

Kept: the top 8 per slot with a score above 0, each with a **why**: the one or two largest
contributions in plain words ("the recipe says to serve it with naan", "same cuisine",
"a fresh side for a rich main"). The words live in the rules file.

### 2.3 Publishing (`scraper/publish.py`, `server`)

- After the recipes are stored, the pass sends pairings in chunks to a new admin route,
  `POST /api/gluttony-admin/pairings`: `[{key, pairings: [{slot, key, rank, why}]}]`. Each item
  replaces that recipe's whole set. A key plutus does not know (or a removed recipe) is a 400 for
  that item, reported like a refused recipe; the rest are stored.
- Pairings are not part of the recipe payload or its content hash, so a weekly change of scores
  never resends recipes. A recipe whose pairings did not change is not sent (its own hash in
  `data/published.json`).
- Schema migration `schema-part3.sql`: `RecipePairings (RecipeID, Slot, PairedID, Rank, Why)`,
  primary key `(RecipeID, Slot, Rank)`, both ids referencing `Recipes` with `ON DELETE CASCADE`.

### 2.4 Server and app

- `GET /recipes/<id>` adds `pairings: [{slot, items: [{why, …tile fields}]}]`: per slot, in rank
  order, the first 2 paired recipes that are shown and fit the account's diet profile (unless
  `profile=off`, as for listings). A slot with none is left out; no pairings is an empty list.
  `docs/api.md` documents it.
- **Recipe page:** a "Goes with" section after the steps, one row per slot with its label
  (words in `words.mjs`), small tiles (picture, title, time) and the why line in small print. A
  tile opens that recipe. No section when the list is empty.
- **Offline:** the offline copy keeps the pairings as fetched; opening a paired recipe needs a
  connection unless it is saved too. Cook mode does not show pairings.

### 2.5 Rollout

1. On plutus: back up `gluttonyDB`, load `schema-part3.sql`, copy the changed server files into
   `/database/API/util/` (Claude can do the copy), then restart Caduceus. The backup, the schema
   load and the restart need `sudo`, so they are the owner's.
2. VM 103: copy the scraper, re-gate to publish the pairings; the report gives pairings per slot
   and how many recipes have none.
3. App build and release.

## Milestone 3: the glossary

### 3.1 The words (`app/assets/glossary.json`)

```json
{"term": "fold", "forms": ["fold", "folds", "folding", "folded"], "kind": "technique",
 "text": "Turn a light mixture into a heavier one with slow scoops of a spatula, so the air stays in."}
{"term": "caster sugar", "forms": ["caster sugar"], "kind": "word",
 "text": "Fine white sugar that dissolves fast.", "same": "superfine sugar"}
```

- About 150 to 200 terms of two kinds: **techniques** (fold, deglaze, blind bake, julienne,
  muddle, double strain) and **kitchen words** that differ between British and American cooking
  (caster sugar, double cream, hob, grill = broiler, cornflour, coriander = cilantro, spring
  onion, ramekin).
- **Choosing them:** `scraper/scripts/glossaryCandidates.py` counts candidate words and phrases
  (from a seed list of techniques and British/American pairs) across the shown recipes' steps and
  ingredient lines in the page cache, and lists them by frequency. It prints counts only; no
  recipe text leaves the cache. The terms that appear are written up; the owner reviews the list
  before the build that ships it.
- **Upkeep:** the weekly dry-run report lists seed words that appear but have no entry yet.
  Adding a term is an edit to the JSON, then an app build.
- Definitions are one or two sentences in Gluttony's voice, written for this file (no third-party
  text, no licence to carry).

### 3.2 In the app (`app/qml/logic/glossary.mjs`)

- `marks(text, glossary)` returns the spans to mark in one step or ingredient line: whole words
  only, longest form first ("blind bake" before "bake"), the first occurrence of a term per step
  or line, case-insensitive.
- A stop list in the file (`bake`, `mix`, `stir`, `cook`, `chop` and other everyday words) is
  never marked.
- Marked words get a dotted underline on the recipe page (steps and ingredients) and in cook
  mode. Hover shows the definition (and "same as …"); click or tap pins it in a small popup that
  closes on Esc or a click elsewhere.

### 3.3 Rollout

App build and release, after the owner has reviewed the term list.

## Testing

- **Scraper (pytest, hand-written fixtures; nothing scraped is committed):** the drink-category
  rule (match, no match, a drink site kept, kind set before tagging); each pairing score part and
  the slot table; "serve with" extraction and matching (garnish-only phrases match nothing);
  ties stable; the top-8 cut and the why words; the pairings publish (chunks, unchanged sets not
  sent, refused items reported); the glossary candidate count prints no recipe text.
- **Server (pytest on the fake connection):** `schema-part3.sql`; the admin route replaces a set,
  refuses unknown keys per item, needs the admin token; `/recipes/<id>` pairings drop hidden and
  removed recipes, apply the diet profile, honour `profile=off`, cap 2 per slot, and give an empty
  list when there are none.
- **App (QML table tests):** jigger rounding (US quarters, metric 5 ml, the 7.5 ml floor, the
  120 ml cap, scaling before rounding, food unchanged, bare `oz` in a drink); glossary marks
  (longest wins, word edges, first per step, forms, stop list); the "Goes with" section hidden
  when empty.
- **Stub server:** the fixture gains a drink with spoon and ml lines, pairings on a main, and
  steps that use glossary words, so every feature can be tried without plutus.

## Milestones

Each in a fresh session.

1. **Site drinks and jigger amounts:** the drink-category rule, the report lines, jigger
   rounding, re-gate, release.
2. **Pairings:** rules file, scoring, publish route and table, recipe detail, "Goes with"
   section, migration, re-gate, release.
3. **Glossary:** candidate script, the term list (reviewed by the owner), `glossary.mjs`,
   underline and popup, release.

## Done when

"Bottoms up" lists the sites' drinks, and their amounts read as a jigger measures them. A main's
recipe page suggests a side, a sauce, a dessert and a drink from the catalog, each with a reason,
respecting the diet profile. Cooking words and British kitchen words in the steps explain
themselves on hover or tap, offline too. Nothing scraped is in the public repo.
