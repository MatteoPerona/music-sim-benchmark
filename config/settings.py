from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# Weekend Rockstar release — sim sees nothing on or after this date.
CUTOFF_DATE = date(2026, 2, 13)
CUTOFF_DATETIME = datetime(2026, 2, 13, tzinfo=timezone.utc)

PRESS_MANIFEST = PROJECT_ROOT / "config" / "press_articles.json"
PRESS_RAW_DIR = RAW_DIR / "press"

AOTY_MANIFEST = PROJECT_ROOT / "config" / "aoty_albums.json"
AOTY_RAW_DIR = RAW_DIR / "aoty"
AOTY_BASE_URL = "https://www.albumoftheyear.org"

USER_AGENT = (
    "music-sim-benchmark/0.1 (+https://github.com/opi; research data collection)"
)
