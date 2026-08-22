# Middle Atlas Real Estate — عقارات الأطلس المتوسط

A lightweight, bilingual (English / Arabic) web app for managing **rural real-estate**
deal flow: lands, parties (sellers & buyers), and **affairs** (transactions) with a
status lifecycle, media attachments, and a dashboard activity heatmap.

Built with Flask + SQLAlchemy Core + Pydantic, installable as a PWA (works offline,
addable to the home screen on Android/iOS).

## Features

- **Lands** — CRUD with status (Open / In Discussion / Option / In Progress / Completed),
  per-land linked **seller**, media (photos, videos, audio, documents) and auto-generated
  reference IDs (`L-YYMMDDHHMN`).
- **Customers & Sellers** — shared party model, fully bilingual forms & detail views.
- **Affairs (transactions)** — link a seller, a land and a buyer, track status, agreed
  price, deposit, commission and closing date; auto reference IDs (`A-YYMMDDHHMN`).
- **Dashboard** — KPI cards + a GitHub-style **affair activity heatmap** (last 26 weeks),
  with status pipeline chips that deep-link into a filtered affair list.
- **Bilingual UI** — full EN / AR translations with RTL support, language switcher.
- **PWA** — manifest, service worker (offline cache), installable, themed icons.
- **MAC allow-list gate** (optional) — restrict access to approved device MAC addresses.
- **Portable storage** — SQLite by default; swap to any hosted database (e.g. Postgres)
  via the `DATABASE_URL` environment variable. No code changes required.

## Quick start

```bash
python -m venv venv
venv\Scripts\activate          # Windows  (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
python run.py                  # http://127.0.0.1:5000
```

The app creates `data/lands.db` automatically on first run.

## Configuration

| Setting | Env var / file | Default |
| --- | --- | --- |
| Database | `DATABASE_URL` | `sqlite:///<ROOT>/data/lands.db` |
| Secret key | `SECRET_KEY` | `change-me-in-production` |
| App version | `APP_VERSION` (shown in footer) | `1.0.0` |
| MAC filter | `MAC_FILTER_ENABLED` / `MAC_PASSWORD` | enabled, `LooK9LooK` |

To use a hosted database (Neon / Supabase free tier, etc.):

```bash
set DATABASE_URL=postgresql+psycopg://user:pass@host/dbname
pip install "sqlalchemy[postgresql]"   # adds the driver
python run.py
```

## Demo data

```bash
python tests/seed_demo.py     # 100 sellers, 100 buyers, 150 lands, 15 affairs
python tests/clean_data.py    # wipe everything (keeps the schema)
```

## Project layout

```
app/
  __init__.py        Flask app + all routes + template globals
  config.py          settings (DB, media, statuses, version)
  db.py              SQLAlchemy Core data layer (portable, swappable DB)
  schemas.py         Pydantic validation schemas
  mac_filter.py      optional MAC allow-list middleware
  translations.py    EN / AR strings
run.py               entry point
templates/           Jinja2 templates
static/              css, js, manifest, service worker, icons, fonts, uploads/
tests/               seed / clean helpers
```

## License

MIT — see source. Fonts: Comfortaa (OFL), Bouazzi Maghribi (custom).
