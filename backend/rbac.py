"""RBAC (Role-Based Access Control) store.

Mirrors the behaviour of dashboards/backend/src/rbac/store.ts — stores
user → dashboard permissions in a local JSON file.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import g, jsonify

from .config import Config

# ── Dashboard keys ──────────────────────────────────────────────────────

DASHBOARD_KEYS: List[str] = [
    "tools",
    "preventive_maintenance",
    "life_report",
    "production",
    "rm_variance",
    "rm_correction",
    "rm_correction_plus",
    "rept",
    "rept_plus",
    "edit_dpr",
    "edit_buffer",
]

# ── Store path ──────────────────────────────────────────────────────────

def _store_path() -> str:
    configured = str(getattr(Config, "RBAC_STORE_FILE", "") or "").strip()
    if configured:
        return configured
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "rbac.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_store() -> None:
    path = _store_path()
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"users": [], "updatedAt": _iso_now()}, f, indent=2)


def _read_store() -> Dict[str, Any]:
    _ensure_store()
    with open(_store_path(), "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return {"users": [], "updatedAt": _iso_now()}
        parsed = json.loads(content)
    return {
        "users": parsed.get("users") or [],
        "updatedAt": parsed.get("updatedAt") or _iso_now(),
    }


def _write_store(data: Dict[str, Any]) -> None:
    _ensure_store()
    with open(_store_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _normalize_keys(keys: List[str]) -> List[str]:
    allowed = set(DASHBOARD_KEYS)
    seen = set()
    result = []
    for k in keys:
        if k in allowed and k not in seen:
            seen.add(k)
            result.append(k)
    return result


def _migrate_legacy_access_keys(keys: List[str]) -> List[str]:
    """Map legacy `reports` access to `rept`."""
    out: List[str] = []
    for k in keys or []:
        nk = "rept" if k == "reports" else k
        if nk not in out:
            out.append(nk)
    return out


def _migrate_legacy_plus_keys(keys: List[str]) -> List[str]:
    """Map legacy `reports` plus to `rept_plus`."""
    out: List[str] = []
    for k in keys or []:
        nk = "rept_plus" if k == "reports" else k
        if nk not in out:
            out.append(nk)
    return out


# ── Public API ──────────────────────────────────────────────────────────

def list_user_permissions() -> List[Dict[str, Any]]:
    store = _read_store()
    return store["users"]


def get_user_permissions(user_id: int) -> Optional[Dict[str, Any]]:
    store = _read_store()
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        uid = 0
    for u in store["users"]:
        try:
            if int(u.get("userId", 0)) == uid:
                return u
        except (TypeError, ValueError):
            continue
    return None


def set_user_permissions(
    user_id: int,
    login: Optional[str],
    access: List[str],
    plus_access: List[str],
) -> Dict[str, Any]:
    store = _read_store()
    access_norm = _normalize_keys(access)
    plus_norm = _normalize_keys(plus_access)
    now = _iso_now()

    entry = {
        "userId": user_id,
        "login": login,
        "access": access_norm,
        "plusAccess": plus_norm,
        "updatedAt": now,
    }

    idx = next(
        (i for i, u in enumerate(store["users"]) if u.get("userId") == user_id),
        None,
    )
    if idx is not None:
        store["users"][idx] = {**store["users"][idx], **entry}
    else:
        store["users"].append(entry)

    store["updatedAt"] = now
    _write_store(store)
    return entry


def get_effective_permissions(
    user_id: int,
    login: str,
    is_admin: bool,
) -> Dict[str, List[str]]:

    stored = get_user_permissions(user_id)
    if not stored:
        return {"access": [], "plusAccess": []}

    raw_access = _migrate_legacy_access_keys(list(stored.get("access", [])))
    raw_plus = _migrate_legacy_plus_keys(list(stored.get("plusAccess", [])))

    # Mis-saved: rept_plus only belongs in plusAccess; if present in access, move it
    if "rept_plus" in raw_access:
        raw_access = [k for k in raw_access if k != "rept_plus"]
        if "rept_plus" not in raw_plus:
            raw_plus.append("rept_plus")

    plus_access = _normalize_keys(raw_plus)
    access = _normalize_keys(raw_access)

    return {"access": access, "plusAccess": plus_access}


# ── Decorators for use in routes ────────────────────────────────────────

def _is_admin_user(user: Dict[str, Any]) -> bool:
    return user.get("userId") == 43


def require_access(dashboard: str):
    """Decorator: user must have view access to the given dashboard."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            user = g.get("current_user")
            if not user:
                return jsonify({"message": "Authentication required"}), 401
            perms = get_effective_permissions(
                user.get("userId", 0),
                user.get("login", ""),
                _is_admin_user(user),
            )
            if dashboard not in perms["access"]:
                return jsonify({"message": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_any_access(dashboards: List[str]):
    """Decorator: user must have view access to ANY of the given dashboards."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            user = g.get("current_user")
            if not user:
                return jsonify({"message": "Authentication required"}), 401
            perms = get_effective_permissions(
                user.get("userId", 0),
                user.get("login", ""),
                _is_admin_user(user),
            )
            if not any(d in perms["access"] for d in dashboards):
                return jsonify({"message": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_plus_access(dashboard: str):
    """Decorator: user must have edit/plus access to the given dashboard."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            user = g.get("current_user")
            if not user:
                return jsonify({"message": "Authentication required"}), 401
            perms = get_effective_permissions(
                user.get("userId", 0),
                user.get("login", ""),
                _is_admin_user(user),
            )
            if dashboard not in perms.get("plusAccess", []):
                return jsonify({"message": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_admin(f: Callable) -> Callable:
    """Decorator: user must be admin (userId == 43)."""
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        user = g.get("current_user")
        if not user:
            return jsonify({"message": "Authentication required"}), 401
        if not _is_admin_user(user):
            return jsonify({"message": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated
