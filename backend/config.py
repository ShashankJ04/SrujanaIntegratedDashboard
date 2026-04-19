import os

# DPR version polling (Hub `dpr.js` + shop-floor `machine_dpr.js`) — keep in sync with JS fallbacks.
DPR_POLL_INTERVAL_MS_DEFAULT = 500_000


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

    # Shop-floor DPR machine QR (encoded URL uses this host; if empty, LAN IP is detected)
    MACHINE_IP = os.environ.get("MACHINE_IP", "").strip()
    APP_PORT = int(os.environ.get("APP_PORT", os.environ.get("PORT", "5000")))

    # PM attachments directory (relative to project root)
    PM_ATTACHMENTS_DIR = os.environ.get("PM_ATTACHMENTS_DIR", "pm-attachments")



def get_config():
    """Return the active configuration class.

    The main app will first try to import Config from `config.py`;
    if that doesn't exist, it can fall back to this example.
    """

    return Config