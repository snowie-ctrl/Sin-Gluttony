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
   answer `{"status": "ok"}` (until milestone 4). (Part 2 opens `/api/gluttony/` on purpose; see below.)

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

1. **Check what is there (Claude, read only).** The four part 1 files in `util/` match the commit last deployed
   (`git show <commit>:server/<file> | md5sum` against `md5sum` on plutus; `diff --strip-trailing-cr` if only line
   endings differ). `DBUtils.py` maps `"gluttony"`. `Caduceus.py` sets no `MAX_CONTENT_LENGTH`.
2. **Scratch database (owner).** `gluttony_smoke` as in "The smoke test" above, with `schema.sql` then
   `schema-part2.sql` loaded.
3. **Copy the routes (Claude).** Back up the four existing files as `<file>.bak-<date>`, then copy
   `gluttonyAdminRoutes.py`, `gluttonyRoutes.py`, `gluttonyRules.py`, `gluttonySession.py`, `gluttonyKept.py`,
   `gluttonyUserRoutes.py` and `gluttonySmoke.py` from `main` (a `git archive` tar, unpacked on plutus), and
   `python3 -m py_compile` each. Caduceus keeps running the old ones until it restarts.
4. **Smoke test (Claude), then drop the scratch database (owner).** Every line `PASS`, `together` included.
5. **Load the schema (owner).** `sudo mysql gluttonyDB < schema-part2.sql`.
6. **Register the user routes (Claude).** Back up `Caduceus.py`, then inside the Gluttony block, after
   `app.register_blueprint(gluttonyBP, url_prefix="/api/gluttony")`:

   ```python
       from util.gluttonyUserRoutes import gluttonyUserBP
       app.register_blueprint(gluttonyUserBP, url_prefix="/api/gluttony")
   ```

   The block's comment now says the app's routes are public through `gluttony.forculus.net` behind sessions, and
   the admin routes stay LAN-only. Check it imports: `cd /database/API && /database/venv/bin/python -c "import Caduceus"`
   must print no `gluttony routes not loaded`.
7. **Restart (owner).** `sudo systemctl restart Caduceus.service`. LAN check: `/api/gluttony/ping` answers ok,
   `/api/gluttony/recipes` without a session answers 401.
8. **nginx (Claude).** Back up `/etc/nginx/sites-available/forculus.conf`, add this block beside the others, then
   `sudo nginx -t` and `sudo systemctl reload nginx`:

   ```nginx
   # Gluttony's app API: only its own prefix through the tunnel. The admin prefix
   # (/api/gluttony-admin/) never matches this location and stays LAN-only. A
   # /sync/batch of 500 offline notes can be ~4 MB, past nginx's 1 MB default.
   server {
       listen 80;
       server_name gluttony.forculus.net;
       location /api/gluttony/ {
           client_max_body_size 8m;
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
   answers 401; `/api/gluttony-admin/state` and `/` answer 404.
10. **Login keys (owner).** One for the owner, one for the live check:
    `sudo mysql gluttonyDB -e "INSERT INTO LoginKeys (KeyValue) VALUES ('<a long random key>')"`.
11. **Live check (Claude).** `server/liveCheck.py` on the LAN base with `--sign-up`, then on the public base with
    `--outside --limits` (see its docstring). Every line `PASS`.
12. **Remove the check account (owner).**
    `sudo mysql gluttonyDB -e "DELETE FROM Users WHERE Username = 'claude-check'; DELETE FROM LoginKeys WHERE KeyValue = '<the check key>'"`
    (its lists, marks, ratings, notes, devices and sessions go with it).
13. **The app (owner).** Unzip `Gluttony-<version>-windows-x64.zip` (`app/release.ps1`), put `config\secrets.json`
    beside `Gluttony.exe`, sign up with the key, and go through the pages at home, then away (another network).
