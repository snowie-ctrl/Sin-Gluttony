# Gluttony app API (part 2)

The contract between the Gluttony app (`app/`) and the routes on plutus (`server/gluttonyRoutes.py`,
`server/gluttonyUserRoutes.py`), both at `/api/gluttony`. The app's stub (`app/tests/stub/stub_server.py`)
imitates it. Milestone 1's routes are below; milestones 2 and 3 add theirs here.

## Conventions

- JSON bodies. Every answer has `status`: `"ok"`, `"error"`, or a named outcome (`"new"`, `"invalid_key"`, …).
  Errors carry `message`. Data is under `data`, except the sign-in answers (`UID`, `username`, `token` beside
  `status`), which keep Pageturner's shape.
- Every route needs the header `X-Session-Token` except `GET /ping`, `POST /auth` and `POST /device/identify`.
  Without a live session: `401 {"status":"error","message":"not signed in"}`.
- The app also sends `X-Device-Fingerprint` (SHA-256 of the machine id) on every request.
- `POST /auth` allows 5 attempts a minute and `POST /device/identify` 10, per caller: `429 "too many attempts"`.
- A 5xx through the tunnel is `{"status":"error","message":"server error"}`; at home it names the cause.
- Pictures (`/images/<id>`, `/thumbs/<id>`) need the session too; the app's network factory sends it.

## Account

| Route | Body | Answer |
|---|---|---|
| `GET /ping` | | `{"status":"ok"}` |
| `POST /device/identify` | `{fingerprint}` | known: `{status:"ok", UID, username, token}`; unknown: `{status:"new"}` |
| `POST /auth` | `{username, password, fingerprint, key?}` | `{status:"ok", UID, username, token}`. With `key` it signs up: `403 invalid_key` (unknown or used key), `409 username_taken`, `400` for a username outside 3–32 characters or a password outside 8–256. Without `key`: `401 invalid_credentials`. |
| `POST /auth/logout` | `{fingerprint}` | `{status:"ok"}`; this device is forgotten and its sessions end |
| `POST /user/username` | `{username}` | `{status:"ok", username}`; `409 username_taken`; `400` outside 3–32 |
| `POST /user/password` | `{current, password}` | `{status:"ok"}`, every other device signed out; `401 invalid_credentials` (a wrong current password, which is not an ended session) |
| `GET /devices` | | `data: [{id, label, current, lastSignIn}]`, newest first; `id` is the first 16 hex of the fingerprint's SHA-256 |
| `POST /devices/remove` | `{id}` | `{status:"ok"}`; `400` for this device (sign out instead) |

## Diet profile

| Route | Body | Answer |
|---|---|---|
| `GET /me/diet` | | `data: {diets: [...], avoid: [...]}` |
| `POST /me/diet` | `{diets: [...], avoid: [...]}` | the stored profile, same shape; `400 unknown diet: x` / `400 unknown avoid: x` |

Diets: `vegetarian`, `vegan`, `gluten-free`, `dairy-free`. Avoid items: `meat`, `poultry`, `fish`, `shellfish`,
`dairy`, `egg`, `gluten`, `tree-nut`, `peanut`, `soy`, `sesame`, `alcohol`, `honey`. Each word appears once, in this order.

## Catalog

`GET /recipes` filters (any combination; within one filter any value may match, across filters all must):
`kind` (`food`/`drink`), `course`, `cuisine`, `difficulty` (1–3), `maxMinutes`, `flavour`, `occasion`, `alcohol`
(`alcoholic`, `non-alcoholic`, `optional`), `diet`, `avoid`, `include`, `exclude` (ingredient ids; children count),
`q` (text), `sort` (`relevance`, `quickest`, `shuffle`; relevance only with `q`), `page`, `pageSize` (≤ 60),
`profile` (`on`, the default, or `off`). Lists are comma separated.

- **The profile:** unless `profile=off`, the account's saved diets and avoids are added to `diet` and `avoid`.
  Only `Complete` recipes can meet a diet or avoid an allergen, whether asked for or saved.
- `data: {total, page, pageSize, recipes: [tile]}`; a tile is
  `{id, kind, title, course, cuisine, totalMinutes, timeFrom, difficulty, hasImage, source, craving, devouredCount,
  stars}`. The last three are the signed-in person's flags (see "What you keep").

| Route | Answer |
|---|---|
| `GET /recipes/<id>` | `data`: the full recipe (part 1's shape: `servings`, `servingsFrom`, times and their `…From`, `ingredients: [{line, quantity, quantityMax, unit, ingredientId, name, note, optional, group}]`, `steps: [{text, group}]`, `tags: {flavour, occasion, source}`, `facts: {complete, contains, diets}`, `versions: [{id, title, source, hasImage, craving, devouredCount, stars}]`, credit fields), plus `removed` and `mine` (see "What you keep"). `404` when missing, or removed and not kept by this person. |
| `GET /filters` | `data: {kinds, courses, cuisines, difficulties, flavours, occasions, diets: [{value, count}], avoid: [...]}`, whole-catalog counts |
| `GET /ingredients?q=` | `data: [{id, name}]`, up to 20; `q` 1–60 characters |
| `GET /random` | the `/recipes` filters (`sort`, `page` ignored); `data: {recipe: tile or null}` |
| `GET /images/<id>`, `GET /thumbs/<id>` | JPEG (1200 px, 400 px); `404` without one |

## Home

`GET /home?tz=<IANA zone>&profile=on|off` → `data: {date, pick: tile or null, picks: [tile]}`.

- `date` is today in `tz`; an unknown or empty zone means UTC.
- The candidates are food, course `main` or `breakfast`, with a picture, fitting the profile.
- They are ordered by a hash of recipe, account and date, so a person sees the same pick all day. `pick` is the
  first; `picks` are the next eight.

## What you keep (milestone 2)

Everything here belongs to the signed-in person. Every list, item, mark, rating and note is looked up together with
the person's id, so someone else's id, like an unknown one, is `404`, never `403`.

- **Tile flags:** every tile list (`/recipes`, `/random`, `versions`, `/home`, `/lists/<id>/recipes`, `/devoured`)
  adds `craving` (true when the recipe is in the person's Cravings), `devouredCount` (how many times they marked it
  Devoured) and `stars` (1–5, or null). They are read in one query per answer, whatever the page size.
- **The `mine` block:** `/recipes/<id>` adds `mine: {craving, lists: [listId], devoured: [{id, on}], stars, note}`.
  `lists` holds the person's own lists (not Cravings, which is `craving`); `devoured` is newest first; `on` is
  `YYYY-MM-DD`; `note` is the text or null.
- **Removed recipes:** a recipe part 1 has removed never appears in `/recipes`, `/random`, Home's picks or `versions`.
  Its detail and pictures answer only to a person who has it in a list (Cravings included), has devoured it, or has
  a note on it; the detail then has `removed: true` (`false` otherwise). Everyone else gets `404`. Tiles from the
  person's own lists and history carry `removed` too.

### Lists

Every account has one list of kind `cravings` (♥ Cravings), made at sign-up; it can't be renamed, deleted or moved.
The rest are `custom`. A list reads in the person's order; a recipe added goes on top.

| Route | Body | Answer |
|---|---|---|
| `GET /lists` | | `data: [{id, title, kind, count}]`, Cravings first, then the person's order |
| `POST /lists/create` | `{title}` | `data`: the new list. `400 "a list title is 1 to 60 characters"` (trimmed); `400 "you can have at most 50 lists"` (Cravings counts) |
| `POST /lists/rename` | `{id, title}` | `data`: the list. `400 "Cravings can't be renamed"` |
| `POST /lists/delete` | `{id}` | `{status:"ok"}`; the items go, the recipes stay. `400 "Cravings can't be deleted"` |
| `POST /lists/reorder` | `{id, after}` | `{status:"ok"}`; the list moves right after `after` (a list id), or first for `null` or Cravings' id. `400 "Cravings stays first"` |
| `POST /lists/items/add` | `{listId, recipeId}` | `data: {listId, recipeId, count}`; adding a recipe already there changes nothing. `400 "a list holds at most 2000 recipes"`; `404 "no such recipe"` for one the person may not see |
| `POST /lists/items/remove` | `{listId, recipeId}` | `data: {listId, recipeId, count}`; a recipe not on the list is nothing to remove |
| `POST /lists/items/reorder` | `{listId, recipeId, after}` | `{status:"ok"}`; the recipe moves right after `after` (a recipe id on this list), or to the top for `null`. `404 "that recipe is not on this list"` for either id |
| `GET /lists/<id>/recipes` | `?page=&pageSize=` (≤ 60) | `data: {total, page, pageSize, list: {id, title, kind, count}, recipes: [tile]}`; tiles carry the flags and `removed` |

An unknown or someone else's list is `404 "no such list"`. Ids in bodies are whole numbers; anything else is `400`.
