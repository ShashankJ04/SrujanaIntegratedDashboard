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


def _load_env_file() -> None:
    """Load project `.env` for flask CLI and other entrypoints (run.py also loads it)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_runtime_base_dir() / ".env")


_load_env_file()


def resolve_runtime_path(raw_path: str, fallback_relative: str) -> str:
    """Resolve file/dir paths from env for both source and packaged runs."""
    configured = str(raw_path or "").strip()
    target = configured if configured else fallback_relative
    expanded = os.path.expandvars(os.path.expanduser(target))
    p = Path(expanded)
    if p.is_absolute():
        return str(p)
    return str((_runtime_base_dir() / p).resolve())


def _parse_int_tuple_env(env_key: str, default_csv: str) -> tuple:
    raw = str(os.environ.get(env_key, "") or "").strip() or default_csv
    values: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if piece:
            values.append(int(piece))
    return tuple(values)


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
    DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "15"))
    DB_POOL_MAX_OVERFLOW = int(os.environ.get("DB_POOL_MAX_OVERFLOW", "15"))

    # JWT / Auth
    JWT_SECRET = os.environ.get("JWT_SECRET", "Shrujana")
    JWT_EXPIRES_IN = int(os.environ.get("JWT_EXPIRES_IN", "86400"))
    DES_KEY = os.environ.get("DES_KEY", "tJykDLYx")

    # DPR (Daily Production Review)
    DPR_POLL_INTERVAL_MS = int(
        os.environ.get("DPR_POLL_INTERVAL_MS", str(DPR_POLL_INTERVAL_MS_DEFAULT))
    )
    HUB_PULSE_CACHE_SECONDS = int(os.environ.get("HUB_PULSE_CACHE_SECONDS", "20"))
    HUB_SCHEMA_CACHE_SECONDS = int(os.environ.get("HUB_SCHEMA_CACHE_SECONDS", "600"))
    REPORTS_SUMMARY_CACHE_SECONDS = int(
        os.environ.get("REPORTS_SUMMARY_CACHE_SECONDS", "30")
    )
    PM_STATUS_CACHE_SECONDS = int(os.environ.get("PM_STATUS_CACHE_SECONDS", "20"))

    # Tool Management daily schedule: scheduled_production (default) | production_calendar
    _tool_schedule_raw = os.environ.get(
        "TOOL_SCHEDULE_SOURCE", "production_calendar"
    ).strip().lower()
    TOOL_SCHEDULE_SOURCE = (
        _tool_schedule_raw
        if _tool_schedule_raw in ("scheduled_production", "production_calendar")
        else "production_calendar"
    )
    TOOL_SCHEDULE_CACHE_SECONDS = int(
        os.environ.get("TOOL_SCHEDULE_CACHE_SECONDS", "30")
    )

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

    DPR_QR_STORAGE_DIR = resolve_runtime_path(
        os.environ.get("DPR_QR_STORAGE_DIR", ""),
        "qr-codes",
    )
    PM_ATTACHMENTS_DIR = resolve_runtime_path(
        os.environ.get("PM_ATTACHMENTS_DIR", ""),
        "pm-attachments",
    )

    # Inventory report — auto snapshot at 23:59 on the last day of each month
    INVENTORY_SNAPSHOT_ENABLED = os.environ.get(
        "INVENTORY_SNAPSHOT_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Production scheduling — standard work hours per day
    WORK_HOURS_PER_DAY = int(os.environ.get("WORK_HOURS_PER_DAY", "6"))

    # Soft capacity overflow per machine-day (minutes beyond nominal shift)
    CAPACITY_OVERFLOW_MINUTES = int(os.environ.get("CAPACITY_OVERFLOW_MINUTES", "30"))

    # Laser Welding — ERP stock integration (child parts inspect)
    LW_ERP_PLANT_ID = int(os.environ.get("LW_ERP_PLANT_ID", "1"))
    LW_FG_STAGE_ID = int(os.environ.get("LW_FG_STAGE_ID", "6"))
    # Part Inspection whitelist (11 parts) — separate plant/stage from default SS parts.
    LW_WHITELIST_ERP_PLANT_ID = int(os.environ.get("LW_WHITELIST_ERP_PLANT_ID", "2"))
    LW_WHITELIST_PART_INSPECTION_STAGE_ID = int(
        os.environ.get("LW_WHITELIST_PART_INSPECTION_STAGE_ID", "19")
    )
    LW_WHITELIST_CT_SOURCE_REDUCE = int(
        os.environ.get("LW_WHITELIST_CT_SOURCE_REDUCE", "1")
    )
    LW_WHITELIST_REDUCE_OP_STAGE = int(
        os.environ.get("LW_WHITELIST_REDUCE_OP_STAGE", "1")
    )
    LW_WHITELIST_QA_OUTWARD_STAGE_ID = int(
        os.environ.get("LW_WHITELIST_QA_OUTWARD_STAGE_ID", "6")
    )
    LW_WHITELIST_PACK_INWARD_OP_STAGE = int(
        os.environ.get("LW_WHITELIST_PACK_INWARD_OP_STAGE", "19")
    )
    LW_WHITELIST_PACK_INWARD_NEXT_STAGE = int(
        os.environ.get("LW_WHITELIST_PACK_INWARD_NEXT_STAGE", "6")
    )
    LW_PACKING_ERP_PLANT_ID = int(os.environ.get("LW_PACKING_ERP_PLANT_ID", "2"))
    LW_PACKING_INWARD_STAGE_ID = int(os.environ.get("LW_PACKING_INWARD_STAGE_ID", "6"))
    LW_CT_SOURCE_STOCK_TRANSFER = int(os.environ.get("LW_CT_SOURCE_STOCK_TRANSFER", "18"))
    LW_CR_SRC_FG_SEGREGATION = int(os.environ.get("LW_CR_SRC_FG_SEGREGATION", "9"))
    # Part Inspection whitelist — stable component family ids (CO_PARENTID), not part numbers.
    LW_PART_INSPECTION_PARENT_IDS: tuple = _parse_int_tuple_env(
        "LW_PART_INSPECTION_PARENT_IDS",
        "1624,1775,1776,1782,1656,1654,1655,1668,1538,1539,1540",
    )


def get_config():
    """Return the active configuration class."""
    return Config
