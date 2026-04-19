from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from Crypto.Cipher import DES
from flask import current_app, g, jsonify, redirect, request, url_for

from .db import fetch_one


def _jwt_b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt_b64url_decode(s: str) -> bytes:
    pad = (-len(s)) % 4
    if pad:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _jwt_hs256_encode(payload: Dict[str, Any], secret: str) -> str:
    """HS256 JWT using stdlib only (avoids PyJWT → cryptography on Windows)."""
    header = {"alg": "HS256", "typ": "JWT"}
    h = _jwt_b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    p = _jwt_b64url_encode(
        json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    )
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_jwt_b64url_encode(sig)}"


def _jwt_hs256_decode(token: str, secret: str) -> Optional[Dict[str, Any]]:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    h_b64, p_b64, sig_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    expected = _jwt_b64url_encode(
        hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, sig_b64):
        return None
    try:
        payload = json.loads(_jwt_b64url_decode(p_b64).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    exp = payload.get("exp")
    if exp is not None and time.time() > float(exp):
        return None
    return payload


def _get_des_key() -> bytes:
    key_str = current_app.config.get("DES_KEY", "tJykDLYx")
    return key_str.encode("utf-8")[:8].ljust(8, b"\x00")


def decrypt_password(encrypted_pwd: str) -> Optional[str]:
    """Decrypt a DES-ECB + Base64 encoded password from the users table."""
    try:
        ct = base64.b64decode(encrypted_pwd)
        cipher = DES.new(_get_des_key(), DES.MODE_ECB)
        plain = cipher.decrypt(ct)
        pad_len = plain[-1]
        if 1 <= pad_len <= 8 and all(b == pad_len for b in plain[-pad_len:]):
            plain = plain[:-pad_len]
        return plain.decode("utf-8")
    except Exception:
        return None


def verify_credentials(login: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify login credentials against the users table using DES decryption."""
    sql = "SELECT US_ID, US_Login, US_Pwd, US_FirstName, US_LastName FROM users WHERE US_Login = %s LIMIT 1"
    row = fetch_one(sql, (login,))
    if not row:
        return None

    stored_pwd = row.get("US_Pwd", "")
    if not stored_pwd:
        return None

    decrypted = decrypt_password(stored_pwd)
    if decrypted is None or decrypted != password:
        return None

    first = row.get("US_FirstName") or ""
    last = row.get("US_LastName") or ""
    display_name = f"{first} {last}".strip() or row.get("US_Login", "")

    return {
        "user_id": row.get("US_ID"),
        "login": row.get("US_Login"),
        "name": display_name,
    }


def create_token(user_info: Dict[str, Any]) -> str:
    """Create a JWT token for the authenticated user."""
    secret = current_app.config.get("JWT_SECRET", "Shrujana")
    expires_in = current_app.config.get("JWT_EXPIRES_IN", 86400)

    now = datetime.now(timezone.utc)
    payload = {
        "userId": user_info["user_id"],
        "login": user_info["login"],
        "name": user_info.get("name", ""),
        "exp": int((now + timedelta(seconds=int(expires_in))).timestamp()),
        "iat": int(now.timestamp()),
    }
    return _jwt_hs256_encode(payload, secret)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify a JWT token. Returns None on failure or expiry."""
    secret = current_app.config.get("JWT_SECRET", "Shrujana")
    return _jwt_hs256_decode(token, secret)


def get_current_user() -> Optional[Dict[str, Any]]:
    """Get the current user from the JWT cookie."""
    token = request.cookies.get("auth_token")
    if not token:
        return None
    return decode_token(token)


def login_required(f: Callable) -> Callable:
    """Decorator to protect page routes — redirects to login on failure."""
    @functools.wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        user = get_current_user()
        if not user:
            return redirect(url_for("login"))
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def api_login_required():
    """Call from a before_request hook to protect all API routes.

    Returns None to let the request proceed, or a 401 response tuple.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 401
    g.current_user = user
    return None


def is_dpr_editor(user: Optional[Dict[str, Any]] = None) -> bool:
    """True if the user has plusAccess to edit_dpr in the RBAC system."""
    if user is not None and not isinstance(user, dict):
        user = get_current_user()
    if not user:
        user = get_current_user()
    if not user:
        return False

    from . import rbac
    perms = rbac.get_effective_permissions(
        user.get("userId", 0),
        user.get("login", ""),
        user.get("userId") == 43  # Admin ID
    )
    return "edit_dpr" in perms.get("plusAccess", [])


def has_rept_access(user: Optional[Dict[str, Any]] = None) -> bool:
    """True if user may view/run custom reports (REPT)."""
    if user is not None and not isinstance(user, dict):
        user = get_current_user()
    if not user:
        user = get_current_user()
    if not user:
        return False
    from . import rbac
    perms = rbac.get_effective_permissions(
        user.get("userId", 0),
        user.get("login", ""),
        user.get("userId") == 43,
    )
    return "rept" in perms.get("access", [])


def has_rept_plus_access(user: Optional[Dict[str, Any]] = None) -> bool:
    """True if user may manage report definitions (REPT+)."""
    if user is not None and not isinstance(user, dict):
        user = get_current_user()
    if not user:
        user = get_current_user()
    if not user:
        return False
    from . import rbac
    perms = rbac.get_effective_permissions(
        user.get("userId", 0),
        user.get("login", ""),
        user.get("userId") == 43,
    )
    return "rept_plus" in perms.get("plusAccess", [])


def is_buffer_editor(user: Optional[Dict[str, Any]] = None) -> bool:
    """True if the user has plusAccess to edit_buffer in the RBAC system."""
    if user is not None and not isinstance(user, dict):
        user = get_current_user()
    if not user:
        user = get_current_user()
    if not user:
        return False

    from . import rbac
    perms = rbac.get_effective_permissions(
        user.get("userId", 0),
        user.get("login", ""),
        user.get("userId") == 43
    )
    return "edit_buffer" in perms.get("plusAccess", [])
