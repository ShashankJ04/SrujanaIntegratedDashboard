"""Dispatch Calendar — Monthly Order + Consolidated Stock merge for Hub section."""

from __future__ import annotations

import calendar
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from . import reports_store
from .db import fetch_all

MONTHLY_ORDER_REPORT_ID = "dd2e5dd7-d47e-43bb-8a5c-b838c5bd88c3"
STOCK_REPORT_ID = "5c7c5e6c-6f88-4f6e-9b69-bc0f63c8a663"
DISPATCH_BETWEEN_DATES_REPORT_ID = "a491c9dc-b8a5-4d9c-92f2-073926e837e0"

logger = logging.getLogger(__name__)

FG_STOCK_COL = "FG (Stock)"
PART_NO_COL = "Part No"
TOTAL_QTY_COL = "Total Qty"


def _normalize_part_key(part_no: Any) -> str:
    return str(part_no or "").strip().lower()


def _to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _serialize_cell(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float, str, bool)):
        return v
    if hasattr(v, "isoformat"):
        return str(v)
    return v


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _serialize_cell(v) for k, v in row.items()}


def _fg_wip_from_stock_row(stock_row: Dict[str, Any]) -> Tuple[float, float]:
    fg = _to_float(stock_row.get(FG_STOCK_COL))
    wip = 0.0
    for k, v in stock_row.items():
        if k == FG_STOCK_COL:
            continue
        if isinstance(k, str) and k.endswith("(Stock)"):
            wip += _to_float(v)
    return fg, wip


def _build_stock_index(stock_rows: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    out: Dict[str, Tuple[float, float]] = {}
    for sr in stock_rows:
        key = _normalize_part_key(_mo_part_no_raw(sr))
        if not key:
            continue
        out[key] = _fg_wip_from_stock_row(sr)
    return out


def _is_grand_total_row(row: Dict[str, Any]) -> bool:
    return _normalize_part_key(_mo_part_no_raw(row)) == "grand total"


def _day_column_key(day: int) -> str:
    return f"day {day}"


REQUESTED_DATE_COL = "Requested Date"
DISPATCHED_QTY_COL = "Dispatched Qty(Nos)"


def _first_matching_key(row: Dict[str, Any], candidates: Tuple[str, ...]) -> Any:
    """Resolve a column value when drivers may vary casing/aliases (PyMySQL dict keys)."""
    for name in candidates:
        if name in row:
            return row[name]
    lower_index = {str(k).lower(): k for k in row.keys()}
    for name in candidates:
        lk = name.lower()
        if lk in lower_index:
            return row[lower_index[lk]]
    return None


def _mo_part_no_raw(row: Dict[str, Any]) -> Any:
    """Resolve part number from Monthly Order / stock rows (driver-specific column names)."""
    return _first_matching_key(
        row,
        (
            PART_NO_COL,
            "Part No",
            "part no",
            "CO_PARTNO",
            "CO_partNo",
            "partno",
            "PARTNO",
        ),
    )


def _parse_calendar_day_value(
    raw: Any, month: int, year: int, days_in_month: int
) -> Optional[int]:
    """Calendar day-of-month in `month`/`year`, or None (DD-MM-YYYY, ISO, date/datetime)."""
    if raw is None:
        return None
    if isinstance(raw, (date, datetime)):
        dt = raw if isinstance(raw, date) else raw.date()
        if dt.month != month or dt.year != year:
            return None
        if 1 <= dt.day <= days_in_month:
            return int(dt.day)
        return None
    text = str(raw).strip()
    if not text:
        return None
    # ISO date or datetime prefix (e.g. JSON / str(datetime))
    iso_m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if iso_m:
        y, mo, d_d = int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))
        if mo == month and y == year and 1 <= d_d <= days_in_month:
            return d_d
        return None
    # DD-MM-YYYY (report SQL uses DATE_FORMAT … '%d-%m-%Y')
    norm = text.replace(".", "-").replace("/", "-")
    parts = norm.split("-")
    if len(parts) != 3:
        return None
    try:
        d_d, d_m, d_y = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    if d_y < 100:
        d_y += 2000 if d_y < 70 else 1900
    if d_m != month or d_y != year:
        return None
    if 1 <= d_d <= days_in_month:
        return d_d
    return None


def _parse_calendar_day_from_dispatch_row(
    row: Dict[str, Any], month: int, year: int, days_in_month: int
) -> Optional[int]:
    """Return calendar day-of-month (1..days_in_month) for CS_DATE–aligned dispatch row, or None."""
    raw = _first_matching_key(
        row,
        (
            REQUESTED_DATE_COL,
            "Requested Date",
            "requested date",
        ),
    )
    return _parse_calendar_day_value(raw, month, year, days_in_month)


def _aggregate_dispatch_rows(
    rows: List[Dict[str, Any]],
    month: int,
    year: int,
    days_in_month: int,
) -> Tuple[Dict[str, Dict[int, float]], Dict[int, float]]:
    """Sum dispatched qty by normalized part and by calendar day (CS_DATE via Requested Date column)."""
    part_day: Dict[str, Dict[int, float]] = {}
    day_totals: Dict[int, float] = {}
    for r in rows:
        day_i = _parse_calendar_day_from_dispatch_row(r, month, year, days_in_month)
        if day_i is None:
            continue
        dq = _to_float(
            _first_matching_key(
                r,
                (
                    DISPATCHED_QTY_COL,
                    "Dispatched Qty(Nos)",
                    "SD_LOTSIZE",
                ),
            )
        )
        # Always credit daily totals — part keys can differ by driver/casing; skipping rows
        # previously dropped all dispatch qty from Grand Total dayDispatch.
        day_totals[day_i] = day_totals.get(day_i, 0.0) + dq
        pk = _normalize_part_key(
            _first_matching_key(
                r,
                (
                    PART_NO_COL,
                    "CO_PARTNO",
                    "CO_partNo",
                    "co_partno",
                ),
            )
        )
        if not pk:
            continue
        part_day.setdefault(pk, {})
        part_day[pk][day_i] = part_day[pk].get(day_i, 0.0) + dq
    return part_day, day_totals


def _fetch_dispatch_between_dates(month: int, year: int, days_in_month: int) -> List[Dict[str, Any]]:
    rep = reports_store.get_report_by_id(DISPATCH_BETWEEN_DATES_REPORT_ID)
    if not rep:
        logger.warning("Dispatch between dates report not found in store")
        return []
    from_date = f"01-{month:02d}-{year}"
    to_date = f"{days_in_month:02d}-{month:02d}-{year}"
    try:
        sql, params = reports_store.compile_report_query(
            rep["queryTemplate"],
            {"fromDate": from_date, "toDate": to_date},
        )
        return list(fetch_all(sql, tuple(params)))
    except Exception as e:
        logger.exception("Dispatch calendar: dispatch report query failed: %s", e)
        return []


def build_dispatch_calendar_payload(month: int, year: int) -> Dict[str, Any]:
    if month < 1 or month > 12:
        raise ValueError("month must be 1–12")
    if year < 1900 or year > 2100:
        raise ValueError("year out of range")

    mo_report = reports_store.get_report_by_id(MONTHLY_ORDER_REPORT_ID)
    if not mo_report:
        raise ValueError("Monthly Order report not found in store")
    st_report = reports_store.get_report_by_id(STOCK_REPORT_ID)
    if not st_report:
        raise ValueError("Current Consolidated Component Stock report not found in store")

    mo_sql, mo_params = reports_store.compile_report_query(
        mo_report["queryTemplate"],
        {"month": month, "year": year},
    )
    st_sql, st_params = reports_store.compile_report_query(
        st_report["queryTemplate"],
        {},
    )

    mo_rows = fetch_all(mo_sql, tuple(mo_params))
    st_rows = fetch_all(st_sql, tuple(st_params))

    stock_index = _build_stock_index(st_rows)

    days_in_month = calendar.monthrange(year, month)[1]

    columns: List[str] = list(mo_rows[0].keys()) if mo_rows else []

    serialized_rows: List[Dict[str, Any]] = [_serialize_row(r) for r in mo_rows]

    grand_total_stock_fg = 0.0
    grand_total_stock_wip = 0.0
    grand_scheduled_by_day: Dict[int, float] = {}

    for raw in mo_rows:
        if _is_grand_total_row(raw):
            for d in range(1, days_in_month + 1):
                grand_scheduled_by_day[d] = _to_float(raw.get(_day_column_key(d)))
            continue
        pk = _normalize_part_key(_mo_part_no_raw(raw))
        if not pk:
            continue
        fg, wip = stock_index.get(pk, (0.0, 0.0))
        grand_total_stock_fg += fg
        grand_total_stock_wip += wip

    dispatch_rows = _fetch_dispatch_between_dates(month, year, days_in_month)
    part_day_dispatched, day_dispatched_totals = _aggregate_dispatch_rows(
        dispatch_rows, month, year, days_in_month
    )

    eps_pct = 1e-9
    day_scheduled_json: Dict[str, float] = {}
    day_dispatched_json: Dict[str, float] = {}
    day_pct_json: Dict[str, Optional[float]] = {}
    for d in range(1, days_in_month + 1):
        sch = float(grand_scheduled_by_day.get(d, 0.0))
        dis = float(day_dispatched_totals.get(d, 0.0))
        day_scheduled_json[str(d)] = round(sch, 4)
        day_dispatched_json[str(d)] = round(dis, 4)
        if sch > eps_pct:
            day_pct_json[str(d)] = round(100.0 * dis / sch, 2)
        else:
            day_pct_json[str(d)] = None

    part_day_dispatch: Dict[str, Dict[str, Dict[str, float]]] = {}
    for raw in mo_rows:
        if _is_grand_total_row(raw):
            continue
        pk = _normalize_part_key(_mo_part_no_raw(raw))
        if not pk:
            continue
        by_day: Dict[str, Dict[str, float]] = {}
        for d in range(1, days_in_month + 1):
            scheduled = _to_float(raw.get(_day_column_key(d)))
            dispatched = float(part_day_dispatched.get(pk, {}).get(d, 0.0))
            by_day[str(d)] = {
                "dispatched": round(dispatched, 4),
                "scheduledQty": round(scheduled, 4),
            }
        part_day_dispatch[pk] = by_day

    row_meta: List[Optional[Dict[str, Any]]] = []
    for raw in mo_rows:
        if _is_grand_total_row(raw):
            row_meta.append(
                {
                    "isGrandTotal": True,
                    "grandTotalStock": {
                        "stockFg": round(grand_total_stock_fg, 4),
                        "stockWip": round(grand_total_stock_wip, 4),
                    },
                }
            )
            continue

        pk = _normalize_part_key(_mo_part_no_raw(raw))
        fg, wip = stock_index.get(pk, (0.0, 0.0))
        remaining = fg + wip
        partial_used = False
        day_status: Dict[str, Dict[str, str]] = {}

        for d in range(1, 32):
            if d > days_in_month:
                break
            qty = _to_float(raw.get(_day_column_key(d)))
            if qty <= eps_pct:
                continue
            if remaining + eps_pct >= qty:
                status = "full"
            elif remaining > eps_pct:
                if not partial_used:
                    status = "partial"
                    partial_used = True
                else:
                    status = "short"
            else:
                status = "short"
            day_status[str(d)] = {"status": status}
            remaining -= qty

        row_meta.append(
            {
                "stockFg": round(fg, 4),
                "stockWip": round(wip, 4),
                "dayStatus": day_status,
            }
        )

    return {
        "month": month,
        "year": year,
        "daysInMonth": days_in_month,
        "columns": columns,
        "rows": serialized_rows,
        "rowMeta": row_meta,
        "grandTotalStock": {
            "stockFg": round(grand_total_stock_fg, 4),
            "stockWip": round(grand_total_stock_wip, 4),
        },
        "dayDispatch": {
            "scheduled": day_scheduled_json,
            "dispatched": day_dispatched_json,
            "pct": day_pct_json,
        },
        "partDayDispatch": part_day_dispatch,
    }
