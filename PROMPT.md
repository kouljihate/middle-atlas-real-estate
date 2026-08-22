# PROMPT.md — Build Specification & Prompts

This document records the design brief and the key prompts that drove the
construction of **Middle Atlas Real Estate** so the project can be reproduced or
extended by an AI assistant or another developer.

## 1. Product brief

> Build a web app to manage rural real-estate operations. It must track
> **lands**, **parties** (sellers and buyers), and **affairs** (the transactions
> between them), in a simple, responsive, mobile-friendly UI that works in
> Arabic and English.

### Derived requirements

- **Stack**: Python 3 + Flask, server-rendered Jinja2 templates (no SPA framework),
  SQLAlchemy **Core** (not ORM) for a portable data layer, Pydantic for input
  validation, Pillow for media processing.
- **Database**: start with a free, public-domain **SQLite** file; keep the data
  layer swappable to any hosted database (Postgres) via a single `DATABASE_URL`
  setting with **no code changes**.
- **Entities**:
  - *Land*: reference id, title, location, area, price, owner name, status,
    optional linked seller, media (photos/videos/audio/documents).
  - *Party*: kind (seller | buyer), name, contact, address, notes. Reused for
    both Customers and Sellers.
  - *Affair*: links seller + land + buyer, status, agreed price, deposit,
    commission, closing date, notes, auto reference id.
- **Bilingual**: full EN / AR translations, RTL layout when Arabic is active,
  language switcher persisted per session.
- **Mobile-first**: responsive tables that collapse to cards on phones, sticky
  header, large tap targets, hold-to-record microphone button for audio notes.
- **PWA**: installable, offline-capable (service worker + manifest + icons),
  themed for Android & iOS.
- **Access control (optional)**: a MAC allow-list gate restricting access to
  approved devices, behind a password-protected admin page.
- **Branding**: renamed to **Middle Atlas Real Estate / عقارات الأطلس المتوسط**,
  with a green hills + sun identity.

## 2. Evolution prompts (chronological)

1. **Scaffold**: "Create a Flask CRUD app for lands, customers, sellers with
   bilingual EN/AR, responsive design, media uploads, pydantic validation."
2. **Restructure**: "Move the app into an `app/` package and run it via
   `python run.py`; make the database layer SQLAlchemy Core and configurable
   through `DATABASE_URL` so it can run on a free hosted DB."
3. **Affairs**: "Add an *Affair* entity that connects a seller, a land and a
   buyer, with a status pipeline; add it to the menu before lands; generate
   auto reference ids."
4. **Dashboard**: "Make the landing page a Dashboard with KPI cards and a
   GitHub-style heatmap of affair activity; put Dashboard first in the menu;
   remove the agreed-price card; let the heatmap range be chosen from a
   selectable list of weeks."
5. **Branding & PWA**: "Rename to Middle Atlas Real Estate, add a manifest,
   service worker, icons, and meta tags for installability."
6. **Polish & ship**: "Fix corrupted characters in the header/footer, set an
   app version shown in the footer, replace the top-left logo with a clean SVG,
   write README.md and PROMPT.md, and push the project to GitHub (kouljihate)."

## 3. Conventions for AI collaboration

- Prefer editing existing files; avoid creating new docs unless asked.
- Use the project `venv` (`venv\Scripts\python.exe`) for all Python execution.
- Keep the data layer backend-agnostic; never hard-code SQLite-only SQL.
- All user-facing strings go through the `_(...)` translation helper; add new
  keys to **both** `en` and `ar` blocks in `app/translations.py`.
- Bump `APP_VERSION` in `app/config.py` on every release.
