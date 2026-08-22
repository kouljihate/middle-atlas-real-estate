import json
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Column, Float, Integer, MetaData, String, Table, Text,
    create_engine, delete, func, inspect, or_, select, text,
)

from . import config
from .mac_filter import now_iso

MEDIA_COLUMNS = [k["column"] for k in config.MEDIA_KINDS]

engine = create_engine(config.DATABASE_URL)
metadata = MetaData()

# ---------------------------------------------------------------------------
# Table definitions (portable across SQLite / PostgreSQL / MySQL via Core)
# ---------------------------------------------------------------------------
def _media_columns():
    return [Column(col, Text, nullable=False, server_default="[]")
            for col in MEDIA_COLUMNS]


lands = Table(
    "lands", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ref", String(20)),
    Column("title", String(120), nullable=False),
    Column("location", String(160), nullable=False),
    Column("area", Float, nullable=False),
    Column("price", Float, nullable=False),
    Column("owner_name", String(120), nullable=False),
    Column("description", Text),
    *_media_columns(),
    Column("status", String(40), nullable=False, server_default="Open"),
    Column("seller_id", Integer),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)


def _party_table(name: str) -> Table:
    return Table(
        name, metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("full_name", String(120), nullable=False),
        Column("email", String(160)),
        Column("phone", String(30)),
        Column("address", String(200)),
        Column("notes", Text),
        Column("created_at", String(40), nullable=False),
        Column("updated_at", String(40), nullable=False),
    )


customers = _party_table("customers")
sellers = _party_table("sellers")

affairs = Table(
    "affairs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ref", String(20)),
    Column("seller_id", Integer),
    Column("land_id", Integer),
    Column("buyer_id", Integer),
    Column("status", String(40), nullable=False, server_default="Open"),
    Column("agreed_price", Float),
    Column("deposit", Float),
    Column("commission", Float),
    Column("closing_date", String(20)),
    Column("notes", Text),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

_PARTIES = {"customer": customers, "seller": sellers}


# ---------------------------------------------------------------------------
# Setup & migrations
# ---------------------------------------------------------------------------
def _ref_stamp(dt: datetime) -> str:
    """Format a datetime as YYMMDDHHMN (no seconds) in local time."""
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%y%m%d%H%M")


def _valid_ref(ref: Optional[str], prefix: str) -> bool:
    body = ref or ""
    return (body.startswith(prefix + "-")
            and len(body) == len(prefix) + 11
            and body[len(prefix) + 1:].isdigit())


def _ref_from_ts(ts: Optional[str], prefix: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        dt = datetime.now()
    return f"{prefix}-{_ref_stamp(dt)}"


def _next_ref(prefix: str, table, taken: Optional[set] = None,
              from_ts: Optional[str] = None) -> str:
    """Unique business reference like 'L-2608211830' / 'A-2608211830'.

    Same-minute collisions are resolved by stepping one minute forward.
    """
    taken = taken if taken is not None else set()
    with engine.connect() as conn:
        taken |= {r[0] for r in conn.execute(
            select(table.c.ref).where(table.c.ref.is_not(None))
        ).all()}
    ref = _ref_from_ts(from_ts or now_iso(), prefix)
    while ref in taken:
        stamp = ref.split("-", 1)[1]
        dt = datetime.strptime(stamp, "%y%m%d%H%M") + timedelta(minutes=1)
        ref = f"{prefix}-{dt.strftime('%y%m%d%H%M')}"
    return ref


def init_db() -> None:
    if config.DATABASE_URL.startswith("sqlite"):
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    metadata.create_all(engine)
    _migrate_legacy_columns()
    _backfill_refs()


def _migrate_legacy_columns() -> None:
    """Add columns that older versions of the app did not have yet."""
    insp = inspect(engine)
    tables = insp.get_table_names()
    stmts = []
    if "lands" in tables:
        cols = {c["name"] for c in insp.get_columns("lands")}
        for col in ("audios", "documents"):
            if col not in cols:
                stmts.append(f"ALTER TABLE lands ADD COLUMN {col} TEXT DEFAULT '[]'")
        if "status" not in cols:
            stmts.append("ALTER TABLE lands ADD COLUMN status TEXT DEFAULT 'Open'")
        if "seller_id" not in cols:
            stmts.append("ALTER TABLE lands ADD COLUMN seller_id INTEGER")
        if "ref" not in cols:
            stmts.append("ALTER TABLE lands ADD COLUMN ref TEXT")
    if "affairs" in tables:
        cols = {c["name"] for c in insp.get_columns("affairs")}
        if "ref" not in cols:
            stmts.append("ALTER TABLE affairs ADD COLUMN ref TEXT")
    if stmts:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))


def _backfill_refs() -> None:
    """Give every row a business reference derived from created_at.

    Rows without a ref, and rows still carrying an outdated ref format,
    are (re)generated here.
    """
    with engine.begin() as conn:
        for table, prefix in ((lands, "L"), (affairs, "A")):
            rows = conn.execute(
                select(table.c.id, table.c.ref, table.c.created_at)
            ).all()
            need = [r for r in rows if not _valid_ref(r[1], prefix)]
            if not need:
                continue
            good = {r[1] for r in rows if _valid_ref(r[1], prefix)}
            for rid, _old_ref, created_at in need:
                ref = _next_ref(prefix, table, taken=set(good),
                                from_ts=created_at)
                good.add(ref)
                conn.execute(
                    table.update().where(table.c.id == rid).values(ref=ref)
                )


def _row_to_dict(row) -> dict:
    d = dict(row)
    for col in MEDIA_COLUMNS:
        d[col] = json.loads(d[col] or "[]")
    return d


def _order(table):
    return table.c.created_at.desc(), table.c.id.desc()


# ---------------------------------------------------------------------------
# Lands
# ---------------------------------------------------------------------------
def get_all_lands() -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(lands).order_by(*_order(lands))
        ).mappings().all()
    return [_row_to_dict(r) for r in rows]


def get_lands_page(q: str, page: int, per_page: int):
    """Return (items, total) for a search + pagination query."""
    stmt = select(lands)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            lands.c.title.ilike(like),
            lands.c.location.ilike(like),
            lands.c.owner_name.ilike(like),
            lands.c.ref.ilike(like),
        ))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    offset = max(0, (page - 1) * per_page)
    with engine.connect() as conn:
        total = conn.execute(count_stmt).scalar_one()
        rows = conn.execute(
            stmt.order_by(*_order(lands)).limit(per_page).offset(offset)
        ).mappings().all()
    return [_row_to_dict(r) for r in rows], int(total)


def get_land(land_id: int) -> Optional[dict]:
    with engine.connect() as conn:
        row = conn.execute(
            select(lands).where(lands.c.id == land_id)
        ).mappings().first()
    return _row_to_dict(row) if row else None


def create_land(data: dict, media: dict) -> int:
    """Create a land. `media` maps a column name (e.g. 'photos') to a list."""
    ts = now_iso()
    vals = {
        "ref": _next_ref("L", lands),
        "title": data["title"],
        "location": data["location"],
        "area": data["area"],
        "price": data["price"],
        "owner_name": data["owner_name"],
        "description": data.get("description"),
        "status": data.get("status", "Open"),
        "seller_id": data.get("seller_id"),
        **{c: json.dumps(media.get(c, []), ensure_ascii=False) for c in MEDIA_COLUMNS},
        "created_at": ts,
        "updated_at": ts,
    }
    with engine.begin() as conn:
        res = conn.execute(lands.insert().values(**vals))
        return int(res.inserted_primary_key[0])


def update_land(land_id: int, data: dict, media: dict) -> None:
    ts = now_iso()
    vals = {
        "title": data["title"],
        "location": data["location"],
        "area": data["area"],
        "price": data["price"],
        "owner_name": data["owner_name"],
        "description": data.get("description"),
        "status": data.get("status", "Open"),
        "seller_id": data.get("seller_id"),
        **{c: json.dumps(media.get(c, []), ensure_ascii=False) for c in MEDIA_COLUMNS},
        "updated_at": ts,
    }
    with engine.begin() as conn:
        conn.execute(lands.update().where(lands.c.id == land_id).values(**vals))


def delete_land(land_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(delete(lands).where(lands.c.id == land_id))


def clear_lands() -> None:
    """Remove every land row (used by the seed script for a clean reseed)."""
    with engine.begin() as conn:
        conn.execute(delete(lands))


# ---------------------------------------------------------------------------
# Customers / Sellers (parties)
# ---------------------------------------------------------------------------
def get_all_parties(kind: str) -> list[dict]:
    t = _PARTIES[kind]
    with engine.connect() as conn:
        rows = conn.execute(select(t).order_by(*_order(t))).mappings().all()
    return [dict(r) for r in rows]


def get_parties_page(kind: str, q: str, page: int, per_page: int):
    t = _PARTIES[kind]
    stmt = select(t)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            t.c.full_name.ilike(like),
            t.c.email.ilike(like),
            t.c.phone.ilike(like),
        ))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    offset = max(0, (page - 1) * per_page)
    with engine.connect() as conn:
        total = conn.execute(count_stmt).scalar_one()
        rows = conn.execute(
            stmt.order_by(*_order(t)).limit(per_page).offset(offset)
        ).mappings().all()
    return [dict(r) for r in rows], int(total)


def get_party(kind: str, pid: int) -> Optional[dict]:
    t = _PARTIES[kind]
    with engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.id == pid)).mappings().first()
    return dict(row) if row else None


def create_party(kind: str, data: dict) -> int:
    t = _PARTIES[kind]
    ts = now_iso()
    vals = {
        "full_name": data["full_name"],
        "email": data.get("email"),
        "phone": data.get("phone"),
        "address": data.get("address"),
        "notes": data.get("notes"),
        "created_at": ts,
        "updated_at": ts,
    }
    with engine.begin() as conn:
        res = conn.execute(t.insert().values(**vals))
        return int(res.inserted_primary_key[0])


def update_party(kind: str, pid: int, data: dict) -> None:
    t = _PARTIES[kind]
    vals = {
        "full_name": data["full_name"],
        "email": data.get("email"),
        "phone": data.get("phone"),
        "address": data.get("address"),
        "notes": data.get("notes"),
        "updated_at": now_iso(),
    }
    with engine.begin() as conn:
        conn.execute(t.update().where(t.c.id == pid).values(**vals))


def delete_party(kind: str, pid: int) -> None:
    t = _PARTIES[kind]
    with engine.begin() as conn:
        conn.execute(delete(t).where(t.c.id == pid))


def clear_parties() -> None:
    """Remove every customer and seller row."""
    with engine.begin() as conn:
        conn.execute(delete(customers))
        conn.execute(delete(sellers))


# ---------------------------------------------------------------------------
# Affairs (transactions linking a seller, a buyer and a land)
# ---------------------------------------------------------------------------
def get_all_affairs() -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(affairs).order_by(*_order(affairs))
        ).mappings().all()
    return [dict(r) for r in rows]


def get_affairs_page(q: str, page: int, per_page: int):
    stmt = select(affairs)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(affairs.c.status.ilike(like),
                              affairs.c.notes.ilike(like),
                              affairs.c.ref.ilike(like)))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    offset = max(0, (page - 1) * per_page)
    with engine.connect() as conn:
        total = conn.execute(count_stmt).scalar_one()
        rows = conn.execute(
            stmt.order_by(*_order(affairs)).limit(per_page).offset(offset)
        ).mappings().all()
    return [dict(r) for r in rows], int(total)


def get_affair(affair_id: int) -> Optional[dict]:
    with engine.connect() as conn:
        row = conn.execute(
            select(affairs).where(affairs.c.id == affair_id)
        ).mappings().first()
    return dict(row) if row else None


def create_affair(data: dict) -> int:
    ts = now_iso()
    vals = {
        "ref": _next_ref("A", affairs),
        "seller_id": data.get("seller_id"),
        "land_id": data.get("land_id"),
        "buyer_id": data.get("buyer_id"),
        "status": data.get("status", "Open"),
        "agreed_price": data.get("agreed_price"),
        "deposit": data.get("deposit"),
        "commission": data.get("commission"),
        "closing_date": data.get("closing_date"),
        "notes": data.get("notes"),
        "created_at": ts,
        "updated_at": ts,
    }
    with engine.begin() as conn:
        res = conn.execute(affairs.insert().values(**vals))
        return int(res.inserted_primary_key[0])


def update_affair(affair_id: int, data: dict) -> None:
    vals = {
        "seller_id": data.get("seller_id"),
        "land_id": data.get("land_id"),
        "buyer_id": data.get("buyer_id"),
        "status": data.get("status", "Open"),
        "agreed_price": data.get("agreed_price"),
        "deposit": data.get("deposit"),
        "commission": data.get("commission"),
        "closing_date": data.get("closing_date"),
        "notes": data.get("notes"),
        "updated_at": now_iso(),
    }
    with engine.begin() as conn:
        conn.execute(affairs.update().where(affairs.c.id == affair_id)
                     .values(**vals))


def delete_affair(affair_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(delete(affairs).where(affairs.c.id == affair_id))


def clear_affairs() -> None:
    with engine.begin() as conn:
        conn.execute(delete(affairs))


def clear_all() -> None:
    """Remove all business data (lands + parties + affairs)."""
    clear_lands()
    clear_parties()
    clear_affairs()
