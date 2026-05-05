import os
import sys
from pathlib import Path

# DPR version polling (Hub `dpr.js` + shop-floor `machine_dpr.js`) — keep in sync with JS fallbacks.
DPR_POLL_INTERVAL_MS_DEFAULT = 500_000


def _runtime_base_dir() -> Path:
    """Project root in dev, executable directory when packaged."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_runtime_path(raw_path: str, fallback_relative: str) -> str:
    """Resolve file/dir paths from env for both source and packaged runs."""
    configured = str(raw_path or "").strip()
    target = configured if configured else fallback_relative
    expanded = os.path.expandvars(os.path.expanduser(target))
    p = Path(expanded)
    if p.is_absolute():
        return str(p)
    return str((_runtime_base_dir() / p).resolve())


class Config:
    """Application configuration.

    Values are read from the process environment. Use a `.env` file in the
    project root (development) or next to the packaged executable (PyInstaller)
    — loaded in `run.py` before this module is imported.
    """

    # MySQL connection settings — ERP database
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "root")
    DB_NAME = os.environ.get("DB_NAME", "erp")

    # MySQL connection settings — Warehouse database (separate)
    WH_DB_HOST = os.environ.get("WH_DB_HOST", "localhost")
    WH_DB_PORT = int(os.environ.get("WH_DB_PORT", "3306"))
    WH_DB_USER = os.environ.get("WH_DB_USER", "root")
    WH_DB_PASSWORD = os.environ.get("WH_DB_PASSWORD", "root")
    WH_DB_NAME = os.environ.get("WH_DB_NAME", "warehouse_db")

    # Table to visualize in the dashboard
    TARGET_TABLE_NAME = os.environ.get("TARGET_TABLE_NAME", "vw_bharat_dashboard")

    # JWT / Auth
    JWT_SECRET = os.environ.get("JWT_SECRET", "Shrujana")
    JWT_EXPIRES_IN = int(os.environ.get("JWT_EXPIRES_IN", "86400"))
    DES_KEY = os.environ.get("DES_KEY", "tJykDLYx")

    # Pagination defaults
    DEFAULT_PAGE_SIZE = int(os.environ.get("DEFAULT_PAGE_SIZE", "25"))
    MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", "200"))

    # User logins allowed to edit buffer qty on the report table (comma-separated)
    BUFFER_EDIT_LOGINS = frozenset(
        x.strip()
        for x in os.environ.get("BUFFER_EDIT_LOGINS", "Bharath,U3_Bharath").split(",")
        if x.strip()
    )

    # DPR (Daily Production Review)
    DPR_EDIT_LOGINS = frozenset(
        x.strip().lower()
        for x in os.environ.get("DPR_EDIT_LOGINS", "bharath,u3_bharath,vivaan").split(",")
        if x.strip()
    )
    DPR_MACHINE_LIST_SQL = os.environ.get(
        "DPR_MACHINE_LIST_SQL",
        "SELECT MCM_Id AS id, MCM_Name AS label FROM machinemaster WHERE MCM_ACTIVEYN = 'Y' ORDER BY MCM_Name",
    )
    DPR_POLL_INTERVAL_MS = int(
        os.environ.get("DPR_POLL_INTERVAL_MS", str(DPR_POLL_INTERVAL_MS_DEFAULT))
    )
    HUB_PULSE_CACHE_SECONDS = int(os.environ.get("HUB_PULSE_CACHE_SECONDS", "20"))
    HUB_SCHEMA_CACHE_SECONDS = int(os.environ.get("HUB_SCHEMA_CACHE_SECONDS", "600"))
    REPORTS_SUMMARY_CACHE_SECONDS = int(
        os.environ.get("REPORTS_SUMMARY_CACHE_SECONDS", "30")
    )
    PM_STATUS_CACHE_SECONDS = int(os.environ.get("PM_STATUS_CACHE_SECONDS", "20"))

    # Shop-floor DPR machine QR (encoded URL uses this host; if empty, LAN IP is detected)
    MACHINE_IP = os.environ.get("MACHINE_IP", "").strip()
    APP_PORT = int(os.environ.get("APP_PORT", os.environ.get("PORT", "5000")))

    # Operational data and runtime directories (safe for exe packaging)
    APP_DATA_DIR = resolve_runtime_path(os.environ.get("APP_DATA_DIR", ""), "data")
    RBAC_STORE_FILE = resolve_runtime_path(
        os.environ.get("RBAC_STORE_FILE", ""),
        os.path.join(APP_DATA_DIR, "rbac.json"),
    )
    REPORTS_STORE_FILE = resolve_runtime_path(
        os.environ.get("REPORTS_STORE_FILE", ""),
        os.path.join(APP_DATA_DIR, "reports.json"),
    )

    # Bumped when static assets change so packaged apps avoid stale browser/embedded caches.
    STATIC_ASSET_VERSION = str(os.environ.get("STATIC_ASSET_VERSION", "3")).strip() or "3"
    DPR_QR_STORAGE_DIR = resolve_runtime_path(
        os.environ.get("DPR_QR_STORAGE_DIR", ""),
        "qr-codes",
    )
    PM_ATTACHMENTS_DIR = resolve_runtime_path(
        os.environ.get("PM_ATTACHMENTS_DIR", ""),
        "pm-attachments",
    )



def get_config():
    """Return the active configuration class.

    The main app will first try to import Config from `config.py`;
    if that doesn't exist, it can fall back to this example.
    """

    return Config