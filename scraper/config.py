"""
Every setting the scraper reads. Hosts and secrets come from .env, which is
never committed; tuning knobs are plain constants so a change to one is
reviewed in git like any other code.

Other modules read these as config.NAME when they run, never with
`from config import NAME`, so the tests can repoint every path and mode in one
place (tests/conftest.py).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(key, default=None):
    value = os.getenv(key, default)
    if value is None:
        raise RuntimeError(f"Missing required setting '{key}' — add it to .env")
    return value


# ========== FOLDERS ==========
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
IMAGE_DIR = DATA_DIR / "images"
CACHE_DIR = DATA_DIR / "cache"
NORMALISED_FILE = DATA_DIR / "normalised.jsonl"
PUBLISHED_FILE = DATA_DIR / "published.json"
RULES_DIR = BASE_DIR / "rules"
RUN_DIR = BASE_DIR / "run"
REPORT_DIR = BASE_DIR / "reports"
FETCH_FILE = RUN_DIR / "fetch.json"
STATE_FILE = RUN_DIR / "state.json"
CURRENT_FILE = RUN_DIR / "current.json"
RUNS_FILE = RUN_DIR / "runs.jsonl"
LAST_REPORT_FILE = RUN_DIR / "last-report.json"
CONTROL_REQUESTS_FILE = RUN_DIR / "control-requests.json"
STOP_FILE = RUN_DIR / "stop.flag"
LOCK_FILE = RUN_DIR / "scraper.lock"

# ========== SOURCES ==========
# The free key "1" only: the owner pays for nothing the scraper uses.
MEALDB_BASE = "https://www.themealdb.com/api/json/v1/1"
COCKTAILDB_BASE = "https://www.thecocktaildb.com/api/json/v1/1"
WIKIBOOKS_DUMP_URL = "https://dumps.wikimedia.org/enwikibooks/latest/enwikibooks-latest-pages-articles.xml.bz2"
WIKIBOOKS_DUMP_RSS = WIKIBOOKS_DUMP_URL + "-rss.xml"
WIKIBOOKS_API = "https://en.wikibooks.org/w/api.php"
WIKIBOOKS_PAGE_BASE = "https://en.wikibooks.org/wiki/"

# ========== PLUTUS ==========
ADMIN_TOKEN = _env("ADMIN_TOKEN", "")
ADMIN_HOST = _env("ADMIN_HOST", "")
ADMIN_PORT = int(_env("ADMIN_PORT", "5000"))
UPLOAD_HOST = _env("UPLOAD_HOST", "")          # user@host that rsync sends pictures to
MEDIA_ROOT = "/pool/appFiles/gluttony"          # images/ and thumbs/ live under it on plutus
BATCH_SIZE = 50

# ========== MODES ==========
PUBLISH = _env("PUBLISH", "dry")      # "on" sends to plutus; "dry" runs every stage but sending
SCHEDULE = _env("SCHEDULE", "off")    # "on" runs the weekly pass by itself
REMOVAL_GUARD = 0.05                  # a source shrinking by more than this share removes nothing
FAILED_RETRY_HOURS = 6                # a failed weekly pass is tried again after this long
POLL_SECONDS = 10                     # how often the idle loop looks for Surrogate's requests

# ========== CONTROL API ==========
CONTROL_TOKEN = _env("CONTROL_TOKEN", "")
CONTROL_PORT = int(_env("CONTROL_PORT", "5057"))
