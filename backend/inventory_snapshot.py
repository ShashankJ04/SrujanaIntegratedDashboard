"""End-of-month inventory report snapshots and scheduler."""

from __future__ import annotations

import calendar
import json
import logging
import threading
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask

from .db import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)

_SCHEDULER_STARTED = False


def ensure_inventory_snapshot_tables() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_monthly_snapshots (
            snapshot_year INT NOT NULL,
            snapshot_month INT NOT NULL,
            captured_at DATETIME NOT NULL,
            row_count INT NOT NULL DEFAULT 0,
            PRIMARY KEY (snapshot_year, snapshot_month)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_monthly_snapshot_rows (
            snapshot_year INT NOT NULL,
            snapshot_month INT NOT NULL,
            part_no VARCHAR(128) NOT NULL,
            row_json JSON NOT NULL,
            PRIMARY KEY (snapshot_year, snapshot_month, part_no),
            INDEX idx_inv_snap_period (snapshot_year, snapshot_month)
        )
        """
    )


def snapshot_exists(year: int, month: int) -> bool:
    row = fetch_one(
        """
        SELECT 1 AS ok
        FROM inventory_monthly_snapshots
        WHERE snapshot_year = %s AND snapshot_month = %s
        LIMIT 1
        """,
        (year, month),
    )
    return bool(row)


def list_snapshot_periods() -> List[Dict[str, Any]]:
    ensure_inventory_snapshot_tables()
    rows = fetch_all(
        """
        SELECT snapshot_year, snapshot_month, captured_at, row_count
        FROM inventory_monthly_snapshots
        ORDER BY snapshot_year DESC, snapshot_month DESC
        """
    )
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        captured = row.get("captured_at")
        out.append(
            {
                "year": int(row["snapshot_year"]),
                "month": int(row["snapshot_month"]),
                "capturedAt": captured.isoformat() if hasattr(captured, "isoformat") else str(captured),
                "rowCount": int(row.get("row_count") or 0),
            }
        )
    return out


def _decode_row_json(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def load_snapshot_rows(year: int, month: int) -> Optional[List[Dict[str, Any]]]:
    ensure_inventory_snapshot_tables()
    if not snapshot_exists(year, month):
        return None
    rows = fetch_all(
        """
        SELECT row_json
        FROM inventory_monthly_snapshot_rows
        WHERE snapshot_year = %s AND snapshot_month = %s
        ORDER BY part_no
        """,
        (year, month),
    )
    return [_decode_row_json(r.get("row_json")) for r in rows or []]


def capture_monthly_snapshot(year: int, month: int) -> Dict[str, Any]:
    """Persist the current enriched inventory grid for a calendar month."""
    from .models import build_enriched_inventory_rows_for_period

    ensure_inventory_snapshot_tables()
    enriched = build_enriched_inventory_rows_for_period(month, year)
    captured_at = datetime.now()

    execute(
        "DELETE FROM inventory_monthly_snapshot_rows WHERE snapshot_year = %s AND snapshot_month = %s",
        (year, month),
    )
    execute(
        "DELETE FROM inventory_monthly_snapshots WHERE snapshot_year = %s AND snapshot_month = %s",
        (year, month),
    )
    execute(
        """
        INSERT INTO inventory_monthly_snapshots
            (snapshot_year, snapshot_month, captured_at, row_count)
        VALUES (%s, %s, %s, %s)
        """,
        (year, month, captured_at, len(enriched)),
    )

    for row in enriched:
        part_no = str(row.get("part_no") or "").strip()
        if not part_no:
            continue
        execute(
            """
            INSERT INTO inventory_monthly_snapshot_rows
                (snapshot_year, snapshot_month, part_no, row_json)
            VALUES (%s, %s, %s, %s)
            """,
            (year, month, part_no, json.dumps(row, default=str)),
        )

    logger.info(
        "Captured inventory snapshot for %04d-%02d (%s rows)",
        year,
        month,
        len(enriched),
    )
    return {
        "year": year,
        "month": month,
        "rowCount": len(enriched),
        "capturedAt": captured_at.isoformat(),
    }


def is_current_inventory_period(year: int, month: int) -> bool:
    today = date.today()
    return year == today.year and month == today.month


def parse_period_args(year_raw: Any, month_raw: Any) -> Tuple[Optional[int], Optional[int], Optional[tuple]]:
    if year_raw in (None, "") and month_raw in (None, ""):
        today = date.today()
        return today.year, today.month, None
    if year_raw in (None, "") or month_raw in (None, ""):
        return None, None, ({"error": "year and month must be provided together"}, 400)
    try:
        year = int(year_raw)
        month = int(month_raw)
    except (TypeError, ValueError):
        return None, None, ({"error": "Invalid year or month"}, 400)
    if month < 1 or month > 12:
        return None, None, ({"error": "Invalid month"}, 400)
    if year < 2000 or year > 2100:
        return None, None, ({"error": "Invalid year"}, 400)
    return year, month, None


def _month_end_run_at(year: int, month: int) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    return datetime(year, month, last_day, 23, 59, 0)


def _next_scheduled_run(from_dt: datetime) -> datetime:
    """Next wake time: 23:59 on the last day of the current or a future month."""
    run_at = _month_end_run_at(from_dt.year, from_dt.month)
    if from_dt < run_at:
        return run_at
    if from_dt.month == 12:
        return _month_end_run_at(from_dt.year + 1, 1)
    return _month_end_run_at(from_dt.year, from_dt.month + 1)


def _try_capture_if_due(now: datetime) -> None:
    """Capture once when the clock reaches month-end 23:59 (server local time)."""
    last_day = calendar.monthrange(now.year, now.month)[1]
    if now.day != last_day or now.hour < 23 or (now.hour == 23 and now.minute < 59):
        return
    year, month = now.year, now.month
    if not snapshot_exists(year, month):
        capture_monthly_snapshot(year, month)


def _scheduler_loop(app: Flask) -> None:
    disabled_sleep = 3600.0
    while True:
        sleep_seconds = disabled_sleep
        try:
            with app.app_context():
                if not app.config.get("INVENTORY_SNAPSHOT_ENABLED", True):
                    time.sleep(disabled_sleep)
                    continue

                now = datetime.now()
                _try_capture_if_due(now)
                next_run = _next_scheduled_run(now)
                sleep_seconds = max(1.0, (next_run - datetime.now()).total_seconds())
                logger.info(
                    "Inventory snapshot scheduler next run at %s (sleep %.0fs)",
                    next_run.strftime("%Y-%m-%d %H:%M"),
                    sleep_seconds,
                )
        except Exception:
            logger.exception("Inventory snapshot scheduler failed")
            sleep_seconds = 60.0
        time.sleep(sleep_seconds)


def start_inventory_snapshot_scheduler(app: Flask) -> None:
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    if not app.config.get("INVENTORY_SNAPSHOT_ENABLED", True):
        return
    # Avoid duplicate threads under Flask debug reloader.
    if app.debug and app.config.get("WERKZEUG_RUN_MAIN") != "true":
        return
    ensure_inventory_snapshot_tables()
    thread = threading.Thread(
        target=_scheduler_loop,
        args=(app,),
        name="inventory-snapshot-scheduler",
        daemon=True,
    )
    thread.start()
    _SCHEDULER_STARTED = True
    logger.info("Inventory monthly snapshot scheduler started")
