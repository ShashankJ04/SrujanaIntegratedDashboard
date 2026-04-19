from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Sequence

import pymysql
from flask import current_app


@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    db: str
    charset: str = "utf8mb4"
    cursorclass: Any = pymysql.cursors.DictCursor


def _load_db_config() -> DBConfig:
    """
    Prefer Flask app config (from Config / config.py), fall back to environment
    variables. This keeps DB settings in one place.
    """
    host = "localhost"
    port = 3306
    user = "root"
    password = ""
    db_name = "test"

    try:
        cfg = current_app.config
        host = cfg.get("DB_HOST", host)
        port = int(cfg.get("DB_PORT", port))
        user = cfg.get("DB_USER", user)
        password = cfg.get("DB_PASSWORD", password)
        db_name = cfg.get("DB_NAME", db_name)
    except RuntimeError:
        # Not in an application context yet – use environment variables
        host = os.environ.get("DB_HOST", host)
        port = int(os.environ.get("DB_PORT", port))
        user = os.environ.get("DB_USER", user)
        password = os.environ.get("DB_PASSWORD", password)
        db_name = os.environ.get("DB_NAME", db_name)

    return DBConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db_name,
    )


def get_connection() -> pymysql.connections.Connection:
    """Create a new DB connection.

    In a production setting you might prefer pooling; for this
    dashboard-scale app, short-lived connections are fine.
    """

    cfg = _load_db_config()

    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.db,
        charset=cfg.charset,
        cursorclass=cfg.cursorclass,
    )


@contextlib.contextmanager
def get_cursor() -> Iterator[pymysql.cursors.Cursor]:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    finally:
        conn.close()


def fetch_all(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> List[Dict[str, Any]]:
    with get_cursor() as cursor:
        cursor.execute(sql, params or ())
        rows: List[Dict[str, Any]] = list(cursor.fetchall())
    return rows


def fetch_one(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> Optional[Dict[str, Any]]:
    with get_cursor() as cursor:
        cursor.execute(sql, params or ())
        row = cursor.fetchone()
    return row


def execute(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> int:
    with get_cursor() as cursor:
        affected = cursor.execute(sql, params or ())
    return affected


# ── Warehouse DB (separate database) ───────────────────────────────────

def _load_warehouse_db_config() -> DBConfig:
    """Load warehouse_db connection settings from Flask config or env."""
    host = "localhost"
    port = 3306
    user = "root"
    password = ""
    db_name = "warehouse_db"

    try:
        cfg = current_app.config
        host = cfg.get("WH_DB_HOST", host)
        port = int(cfg.get("WH_DB_PORT", port))
        user = cfg.get("WH_DB_USER", user)
        password = cfg.get("WH_DB_PASSWORD", password)
        db_name = cfg.get("WH_DB_NAME", db_name)
    except RuntimeError:
        host = os.environ.get("WH_DB_HOST", host)
        port = int(os.environ.get("WH_DB_PORT", port))
        user = os.environ.get("WH_DB_USER", user)
        password = os.environ.get("WH_DB_PASSWORD", password)
        db_name = os.environ.get("WH_DB_NAME", db_name)

    return DBConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db_name,
    )


def get_warehouse_connection() -> pymysql.connections.Connection:
    """Create a new connection to the warehouse database."""
    cfg = _load_warehouse_db_config()
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.db,
        charset=cfg.charset,
        cursorclass=cfg.cursorclass,
    )


@contextlib.contextmanager
def get_warehouse_cursor() -> Iterator[pymysql.cursors.Cursor]:
    conn = get_warehouse_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    finally:
        conn.close()


def wh_fetch_all(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> List[Dict[str, Any]]:
    with get_warehouse_cursor() as cursor:
        cursor.execute(sql, params or ())
        rows: List[Dict[str, Any]] = list(cursor.fetchall())
    return rows


def wh_fetch_one(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> Optional[Dict[str, Any]]:
    with get_warehouse_cursor() as cursor:
        cursor.execute(sql, params or ())
        row = cursor.fetchone()
    return row


def wh_execute(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> int:
    with get_warehouse_cursor() as cursor:
        affected = cursor.execute(sql, params or ())
    return affected

