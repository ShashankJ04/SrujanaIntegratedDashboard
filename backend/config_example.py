import os
from pathlib import Path
import sys


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_runtime_path(raw_path: str, fallback_relative: str) -> str:
    configured = str(raw_path or "").strip()
    target = configured if configured else fallback_relative
    expanded = os.path.expandvars(os.path.expanduser(target))
    p = Path(expanded)
    if p.is_absolute():
        return str(p)
    return str((_runtime_base_dir() / p).resolve())


class Config:
    """Example configuration for the dashboard app.

    Copy this file to `config.py` and adjust values or
    use environment variables in production.
    """

    # MySQL connection settings
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "test")
    DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "15"))
    DB_POOL_MAX_OVERFLOW = int(os.environ.get("DB_POOL_MAX_OVERFLOW", "15"))

    HUB_PULSE_CACHE_SECONDS = int(os.environ.get("HUB_PULSE_CACHE_SECONDS", "20"))
    HUB_SCHEMA_CACHE_SECONDS = int(os.environ.get("HUB_SCHEMA_CACHE_SECONDS", "600"))
    REPORTS_SUMMARY_CACHE_SECONDS = int(
        os.environ.get("REPORTS_SUMMARY_CACHE_SECONDS", "30")
    )
    PM_STATUS_CACHE_SECONDS = int(os.environ.get("PM_STATUS_CACHE_SECONDS", "20"))
    INVENTORY_BASE_CACHE_SECONDS = int(
        os.environ.get("INVENTORY_BASE_CACHE_SECONDS", "300")
    )
    LW_PART_INSPECTION_CACHE_SECONDS = int(
        os.environ.get("LW_PART_INSPECTION_CACHE_SECONDS", "300")
    )

    # Runtime paths for packaged deployments
    APP_DATA_DIR = resolve_runtime_path(os.environ.get("APP_DATA_DIR", ""), "data")
    RBAC_STORE_FILE = resolve_runtime_path(
        os.environ.get("RBAC_STORE_FILE", ""),
        os.path.join(APP_DATA_DIR, "rbac.json"),
    )
    REPORTS_STORE_FILE = resolve_runtime_path(
        os.environ.get("REPORTS_STORE_FILE", ""),
        os.path.join(APP_DATA_DIR, "reports.json"),
    )


def get_config():
    """Return the active configuration class.

    The main app will first try to import Config from `config.py`;
    if that doesn't exist, it can fall back to this example.
    """

    return Config

