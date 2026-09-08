import os
import re
import secrets

from flask import (
    Flask, abort, flash, get_flashed_messages, redirect, render_template,
    request, Response, session, url_for,
)
from pydantic import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

from . import config
from . import db
from .auth import (
    ALL_ROLES, ROLE_LABELS, Role, current_role, current_user_id,
    current_user_name, has_permission, is_logged_in, login_required,
    role_required,
)
from .mac_filter import (
    get_server_mac, is_mac_allowed, load_allowlist, normalize_mac,
    resolve_mac_from_ip, save_allowlist,
)
from .schemas import (
    ALLOWED_PHOTO_EXT, ALLOWED_VIDEO_EXT, AffairCreate, AffairUpdate, AgentCreate,
    AgentUpdate, LandCreate, LandUpdate, PartyCreate, PartyUpdate,
    validate_media_files,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(_ROOT, "templates"),
    static_folder=os.path.join(_ROOT, "static"),
)
app.secret_key = config.SECRET_KEY


def _seed_default_admin():
    """Create the default admin user if the users table is empty."""
    if db.user_count() == 0:
        db.create_user({
            "username": config.DEFAULT_ADMIN_USERNAME,
            "password_hash": generate_password_hash(config.DEFAULT_ADMIN_PASSWORD),
            "full_name": config.DEFAULT_ADMIN_NAME,
            "role": "admin",
        })


db.init_db()
_seed_default_admin()

# ---------------------------------------------------------------------------
# Translations (English / Arabic)
# ---------------------------------------------------------------------------
from .translations import TRANSLATIONS


def get_lang():
    return session.get("lang", "en")


def _(key: str) -> str:
    return TRANSLATIONS.get(get_lang(), TRANSLATIONS["en"]).get(key, key)


app.jinja_env.globals["_"] = _
app.jinja_env.globals["get_lang"] = get_lang
app.jinja_env.globals["dir"] = lambda: "rtl" if get_lang() == "ar" else "ltr"


def status_label(value: str) -> str:
    for v, key in config.STATUS_CHOICES:
        if v == value:
            return _(key)
    return value


app.jinja_env.globals["status_choices"] = config.STATUS_CHOICES
app.jinja_env.globals["status_label"] = status_label
app.jinja_env.globals["affair_status_choices"] = config.AFFAIR_STATUS_CHOICES
app.jinja_env.globals["version"] = config.APP_VERSION
app.jinja_env.globals["currency"] = config.CURRENCY


def _pydantic_errors(exc: ValidationError) -> list:
    out = []
    for e in exc.errors():
        loc = ".".join(map(str, e.get("loc", []))) or "form"
        out.append(f"{loc}: {e.get('msg', '')}")
    return out


@app.context_processor
def inject_year():
    from datetime import datetime
    return {"now_year": datetime.now().year}


@app.context_processor
def inject_auth():
    """Make auth helpers available in all templates."""
    return {
        "is_logged_in": is_logged_in,
        "current_role": current_role,
        "current_user_name": current_user_name,
        "current_user_id": current_user_id,
        "has_permission": has_permission,
        "role_labels": ROLE_LABELS,
    }


# ---------------------------------------------------------------------------
# Agent scoping helpers
# ---------------------------------------------------------------------------
def _current_agent_id():
    """Return the agent id linked to the logged-in user, or None.

    - admin (and other non-agent roles): None → sees everything allowed.
    - agent role: the linked agents.id, or -1 when no agent record exists
      (so queries safely return nothing instead of leaking all data).
    """
    if current_role() != Role.AGENT:
        return None
    agent = db.get_agent_by_user_id(current_user_id())
    return agent["id"] if agent else -1


def _scope_agent_id():
    """Agent id to filter business queries by, or None for unscoped."""
    if current_role() == Role.AGENT:
        return _current_agent_id()
    return None


def _check_ownership(record: dict | None, scope):
    """Abort 404/403 when an agent touches another agent's record."""
    if not record:
        abort(404)
    if scope is not None and record.get("agent_id") != scope:
        abort(403, description="You do not have permission to access this page.")


def _apply_agent_scope(data: dict, scope):
    """Force agent-owned creates/updates to carry the agent's own id."""
    if scope is not None:
        data["agent_id"] = scope
    return data


def _sync_land_from_affair(data: dict):
    """Mirror an affair's status onto its linked land (Cancelled → Open)."""
    land_id = data.get("land_id")
    status = (data.get("status") or "").strip()
    if not land_id or not status:
        return
    if not db.get_land(land_id):
        return
    db.set_land_status(land_id, "Open" if status == "Cancelled" else status)


def _resolve_land_seller(data: dict, scope):
    """Link a land to its seller by owner name.

    When no seller was picked explicitly, look up the owner name in the
    sellers collection (case-insensitive): link the match if found,
    otherwise create the seller so the new name is stored.
    """
    if data.get("seller_id"):
        return data
    name = (data.get("owner_name") or "").strip()
    if not name:
        return data
    existing = next(
        (s for s in db.get_all_parties("seller", scope)
         if (s.get("full_name") or "").strip().lower() == name.lower()),
        None,
    )
    if existing:
        data["seller_id"] = existing["id"]
    else:
        data["seller_id"] = db.create_party("seller", {
            "full_name": name,
            "email": None,
            "phone": None,
            "address": None,
            "notes": None,
            "agent_id": scope,
        })
    return data


# ---------------------------------------------------------------------------
# Authentication routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def auth_login():
    if is_logged_in():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = db.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            if not user["is_active"]:
                flash(_("account_disabled"), "error")
                return render_template("login.html", data={}, errors=[])
            session["user"] = {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"],
            }
            flash(_("login_success"), "success")
            return redirect(url_for("dashboard"))
        flash(_("login_failed"), "error")
    return render_template("login.html", data={}, errors=[])


@app.route("/logout")
def auth_logout():
    session.pop("user", None)
    flash(_("logout_success"), "success")
    return redirect(url_for("auth_login"))


@app.route("/register", methods=["GET", "POST"])
def auth_register():
    if is_logged_in():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip() or None
        phone = (request.form.get("phone") or "").strip() or None

        errors = []
        if len(username) < 3:
            errors.append("Username must be at least 3 characters")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters")
        if len(full_name) < 2:
            errors.append("Full name is required")
        if db.get_user_by_username(username):
            errors.append("Username already taken")

        if not errors:
            db.create_user({
                "username": username,
                "password_hash": generate_password_hash(password),
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "role": "visitor",  # new registrations are visitors by default
            })
            flash(_("register_success"), "success")
            return redirect(url_for("auth_login"))

        return render_template("register.html", errors=errors, data=request.form.to_dict())

    return render_template("register.html", errors=[], data={})


@app.route("/profile", methods=["GET", "POST"])
@login_required
def auth_profile():
    user = db.get_user(current_user_id())
    if not user:
        abort(404)
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        new_pass = (data.get("password") or "").strip()
        if new_pass and len(new_pass) < 6:
            errors.append("Password must be at least 6 characters")

        if not errors:
            update_data = {
                "full_name": data.get("full_name", user["full_name"]),
                "email": data.get("email") or None,
                "phone": data.get("phone") or None,
                "role": user["role"],  # can't change own role
                "is_active": user["is_active"],
            }
            if new_pass:
                update_data["password_hash"] = generate_password_hash(new_pass)
            db.update_user(user["id"], update_data)
            # Update session
            session["user"]["full_name"] = update_data["full_name"]
            flash(_("save") + " ✓", "success")
            return redirect(url_for("auth_profile"))

        return render_template("profile.html", user=user, errors=errors, data=data)

    return render_template("profile.html", user=user, errors=[], data=user)


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------
@app.route("/users")
@role_required("manage_users")
def user_list():
    from math import ceil
    per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    q = (request.args.get("q") or "").strip()
    items, total = db.get_users_page(q, page, per_page)
    total_pages = max(1, ceil(total / per_page)) if total else 1
    if page > total_pages:
        page = total_pages
        items, total = db.get_users_page(q, page, per_page)
        total_pages = max(1, ceil(total / per_page)) if total else 1
    return render_template(
        "user_list.html", users=items, q=q, page=page,
        total_pages=total_pages, total=total, per_page=per_page,
    )


@app.route("/user/new", methods=["GET", "POST"])
@role_required("manage_users")
def user_new():
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        full_name = (data.get("full_name") or "").strip()
        role = data.get("role", "visitor")

        if len(username) < 3:
            errors.append("Username must be at least 3 characters")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters")
        if len(full_name) < 2:
            errors.append("Full name is required")
        if db.get_user_by_username(username):
            errors.append("Username already taken")
        if role not in [r.value for r in Role]:
            errors.append("Invalid role")

        if not errors:
            db.create_user({
                "username": username,
                "password_hash": generate_password_hash(password),
                "full_name": full_name,
                "email": (data.get("email") or "").strip() or None,
                "phone": (data.get("phone") or "").strip() or None,
                "role": role,
            })
            flash(_("save") + " ✓", "success")
            return redirect(url_for("user_list"))

        return render_template(
            "user_form.html", user=None, errors=errors, data=data, roles=ALL_ROLES,
        )

    return render_template(
        "user_form.html", user=None, errors=[], data={}, roles=ALL_ROLES,
    )


@app.route("/user/<int:uid>/edit", methods=["GET", "POST"])
@role_required("manage_users")
def user_edit(uid):
    user = db.get_user(uid)
    if not user:
        abort(404)
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        full_name = (data.get("full_name") or "").strip()
        role = data.get("role", user["role"])

        if len(full_name) < 2:
            errors.append("Full name is required")
        if role not in [r.value for r in Role]:
            errors.append("Invalid role")

        if not errors:
            update_data = {
                "full_name": full_name,
                "email": (data.get("email") or "").strip() or None,
                "phone": (data.get("phone") or "").strip() or None,
                "role": role,
                "is_active": 1 if data.get("is_active") else 0,
            }
            new_pass = (data.get("password") or "").strip()
            if new_pass:
                if len(new_pass) < 6:
                    errors.append("Password must be at least 6 characters")
                else:
                    update_data["password_hash"] = generate_password_hash(new_pass)
            if not errors:
                db.update_user(uid, update_data)
                flash(_("save") + " ✓", "success")
                return redirect(url_for("user_list"))

        return render_template(
            "user_form.html", user=user, errors=errors, data=data, roles=ALL_ROLES,
        )

    return render_template(
        "user_form.html", user=user, errors=[], data=user, roles=ALL_ROLES,
    )


@app.route("/user/<int:uid>/delete", methods=["POST"])
@role_required("manage_users")
def user_delete(uid):
    if uid == current_user_id():
        flash("Cannot delete your own account", "error")
        return redirect(url_for("user_list"))
    if not db.get_user(uid):
        abort(404)
    db.delete_user(uid)
    flash(_("delete") + " ✓", "success")
    return redirect(url_for("user_list"))


@app.route("/.well-known/assetlinks.json")
def assetlinks():
    """TWA / Digital Asset Links verification for the Android app."""
    return Response(config.ASSETLINKS_JSON, mimetype="application/json")


@app.route("/api/db-status")
def api_db_status():
    """Live database health for the footer pill (public, no login needed).

    ready    (green)  - test query answers in under 1s.
    idle     (orange) - reachable but slow (e.g. waking from sleep).
    not_ready (red)   - unreachable / error.
    """
    import time

    from flask import jsonify
    from sqlalchemy import text as sa_text

    try:
        start = time.monotonic()
        with db.engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        latency_ms = int((time.monotonic() - start) * 1000)
    except Exception:
        return jsonify({"state": "not_ready"})
    if latency_ms < 1000:
        return jsonify({"state": "ready", "latency_ms": latency_ms})
    return jsonify({"state": "idle", "latency_ms": latency_ms})


# ---------------------------------------------------------------------------
# MAC allow-list middleware
# ---------------------------------------------------------------------------
@app.before_request
def enforce_mac_allowlist():
    # The MAC admin page is always reachable so operators can manage the list.
    if request.endpoint in ("mac_admin", "static"):
        return
    mac = request.headers.get(config.MAC_HEADER, "").strip()
    if not mac:
        mac = resolve_mac_from_ip(request.remote_addr or "")
    if not is_mac_allowed(mac):
        if request.endpoint == "set_lang":
            flash(_("mac_denied"), "error")
            return redirect(url_for("lands_list"))
        abort(403, description=_("mac_denied"))


# ---------------------------------------------------------------------------
# File upload helpers
# ---------------------------------------------------------------------------
def save_uploads(files, allowed_ext):
    saved = []
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    for f in files:
        if not f or not getattr(f, "filename", ""):
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in allowed_ext:
            continue
        safe_name = secrets.token_hex(12) + ext
        f.save(os.path.join(config.UPLOAD_DIR, safe_name))
        saved.append("uploads/" + safe_name)
    return saved


def collect_existing_media(land, kind):
    column = next(k["column"] for k in config.MEDIA_KINDS if k["name"] == kind)
    existing = request.form.getlist(f"keep_{kind}")
    # keep only those that actually belong to this land
    valid = set(land.get(column, []))
    return [e for e in existing if e in valid]


def build_media(land):
    media = {}
    for k in config.MEDIA_KINDS:
        kept = collect_existing_media(land, k["name"]) if land else []
        media[k["column"]] = kept + save_uploads(
            request.files.getlist(k["field"]), k["ext"]
        )
    return media


def validate_media():
    errors = []
    for k in config.MEDIA_KINDS:
        errors += validate_media_files(
            request.files.getlist(k["field"]), k["ext"], _(k["label_key"])
        )
    return errors


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in TRANSLATIONS:
        session["lang"] = lang
    return redirect(request.referrer or url_for("lands_list"))


@app.route("/")
@app.route("/dashboard")
@login_required
@role_required("view_dashboard")
def dashboard():
    """Landing page: KPI cards + activity heatmap over affairs."""
    from datetime import date, datetime, timedelta

    WEEK_OPTIONS = [4, 8, 13, 26, 52]
    try:
        w = int(request.args.get("w", 26))
    except (TypeError, ValueError):
        w = 26
    if w not in WEEK_OPTIONS:
        w = 26

    scope = _scope_agent_id()
    affairs = db.get_all_affairs(scope)
    today = date.today()

    per_day = {}
    for a in affairs:
        try:
            d = datetime.fromisoformat(a["created_at"]).date()
        except (ValueError, TypeError):
            continue
        per_day[d.isoformat()] = per_day.get(d.isoformat(), 0) + 1

    # Last `w` weeks, columns are Monday-based weeks, trimmed at today.
    start = today - timedelta(days=w * 7 - 1)
    start -= timedelta(days=start.weekday())
    weeks, counts = [], []
    d = start
    while d <= today:
        col = []
        for i in range(7):
            day = d + timedelta(days=i)
            if day > today:
                break
            n = per_day.get(day.isoformat(), 0)
            col.append({"iso": day.isoformat(), "count": n})
            counts.append(n)
        weeks.append(col)
        d += timedelta(days=7)

    peak = max(counts) if counts else 0
    for col in weeks:
        for cell in col:
            n = cell["count"]
            cell["level"] = 0 if n == 0 else min(4, 1 + (n - 1) * 4 // max(peak, 1))

    active = [a for a in affairs
              if a["status"] not in ("Completed", "Cancelled")]
    statuses = [{"status": s, "key": k,
                 "n": sum(1 for a in affairs if a["status"] == s)}
                for s, k in config.AFFAIR_STATUS_CHOICES]
    agreed_total = sum(a["agreed_price"] or 0 for a in affairs)
    year_prefix = str(today.year)
    commission_year = sum(
        (a["commission"] or 0) for a in affairs
        if (a.get("created_at") or "").startswith(year_prefix)
    )

    return render_template(
        "dashboard.html",
        weeks=weeks,
        statuses=statuses,
        week_options=WEEK_OPTIONS,
        w=w,
        n_lands=db.get_lands_page("", 1, 1, scope)[1],
        n_sellers=len(db.get_all_parties("seller", scope)),
        n_buyers=len(db.get_all_parties("customer", scope)),
        n_affairs=len(affairs),
        n_active=len(active),
        agreed_total=agreed_total,
        commission_year=commission_year,
        year=today.year,
        peak=peak,
        today=today.isoformat(),
    )


@app.route("/lands")
@login_required
@role_required("view_lands")
def lands_list():
    from math import ceil

    per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    query = (request.args.get("q") or "").strip()
    scope = _scope_agent_id()
    lands, total = db.get_lands_page(query, page, per_page, scope)
    total_pages = max(1, ceil(total / per_page))
    if page > total_pages:
        page = total_pages
        lands, total = db.get_lands_page(query, page, per_page, scope)
        total_pages = max(1, ceil(total / per_page))

    return render_template(
        "index.html",
        lands=lands, q=query, page=page, total_pages=total_pages, total=total,
        per_page=per_page,
    )


@app.route("/land/new", methods=["GET", "POST"])
@login_required
@role_required("create_land")
def land_new():
    scope = _scope_agent_id()
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        try:
            validated = LandCreate(**_apply_agent_scope(data, scope))
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None

        errors += validate_media()

        if validated and not errors:
            payload = _resolve_land_seller(validated.model_dump(), scope)
            db.create_land(payload, build_media(None))
            flash(_("save") + " ✓", "success")
            return redirect(url_for("lands_list"))

        return render_template(
            "land_form.html", land=None, errors=errors, data=data,
            media_kinds=config.MEDIA_KINDS,
            sellers=db.get_all_parties("seller", scope),
        )

    return render_template(
        "land_form.html", land=None, errors=[], data={},
        media_kinds=config.MEDIA_KINDS,
        sellers=db.get_all_parties("seller", scope),
    )


@app.route("/land/<int:land_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("edit_land")
def land_edit(land_id):
    scope = _scope_agent_id()
    land = db.get_land(land_id)
    _check_ownership(land, scope)

    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        try:
            validated = LandUpdate(**_apply_agent_scope(data, scope))
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None

        errors += validate_media()

        if validated and not errors:
            payload = _resolve_land_seller(validated.model_dump(), scope)
            db.update_land(land_id, payload, build_media(land))
            flash(_("save") + " ✓", "success")
            return redirect(url_for("lands_list"))

        land.update(data)
        return render_template(
            "land_form.html", land=land, errors=errors, data=data,
            media_kinds=config.MEDIA_KINDS,
            sellers=db.get_all_parties("seller", scope),
        )

    return render_template(
        "land_form.html", land=land, errors=[], data=land,
        media_kinds=config.MEDIA_KINDS,
        sellers=db.get_all_parties("seller", scope),
    )


@app.route("/land/<int:land_id>/delete", methods=["POST"])
@login_required
@role_required("delete_land")
def land_delete(land_id):
    _check_ownership(db.get_land(land_id), _scope_agent_id())
    db.delete_land(land_id)
    flash(_("delete") + " ✓", "success")
    return redirect(url_for("lands_list"))


@app.route("/land/<int:land_id>/view")
@login_required
@role_required("view_lands")
def land_view(land_id):
    land = db.get_land(land_id)
    _check_ownership(land, _scope_agent_id())
    return render_template("land_detail.html", land=land)


# ---------------------------------------------------------------------------
# Affairs (transactions)
# ---------------------------------------------------------------------------
def _affair_form_context():
    scope = _scope_agent_id()
    sellers = db.get_all_parties("seller", scope)
    customers = db.get_all_parties("customer", scope)
    lands = db.get_all_lands(scope)
    lands_by_seller = {}
    for s in sellers:
        sid = s["id"]
        lands_by_seller[sid] = [
            {"id": l["id"], "title": l["title"]}
            for l in lands
            if l.get("seller_id") == sid or l.get("owner_name") == s["full_name"]
        ]
    seller_options = [(s["id"], s["full_name"]) for s in sellers]
    buyer_options = [(c["id"], c["full_name"]) for c in customers]
    return sellers, customers, lands, lands_by_seller, seller_options, buyer_options


def _land_options_for(lands_by_seller: dict, seller_value) -> list:
    try:
        sid = int(seller_value) if seller_value not in (None, "") else None
    except (ValueError, TypeError):
        sid = None
    if sid is None:
        return []
    return lands_by_seller.get(sid, [])


@app.route("/affairs")
@login_required
@role_required("view_affairs")
def affairs_list():
    from math import ceil

    per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    q = (request.args.get("q") or "").strip()
    scope = _scope_agent_id()
    items, total = db.get_affairs_page(q, page, per_page, scope)
    total_pages = max(1, ceil(total / per_page))
    if page > total_pages:
        page = total_pages
        items, total = db.get_affairs_page(q, page, per_page, scope)
        total_pages = max(1, ceil(total / per_page))

    sellers = {s["id"]: s["full_name"] for s in db.get_all_parties("seller", scope)}
    buyers = {c["id"]: c["full_name"] for c in db.get_all_parties("customer", scope)}
    lands = {l["id"]: l["title"] for l in db.get_all_lands(scope)}
    for a in items:
        a["seller_name"] = sellers.get(a.get("seller_id")) or "-"
        a["buyer_name"] = buyers.get(a.get("buyer_id")) or "-"
        a["land_title"] = lands.get(a.get("land_id")) or "-"
    return render_template(
        "affair_list.html", affairs=items, q=q, page=page,
        total_pages=total_pages, total=total, per_page=per_page,
    )


@app.route("/affair/new", methods=["GET", "POST"])
@login_required
@role_required("create_affair")
def affair_new():
    from datetime import datetime
    scope = _scope_agent_id()
    # Preview of the auto reference (YYMMDDHHMN stamp); final value is
    # assigned on save and shown read-only here.
    ref_preview = "A-" + datetime.now().strftime("%y%m%d%H%M")
    sellers, customers, lands, lands_by_seller, seller_options, buyer_options = _affair_form_context()
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        try:
            validated = AffairCreate(**_apply_agent_scope(data, scope))
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None

        if validated and not errors:
            payload = validated.model_dump()
            db.create_affair(payload)
            _sync_land_from_affair(payload)
            flash(_("save") + " ✓", "success")
            return redirect(url_for("affairs_list"))

        land_options = _land_options_for(lands_by_seller, data.get("seller_id"))
        return render_template(
            "affair_form.html", affair=None, errors=errors, data=data,
            sellers=sellers, customers=customers,
            seller_options=seller_options, buyer_options=buyer_options,
            lands_by_seller=lands_by_seller, land_options=land_options,
            ref_preview=ref_preview,
        )

    return render_template(
        "affair_form.html", affair=None, errors=[], data={},
        sellers=sellers, customers=customers,
        seller_options=seller_options, buyer_options=buyer_options,
        lands_by_seller=lands_by_seller, land_options=[],
        ref_preview=ref_preview,
    )


@app.route("/affair/<int:affair_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("edit_affair")
def affair_edit(affair_id):
    scope = _scope_agent_id()
    affair = db.get_affair(affair_id)
    _check_ownership(affair, scope)
    sellers, customers, lands, lands_by_seller, seller_options, buyer_options = _affair_form_context()
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        try:
            validated = AffairUpdate(**_apply_agent_scope(data, scope))
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None

        if validated and not errors:
            payload = validated.model_dump()
            db.update_affair(affair_id, payload)
            _sync_land_from_affair(payload)
            flash(_("save") + " ✓", "success")
            return redirect(url_for("affairs_list"))

        affair.update(data)
        land_options = _land_options_for(lands_by_seller, data.get("seller_id"))
        return render_template(
            "affair_form.html", affair=affair, errors=errors, data=data,
            sellers=sellers, customers=customers,
            seller_options=seller_options, buyer_options=buyer_options,
            lands_by_seller=lands_by_seller, land_options=land_options,
        )

    land_options = _land_options_for(lands_by_seller, affair.get("seller_id"))
    # Keep the currently linked land selectable even if it is no longer
    # matched to this seller, so opening Edit never silently unlinks it.
    if affair.get("land_id") and not any(
        l["id"] == affair["land_id"] for l in land_options
    ):
        current_land = db.get_land(affair["land_id"])
        if current_land:
            land_options = [
                {"id": current_land["id"], "title": current_land["title"]}
            ] + land_options
    return render_template(
        "affair_form.html", affair=affair, errors=[], data=affair,
        sellers=sellers, customers=customers,
        seller_options=seller_options, buyer_options=buyer_options,
        lands_by_seller=lands_by_seller, land_options=land_options,
    )


@app.route("/affair/<int:affair_id>/view")
@login_required
@role_required("view_affairs")
def affair_view(affair_id):
    affair = db.get_affair(affair_id)
    _check_ownership(affair, _scope_agent_id())
    seller = db.get_party("seller", affair["seller_id"]) if affair.get("seller_id") else None
    buyer = db.get_party("customer", affair["buyer_id"]) if affair.get("buyer_id") else None
    land = db.get_land(affair["land_id"]) if affair.get("land_id") else None
    return render_template(
        "affair_detail.html", affair=affair, seller=seller, buyer=buyer, land=land
    )


@app.route("/affair/<int:affair_id>/delete", methods=["POST"])
@login_required
@role_required("delete_affair")
def affair_delete(affair_id):
    _check_ownership(db.get_affair(affair_id), _scope_agent_id())
    db.delete_affair(affair_id)
    flash(_("delete") + " ✓", "success")
    return redirect(url_for("affairs_list"))


# ---------------------------------------------------------------------------
# Customers & Sellers
# ---------------------------------------------------------------------------
def _clean_optionals(data: dict) -> dict:
    for k in ("email", "address", "notes"):
        if not (data.get(k) or "").strip():
            data[k] = None
    return data


def _party_list(kind: str):
    from math import ceil

    per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    q = (request.args.get("q") or "").strip()
    scope = _scope_agent_id()
    parties, total = db.get_parties_page(kind, q, page, per_page, scope)
    total_pages = max(1, ceil(total / per_page))
    if page > total_pages:
        page = total_pages
        parties, total = db.get_parties_page(kind, q, page, per_page, scope)
        total_pages = max(1, ceil(total / per_page))
    return render_template(
        "party_list.html", kind=kind, parties=parties, q=q, page=page,
        total_pages=total_pages, total=total, per_page=per_page,
    )


@app.route("/customers")
@login_required
@role_required("view_parties")
def customer_list():
    return _party_list("customer")


@app.route("/sellers")
@login_required
@role_required("view_parties")
def seller_list():
    return _party_list("seller")


def _party_new(kind: str):
    scope = _scope_agent_id()
    if request.method == "POST":
        data = _clean_optionals(request.form.to_dict())
        errors = []
        try:
            validated = PartyCreate(**_apply_agent_scope(data, scope))
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None
        if validated and not errors:
            db.create_party(kind, validated.model_dump())
            flash(_("save") + " ✓", "success")
            return redirect(url_for(kind + "_list"))
        return render_template(
            "party_form.html", kind=kind, party=None, errors=errors, data=data
        )
    return render_template(
        "party_form.html", kind=kind, party=None, errors=[], data={}
    )


@app.route("/customer/new", methods=["GET", "POST"])
@login_required
@role_required("create_party")
def customer_new():
    return _party_new("customer")


@app.route("/seller/new", methods=["GET", "POST"])
@login_required
@role_required("create_party")
def seller_new():
    return _party_new("seller")


def _party_edit(kind: str, pid: int):
    scope = _scope_agent_id()
    party = db.get_party(kind, pid)
    _check_ownership(party, scope)
    if request.method == "POST":
        data = _clean_optionals(request.form.to_dict())
        errors = []
        try:
            validated = PartyUpdate(**_apply_agent_scope(data, scope))
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None
        if validated and not errors:
            db.update_party(kind, pid, validated.model_dump())
            flash(_("save") + " ✓", "success")
            return redirect(url_for(kind + "_list"))
        party.update(data)
        return render_template(
            "party_form.html", kind=kind, party=party, errors=errors, data=data
        )
    return render_template(
        "party_form.html", kind=kind, party=party, errors=[], data=party
    )


@app.route("/customer/<int:pid>/edit", methods=["GET", "POST"])
@login_required
@role_required("edit_party")
def customer_edit(pid):
    return _party_edit("customer", pid)


@app.route("/seller/<int:pid>/edit", methods=["GET", "POST"])
@login_required
@role_required("edit_party")
def seller_edit(pid):
    return _party_edit("seller", pid)


def _party_view(kind: str, pid: int):
    party = db.get_party(kind, pid)
    _check_ownership(party, _scope_agent_id())
    return render_template("party_detail.html", kind=kind, party=party)


@app.route("/customer/<int:pid>/view")
@login_required
@role_required("view_parties")
def customer_view(pid):
    return _party_view("customer", pid)


@app.route("/seller/<int:pid>/view")
@login_required
@role_required("view_parties")
def seller_view(pid):
    return _party_view("seller", pid)


def _party_delete(kind: str, pid: int):
    _check_ownership(db.get_party(kind, pid), _scope_agent_id())
    db.delete_party(kind, pid)
    flash(_("delete") + " ✓", "success")
    return redirect(url_for(kind + "_list"))


@app.route("/customer/<int:pid>/delete", methods=["POST"])
@login_required
@role_required("delete_party")
def customer_delete(pid):
    return _party_delete("customer", pid)


@app.route("/seller/<int:pid>/delete", methods=["POST"])
@login_required
@role_required("delete_party")
def seller_delete(pid):
    return _party_delete("seller", pid)


# ---------------------------------------------------------------------------
# Agents (managed by admin; lands/affairs/parties belong to an agent)
# ---------------------------------------------------------------------------
def _agent_user_options():
    """Users eligible to be linked to an agent (role == agent)."""
    return [
        u for u in db.get_all_users()
        if u.get("role") == Role.AGENT.value
    ]


@app.route("/agents")
@login_required
@role_required("view_agents")
def agent_list():
    from math import ceil
    per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    q = (request.args.get("q") or "").strip()
    items, total = db.get_agents_page(q, page, per_page)
    total_pages = max(1, ceil(total / per_page)) if total else 1
    if page > total_pages:
        page = total_pages
        items, total = db.get_agents_page(q, page, per_page)
    users_by_id = {u["id"]: u for u in db.get_all_users()}
    for a in items:
        u = users_by_id.get(a.get("user_id")) if a.get("user_id") else None
        a["linked_username"] = u["username"] if u else None
    return render_template(
        "agent_list.html", agents=items, q=q, page=page,
        total_pages=total_pages, total=total, per_page=per_page,
    )


@app.route("/agent/new", methods=["GET", "POST"])
@login_required
@role_required("manage_agents")
def agent_new():
    users = _agent_user_options()
    if request.method == "POST":
        data = _clean_optionals(request.form.to_dict())
        errors = []
        try:
            validated = AgentCreate(**data)
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None
        if validated and not errors:
            if validated.user_id and not db.get_user(validated.user_id):
                errors.append("user_id: linked user not found")
            else:
                db.create_agent(validated.model_dump())
                flash(_("save") + " ✓", "success")
                return redirect(url_for("agent_list"))
        return render_template(
            "agent_form.html", agent=None, errors=errors, data=data, users=users,
        )
    return render_template(
        "agent_form.html", agent=None, errors=[], data={}, users=users,
    )


@app.route("/agent/<int:aid>/edit", methods=["GET", "POST"])
@login_required
@role_required("manage_agents")
def agent_edit(aid):
    agent = db.get_agent(aid)
    if not agent:
        abort(404)
    users = _agent_user_options()
    if request.method == "POST":
        data = _clean_optionals(request.form.to_dict())
        errors = []
        try:
            validated = AgentUpdate(**data)
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None
        if validated and not errors:
            if validated.user_id and not db.get_user(validated.user_id):
                errors.append("user_id: linked user not found")
            else:
                db.update_agent(aid, validated.model_dump())
                flash(_("save") + " ✓", "success")
                return redirect(url_for("agent_list"))
        agent.update(data)
        return render_template(
            "agent_form.html", agent=agent, errors=errors, data=data, users=users,
        )
    return render_template(
        "agent_form.html", agent=agent, errors=[], data=agent, users=users,
    )


@app.route("/agent/<int:aid>/view")
@login_required
@role_required("view_agents")
def agent_view(aid):
    agent = db.get_agent(aid)
    if not agent:
        abort(404)
    linked = db.get_user(agent["user_id"]) if agent.get("user_id") else None
    stats = {
        "lands": db.get_lands_page("", 1, 1, agent["id"])[1],
        "affairs": db.get_affairs_page("", 1, 1, agent["id"])[1],
    }
    return render_template("agent_detail.html", agent=agent, linked=linked, stats=stats)


@app.route("/agent/<int:aid>/delete", methods=["POST"])
@login_required
@role_required("manage_agents")
def agent_delete(aid):
    if not db.get_agent(aid):
        abort(404)
    db.delete_agent(aid)
    flash(_("delete") + " ✓", "success")
    return redirect(url_for("agent_list"))


# ---------------------------------------------------------------------------
# MAC allow-list admin
# ---------------------------------------------------------------------------
@app.route("/mac-admin", methods=["GET", "POST"])
@login_required
@role_required("manage_mac")
def mac_admin():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "login":
            if request.form.get("password", "") == config.MAC_PASSWORD:
                session["mac_authed"] = True
                flash(_("mac_unlocked"), "success")
                return redirect(url_for("mac_admin"))
            flash(_("mac_wrong_password"), "error")
            return render_template("mac_login.html")
        if action == "logout":
            session.pop("mac_authed", None)
            return redirect(url_for("mac_admin"))
        # Any other action requires the password gate.
        if not session.get("mac_authed"):
            return render_template("mac_login.html")

        data = load_allowlist()
        if action == "toggle":
            data["enabled"] = not data.get("enabled", False)
            save_allowlist(data)
        elif action == "add":
            mac = normalize_mac(request.form.get("mac", ""))
            if not mac:
                flash(_("mac_invalid"), "error")
            elif mac not in data["allowed"]:
                data["allowed"].append(mac)
                save_allowlist(data)
                flash(_("mac_added"), "success")
        elif action == "remove":
            mac = normalize_mac(request.form.get("mac", ""))
            data["allowed"] = [m for m in data["allowed"] if m != mac]
            save_allowlist(data)
            flash(_("mac_removed"), "success")
        return redirect(url_for("mac_admin"))

    if not session.get("mac_authed"):
        return render_template("mac_login.html")

    data = load_allowlist()
    return render_template("mac_admin.html", allowlist=data, server_mac=get_server_mac())


@app.errorhandler(403)
def forbidden(err):
    return render_template("error.html", code=403, message=str(err.description)), 403


@app.errorhandler(404)
def not_found(err):
    return render_template("error.html", code=404, message="Not found"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
