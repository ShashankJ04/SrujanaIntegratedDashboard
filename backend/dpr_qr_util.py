"""DPR machine QR public URLs — no warehouse/receiver coupling."""

from __future__ import annotations

import os
import socket
from typing import Any


def detect_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_machine_ip_for_qr(config: Any) -> str:
    """`MACHINE_IP` env / Flask config; else LAN IP (same idea as shop-floor default)."""
    h = ""
    try:
        h = str(config.get("MACHINE_IP", "") or "").strip()
    except Exception:
        pass
    if h:
        return h
    raw = os.environ.get("MACHINE_IP", "").strip()
    if raw:
        return raw
    return detect_lan_ip()


def get_app_port_for_qr(config: Any) -> int:
    try:
        return int(config.get("APP_PORT", 5000))
    except (TypeError, ValueError):
        try:
            return int(os.environ.get("APP_PORT", os.environ.get("PORT", "5000")))
        except (TypeError, ValueError):
            return 5000


def build_dpr_machine_scan_url(config: Any, qr_token: str) -> str:
    """Encoded in printed QR, e.g. http://192.168.29.193:5000/machine/<token>."""
    host = get_machine_ip_for_qr(config)
    port = get_app_port_for_qr(config)
    tok = str(qr_token or "").strip()
    return f"http://{host}:{port}/machine/{tok}"
