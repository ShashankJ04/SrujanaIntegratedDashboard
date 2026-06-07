from __future__ import annotations

import contextlib
import os
import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

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


class _ConnectionPool:
    """Thread-safe pool of reusable PyMySQL connections."""

    def __init__(
        self,
        create_connection: Callable[[], pymysql.connections.Connection],
        max_size: int,
        max_overflow: int = 10,
    ) -> None:
        self._create_connection = create_connection
        self._max_size = max(1, int(max_size))
        self._max_overflow = max(0, int(max_overflow))
        self._max_total = self._max_size + self._max_overflow
        self._pool: Queue[pymysql.connections.Connection] = Queue(maxsize=self._max_size)
        self._created = 0
        self._lock = threading.Lock()

    def acquire(self) -> pymysql.connections.Connection:
        try:
            conn = self._pool.get_nowait()
        except Empty:
            conn = None

        if conn is not None:
            if self._ping(conn):
                return conn
            self._discard(conn)

        with self._lock:
            if self._created < self._max_total:
                self._created += 1
                try:
                    return self._create_connection()
                except Exception:
                    self._created -= 1
                    raise

        try:
            conn = self._pool.get(timeout=30)
        except Empty as exc:
            raise RuntimeError(
                f"Database connection pool exhausted ({self._max_total} connections in use)"
            ) from exc

        if self._ping(conn):
            return conn
        self._discard(conn)
        return self.acquire()

    def release(self, conn: pymysql.connections.Connection) -> None:
        if conn is None:
            return
        try:
            conn.rollback()
        except Exception:
            self._discard(conn)
            return
        try:
            self._pool.put_nowait(conn)
        except Exception:
            self._discard(conn)

    def _ping(self, conn: pymysql.connections.Connection) -> bool:
        try:
            conn.ping(reconnect=True)
            return True
        except Exception:
            return False

    def _discard(self, conn: pymysql.connections.Connection) -> None:
        try:
            conn.close()
        except Exception:
            pass
        with self._lock:
            self._created = max(0, self._created - 1)


_pool_lock = threading.Lock()
_erp_pool: Optional[_ConnectionPool] = None


def _pool_size(config_key: str, env_key: str, default: int = 10) -> int:
    try:
        return max(1, int(current_app.config.get(config_key, default)))
    except RuntimeError:
        return max(1, int(os.environ.get(env_key, default)))


def _pool_overflow(config_key: str, env_key: str, default: int = 15) -> int:
    try:
        return max(0, int(current_app.config.get(config_key, default)))
    except RuntimeError:
        return max(0, int(os.environ.get(env_key, default)))


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


def _connect_from_config(cfg: DBConfig) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.db,
        charset=cfg.charset,
        cursorclass=cfg.cursorclass,
        autocommit=False,
    )


def _get_erp_pool() -> _ConnectionPool:
    global _erp_pool
    if _erp_pool is not None:
        return _erp_pool
    with _pool_lock:
        if _erp_pool is None:
            max_size = _pool_size("DB_POOL_SIZE", "DB_POOL_SIZE", 15)
            max_overflow = _pool_overflow("DB_POOL_MAX_OVERFLOW", "DB_POOL_MAX_OVERFLOW", 15)

            def _create() -> pymysql.connections.Connection:
                return _connect_from_config(_load_db_config())

            _erp_pool = _ConnectionPool(_create, max_size, max_overflow)
    return _erp_pool


@contextlib.contextmanager
def get_cursor() -> Iterator[pymysql.cursors.Cursor]:
    pool = _get_erp_pool()
    conn = pool.acquire()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool.release(conn)


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
