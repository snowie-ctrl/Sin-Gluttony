# Gluttony server pieces

Deployed to plutus beside the other blueprints, in `/database/API/util/`. In part 1 nothing here is public: neither
prefix goes through the tunnel, and `gluttonyRoutes.py` answers 404 to any request that did. From part 2, the read
API at `/api/gluttony/` is public through the tunnel at `gluttony.forculus.net`, but every request except `ping`,
`auth` and `device/identify` needs a session (`gluttonySession.py`); `/api/gluttony-admin/` stays LAN only.

| File | Goes to |
|---|---|
| `gluttonyAdminRoutes.py`, `gluttonyRoutes.py`, `gluttonyRules.py` | `/database/API/util/` |
| `gluttonySession.py`, `gluttonyKept.py`, `gluttonyUserRoutes.py` | `/database/API/util/` (from part 2) |
| `gluttonyAdminConfig.json` (from the example; never committed) | `/database/API/util/`, `chmod 600` |
| `gluttonySmoke.py` | `/database/API/util/` (only for the smoke test; harmless if left) |
| `schema.sql` | run once by the owner |
| `schema-part2.sql` | run once by the owner, after part 2's smoke test |
| `schema-catalog.sql` | run once by the owner, before the new catalog's server code (new catalog, milestone 3) |
| `gluttonySwitch.py` | `/database/API/util/` (only for the catalog switch; harmless if left) |
| `schema-part3.sql` | run once by the owner, before part 3's pairing server code (`RecipePairings`) |

Tests: `cd server && .venv/Scripts/python.exe -m pytest -q`.

## Before the smoke test (owner)

1. Check that `DBUtils.py` maps `"gluttony"` to `gluttonyDB` the way it maps `"pageturner"` to `pageturnerDB`; if it
   doesn't, add the mapping. The routes and the smoke test both connect through this name.
2. Create an empty `gluttonyDB` and grant the API user on it. This is harmless: `schema.sql` is not loaded into it
   until cut-over. The smoke test connects to `gluttonyDB` before it switches to the scratch database, so this must
   exist first.
   `sudo mysql -e "CREATE DATABASE gluttonyDB CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"`,
   `sudo mysql -e "GRANT ALL ON gluttonyDB.* TO '<the API user>'@'localhost'"`

A 500 on the `seed` step of the smoke test usually means step 1 or step 2 above was missed.

## The smoke test (owner, then Claude or the owner)

The scratch database's name must contain `smoke` (any case); the tool refuses every other name, `gluttonyDB` included.

Every run, pass or fail, is followed by `DROP DATABASE gluttony_smoke`. The next run starts again from the CREATE,
GRANT and schema steps below. A run that finds rows already in the scratch database fails at `seed` with "the scratch
database is not empty: drop and recreate it".

1. Owner: `sudo mysql -e "CREATE DATABASE gluttony_smoke CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"`,
   `sudo mysql -e "GRANT ALL ON gluttony_smoke.* TO '<the API user>'@'localhost'"`,
   `sudo mysql gluttony_smoke < schema.sql`
2. With the part 1 route files and `gluttonySmoke.py` in `util/` (part 2 adds more files; see below):
   `cd /database/API && /database/venv/bin/python -m util.gluttonySmoke --database gluttony_smoke`
   Every line should start with `PASS`. A `FAIL` line names the step; a failed connection prints its cause to stderr
   beside it.
3. Owner: `sudo mysql -e "DROP DATABASE gluttony_smoke"`, whether the run passed or failed.

## Cut-over, part 1 (owner)

1. Load the schema into the empty `gluttonyDB` created before the smoke test: `sudo mysql gluttonyDB < schema.sql`
   (if `gluttonyDB` was never created, create it and grant the API user first, as in "Before the smoke test").
2. `gluttonyAdminConfig.json` with a long random token, `chmod 600`.
3. In `Caduceus.py`, beside the other blueprints:

   ```python
   try:
       from util.gluttonyAdminRoutes import gluttonyAdminBP
       app.register_blueprint(gluttonyAdminBP, url_prefix="/api/gluttony-admin")
       from util.gluttonyRoutes import gluttonyBP
       app.register_blueprint(gluttonyBP, url_prefix="/api/gluttony")
   except Exception as e:
       print(f"gluttony routes not loaded: {e}")
   ```
4. `sudo mkdir -p /pool/appFiles/gluttony/images /pool/appFiles/gluttony/thumbs` owned by the upload user.
5. Restart `Caduceus.service`.
6. Check from outside that the tunnel does not route either prefix: the public host's `/api/gluttony/ping` must not
   answer `{"status": "ok"}` until milestone 4. (Part 2 opens `/api/gluttony/` on purpose; see below.)

## Part 2 (accounts and the app's routes)

Written in part 2's milestones, deployed together in milestone 4; nothing here is live before then.

- **Smoke test:** as above, with `schema-part2.sql` loaded into the scratch database after `schema.sql`
  (`sudo mysql gluttony_smoke < schema-part2.sql`) and `gluttonyAdminRoutes.py`, `gluttonyRoutes.py`,
  `gluttonyRules.py`, `gluttonySession.py`, `gluttonyKept.py` and `gluttonyUserRoutes.py` in `util/`, beside
  `gluttonySmoke.py`. It now signs up with a key it inserts itself, browses with a session, checks the diet
  profile, Home and Go on, makes and edits lists, marks Devoured (once per clientId), stars and notes, signs up a
  second account to check it sees none of the first one's, removes a recipe and checks only its saver still sees
  it, and signs out. It inserts two login keys and a second recipe on the scratch database.

  Milestone 3 adds `sync` (a batch of offline changes: a mark stored once however often it is sent, a star older
  than the stored one kept out, a newer note applied, a cleared rating not brought back, an unknown recipe refused)
  and `manifest` (every list with its recipes in order, each recipe's `UpdatedAt`, the cook-mode extras). Both need
  `schema-part2.sql` as this milestone leaves it: `Ratings` and `Notes` with `UpdatedAt DATETIME(3)` and nullable stars.

  Milestone 4 adds `mine` to the `manifest` step (the manifest's `mine` must equal the recipe page's) and a
  `together` step: four batches for one unrated recipe sent at the same moment, as two devices reconnecting would.
  Every batch must answer 200 and the newest change must stand. Its PASS line says how many batches met a MySQL lock
  conflict and were tried again; a few is fine, a FAIL is not.
- **Cut-over:** `sudo mysql gluttonyDB < schema-part2.sql`, then in `Caduceus.py`, inside the existing Gluttony
  block, beside `gluttonyBP`:

  ```python
      from util.gluttonyUserRoutes import gluttonyUserBP
      app.register_blueprint(gluttonyUserBP, url_prefix="/api/gluttony")
  ```

  Restart `Caduceus.service`. From then on `/api/gluttony/*` needs a session except `ping`, `auth` and
  `device/identify`.
- **Login keys:** `sudo mysql gluttonyDB -e "INSERT INTO LoginKeys (KeyValue) VALUES ('<a long random key>')"`.
- **The tunnel:** `gluttony.forculus.net` passes only `/api/gluttony/`; `/api/gluttony-admin/` stays LAN only.

## Milestone 4: the rollout

Each server step below waits for the owner's go-ahead at the time. "Claude" steps run from the PC over SSH; "owner"
steps are typed by the owner on plutus.

1. **Check what is there (Claude, read only).** The four part 1 files in `util/` (`gluttonyAdminRoutes.py`,
   `gluttonyRoutes.py`, `gluttonyRules.py`, `gluttonySmoke.py`) match the commit last deployed
   (`git show <commit>:server/<file> | md5sum` against `md5sum` on plutus; `diff --strip-trailing-cr` if only line
   endings differ). `DBUtils.py` maps `"gluttony"`, and how it hands out connections: if it pools, the pool must allow
   four concurrent requests plus their session checks, or the smoke test's `together` step fails with a pool error.
   `Caduceus.py` sets no `MAX_CONTENT_LENGTH`. Read `/etc/nginx/sites-available/forculus.conf` too: the `listen` port and
   the upstream its existing server blocks use, and whether one of them is the `default_server`.
2. **Copy the files (Claude).** Back up the four part 1 files in `util/` (`gluttonyAdminRoutes.py`, `gluttonyRoutes.py`,
   `gluttonyRules.py`, `gluttonySmoke.py`) as `<file>.bak-<date>` in `/database/API/util/`. From `main`, make a tar of
   the server files and unpack it on plutus: `git -c core.autocrlf=false archive -o gluttony-m4.tar main:server gluttonyAdminRoutes.py gluttonyRoutes.py gluttonyRules.py gluttonySession.py gluttonyKept.py gluttonyUserRoutes.py gluttonySmoke.py schema.sql schema-part2.sql`
   (`core.autocrlf=false` keeps the files' LF endings; a Windows checkout's archive is CRLF otherwise),
   copy it to plutus, unpack it with `mkdir -p /tmp/gluttony-m4 && tar -xf gluttony-m4.tar -C /tmp/gluttony-m4`, copy the seven `.py` files
   into `/database/API/util/`, and `/database/venv/bin/python -m py_compile` each `.py`. Caduceus keeps running the old ones until it restarts.
3. **Scratch database (owner).** `gluttony_smoke` as in "The smoke test" above, with `/tmp/gluttony-m4/schema.sql` then
   `/tmp/gluttony-m4/schema-part2.sql` loaded (`sudo mysql gluttony_smoke < /tmp/gluttony-m4/schema.sql`, then
   `sudo mysql gluttony_smoke < /tmp/gluttony-m4/schema-part2.sql`).
4. **Smoke test (Claude), then drop the scratch database (owner).** Every line `PASS`, `together` included.
5. **Load the schema (owner).** `sudo mysql gluttonyDB < /tmp/gluttony-m4/schema-part2.sql`.
6. **Register the user routes (Claude).** Back up `Caduceus.py` as `Caduceus.py.bak-<date>` in `/database/API/`. In it,
   replace the three-line comment above the Gluttony `try:` block with this comment:

   ```python
   # Gluttony's routes (Code-Development/Gluttony server/): the admin routes for its
   # scraper and Surrogate, LAN only, with their own token; the app's routes, public
   # through gluttony.forculus.net behind sessions (gluttonySession.py).
   ```

   Then, inside that block, after `app.register_blueprint(gluttonyBP, url_prefix="/api/gluttony")`, add:

   ```python
       from util.gluttonyUserRoutes import gluttonyUserBP
       app.register_blueprint(gluttonyUserBP, url_prefix="/api/gluttony")
   ```

   Check it compiles (importing `Caduceus` would run its module-level code on the live box):
   `cd /database/API && /database/venv/bin/python -m py_compile Caduceus.py`.
7. **Restart (owner).** `sudo systemctl restart Caduceus.service`. Then
   `journalctl -u Caduceus.service -n 100 --no-pager | grep -i "gluttony routes not loaded"` must print nothing. LAN
   check: `/api/gluttony/ping` answers ok; `/api/gluttony/lists` without a session answers 401 (a 404 means the user
   routes did not load: that route lives only in `gluttonyUserRoutes`).
8. **nginx (Claude).** Back up `/etc/nginx/sites-available/forculus.conf`, add this block beside the others, then
   `sudo nginx -t` and `sudo systemctl reload nginx`. The block's `listen` port and `proxy_pass` upstream must be the
   same as the existing blocks' (step 1); change those two lines if they are not port 80 and `127.0.0.1:5000`:

   ```nginx
   # Gluttony's app API: only its own prefix through the tunnel. The admin prefix
   # (/api/gluttony-admin/) never matches this location and stays LAN-only. A
   # /sync/batch of 500 offline notes can be ~4 MB, past nginx's 1 MB default.
   server {
       listen 80;
       server_name gluttony.forculus.net;
       location /api/gluttony/ {
           client_max_body_size 8m;
           # A zone-wide cache rule must never cache session-protected answers. Not no-store: that would also
       # undo the picture routes' own private one-day cache in the app.
           add_header Cache-Control "private" always;
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
       location / {
           return 404;
       }
   }
   ```
9. **From outside (Claude).** `https://gluttony.forculus.net/api/gluttony/ping` answers ok; `/api/gluttony/recipes`
   answers 401; `/api/gluttony-admin/state` and `/` answer 404. On each other public hostname in `forculus.conf`,
   `/api/gluttony/ping` and `/api/gluttony-admin/state` answer 404. The `cf-cache-status` header on a signed
   `/api/gluttony/images/<id>` (from the live check, or `curl -I` with a token) is not `HIT`.
10. **Login keys (owner).** One for the owner, one for the live check:
    `sudo mysql gluttonyDB -e "INSERT INTO LoginKeys (KeyValue) VALUES ('<a long random key>')"`.
11. **Live check (Claude).** `server/liveCheck.py` on the LAN base with `--sign-up`, then on the public base with
    `--outside --limits` (see its docstring). Every line `PASS`.
12. **Remove the check account (owner).**
    `sudo mysql gluttonyDB -e "DELETE FROM Users WHERE Username = 'claude-check'; DELETE FROM LoginKeys WHERE KeyValue = '<the check key>'"`
    (its lists, marks, ratings, notes, devices and sessions go with it).
13. **The app (owner).** Unzip `Gluttony-<version>-windows-x64.zip` (`app/release.ps1`), put `config\secrets.json`
    beside `Gluttony.exe`, sign up with the key, and go through the pages at home, then away (another network).

## The catalog switch (runbook)

The new catalog's step 3 (spec `2026-11-13-new-catalog-design.md`, §5): the recipe sites are published, and
TheMealDB, TheCocktailDB and Wikibooks leave the app. `gluttonySwitch.py` retires the old recipes (`RemovedAt`; none is
deleted) and moves what people kept on them (list entries, Devoured marks, stars, notes) to the shown site recipe with
the same `DishKey` and kind. With several, it picks the one with the most facts: nutrition from the page, then prep and
cook given, then the wider picture, then the lowest `RecipeID`. A clash (the person already has the new recipe) keeps
the higher rating, joins the notes with a blank line (the note already there first), keeps every Devoured date, and
keeps one list entry. Moved stars and notes take the moment of the move as `UpdatedAt`, so a change queued offline
before the switch never overwrites them. A reference with no match stays on the retired recipe, which the app no
longer shows. A joined note that would pass 2,000 characters is left where it is and counted as "too long to join".

It reads and writes in one transaction, with the old recipes and every row that references one locked. Without
`--apply` it is a dry run: it reports and writes nothing. It is safe to run again: a recipe already retired keeps
its first `RemovedAt`, and a reference still on a retired recipe moves once a match has been published. `--apply`
refuses (exit 1, nothing changed) while no site recipe is shown, or while a kind that has old recipes has none
shown and is not named with `--without KIND`.

The steps run in this order. Each waits for the owner's go-ahead at the time.

1. **Back up (owner).** On plutus:
   `sudo mysqldump --single-transaction --routines gluttonyDB > ~/gluttonyDB-before-switch-<date>.sql` and
   `sudo cp -a /pool/appFiles/gluttony ~/gluttony-files-before-switch-<date>`. Check the dump ends with
   `-- Dump completed`. This backup is the undo for everything below.
2. **Publish the new catalog (VM 103).** Wait until the full trial has finished: the pass below takes
   `run/scraper.lock`, so stop the trial's tmux window first if it is still up. The weekly loop is off. In
   `~/Gluttony/.env` set `CATALOG=new` and `PUBLISH=on`. Then either a full pass,
   `.venv/bin/python main.py --once full`, or, to publish what the full trial already fetched, a re-gate over the
   cache, `.venv/bin/python main.py --once retag`. Check the pass's report (no site stopped; the FDC mappings were
   sent), then `GET /api/gluttony-admin/stats` on the LAN with the admin token in the `X-Admin-Token` header. Go or
   no-go per kind:
   - food: go when the meal sites have shown recipes, with the counts the trial led you to expect.
   - drinks: go only if Difford's was crawled and has shown recipes. Today it refuses the crawler (403), so drinks
     are out for now: no drink is shown, and step 3 needs `--without drink`.
3. **The switch (Claude or the owner, on plutus).** Copy `gluttonySwitch.py` and the current `gluttonyRules.py`
   into `/database/API/util/` (it needs `OLD_SOURCES`), then:
   - dry run: `cd /database/API && /database/venv/bin/python -m util.gluttonySwitch --list`. Read the report: how
     many old recipes people kept, how many have a match, and per table how many references move, merge and stay.
     One line per kind (`food`, `drink`) shows its shown site recipes, old recipes, kept old recipes and how many
     of those have a match: that is what each kind will keep. `--list` names each kept old recipe and the new
     `RecipeID` it goes to (or `no match`).
   - for real, when the dry run looks right: `cd /database/API && /database/venv/bin/python -m util.gluttonySwitch --apply`.
     While no drink is shown, `--apply` refuses (exit 1, nothing changed) unless the owner passes `--without drink`:
     `cd /database/API && /database/venv/bin/python -m util.gluttonySwitch --apply --without drink`. That retires
     the TheCocktailDB drinks with nothing to move people's drink items to: they stay on the retired recipes and
     disappear from the app (the backup undoes it). The first line says `switch: applied`. A failure prints
     `switch: failed, nothing was changed: ...` and rolls back.
   - run it when nobody is using the app: it locks the rows it reads. A failure (for example a lock conflict)
     changes nothing and the command can simply be run again.
   No restart is needed: the server already hides every retired recipe.
4. **Live checks (Claude).** `server/liveCheck.py` as in "Milestone 4: the rollout", step 11, with a fresh check
   key. Then by hand in the app: Browse shows only site recipes; Saved shows the moved items on their new recipes,
   with stars and notes; a recipe that had no match is gone from Saved. `GET /stats` shows no old source.
5. **Restart the weekly loop (VM 103).** `SCHEDULE=on` in `.env`, then `./run.sh` (it says "already running" if the
   tmux session is up: `tmux kill-session -t gluttony` first). Keep `CATALOG=new` and `PUBLISH=on`.
6. **Remove the old adapters (Claude, once the switch is confirmed).** Merge the held branch `catalog-retire-old`
   into `main` (it deletes `adaptTheDb.py`, `adaptWikibooks.py`, `sources/thedb.py`, `sources/wikibooks.py`,
   `sources/wikiImages.py` and their tests, and makes `CATALOG=new` the default) and copy the scraper to the VM.
   Old pictures stay on plutus until a later cleanup.

After the switch, never run a `CATALOG=old` pass: it re-posts the old recipes, and the server clears `RemovedAt` on
a re-post, which brings them back. Then regenerate the app's stub snapshot (`app/tests/stub/snapshot.py --token`)
and release the app build (its Quick fix sends `occasion=basic`).

**Undo:** stop the weekly loop, then restore the dump (`sudo mysql gluttonyDB < ~/gluttonyDB-before-switch-<date>.sql`)
and, if pictures changed, the copy of `/pool/appFiles/gluttony`. The VM goes back to `CATALOG=old` until the switch is
tried again. Once step 6 is merged the scraper refuses `CATALOG=old`, so an undo after that also puts the scraper from
before the merge back on the VM (`git revert -m 1` of the merge on `main`, then copy it over).

## Part 3: pairings

The scraper sends what goes with each recipe to `POST /api/gluttony-admin/pairings` (LAN, admin token):
`{"items": [{key, pairings: [{slot, key, rank, why}]}]}`, up to 200 items. Each item replaces that recipe's whole set
in `RecipePairings` (an empty list clears it), one transaction per item. `slot` is one of `side`, `sauce`,
`dessert`, `drink`, `goes-on`, `snack`; `rank` 1 to 8 within a slot; `why` 1 to 120 characters. An item whose own
key or any paired key plutus does not hold (or holds as removed) is refused with `unknown or removed recipe: <key>`;
the answer is `{stored: [keys], failed: [{key, message}]}`, as for `/recipes/batch`. `GET /api/gluttony/recipes/<id>`
then gives per slot the first 2 that are shown and fit the profile (`docs/api.md`).

Rollout (spec 2026-11-19 part 3, 2.5):

1. **Back up (owner).** `sudo mysqldump gluttonyDB | gzip > ~/gluttony-backups/gluttonyDB-<date>-prePairings.sql.gz`
2. **Load the schema (owner).** `sudo mysql gluttonyDB < schema-part3.sql` (from a copy of this folder).
3. **Copy the server files (Claude).** `gluttonyAdminRoutes.py`, `gluttonyRoutes.py`, `gluttonyRules.py` to
   `/database/API/util/` (LF endings: `git -c core.autocrlf=false archive`), the old ones kept as `*.bak-<date>`.
   The recipe page now reads `RecipePairings`, so step 2 comes first.
4. **Restart Caduceus (owner).** `sudo systemctl restart Caduceus.service`.
5. **Re-gate (Claude, VM 103).** Copy the scraper and run `main.py --once retag`; it publishes the pairings and its
   report (`run/last-report.json`, `pairings`) gives pairings per slot and how many recipes found none.
