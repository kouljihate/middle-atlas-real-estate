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

## Deploy (hosted backend)

The app is server-rendered, so the Flask backend must run online over HTTPS for
the PWA / Android app to work. It was built to swap databases via `DATABASE_URL`,
so deployment is configuration-only.

**Render (recommended, free):**

1. Push this repo to GitHub and create a new Render *Web Service* (the included
   `render.yaml` provisions the service + a free Postgres database).
2. Set environment variables in the Render dashboard:
   - `DATABASE_URL` — auto-injected from the Postgres database.
   - `MAC_FILTER_ENABLED=false` — **required** on a public host (the MAC gate is
     LAN-only; otherwise every request is blocked).
   - `SECRET_KEY` — any random string.
   - `ASSETLINKS_JSON` — the TWA verification JSON (see below).
3. Render runs `gunicorn --bind 0.0.0.0:$PORT app:app`. The app creates its
   tables automatically on first request.

Any other host (Railway, PythonAnywhere, Fly…) works the same: install
`requirements.txt`, set `DATABASE_URL` to a Postgres URL, disable the MAC filter,
and run the app on `$PORT`.

> Note: uploaded media lives on the host's ephemeral disk and resets on
> redeploy. Fine for a demo; use object storage (S3) for permanent files.

## Android app (TWA, sideloaded APK)

The app is already a PWA, so it can be wrapped as a **Trusted Web Activity**
with no UI rewrite — reusing 100% of the Flask code.

**1. Host the backend** (above) so the PWA is served over HTTPS.
**2. On your dev machine, install build tools:** Node.js, Java JDK 17, Android
SDK command-line tools, `bundletool`, then `npm i -g @bubblewrap/cli`.
**3. Generate a signing key:**
```bash
keytool -genkeypair -v -keystore android.keystore -alias atlas \
  -keyalg RSA -keysize 2048 -validity 10000
```
**4. Generate the Android project** (reads your live manifest):
```bash
bubblewrap init --manifest https://<your-host>/manifest.webmanifest
bubblewrap build
```
This produces an Android App Bundle (`.aab`).
**5. Convert to a sideloadable APK:**
```bash
bundletool build-apks --bundle app-release-bundle.aab \
  --output app.apks --ks android.keystore --ks-key-alias atlas
# extract the universal APK, or install directly:
bundletool install-apks --apks app.apks
```
**6. Trusted launch (no browser bar):** put the SHA256 of your key into
`ASSETLINKS_JSON` (env var) as a Digital Asset Links file and host it — the app
already serves it at `/.well-known/assetlinks.json`. Generate the JSON with:
```bash
bubblewrap fingerprint
```
**7. Install:** on the phone enable *Install unknown apps*, copy `app.apks` /
the extracted APK, and install.

## License

MIT — see source. Fonts: Comfortaa (OFL), Bouazzi Maghribi (custom).
