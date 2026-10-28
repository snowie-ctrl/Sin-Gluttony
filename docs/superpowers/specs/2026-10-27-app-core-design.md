# Gluttony part 2: the app core

Status: approved by the owner 2026-10-27 (designed in conversation section by section, with the
look chosen from mockups).

Part 1 (`2026-10-19-catalog-design.md`) built the catalog: 5,116 recipes in
`gluttonyDB` on plutus, refreshed weekly by the scraper on VM 103, with a
LAN-only read API at `/api/gluttony`. Part 2 is the desktop app on top of it:
accounts, browsing, filters, search, the recipe page, cook mode and what a
person keeps. It also opens the read API to the outside, behind sessions.

## Why

Gluttony answers "what should I eat (or drink)?". A person opens it with a
vague idea ("quick and easy", "something to impress at a party", "sweet and
Japanese"), narrows the catalog in a few taps, and lands on a recipe they would
actually make. Part 2 is the first time anyone can do that: until now the
catalog is only reachable through raw API calls and Surrogate.

## Decisions

| Topic | Decision |
|---|---|
| Platform | Desktop (Windows) first, Qt 6.11.1 / QML, as Pageturner. iOS is part 7. |
| Foundations | Copied from Pageturner (and `KeepAwake` from Showtime), each copied file naming its source and commit. Neither source repo is changed. |
| Users | The owner and friends, with Gluttony's own accounts (not shared with Showtime or Pageturner): sign-up with a login key, device sign-in. |
| Login keys | The owner inserts `LoginKeys` rows by hand in SQL. No Surrogate work in part 2. |
| Narrowing | Mood starters on home open the results with filters already set, and the filters are adjusted from there. |
| What a person keeps | Cravings (favourites), named lists, Devoured marks with a date, a 1–5 rating, and a private note per recipe. |
| Diet profile | Saved per account and applied everywhere by default, switchable off for one search. |
| Recipe page | Scale servings, metric/US units, cook mode, and "Seconds?" (other versions of the dish). |
| Offline | Saved recipes only (lists, Cravings, anything opened in cook mode). Browsing and search need the server. |
| Sharing | None. Every account is private. |
| Away from home | Its own tunnel hostname, `gluttony.forculus.net` (created by the owner 2026-10-27). Only `/api/gluttony/` goes through it. Claude wires nginx at rollout. |
| Look | "Gula": the sin's traditional orange, molten into crimson, on a dark chocolate ground, with a cheeky voice. |
| Layouts (chosen from mockups) | Home B (today's pick beside mood tiles), recipe page A (wide picture, ingredients column beside the steps), results with a filter side panel, cook mode with every step listed and the current one lit. |
| Build order | App against a stub server fed by a snapshot of real recipes; the server routes are written beside it and deployed together at the end. |
| Not in part 2 | Nutrition, glossary, pairings, packaged drinks (part 3); pantry and grocery lists (part 4); prices (5); restaurants (6); iOS (7). Gluttony never shows an intake tracker: Pride owns what a person ate. |

## 1. Architecture

```
 QML pages (Home, Results, Recipe, Cook, Saved, Settings, Sign-in)
   │ bindings / calls                          │ Image { source: … }
   ▼                                           ▼
 Session  Catalog  Recipes  Saved  Diet  Cook   RecipeStore ── disk: accounts/<UID>/recipes/
   └────────┴────────┴───────┴─────┴─────┘          │ (network only when not on disk)
                 Api ── SessionAuth ────────────────┘
                  │  (LAN address if it answers, gluttony.forculus.net otherwise)
                  ▼
   gluttonyRoutes.py (session hook) + gluttonyUserRoutes.py → gluttonyDB
```

### Repository layout

```
Gluttony/                         git repository (private, no remote yet)
  app/                            the Qt project (CMakeLists.txt, target appGluttony, QML module Gluttony)
    main.cpp
    api/          Api, SessionAuth, AuthNetworkFactory, AppConfig, TileModel (copied from Pageturner)
    services/     Session, Catalog, Recipes, Saved, Diet, Cook, RecipeStore, AccountStore (copied), KeepAwake (copied from Showtime)
    assets/       Preferences (copied, Gluttony's tokens), fonts (Playfair Display), placeholders, icons
    qml/          Main.qml, NavShell.qml, pages/, component/, logic/*.mjs
    tests/        C++ tests, qml/, stub/ (stub server, grab.ps1)
    config/secrets.json           gitignored; secrets.example.json committed
  server/                         part 1's routes, plus gluttonyUserRoutes.py and schema-part2.sql
  scraper/                        part 1, unchanged
```

The repository is private, so `server/` stays tracked, unlike Pageturner's. The
server address, SSH details and `config/secrets.json` are still never committed.

### Copied foundations

- **From Pageturner:**
  - `Api`: the envelope, `whenReady`, LAN/public switching, the offline state and backing-off `/ping`.
  - `SessionAuth` and `AuthNetworkFactory`: the session token on image requests, limited to the server's origins.
  - `AppConfig`: the `secrets.json` search order with `$GLUTTONY_SECRETS`, and the device fingerprint.
  - `Preferences`: reflected `MEMBER` properties in a QSettings ini, `Gluttony/preferences.ini`.
  - `TileModel`, and `AccountStore`: the per-account folder, wiped on sign-out.
  - The test harness pattern, the stub server, and `grab.ps1` with `GLUTTONY_GRAB` / `GLUTTONY_CLICK` hooks in `main.cpp`.
- **From Showtime:** `KeepAwake`, for cook mode.

Not copied: the reader, `PageStore`, `Progress`, AniList, gamification, downloads.

### Services

Each service is a context property declared before the `QQmlApplicationEngine`.

- **Session:**
  - device sign-in (`/device/identify`)
  - sign-in, and sign-up with a key (`/auth`)
  - sign-out (removes the device)
  - username, password, devices
  
  An ended session returns to sign-in.
- **Catalog:** filter options, one results query (filters, sort, paging), Ctrl+K search, and the ingredient picker.
- **Recipes:** opens a recipe, and holds the chosen servings and units for it.
- **Saved:** lists, Cravings, Devoured, stars and notes, plus the offline queue for Devoured, stars and notes.
- **Diet:** the account's profile, and whether it is on for the current search.
- **Cook:** the open cook session (current step, ticks, timers) and the keep-awake.
- **RecipeStore:** the offline copies of saved recipes and their pictures.

### Logic helpers

These are pure functions in `qml/logic/*.mjs`, table-tested with `qmltestrunner`:

- `scale.mjs`: servings, ranges, multipliers.
- `units.mjs`: metric/US, kitchen fractions, temperatures.
- `moods.mjs`: the mood definitions.
- `stepIngredients.mjs`: which ingredients a step mentions.
- `words.mjs`: every word the app says.

## 2. Data (`gluttonyDB`, new tables)

The catalog tables are unchanged. Multi-valued facts live in child tables,
never SET, ENUM or JSON columns. `server/schema-part2.sql` creates these:

- **`Users`** (`UserID`, `Username` unique, `PasswordHash`, `CreatedAt`)
- **`Devices`** (`Fingerprint` PK, `UserID`), as in Pageturner: a device's last sign-in is read from its newest session.
- **`Sessions`** (`Token` CHAR(64) PK, `UserID`, `DeviceFingerprint`, `ExpiresAt`)
- **`LoginKeys`** (`KeyValue` PK, `Used`, `UsedBy`, `CreatedAt`). The owner inserts rows by hand.
- **`UserDiets`** (`UserID`, `Diet`) with part 1's diet words. **`UserAvoids`** (`UserID`, `Item`) with part 1's contains words.
- **`Lists`** (`ListID`, `UserID`, `Title`, `Kind` = `cravings` or `custom`, `CreatedAt`). Each account has exactly one `cravings` list, made at sign-up, which can't be renamed or deleted.
- **`ListItems`** (`ListID`, `RecipeID`, `OrderIndex`, `AddedAt`, PK `(ListID, RecipeID)`)
- **`Devoured`** (`DevouredID`, `UserID`, `RecipeID`, `MadeOn` DATE, `ClientID` CHAR(36) unique, `CreatedAt`). There is one row per time a person made the recipe. `ClientID` is made by the app, so a resent offline mark is stored once.
- **`Ratings`** (`UserID`, `RecipeID`, `Stars` 1–5, `UpdatedAt`, PK `(UserID, RecipeID)`)
- **`Notes`** (`UserID`, `RecipeID`, `Text` up to 2,000 characters, `UpdatedAt`, PK `(UserID, RecipeID)`)

Indexes: `Devoured (UserID, MadeOn)`, `ListItems (RecipeID)`, `Sessions (UserID)`.
User rows reference `Recipes` with `ON DELETE CASCADE`. That never fires in
practice, because part 1 only ever hides recipes (`RemovedAt`).

## 3. Server routes

Everything is under `/api/gluttony`: part 1's `gluttonyRoutes.py`, plus a new
`gluttonyUserRoutes.py` blueprint on the same prefix. The admin blueprint is
unchanged and LAN-only.

### Conventions (Pageturner's)

- One `requireSession` hook replaces part 1's `lanOnly` check. Nothing else calls the read API: Surrogate and the scraper use only the admin routes. `PUBLIC_ROUTES` are `ping`, `auth` and `identifyDevice`. Routes read the user from `requestUID()`, never from the request.
- `/auth` (5 per minute) and `/device/identify` (10 per minute) are rate-limited per `clientIP()` (`CF-Connecting-IP`, then `X-Real-IP`).
- Password hashing and session lifetime are Pageturner's.
- Responses are `{"status": …}`. A 5xx to a tunnel request becomes `{"status":"error","message":"server error"}`, and the detail goes to the audit log.
- Pictures (`/images/<id>`, `/thumbs/<id>`) need the session. The app's `SessionAuth` sends it.

### Routes

| Area | Routes |
|---|---|
| Account | `GET /ping`, `POST /auth` (sign in; sign up with `key`), `POST /auth/logout`, `POST /device/identify`, `POST /user/username`, `POST /user/password`, `GET /devices`, `POST /devices/remove` |
| Diet | `GET /me/diet`, `POST /me/diet {diets, avoid}` |
| Catalog | part 1's `GET /recipes`, `/recipes/<id>`, `/filters`, `/ingredients`, `/images/<id>`, `/thumbs/<id>`; new `GET /random` (one recipe matching the same filters) |
| Home | `GET /home?tz=` (today's pick, Cravings, Again?, today's picks) |
| Lists | `GET /lists`, `POST /lists/create`, `/lists/rename`, `/lists/delete`, `/lists/items/add`, `/lists/items/remove`, `/lists/items/reorder`; `GET /lists/<id>/recipes` (paged tiles) |
| Yours | `POST /devoured/add {recipeId, on, clientId}`, `POST /devoured/remove {id}`, `GET /devoured` (paged history), `POST /rating {recipeId, stars or null}`, `POST /note {recipeId, text}` (empty text deletes), `POST /sync/batch`, `GET /saved/manifest` |

### Changes to part 1's read routes

- **Diet profile:**
  - `/recipes`, `/random` and `/home` add the account's diets and avoids to whatever the request asks for, unless `profile=off`. The name `diet` is already part 1's filter key, which is why this one is `profile`.
  - Part 1's safety rule holds: only `Complete` recipes count as meeting a diet or being free of an allergen.
- **New filter `alcohol`** (`alcoholic`, `non-alcoholic`, `optional`) on `Recipes.Alcohol`, for drinks.
- **Tile flags:**
  - Every tile list adds the user's flags: `craving`, `devouredCount`, `stars`.
  - One `attachTileFlags` adds them in a fixed number of queries, whatever the page size.
- **The `mine` block:** `/recipes/<id>` adds `mine: {craving, lists, devoured: [{id, on}], stars, note}`.
- **Removed recipes:**
  - A recipe with `RemovedAt` set still never appears in `/recipes`, `/random`, `/home` picks or Seconds?.
  - Its detail and pictures answer only to a user who has it in a list, has devoured it, or has a note on it. The detail then carries `removed: true`.
  - Everyone else gets `404`.

### Rules

- **Today's pick:**
  - The pick is the same all day, in the viewer's zone (`tz`, `zoneinfo`, UTC for an unknown name).
  - It is chosen by hashing UID and date over recipes that have a picture, fit the profile, are food courses `main` or `breakfast`, and weren't devoured by this user in the last 30 days.
  - Today's picks (8 tiles) use the same hash for the next eight.
- **Sign-up:**
  - Sign-up takes an unused key, marks it `Used`/`UsedBy`, and creates the Cravings list, all in one transaction.
  - A used or unknown key gets `403 invalid_key`, as in Pageturner.
- **Ownership:** every list, item, devoured row, rating and note is looked up together with the user's id. Someone else's id gets `404`, never `403`.
- **`/sync/batch`:**
  - Up to 500 queued operations, applied in `at` order.
  - Devoured adds are idempotent by `clientId`.
  - For stars and notes, the newest `at` wins, so a late queue never overwrites a newer change.
  - It answers per operation: applied, already applied, or refused with a reason.
- **`/saved/manifest`:**
  - Every recipe in the user's lists (Cravings included), with each recipe's `UpdatedAt`.
  - Plus every recipe opened in cook mode, which the app sends as `extra=` ids; those are its own, not stored server-side.
- **Limits:**
  - Username: 3–32 characters.
  - List title: 1–60 characters.
  - Lists: 50 per account.
  - Recipes: 2,000 per list.
  - Note: 2,000 characters.
  - Batch: 500 operations.

## 4. The pages

### Navigation

An icon rail on the left: Home, Browse, Saved (Cravings, lists, Devoured), and
Settings. Search is on every page (Ctrl+K). The diet chip
("Vegetarian · no peanuts") is at the top of Home and Results whenever the
profile has anything in it.

### Sign-in

A known device signs in by itself. Otherwise, a username and password. A new
account also needs a login key.

### Home (layout B)

- At the top, **Today's temptation** is a large picture with its title, cuisine, time and effort. Beside it are four mood tiles, with **Go on, then** under them.
- Below come the rows: **Cravings**, **Again?** (recently devoured), and **Today's picks**.
- The moods (`moods.mjs`) are a fixed list of filter sets:
  - **Quick fix:** `kind=food`, `maxMinutes=30`, `difficulty=1`
  - **Feed a crowd:** `occasion=party`
  - **Sweet tooth:** `course=dessert`
  - **Bottoms up:** `kind=drink`
- A mood opens Results with its filters set and its name as the page title.
- **Go on, then** asks `/random` with the profile and opens the recipe.

### Results (filter side panel)

- A mood, a search or Browse opens the same page.
- The left panel groups:
  - Your diet (on/off)
  - Food or drink
  - Time (15, 30, 60 minutes, any)
  - Effort
  - Course
  - Cuisine
  - Taste
  - Occasion
  - Alcohol (drinks only)
  - Avoid (allergens)
  - Must include and Leave out (an ingredient picker over `/ingredients`)
- Counts beside the options are whole-catalog counts from `/filters`. The panel collapses to a button.
- Sort: relevance (when searching), quickest, or the daily shuffle. Pages load as the grid scrolls.
- **Tiles:**
  - The picture sits on `surfaceArt`, with the title, then time and effort ("about 15 min" in italics when guessed), and the ♥, ✓ and ★ badges.
  - A tile with no picture uses part 1's course placeholder.

### Search (Ctrl+K)

- A popup lists matching recipes (part 1's full-text search) and matching ingredients. The arrow keys walk it.
- Choosing an ingredient opens Results with that ingredient as Must include.
- Enter opens Results searched for the typed text.

### Recipe page (layout A)

- **Top:**
  - A wide picture with the title over it, and cuisine · course · source.
  - Chips for time, effort, servings, contains, diets and taste. A value whose `…From` is `rule` reads "about …" in italics.
  - When the profile is on and the recipe isn't `Complete` (reached through Seconds?, a list, or the profile switched off), a warning chip says "Some ingredients unknown, may not suit your diet".
- **Actions:** ▶ Cook mode, ♥ Craving, + List, ✓ Devoured (with today's date, changeable) and the stars, ✎ Note. A note shows under the actions.
- **Body:**
  - **Ingredients** on the left: a column that stays put while the page scrolls, with group headings, the servings stepper and the metric/US switch. Optional lines are marked.
  - **Method** on the right, with group headings, and a timer chip wherever a step states a time.
- **Bottom:**
  - **Seconds?**: the other versions (same `DishKey`) as tiles.
  - Then the credit: the licence, the source link, and the picture credit, as part 1's sources require.

### Scaling and units

- **Scaling:**
  - A parsed quantity is multiplied by (chosen ÷ stated servings). Both ends of a range scale.
  - A recipe with no stated servings offers ×½, ×1, ×2, ×3 instead of a servings count.
  - A line with no parsed quantity, and "to taste", is shown as written.
  - Counts of pieces, cans and cloves scale, but keep their wording ("4 eggs" becomes "2 eggs").
- **Units:**
  - **US:** volumes as tsp, tbsp, cup and fl oz, and weights as oz and lb, with kitchen fractions (¼ ⅓ ½ ⅔ ¾).
  - **Metric:** ml, l, g and kg, rounded sensibly (to the nearest 5 g over 100 g, to 1 g under).
  - Volume never becomes weight, because that would need densities.
- **Temperatures:** a temperature in a step ("180°C", "350 F") shows the other scale in brackets.
- **The original line:** clicking a scaled or converted line shows its original text.
- **Where the choice lives:** the units choice is a `Preferences` setting (default metric). The servings choice is per recipe and per visit.

### Saved

- Tabs: **Cravings**, each named list, and **Devoured**.
- Lists can be created, renamed, deleted and reordered. Their items are reordered by dragging.
- **Devoured** is the history, newest first, with dates and stars. It can be sorted by your stars.
- A removed recipe shows "gone from its source" and still opens.

### Settings

- **Account:** username, password, devices (forget one), sign out.
- **Diet profile:** the diets and the avoid items.
- **Units:** metric or US.
- **Colours:** reset.
- **Connection:** "Connected at home" or public.
- **Waiting to sync:** queued writes that failed 5 times, with Retry and Discard.

## 5. Cook mode

- It opens full screen from ▶. `KeepAwake` keeps the screen on while it is open.
- **Steps:** every step is listed. The current one is enlarged and lit, and the rest are dimmed. ↑ ↓, space and a click move between steps, and Esc leaves.
- **Ingredients column:** it uses the servings and units chosen on the recipe page. Each line can be ticked off.
  - The lines the current step mentions are highlighted.
  - `stepIngredients.mjs` matches the step's text, as whole words, against each line's ingredient name (`name`, or the cleaned unknown name) and its last word ("chicken thighs" also matches "chicken").
- **Timers:**
  - A timer chip on a step (a stated duration, parsed by the same rules as part 1's step times) starts a countdown.
  - Several can run at once. They stay in a corner stack while the cook moves on, and each chimes and flashes when done.
  - They keep running after cook mode closes, shown in the rail, until dismissed.
- **Resume:** the current step and ticks are kept for that recipe for 12 hours (per device, in the account folder), so coming back resumes.
- **Offline copy:** opening cook mode stores the recipe in `RecipeStore`.

## 6. Offline

- **What is kept:**
  - `RecipeStore` keeps the full recipe JSON and the large picture for every saved recipe and every recipe opened in cook mode.
  - The files are under `<data>/accounts/<UID>/recipes/<id>.json` and `…/<id>.jpg`, in Pageturner's `AccountStore` folder.
  - At sign-in and on reconnect, the app fetches `/saved/manifest` and refreshes any copy whose `UpdatedAt` has moved on. A recipe that leaves the lists (and isn't a cook-mode copy younger than 30 days) is deleted.
- **What works offline:**
  - Home shows the saved rows only. Results and search say "You're offline" and offer the saved recipes.
  - The recipe page and cook mode work fully from the copy.
  - Thumbnails come from the large picture.
- **The queue:**
  - Devoured marks, stars and notes made offline go into a queue in the account folder, sent with `/sync/batch` on reconnect.
  - List changes need the connection, and say so.
- **Connection:** handled as in Pageturner. The home address is tried first, then `gluttony.forculus.net`, with the Offline banner and the `/ping` back-off.
- **Sign-out:** signing out deletes the account's folder, queue included, after a warning when the queue isn't empty. A forgotten device or an ended session only closes it, as in Pageturner.

## 7. Look and voice

### Tokens (`Preferences`, resettable)

| token | value | used for |
|---|---|---|
| `backgroundPrimary` | `#140c08` | the page behind everything |
| `backgroundSecondary` | `#22140d` | panels, the rail, the top bar, mood cards |
| `backgroundTertiary` | `#2e1b12` | fields, pills, hovered rows |
| `surfaceArt` | `#161312` | the ground under every picture: tile frames, the hero, Seconds? |
| `accentColor` | `#ff7a1a` | focus, selection, the active rail item, headings |
| `accentDeep` | `#c8212f` | the end of the molten gradient (`accentColor` → `accentDeep`) |
| `accentSubtle` | `#3a1a0d` | accent-tinted grounds: a selected chip, the active rail pill |
| `borderColor` | `#3a2418` | hairlines, field borders, dividers |
| `textPrimary` | `#fbeee2` | body and headings |
| `textSecondary` | `#d8b9a0` | supporting text |
| `textMuted` | `#9a7a64` | placeholders, metadata, counts |
| `dangerColor` | `#e23d3d` | errors and destructive actions |
| `successColor` | `#6fbf73` | ticks, Devoured |

- The gradient is used only on primary actions, mood tiles and the "Today's temptation" badge.
- The accent ends in crimson, so destructive buttons are never gradient-filled. They are outlined in `dangerColor` and named in words.
- Pictures always sit on `surfaceArt`, never on a warm ground. This is Lust's rule: the mood lives in the chrome, and the food is not tinted.

### Type, shape, spacing

- **Type:** headings, mood names and page titles use **Playfair Display** (Black / Bold, SIL Open Font License, bundled in `assets/fonts/`). Body text is Tahoma (`appFont`). The sizes follow Lust's scale: display 26, heading 18, body 14, label 13, caption 12.
- **Shape:** `cornerRadius` 12 (cards, tiles, the hero) and `controlRadius` 8 (buttons, fields). Chips and pills are fully round.
- **Spacing:** 8 / 16 / 24.

### Voice (`words.mjs`)

| Plain | Gluttony |
|---|---|
| Favourites | Cravings |
| Made it | Devoured |
| Made before (row) | Again? |
| Surprise me | Go on, then |
| Other versions | Seconds? |
| Daily pick | Today's temptation |
| Search box | What are you hungry for? |
| Moods | Quick fix · Feed a crowd · Sweet tooth · Bottoms up |

Error messages and warnings stay plain: no jokes where something went wrong.

## 8. Errors

- **Server:** bad input gets a `400` that says why. Unknown or someone else's ids get `404`. Limits are in section 3.
- **Session:** a `401` other than `invalid_credentials` (a wrong current password) ends the session and returns to sign-in.
- **Page loads:** a failed page load shows the reason in plain words, with Retry.
- **Pictures:** a picture that fails to load shows the course placeholder, never an empty box.
- **The queue:** a queued write that fails is retried on each reconnect. After 5 failures it moves to Settings › Waiting to sync, with Retry and Discard.
- **Lost connection:** losing the connection mid-recipe keeps the open page and cook mode working from memory, and from the offline copy when there is one.

## 9. Testing

Test first.

- **Server:** pytest against part 1's fake connection. It covers:
  - every new route
  - the session hook and the public routes
  - rate limits
  - sign-up's one transaction
  - the profile and the safety rule
  - `profile=off`
  - `attachTileFlags` in a fixed number of queries
  - today's pick being stable for a day and changing the next
  - `clientId` idempotency
  - newest-`at`-wins
  - removed recipes visible only to their savers
  - ownership `404`s
  
  `gluttonySmoke.py` grows to run every new route against a scratch database.
- **Logic:** `qmltestrunner` table tests for scaling (ranges, counts, no-servings multipliers), units and fractions, temperatures, `stepIngredients`, and the mood filter sets.
- **C++:** Pageturner's harness for `Session`, `RecipeStore` (manifest refresh, deletion, per-account folders) and the offline queue.
- **Stub server:** Pageturner's stub, serving a snapshot of about 300 real recipes and their pictures.
  - The recipes are chosen to cover every source, kind, course, guessed values, unknown ingredients, ranges, group headings and missing pictures.
  - The snapshot is taken once from the LAN read API by `tests/stub/snapshot.py`, in milestone 1, while that API still needs no session. It is kept out of git, because it is the sources' content.
- **Screenshots:** `grab.ps1` captures every page against the stub at the end of each milestone, for the owner's review.

## 10. Milestones

One spec, planned and built one milestone at a time. Each ends in something
runnable.

1. **Foundations and browsing:** the project skeleton and copied foundations, the stub server and snapshot, sign-in, the diet profile, Home, Results with the filter panel, Ctrl+K search, and the recipe page with scaling, units and Seconds?.
2. **What you keep:** Cravings, lists, Devoured with stars, notes, the Saved page, and Settings.
3. **Cook mode and offline:** cook mode with ticks, highlighting and timers; `RecipeStore`; the offline queue and `/sync/batch`.
4. **Real server** (rollout below).

## 11. Rollout (milestone 4)

1. **Schema:** Claude hands over `schema-part2.sql`. The owner runs the smoke test on a scratch database (as in part 1's README), then loads the file into `gluttonyDB`.
2. **Routes:**
   - Claude copies `gluttonyRoutes.py`, `gluttonyUserRoutes.py` and `gluttonyRules.py` to `/database/API/util/` (backups first) and registers `gluttonyUserRoutes` in `Caduceus.py` beside part 1's block.
   - The owner restarts Caduceus.
3. **LAN check:** the app points at plutus on the LAN and is checked page by page against the real catalog.
4. **Tunnel:**
   - Claude wires nginx for `gluttony.forculus.net`: only `/api/gluttony/` is proxied, and `/api/gluttony-admin/` and everything else get 404.
   - Claude then checks from outside: `/api/gluttony/ping` answers, an unsigned `/api/gluttony/recipes` gets 401, and the admin prefix is refused.
5. **First account:** the owner inserts a login key by hand and signs up. Friends' keys are made the same way.

## Done when

- The owner signs up with a key and signs in at home and away, on a device that then signs in by itself.
- From a mood, a search or the filters, a few taps land on a recipe, with the diet profile applied and never breaking the safety rule.
- Scaling, metric/US and cook mode with timers work on real recipes from all three sources.
- Cravings, lists, Devoured, stars and notes persist across devices.
- Saved recipes open with no connection, and Devoured marks, stars and notes made offline arrive after reconnecting.
- From outside, only `/api/gluttony/` answers on `gluttony.forculus.net`, and only with a session (except `ping`, `auth` and `device/identify`).
