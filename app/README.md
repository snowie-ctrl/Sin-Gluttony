# Gluttony app

The desktop app for Gluttony (part 2 of the project; spec `../docs/superpowers/specs/2026-10-27-app-core-design.md`,
contract `../docs/api.md`). Qt 6.11.1 / QML with small C++ services; foundations copied from Pageturner, each copied
file naming its source and commit. Windows first; iOS is part 7.

## Build and test

- `powershell -File tests\build.ps1`: configures and builds the Debug test build in `build\tests` (the app and
  every test). Paths default to the owner's Qt (`D:\allNewQT6`); override with `GLUTTONY_QT`, `GLUTTONY_QT_TOOLS`,
  `GLUTTONY_VCVARS`.
- `powershell -File tests\run.ps1`: the C++ tests (ctest), then the QML logic tests (qmltestrunner).
  `-R <name>` runs only matching C++ tests; `-NoQml` skips the QML stage.
- The stub's own tests: `..\server\.venv\Scripts\python.exe -m pytest tests\stub -q` from `app\`.

## Running against the stub

The stub (`tests/stub/stub_server.py`, port 5079) imitates `docs/api.md`. It serves `tests/stub/snapshot/` (real
recipes, taken once with `tests/stub/snapshot.py`; never committed) or, without one, four fixture recipes. Sign in as
`stub` / `stub-password`; sign up with the key `stub-key`. Lists, Devoured marks, stars and notes last until the
stub stops; `STUB_KEPT=1` starts with some kept, and `STUB_REMOVED=<ids>` marks recipes removed by their source.

1. `config/secrets.json` (git ignores it): `{"apiBase": "http://127.0.0.1:5079/api/gluttony"}`.
2. `..\server\.venv\Scripts\python.exe tests\stub\stub_server.py`
3. `build\tests\appGluttony.exe` with `D:\allNewQT6\6.11.1\msvc2022_64\bin` on PATH.

## Screenshots

`powershell -File tests\stub\grab.ps1 -Out <png> [...]` starts the stub, runs the app in its own settings and data
folders, opens a page, recipe or search, and saves the window. The examples at the top of `grab.ps1` cover each
page and state. `grab.ps1` finds the server's venv beside the app; in a git worktree, which has none, set
`GLUTTONY_PYTHON` to the main checkout's `python.exe`.

## Where things are

- `api/`: Api (envelope, LAN or public, offline), AppConfig (`secrets.json`), SessionAuth and AuthNetworkFactory
  (the token on picture requests), TileModel.
- `services/`: Nav, AccountStore, Session, Diet, RecipeQuery (any paged list of tiles), Catalog, Home, Recipes,
  Saved (lists, Cravings, Devoured, stars, notes, and the flags every tile reads), and Wiring (what follows a
  sign-in and a sign-out).
- `qml/`: Main, NavShell, `pages/` (Login, Home, Results, Recipe, Saved, Settings), `component/`, and
  `logic/*.mjs` (words, moods, tiles, filters, scale, units, credit, days). Every word the app shows is in
  `logic/words.mjs`; every date is handled by `logic/days.mjs`, never by `new Date(text)`.
- `assets/`: Preferences (the Gula look's tokens), Playfair Display (SIL OFL), icons.
