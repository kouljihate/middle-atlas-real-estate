import os
import re
import secrets

from flask import (
    Flask, abort, flash, get_flashed_messages, redirect, render_template,
    request, session, url_for,
)
from pydantic import ValidationError

from . import config
from . import db
from .mac_filter import (
    get_server_mac, is_mac_allowed, load_allowlist, normalize_mac,
    resolve_mac_from_ip, save_allowlist,
)
from .schemas import (
    ALLOWED_PHOTO_EXT, ALLOWED_VIDEO_EXT, AffairCreate, AffairUpdate, LandCreate,
    LandUpdate, PartyCreate, PartyUpdate, validate_media_files,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(_ROOT, "templates"),
    static_folder=os.path.join(_ROOT, "static"),
)
app.secret_key = config.SECRET_KEY

db.init_db()

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
def dashboard():
    """Landing page: KPI cards + activity heatmap over affairs."""
    import calendar
    from datetime import date, datetime, timedelta

    affairs = db.get_all_affairs()
    today = date.today()

    per_day = {}
    for a in affairs:
        try:
            d = datetime.fromisoformat(a["created_at"]).date()
        except (ValueError, TypeError):
            continue
        per_day[d.isoformat()] = per_day.get(d.isoformat(), 0) + 1

    # Last 26 weeks, columns are Monday-based weeks, trimmed at today.
    start = today - timedelta(days=181)
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

    return render_template(
        "dashboard.html",
        weeks=weeks,
        statuses=statuses,
        month_label=calendar.month_abbr[today.month],
        n_lands=db.get_lands_page("", 1, 1)[1],
        n_sellers=len(db.get_all_parties("seller")),
        n_buyers=len(db.get_all_parties("customer")),
        n_affairs=len(affairs),
        n_active=len(active),
        agreed_total=agreed_total,
        peak=peak,
        today=today.isoformat(),
    )


@app.route("/lands")
def lands_list():
    from math import ceil

    per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    query = (request.args.get("q") or "").strip()
    lands, total = db.get_lands_page(query, page, per_page)
    total_pages = max(1, ceil(total / per_page))
    if page > total_pages:
        page = total_pages
        lands, total = db.get_lands_page(query, page, per_page)
        total_pages = max(1, ceil(total / per_page))

    return render_template(
        "index.html",
        lands=lands, q=query, page=page, total_pages=total_pages, total=total,
        per_page=per_page,
    )


@app.route("/land/new", methods=["GET", "POST"])
def land_new():
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        try:
            validated = LandCreate(**data)
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None

        errors += validate_media()

        if validated and not errors:
            db.create_land(validated.model_dump(), build_media(None))
            flash(_("save") + " ✓", "success")
            return redirect(url_for("lands_list"))

        return render_template(
            "land_form.html", land=None, errors=errors, data=data,
            media_kinds=config.MEDIA_KINDS,
            sellers=db.get_all_parties("seller"),
        )

    return render_template(
        "land_form.html", land=None, errors=[], data={},
        media_kinds=config.MEDIA_KINDS,
        sellers=db.get_all_parties("seller"),
    )


@app.route("/land/<int:land_id>/edit", methods=["GET", "POST"])
def land_edit(land_id):
    land = db.get_land(land_id)
    if not land:
        abort(404)

    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        try:
            validated = LandUpdate(**data)
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None

        errors += validate_media()

        if validated and not errors:
            db.update_land(land_id, validated.model_dump(), build_media(land))
            flash(_("save") + " ✓", "success")
            return redirect(url_for("lands_list"))

        land.update(data)
        return render_template(
            "land_form.html", land=land, errors=errors, data=data,
            media_kinds=config.MEDIA_KINDS,
            sellers=db.get_all_parties("seller"),
        )

    return render_template(
        "land_form.html", land=land, errors=[], data=land,
        media_kinds=config.MEDIA_KINDS,
        sellers=db.get_all_parties("seller"),
    )


@app.route("/land/<int:land_id>/delete", methods=["POST"])
def land_delete(land_id):
    if not db.get_land(land_id):
        abort(404)
    db.delete_land(land_id)
    flash(_("delete") + " ✓", "success")
    return redirect(url_for("lands_list"))


@app.route("/land/<int:land_id>/view")
def land_view(land_id):
    land = db.get_land(land_id)
    if not land:
        abort(404)
    return render_template("land_detail.html", land=land)


# ---------------------------------------------------------------------------
# Affairs (transactions)
# ---------------------------------------------------------------------------
def _affair_form_context():
    sellers = db.get_all_parties("seller")
    customers = db.get_all_parties("customer")
    lands = db.get_all_lands()
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
def affairs_list():
    from math import ceil

    per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    q = (request.args.get("q") or "").strip()
    items, total = db.get_affairs_page(q, page, per_page)
    total_pages = max(1, ceil(total / per_page))
    if page > total_pages:
        page = total_pages
        items, total = db.get_affairs_page(q, page, per_page)
        total_pages = max(1, ceil(total / per_page))

    sellers = {s["id"]: s["full_name"] for s in db.get_all_parties("seller")}
    buyers = {c["id"]: c["full_name"] for c in db.get_all_parties("customer")}
    lands = {l["id"]: l["title"] for l in db.get_all_lands()}
    for a in items:
        a["seller_name"] = sellers.get(a.get("seller_id")) or "-"
        a["buyer_name"] = buyers.get(a.get("buyer_id")) or "-"
        a["land_title"] = lands.get(a.get("land_id")) or "-"
    return render_template(
        "affair_list.html", affairs=items, q=q, page=page,
        total_pages=total_pages, total=total, per_page=per_page,
    )


@app.route("/affair/new", methods=["GET", "POST"])
def affair_new():
    sellers, customers, lands, lands_by_seller, seller_options, buyer_options = _affair_form_context()
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        try:
            validated = AffairCreate(**data)
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None

        if validated and not errors:
            db.create_affair(validated.model_dump())
            flash(_("save") + " ✓", "success")
            return redirect(url_for("affairs_list"))

        land_options = _land_options_for(lands_by_seller, data.get("seller_id"))
        return render_template(
            "affair_form.html", affair=None, errors=errors, data=data,
            sellers=sellers, customers=customers,
            seller_options=seller_options, buyer_options=buyer_options,
            lands_by_seller=lands_by_seller, land_options=land_options,
        )

    return render_template(
        "affair_form.html", affair=None, errors=[], data={},
        sellers=sellers, customers=customers,
        seller_options=seller_options, buyer_options=buyer_options,
        lands_by_seller=lands_by_seller, land_options=[],
    )


@app.route("/affair/<int:affair_id>/edit", methods=["GET", "POST"])
def affair_edit(affair_id):
    affair = db.get_affair(affair_id)
    if not affair:
        abort(404)
    sellers, customers, lands, lands_by_seller, seller_options, buyer_options = _affair_form_context()
    if request.method == "POST":
        data = request.form.to_dict()
        errors = []
        try:
            validated = AffairUpdate(**data)
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
            validated = None

        if validated and not errors:
            db.update_affair(affair_id, validated.model_dump())
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
    return render_template(
        "affair_form.html", affair=affair, errors=[], data=affair,
        sellers=sellers, customers=customers,
        seller_options=seller_options, buyer_options=buyer_options,
        lands_by_seller=lands_by_seller, land_options=land_options,
    )


@app.route("/affair/<int:affair_id>/view")
def affair_view(affair_id):
    affair = db.get_affair(affair_id)
    if not affair:
        abort(404)
    seller = db.get_party("seller", affair["seller_id"]) if affair.get("seller_id") else None
    buyer = db.get_party("customer", affair["buyer_id"]) if affair.get("buyer_id") else None
    land = db.get_land(affair["land_id"]) if affair.get("land_id") else None
    return render_template(
        "affair_detail.html", affair=affair, seller=seller, buyer=buyer, land=land
    )


@app.route("/affair/<int:affair_id>/delete", methods=["POST"])
def affair_delete(affair_id):
    if not db.get_affair(affair_id):
        abort(404)
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
    parties, total = db.get_parties_page(kind, q, page, per_page)
    total_pages = max(1, ceil(total / per_page))
    if page > total_pages:
        page = total_pages
        parties, total = db.get_parties_page(kind, q, page, per_page)
        total_pages = max(1, ceil(total / per_page))
    return render_template(
        "party_list.html", kind=kind, parties=parties, q=q, page=page,
        total_pages=total_pages, total=total, per_page=per_page,
    )


@app.route("/customers")
def customer_list():
    return _party_list("customer")


@app.route("/sellers")
def seller_list():
    return _party_list("seller")


def _party_new(kind: str):
    if request.method == "POST":
        data = _clean_optionals(request.form.to_dict())
        errors = []
        try:
            validated = PartyCreate(**data)
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
def customer_new():
    return _party_new("customer")


@app.route("/seller/new", methods=["GET", "POST"])
def seller_new():
    return _party_new("seller")


def _party_edit(kind: str, pid: int):
    party = db.get_party(kind, pid)
    if not party:
        abort(404)
    if request.method == "POST":
        data = _clean_optionals(request.form.to_dict())
        errors = []
        try:
            validated = PartyUpdate(**data)
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
def customer_edit(pid):
    return _party_edit("customer", pid)


@app.route("/seller/<int:pid>/edit", methods=["GET", "POST"])
def seller_edit(pid):
    return _party_edit("seller", pid)


def _party_view(kind: str, pid: int):
    party = db.get_party(kind, pid)
    if not party:
        abort(404)
    return render_template("party_detail.html", kind=kind, party=party)


@app.route("/customer/<int:pid>/view")
def customer_view(pid):
    return _party_view("customer", pid)


@app.route("/seller/<int:pid>/view")
def seller_view(pid):
    return _party_view("seller", pid)


def _party_delete(kind: str, pid: int):
    if not db.get_party(kind, pid):
        abort(404)
    db.delete_party(kind, pid)
    flash(_("delete") + " ✓", "success")
    return redirect(url_for(kind + "_list"))


@app.route("/customer/<int:pid>/delete", methods=["POST"])
def customer_delete(pid):
    return _party_delete("customer", pid)


@app.route("/seller/<int:pid>/delete", methods=["POST"])
def seller_delete(pid):
    return _party_delete("seller", pid)


# ---------------------------------------------------------------------------
# MAC allow-list admin
# ---------------------------------------------------------------------------
@app.route("/mac-admin", methods=["GET", "POST"])
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
    app.run(host="0.0.0.0", port=5000, debug=True)
