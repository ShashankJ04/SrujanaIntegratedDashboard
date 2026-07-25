"""Inventory report row snapshots and end-of-month JSON archive scheduler."""

from __future__ import annotations

import calendar
import json
import logging
import threading
import time
from datetime import date, datetime, timedelta
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
    execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_report_rows (
            report_year INT NOT NULL,
            report_month INT NOT NULL,
            part_id INT NOT NULL,
            total_requirement DOUBLE NOT NULL DEFAULT 0,
            buffer_qty DOUBLE NOT NULL DEFAULT 0,
            total_stock DOUBLE NOT NULL DEFAULT 0,
            production_pending DOUBLE NOT NULL DEFAULT 0,
            produced_qty DOUBLE NOT NULL DEFAULT 0,
            balance_production_qty DOUBLE NOT NULL DEFAULT 0,
            PRIMARY KEY (report_year, report_month, part_id),
            INDEX idx_irr_period (report_year, report_month)
        )
        """
    )


def _resolve_part_id_from_row(row: Dict[str, Any]) -> Optional[int]:
    raw = row.get("part_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    part_no = str(row.get("part_no") or "").strip()
    if not part_no:
        return None
    db_row = fetch_one(
        """
        SELECT CO_ID AS part_id
        FROM components
        WHERE TRIM(CO_PARTNO) = %s
          AND CO_ACTIVEYN = 'Y'
          AND CO_ID = CO_PARENTID
        ORDER BY CO_ID
        LIMIT 1
        """,
        (part_no,),
    )
    if db_row and db_row.get("part_id") is not None:
        return int(db_row["part_id"])
    db_row = fetch_one(
        """
        SELECT CO_PARENTID AS part_id
        FROM components
        WHERE TRIM(CO_PARTNO) = %s AND CO_ACTIVEYN = 'Y'
        ORDER BY CO_ID
        LIMIT 1
        """,
        (part_no,),
    )
    if not db_row or db_row.get("part_id") is None:
        return None
    return int(db_row["part_id"])


def _typed_report_row_from_enriched(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    part_id = _resolve_part_id_from_row(row)
    if part_id is None:
        return None
    return {
        "part_id": part_id,
        "total_requirement": float(row.get("feb") or 0),
        "buffer_qty": float(row.get("buffer_qty") or 0),
        "total_stock": float(row.get("total_stock") or 0),
        "production_pending": float(row.get("production_pending") or 0),
        "produced_qty": float(row.get("produced_qty") or 0),
        "balance_production_qty": float(row.get("balance_production_qty") or 0),
    }


def _delete_inventory_report_rows(year: int, month: int) -> None:
    execute(
        "DELETE FROM inventory_report_rows WHERE report_year = %s AND report_month = %s",
        (year, month),
    )


def _insert_inventory_report_rows(year: int, month: int, enriched: List[Dict[str, Any]]) -> int:
    inserted = 0
    for row in enriched:
        typed = _typed_report_row_from_enriched(row)
        if not typed:
            continue
        execute(
            """
            INSERT INTO inventory_report_rows (
                report_year, report_month, part_id,
                total_requirement, buffer_qty, total_stock,
                production_pending, produced_qty, balance_production_qty
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                year,
                month,
                typed["part_id"],
                typed["total_requirement"],
                typed["buffer_qty"],
                typed["total_stock"],
                typed["production_pending"],
                typed["produced_qty"],
                typed["balance_production_qty"],
            ),
        )
        inserted += 1
    return inserted


def capture_current_month_report_rows() -> Dict[str, Any]:
    """Replace inventory_report_rows for the open calendar month with live inventory data."""
    from .models import build_enriched_inventory_rows_for_period

    ensure_inventory_snapshot_tables()
    today = date.today()
    year, month = today.year, today.month
    enriched = build_enriched_inventory_rows_for_period(month, year)
    captured_at = datetime.now()

    _delete_inventory_report_rows(year, month)
    report_row_count = _insert_inventory_report_rows(year, month, enriched)

    logger.info(
        "Captured daily inventory_report_rows for %04d-%02d (%s rows)",
        year,
        month,
        report_row_count,
    )
    return {
        "year": year,
        "month": month,
        "rowCount": len(enriched),
        "reportRowCount": report_row_count,
        "capturedAt": captured_at.isoformat(),
    }


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
    _delete_inventory_report_rows(year, month)
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

    report_row_count = _insert_inventory_report_rows(year, month, enriched)

    logger.info(
        "Captured inventory snapshot for %04d-%02d (%s rows, %s report rows)",
        year,
        month,
        len(enriched),
        report_row_count,
    )
    return {
        "year": year,
        "month": month,
        "rowCount": len(enriched),
        "reportRowCount": report_row_count,
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


def _daily_run_at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 23, 59, 0)


def _next_daily_run(from_dt: datetime) -> datetime:
    """Next wake time: 23:59 today or on a future calendar day."""
    run_at = _daily_run_at(from_dt.year, from_dt.month, from_dt.day)
    if from_dt < run_at:
        return run_at
    next_day = from_dt.date() + timedelta(days=1)
    return _daily_run_at(next_day.year, next_day.month, next_day.day)


def _next_scheduled_run(from_dt: datetime) -> datetime:
    """Next wake time: the sooner of daily report-row capture or month-end JSON snapshot."""
    return min(_next_daily_run(from_dt), _next_month_end_run(from_dt))


def _next_month_end_run(from_dt: datetime) -> datetime:
    """Next wake time: 23:59 on the last day of the current or a future month."""
    run_at = _month_end_run_at(from_dt.year, from_dt.month)
    if from_dt < run_at:
        return run_at
    if from_dt.month == 12:
        return _month_end_run_at(from_dt.year + 1, 1)
    return _month_end_run_at(from_dt.year, from_dt.month + 1)


def _try_capture_daily_report_rows_if_due(now: datetime) -> None:
    """Refresh current-month inventory_report_rows once per day at 23:59."""
    if now.hour < 23 or (now.hour == 23 and now.minute < 59):
        return
    capture_current_month_report_rows()


def _try_capture_monthly_snapshot_if_due(now: datetime) -> None:
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
                _try_capture_daily_report_rows_if_due(now)
                _try_capture_monthly_snapshot_if_due(now)
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


def bootstrap_inventory_report_rows(app: Flask) -> None:
    """Populate inventory_report_rows for the open month on application startup."""
    if not app.config.get("INVENTORY_SNAPSHOT_ENABLED", True):
        return
    with app.app_context():
        try:
            capture_current_month_report_rows()
        except Exception:
            logger.exception("Initial inventory_report_rows capture failed")


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
    logger.info("Inventory snapshot scheduler started (daily report rows + month-end JSON archive)")
