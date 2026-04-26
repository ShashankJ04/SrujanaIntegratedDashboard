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

    # Table to visualize in the dashboard
    TARGET_TABLE_NAME = os.environ.get("TARGET_TABLE_NAME", "your_table_name_here")

    # Pagination defaults
    DEFAULT_PAGE_SIZE = int(os.environ.get("DEFAULT_PAGE_SIZE", "25"))
    MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", "200"))
    HUB_PULSE_CACHE_SECONDS = int(os.environ.get("HUB_PULSE_CACHE_SECONDS", "20"))
    HUB_SCHEMA_CACHE_SECONDS = int(os.environ.get("HUB_SCHEMA_CACHE_SECONDS", "600"))
    REPORTS_SUMMARY_CACHE_SECONDS = int(
        os.environ.get("REPORTS_SUMMARY_CACHE_SECONDS", "30")
    )
    PM_STATUS_CACHE_SECONDS = int(os.environ.get("PM_STATUS_CACHE_SECONDS", "20"))

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

