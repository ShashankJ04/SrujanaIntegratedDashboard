import os


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


def get_config():
    """Return the active configuration class.

    The main app will first try to import Config from `config.py`;
    if that doesn't exist, it can fall back to this example.
    """

    return Config

