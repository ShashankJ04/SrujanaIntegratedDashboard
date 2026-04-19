"""Admin API Blueprint.

Port of dashboards/backend/src/routes/admin.ts.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from .auth import api_login_required
from .rbac import require_admin, DASHBOARD_KEYS
from . import rbac as rbac_store
from .db import fetch_all

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/api/admin")


@admin_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


# ── GET /users — list active users ──────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@require_admin
def list_users():
    rows = fetch_all(
        """
        SELECT
            US_ID AS id,
            US_Login AS login,
            COALESCE(US_FirstName, '') AS firstName,
            COALESCE(US_LastName, '') AS lastName
        FROM users
        WHERE US_CurrentYn = 'Y'
        ORDER BY US_Login
        """
    )
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "login": r["login"],
            "firstName": r["firstName"],
            "lastName": r["lastName"],
        })
    return jsonify(result)


# ── GET /rbac — get RBAC store (all users + dashboard keys) ─────────────

@admin_bp.route("/rbac", methods=["GET"])
@require_admin
def get_rbac():
    users = rbac_store.list_user_permissions()
    return jsonify({
        "dashboards": DASHBOARD_KEYS,
        "users": users,
    })


# ── PUT /rbac/<user_id> — set user permissions ─────────────────────────

@admin_bp.route("/rbac/<int:user_id>", methods=["PUT"])
@require_admin
def set_user_permissions(user_id):
    data = request.get_json(force=True)
    entry = rbac_store.set_user_permissions(
        user_id=user_id,
        login=data.get("login"),
        access=data.get("access", []),
        plus_access=data.get("plusAccess", []),
    )
    return jsonify(entry)
