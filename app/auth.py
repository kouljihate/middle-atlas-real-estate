"""Authentication and role-based access control for Rural-RealEstate.

Roles:
  admin   – full access: user management, all CRUD, MAC admin, dashboard
  agent   – manage lands, parties, affairs, dashboard (no user mgmt / MAC admin)
  seller  – view own lands, edit own profile, view own affairs
  buyer   – browse lands, view own affairs, edit own profile
  visitor – read-only: browse lands list only
"""

from enum import Enum
from functools import wraps

from flask import abort, redirect, session, url_for


class Role(str, Enum):
    ADMIN = "admin"
    AGENT = "agent"
    SELLER = "seller"
    BUYER = "buyer"
    VISITOR = "visitor"


ROLE_LABELS = {
    Role.ADMIN: "Administrator",
    Role.AGENT: "Agent",
    Role.SELLER: "Seller",
    Role.BUYER: "Buyer",
    Role.VISITOR: "Visitor",
}

ALL_ROLES = list(Role)

# ---------------------------------------------------------------------------
# Permission matrix
# ---------------------------------------------------------------------------
# Each key maps to a set of roles that hold that permission.
PERMISSIONS = {
    # Dashboard
    "view_dashboard":     {Role.ADMIN, Role.AGENT},
    # Lands
    "view_lands":         {Role.ADMIN, Role.AGENT, Role.SELLER, Role.BUYER, Role.VISITOR},
    "create_land":        {Role.ADMIN, Role.AGENT},
    "edit_land":          {Role.ADMIN, Role.AGENT},
    "delete_land":        {Role.ADMIN},
    # Parties (customers / sellers)
    "view_parties":       {Role.ADMIN, Role.AGENT},
    "create_party":       {Role.ADMIN, Role.AGENT},
    "edit_party":         {Role.ADMIN, Role.AGENT},
    "delete_party":       {Role.ADMIN},
    # Affairs
    "view_affairs":       {Role.ADMIN, Role.AGENT},
    "create_affair":      {Role.ADMIN, Role.AGENT},
    "edit_affair":        {Role.ADMIN, Role.AGENT},
    "delete_affair":      {Role.ADMIN},
    # User management
    "manage_users":       {Role.ADMIN},
    # Agents entity (managed by admin; each agent owns lands/affairs/parties)
    "view_agents":        {Role.ADMIN},
    "manage_agents":      {Role.ADMIN},
    # MAC admin
    "manage_mac":         {Role.ADMIN},
    # Profile (own)
    "edit_own_profile":   {Role.ADMIN, Role.AGENT, Role.SELLER, Role.BUYER},
}


def has_permission(role: Role, permission: str) -> bool:
    """Return True if *role* grants *permission*."""
    allowed = PERMISSIONS.get(permission, set())
    return role in allowed


def _current_user():
    """Return the current user dict from the session, or None."""
    return session.get("user")


def current_role() -> Role | None:
    """Return the current user's Role, or None if not logged in."""
    user = _current_user()
    if not user:
        return None
    try:
        return Role(user["role"])
    except (KeyError, ValueError):
        return None


def is_logged_in() -> bool:
    return _current_user() is not None


def current_user_id() -> int | None:
    user = _current_user()
    return user["id"] if user else None


def current_user_name() -> str:
    user = _current_user()
    return user.get("full_name", "") if user else ""


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------
def login_required(f):
    """Redirect to login page if the user is not authenticated."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("auth_login"))
        return f(*args, **kwargs)

    return decorated


def role_required(permission: str):
    """Decorator that aborts 403 unless the current user holds *permission*."""

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            role = current_role()
            if role is None:
                return redirect(url_for("auth_login"))
            if not has_permission(role, permission):
                abort(403, description="You do not have permission to access this page.")
            return f(*args, **kwargs)

        return decorated

    return decorator
