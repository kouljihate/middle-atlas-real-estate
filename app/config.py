import os

# Project root (package parent) so data/, static/ paths stay stable.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")

# Public, file-based database (SQLite — free & public domain).
# Swap to any free hosted database by setting the DATABASE_URL env var, e.g.
#   PostgreSQL (Neon / Supabase free tier): postgresql+psycopg://user:pass@host/dbname
DB_PATH = os.path.join(DATA_DIR, "lands.db")


def _normalize_db_url(url: str) -> str:
    """Accept raw provider URLs (e.g. Neon's `postgresql://...`).

    This project ships the psycopg v3 driver (not psycopg2), so plain
    `postgresql://` / legacy `postgres://` URLs are rewritten to the
    `postgresql+psycopg://` scheme SQLAlchemy needs.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalize_db_url(os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(DATA_DIR, "lands.db").replace("\\", "/"),
))

UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_VIDEO_EXT = {".mp4", ".webm", ".ogg", ".mov", ".avi"}
ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".webm"}
ALLOWED_DOC_EXT = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}
MAX_UPLOAD_MB = 25

# Generic media definitions shared by the form, validation, DB and templates.
MEDIA_KINDS = [
    {
        "name": "photo", "column": "photos", "field": "photos",
        "ext": ALLOWED_PHOTO_EXT, "label_key": "photos", "accept": "image/*",
    },
    {
        "name": "video", "column": "videos", "field": "videos",
        "ext": ALLOWED_VIDEO_EXT, "label_key": "videos", "accept": "video/*",
    },
    {
        "name": "audio", "column": "audios", "field": "audios",
        "ext": ALLOWED_AUDIO_EXT, "label_key": "audios", "accept": "audio/*",
    },
    {
        "name": "document", "column": "documents", "field": "documents",
        "ext": ALLOWED_DOC_EXT, "label_key": "documents",
        "accept": ".pdf,.doc,.docx,.txt,.rtf,.odt",
    },
]

# Land lifecycle status. Each value maps to a translation key for the UI.
STATUS_CHOICES = [
    ("Open", "status_open"),
    ("In Discussion", "status_in_discussion"),
    ("Option", "status_option"),
    ("In Progress", "status_in_progress"),
    ("Completed", "status_completed"),
]

# Affair (transaction) lifecycle — reuses the land statuses plus "Cancelled".
AFFAIR_STATUS_CHOICES = STATUS_CHOICES + [("Cancelled", "status_cancelled")]

# MAC allow-list behaviour
MAC_ALLOWLIST_FILE = os.path.join(BASE_DIR, "mac_allowlist.json")
# When True, every request must come from a device whose MAC is on the list.
# Overridable via the MAC_FILTER_ENABLED env var (see below).
# Header the client/network gateway is expected to present its MAC in.
MAC_HEADER = "X-Device-MAC"
# Hardcoded password required before the MAC allow-list page can be viewed.
MAC_PASSWORD = "LooK9LooK"

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

# App version (displayed in the footer). Bump on every release.
APP_VERSION = "1.4.6"

# Default currency, shown after every price. Override with CURRENCY env var.
CURRENCY = os.environ.get("CURRENCY", "MAD")

# MAC allow-list is meant for LAN deployments. On a public/hosted deployment
# client MAC addresses are not available, so the filter must be disabled.
MAC_FILTER_ENABLED = os.environ.get("MAC_FILTER_ENABLED", "true").lower() in (
    "1", "true", "yes", "on"
)

# Raw JSON served at /.well-known/assetlinks.json for Trusted Web Activity
# (Android TWA) verification. Set ASSETLINKS_JSON to the generated content
# (contains the SHA256 of your app's signing key). Defaults to empty.
ASSETLINKS_JSON = os.environ.get("ASSETLINKS_JSON", "[]")

# Default admin account (created on first run if no users exist)
DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASS", "admin123")
DEFAULT_ADMIN_NAME = os.environ.get("DEFAULT_ADMIN_NAME", "Administrator")
