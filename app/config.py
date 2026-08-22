import os

# Project root (package parent) so data/, static/ paths stay stable.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")

# Public, file-based database (SQLite — free & public domain).
# Swap to any free hosted database by setting the DATABASE_URL env var, e.g.
#   PostgreSQL (Neon / Supabase free tier): postgresql+psycopg://user:pass@host/dbname
DB_PATH = os.path.join(DATA_DIR, "lands.db")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(DATA_DIR, "lands.db").replace("\\", "/"),
)

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
MAC_FILTER_ENABLED = True
# Header the client/network gateway is expected to present its MAC in.
MAC_HEADER = "X-Device-MAC"
# Hardcoded password required before the MAC allow-list page can be viewed.
MAC_PASSWORD = "LooK9LooK"

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

# App version (displayed in the footer). Bump on every release.
APP_VERSION = "1.0.0"
