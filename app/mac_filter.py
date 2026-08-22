import json
import os
import uuid
from datetime import datetime, timezone

from . import config


def get_server_mac() -> str:
    """Return this machine's MAC address (used as a sane default for localhost)."""
    return ":".join(("%012X" % uuid.getnode())[i:i + 2] for i in range(0, 12, 2))


def _default_allowlist() -> dict:
    return {"enabled": config.MAC_FILTER_ENABLED, "allowed": [get_server_mac()]}


def load_allowlist() -> dict:
    if not os.path.exists(config.MAC_ALLOWLIST_FILE):
        data = _default_allowlist()
        save_allowlist(data)
        return data
    try:
        with open(config.MAC_ALLOWLIST_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("enabled", False)
        data.setdefault("allowed", [])
        return data
    except (json.JSONDecodeError, OSError):
        data = _default_allowlist()
        save_allowlist(data)
        return data


def save_allowlist(data: dict) -> None:
    with open(config.MAC_ALLOWLIST_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def normalize_mac(value: str) -> str:
    """Normalize a MAC string to 'AA:BB:CC:DD:EE:FF' upper-case form."""
    if not value:
        return ""
    cleaned = value.strip().upper().replace("-", "").replace(":", "")
    if len(cleaned) != 12 or any(c not in "0123456789ABCDEF" for c in cleaned):
        return ""
    return ":".join(cleaned[i:i + 2] for i in range(0, 12, 2))


def is_mac_allowed(mac: str) -> bool:
    data = load_allowlist()
    if not data.get("enabled", False):
        return True
    if not data.get("allowed"):
        # No entries configured -> fail closed is too strict for a demo,
        # so we allow when the list is empty to avoid lock-out.
        return True
    return normalize_mac(mac) in {normalize_mac(m) for m in data["allowed"]}


def resolve_mac_from_ip(ip: str) -> str:
    """Best-effort ARP lookup of the MAC behind an IP (LAN environments only)."""
    if ip in ("127.0.0.1", "::1", "localhost"):
        return get_server_mac()
    try:
        import subprocess

        out = subprocess.run(
            ["arp", "-a", ip], capture_output=True, text=True, timeout=5
        ).stdout
        for line in out.splitlines():
            parts = line.split()
            for p in parts:
                if len(p) >= 17 and p.count(":") == 5:
                    return normalize_mac(p)
    except Exception:
        pass
    return ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
