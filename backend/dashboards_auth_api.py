"""Dashboards Auth API Blueprint.

Provides /api/auth/me endpoint for the dashboards frontend to get
the current user and their permissions (via cookies).
"""

from __future__ import annotations

from flask import Blueprint, jsonify, g

from .auth import api_login_required
from . import rbac as rbac_store

dash_auth_bp = Blueprint("dash_auth_bp", __name__, url_prefix="/api/auth")


@dash_auth_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


@dash_auth_bp.route("/me", methods=["GET"])
def me():
    user = g.current_user
    user_id = user.get("userId", 0)
    login = user.get("login", "")
    is_admin = user_id == 43

    permissions = rbac_store.get_effective_permissions(user_id, login, is_admin)

    return jsonify({
        "user": {
            "id": user_id,
            "login": login,
            "firstName": user.get("firstName", ""),
            "lastName": user.get("lastName", ""),
            "isAdmin": is_admin,
        },
        "permissions": permissions,
    })
