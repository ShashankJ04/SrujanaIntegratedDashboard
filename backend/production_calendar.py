"""Production Calendar — production-specific view built on Dispatch Calendar payload."""

from __future__ import annotations

import calendar
import re
from typing import Any, Dict, List, Optional, Tuple

from .db import fetch_all
from .dispatch_calendar import (
    NO_OF_OPERATIONS_COL,
    PART_NO_COL,
    TOTAL_QTY_COL,
    build_dispatch_calendar_payload,
)

PLANNED_QTY_COL = "Planned Qty"
BALANCE_PRODUCTION_COL = "Balance Qty"
PRODUCED_QTY_COL = "Produced Qty"
OPENING_STOCK_COL = "Opening Stock"
COMPLETION_PCT_COL = "% Completion"
ESTIMATED_TIME_COL = "Estimated Time"

_DEFAULT_WORK_HOURS = 6


def _work_hours_per_day() -> int:
    try:
        from flask import current_app
        return int(current_app.config.get("WORK_HOURS_PER_DAY", _DEFAULT_WORK_HOURS))
    except RuntimeError:
        return _DEFAULT_WORK_HOURS


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_null_qty(value: Any) -> bool:
    """True when a qty cell is unset (null/empty), not a numeric zero."""
    return value is None or value == ""


def _normalize_part_key(part_no: Any) -> str:
    return str(part_no or "").strip().lower()


def _day_col_regex() -> re.Pattern:
    return re.compile(r"^\s*day\s+(\d+)\s*$", flags=re.IGNORECASE)


def _parse_day_cols(columns: List[str]) -> List[Tuple[str, int]]:
    """Return (colName, dayNumber) pairs sorted by day number."""
    pat = _day_col_regex()
    day_cols: List[Tuple[str, int]] = []
    for col in columns:
        m = pat.match(str(col or ""))
        if m:
            day_cols.append((col, int(m.group(1))))
    day_cols.sort(key=lambda x: x[1])
    return day_cols


# ---------------------------------------------------------------------------
# Data lookups
# ---------------------------------------------------------------------------

def _fetch_part_info() -> Dict[str, Dict[str, Any]]:
    """Component info keyed by normalized part_no: leadTime, tools, SPM, cavity, RM."""
    rows = fetch_all(
        """
        SELECT
            c.CO_PARTNO       AS partNo,
            MAX(c.CO_LEADTIME) AS leadTime,
            GROUP_CONCAT(DISTINCT ct.CT_TOOLNO ORDER BY ct.CT_TOOLNO SEPARATOR ', ') AS tools
        FROM components c
        LEFT JOIN components_tool ct
            ON ct.CT_COMPID = c.CO_ID
            AND ct.CT_ACTIVEYN = 'Y'
        WHERE c.CO_ACTIVEYN = 'Y'
            AND c.CO_PARTNO IS NOT NULL
        GROUP BY c.CO_PARTNO
        """,
        (),
    )

    rm_rows = fetch_all(
        """
        SELECT
            c.CO_PARTNO                     AS partNo,
            m.MM_RawMtPartNo                AS rmName,
            m.MM_Id                         AS rmId,
            ct.CT_NO_OF_CAVITY              AS cavity,
            ((1 / ((mt.MT_Density * m.MM_Thickness) * m.MM_StripWidth))
              * ((1000 * ct.CT_NO_OF_CAVITY) / ct.CT_Pitch)) AS conVal
        FROM components c
        INNER JOIN components_tool ct ON ct.CT_COMPID = c.CO_ID
        INNER JOIN materialmaster m   ON ct.CT_RMID = m.MM_Id
        INNER JOIN materialtypemaster mt ON m.MM_MTID = mt.MT_Id
        WHERE ct.CT_ActiveYN = 'Y'
          AND ct.CT_PPC = 'Y'
          AND ct.CT_PITCH > 0
          AND ct.CT_NO_OF_CAVITY > 0
        """,
        (),
    )

    spm_rows = fetch_all(
        """
        SELECT
            tl.TL_tool_number AS toolNo,
            MAX(tl.TL_spm)    AS spm
        FROM tool_life tl
        GROUP BY tl.TL_tool_number
        """,
        (),
    )
    spm_by_tool: Dict[str, float] = {}
    for sr in spm_rows:
        tn = str(sr.get("toolNo") or "").strip()
        if tn:
            spm_by_tool[tn.lower()] = _to_float(sr.get("spm"))

    avail_rows = fetch_all(
        """
        SELECT
            RD_RMID as rmId,
            SUM(CASE WHEN ri_movement = 'I' THEN rd_qty ELSE 0 END) -
            SUM(CASE WHEN ri_movement = 'O' THEN rd_qty ELSE 0 END) as available
        FROM rm_inwarddetails
        INNER JOIN rm_inwardmaster ON rd_riid = ri_id
        GROUP BY RD_RMID
        """,
        (),
    )
    avail_lookup = {r.get("rmId"): _to_float(r.get("available")) for r in avail_rows}

    rm_lookup: Dict[str, Dict[str, Any]] = {}
    for r in rm_rows:
        pk = _normalize_part_key(r.get("partNo"))
        if pk and pk not in rm_lookup:
            rm_id = r.get("rmId")
            rm_lookup[pk] = {
                "rmId": rm_id,
                "rmName": r.get("rmName"),
                "conVal": _to_float(r.get("conVal")),
                "rmAvailable": avail_lookup.get(rm_id, 0.0),
                "cavity": _to_float(r.get("cavity")),
            }

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _normalize_part_key(row.get("partNo"))
        if not key:
            continue
        rd = rm_lookup.get(key, {})
        tool_str = str(row.get("tools") or "")
        first_tool = tool_str.split(",")[0].strip().lower() if tool_str else ""
        spm = spm_by_tool.get(first_tool, 0.0)
        out[key] = {
            "leadTime": row.get("leadTime"),
            "tools": tool_str,
            "rmId": rd.get("rmId"),
            "rmName": rd.get("rmName"),
            "conVal": rd.get("conVal"),
            "rmAvailable": rd.get("rmAvailable"),
            "cavity": rd.get("cavity", 0.0),
            "spm": spm,
        }
    return out


def _completion_pct_from_balance_produced(produced: float, pending: float) -> Optional[float]:
    """Completion % = produced qty / production pending qty."""
    if pending <= 0:
        return None
    return round((produced / pending) * 100.0, 2)


def _monthly_produced_from_daily(daily_map: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Sum daily production to monthly totals per part."""
    return {pk: round(sum(days.values()), 4) for pk, days in daily_map.items()}


def _fetch_opening_stock_map(month: int, year: int) -> Dict[str, float]:
    """Opening stock per part from comp_stockhistory (month opening snapshot)."""
    rows = fetch_all(
        """
        SELECT
            c.CO_PARTNO AS partNo,
            SUM(ch.CH_QTY) AS openingQty
        FROM comp_stockhistory ch
        INNER JOIN components c
            ON c.CO_ID = ch.CH_COMPID
        WHERE ch.CH_QTY > 0
          AND ch.CH_YEAR = %s
          AND ch.CH_MONTH = %s
          AND ch.CH_WEEK = 0
          AND c.CO_ACTIVEYN = 'Y'
        GROUP BY c.CO_PARTNO
        """,
        (year, month),
    )
    out: Dict[str, float] = {}
    for row in rows:
        pk = _normalize_part_key(row.get("partNo"))
        if pk:
            out[pk] = _to_float(row.get("openingQty"))
    return out


def _fetch_daily_production_map(month: int, year: int) -> Dict[str, Dict[str, float]]:
    """Daily produced qty per part (Date-wise Monthly Production report source)."""
    rows = fetch_all(
        """
        SELECT
            TRIM(c.CO_PARTNO) AS partNo,
            DAY(pd.PD_DATE) AS prodDay,
            SUM(pd.PD_PRODQTY) AS producedQty
        FROM production_details pd
        INNER JOIN scheduled_production sp ON pd.PD_PSID = sp.PS_ID
        INNER JOIN components c ON sp.PS_PARENTCOMPID = c.CO_ID
        WHERE MONTH(pd.PD_DATE) = %s
          AND YEAR(pd.PD_DATE) = %s AND pd.PD_ECSID != 6
        GROUP BY TRIM(c.CO_PARTNO), DAY(pd.PD_DATE)
        """,
        (month, year),
    )
    out: Dict[str, Dict[str, float]] = {}
    for row in rows:
        pk = _normalize_part_key(row.get("partNo"))
        day_num = row.get("prodDay")
        if not pk or day_num is None:
            continue
        day_key = str(int(day_num))
        bucket = out.setdefault(pk, {})
        bucket[day_key] = round(_to_float(row.get("producedQty")), 4)
    return out


# ---------------------------------------------------------------------------
# Payload transformations
# ---------------------------------------------------------------------------

def _fetch_inventory_production_pending_map() -> Dict[str, float]:
    """Inventory production_pending keyed by normalized part_no."""
    from .models import _get_enriched_rows_for_reports

    rows = _get_enriched_rows_for_reports()
    out: Dict[str, float] = {}
    for row in rows:
        pk = _normalize_part_key(row.get("part_no"))
        if pk:
            out[pk] = float(row.get("production_pending") or 0)
    return out


def _insert_production_summary_columns(
    payload: Dict[str, Any],
    opening_stock_map: Dict[str, float],
    monthly_produced_map: Dict[str, float],
) -> Dict[str, float]:
    """Insert Planned Qty, Opening Stock, Balance Qty, Produced Qty, and % Completion."""
    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []
    inv_pending_map = _fetch_inventory_production_pending_map()

    grand_planned = 0.0
    grand_balance = 0.0
    grand_opening = 0.0
    grand_produced = 0.0

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            continue

        pk = _normalize_part_key(row.get(PART_NO_COL))
        pending_raw = round(_to_float(inv_pending_map.get(pk, 0.0)), 4)
        pending = max(0.0, pending_raw)
        opening = _to_float(opening_stock_map.get(pk))
        produced = _to_float(monthly_produced_map.get(pk))
        completion_pct = _completion_pct_from_balance_produced(produced, pending)

        row[PLANNED_QTY_COL] = round(pending, 4) if pending > 0 else None
        row[OPENING_STOCK_COL] = round(opening, 4) if opening > 0 else None
        row[BALANCE_PRODUCTION_COL] = round(pending, 4) if pending > 0 else None
        row[PRODUCED_QTY_COL] = round(produced, 4) if produced > 0 else None
        row[COMPLETION_PCT_COL] = completion_pct

        grand_planned += pending
        grand_balance += pending
        grand_opening += opening
        grand_produced += produced

    grand_completion: Optional[float] = _completion_pct_from_balance_produced(
        grand_produced, grand_balance
    )

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            row[PLANNED_QTY_COL] = round(grand_planned, 4)
            row[OPENING_STOCK_COL] = round(grand_opening, 4)
            row[BALANCE_PRODUCTION_COL] = round(grand_balance, 4)
            row[PRODUCED_QTY_COL] = round(grand_produced, 4)
            row[COMPLETION_PCT_COL] = grand_completion
            break

    from .models import get_inventory_balance_total, get_inventory_planned_total

    inventory_planned = round(get_inventory_planned_total(), 4)
    inventory_balance = round(get_inventory_balance_total(), 4)

    return {
        "planned": inventory_planned,
        "openingStock": round(grand_opening, 4),
        "balance": inventory_balance,
        "produced": round(grand_produced, 4),
        "pct": grand_completion,
    }


def _insert_estimated_time_column(
    payload: Dict[str, Any],
    part_info: Dict[str, Dict[str, Any]],
) -> None:
    """Estimated time (days) = Balance Qty / (SPM * cavity * 60 * work_hours).

    Grand Total shows the sum of individual estimated days (total machine-days).
    """
    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []

    grand_est_days = 0.0

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            continue

        balance = max(0.0, _to_float(row.get(BALANCE_PRODUCTION_COL)))
        pk = _normalize_part_key(row.get(PART_NO_COL))
        info = part_info.get(pk, {})
        spm = _to_float(info.get("spm"))
        cavity = _to_float(info.get("cavity"))
        rate = spm * cavity

        if balance > 0 and rate > 0:
            days = balance / (rate * _work_hours_per_day() * 60)
            row[ESTIMATED_TIME_COL] = round(days, 2)
            grand_est_days += days
        else:
            row[ESTIMATED_TIME_COL] = None

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            row[ESTIMATED_TIME_COL] = round(grand_est_days, 2) if grand_est_days > 0 else None
            break


def _all_day_cols_for_payload(payload: Dict[str, Any]) -> List[Tuple[str, int]]:
    """Resolve day columns from payload columns or row keys."""
    day_cols = _parse_day_cols(list(payload.get("columns") or []))
    if day_cols:
        return day_cols
    rows = payload.get("rows") or []
    if not rows or not isinstance(rows[0], dict):
        return []
    return _parse_day_cols(list(rows[0].keys()))


def _should_hide_production_row(
    row: Dict[str, Any],
    _day_cols: Optional[List[Tuple[str, int]]] = None,
) -> bool:
    """Hide when Planned Qty and Produced Qty are both null (no summary qty)."""
    return _is_null_qty(row.get(BALANCE_PRODUCTION_COL)) and _is_null_qty(
        row.get(PRODUCED_QTY_COL)
    )


def _recompute_production_grand_total_row(
    grand_row: Dict[str, Any],
    part_rows: List[Dict[str, Any]],
    day_cols: List[Tuple[str, int]],
) -> None:
    grand_planned = 0.0
    grand_produced = 0.0
    grand_opening = 0.0
    grand_est_days = 0.0

    for col, _ in day_cols:
        day_sum = sum(_to_float(r.get(col)) for r in part_rows)
        grand_row[col] = round(day_sum, 4) if day_sum > 0 else None

    for row in part_rows:
        grand_planned += _to_float(row.get(BALANCE_PRODUCTION_COL))
        grand_produced += _to_float(row.get(PRODUCED_QTY_COL))
        grand_opening += _to_float(row.get(OPENING_STOCK_COL))
        est = row.get(ESTIMATED_TIME_COL)
        if est is not None and est != "":
            grand_est_days += _to_float(est)

    grand_row[PLANNED_QTY_COL] = round(grand_planned, 4)
    grand_row[BALANCE_PRODUCTION_COL] = round(grand_planned, 4)
    grand_row[PRODUCED_QTY_COL] = round(grand_produced, 4) if grand_produced > 0 else 0.0
    grand_row[OPENING_STOCK_COL] = round(grand_opening, 4) if grand_opening > 0 else 0.0
    grand_row[ESTIMATED_TIME_COL] = round(grand_est_days, 2) if grand_est_days > 0 else None
    grand_row[COMPLETION_PCT_COL] = _completion_pct_from_balance_produced(
        grand_produced, grand_planned
    )


def _filter_inactive_production_rows(payload: Dict[str, Any]) -> None:
    """Drop parts where both Planned Qty and Produced Qty are null."""
    day_cols = _all_day_cols_for_payload(payload)
    rows = payload.get("rows") or []
    row_meta = list(payload.get("rowMeta") or [])

    kept_rows: List[Dict[str, Any]] = []
    kept_meta: List[Any] = []
    grand_row: Optional[Dict[str, Any]] = None
    grand_meta: Optional[Dict[str, Any]] = None

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            grand_row = row
            grand_meta = meta
            continue
        if _should_hide_production_row(row, day_cols):
            continue
        kept_rows.append(row)
        kept_meta.append(meta)

    if grand_row is not None:
        _recompute_production_grand_total_row(grand_row, kept_rows, day_cols)
        kept_rows.append(grand_row)
        kept_meta.append(grand_meta or {})

    payload["rows"] = kept_rows
    payload["rowMeta"] = kept_meta


def _set_visible_production_columns(payload: Dict[str, Any]) -> None:
    """Filter and reorder columns for the production calendar view."""
    columns = list(payload.get("columns") or [])

    for col_name in (
        PLANNED_QTY_COL,
        BALANCE_PRODUCTION_COL,
        PRODUCED_QTY_COL,
        COMPLETION_PCT_COL,
        OPENING_STOCK_COL,
        ESTIMATED_TIME_COL,
    ):
        if col_name not in columns:
            columns.append(col_name)

    day_cols = _parse_day_cols(columns)
    day_col_names = [c for c, _ in day_cols]

    visible = [
        PART_NO_COL,
        BALANCE_PRODUCTION_COL,
        PRODUCED_QTY_COL,
        COMPLETION_PCT_COL,
        ESTIMATED_TIME_COL,
    ] + day_col_names
    payload["columns"] = [col for col in visible if col in columns]


def _attach_part_info(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Attach per-part metadata (lead time, tools, RM, SPM, cavity) to rowMeta."""
    part_info = _fetch_part_info()
    row_meta = payload.get("rowMeta")
    if not isinstance(row_meta, list):
        row_meta = []
        payload["rowMeta"] = row_meta

    rows = payload.get("rows") or []
    while len(row_meta) < len(rows):
        row_meta.append({})

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if isinstance(row_meta[idx], dict) else {}
        row_meta[idx] = meta
        if meta.get("isGrandTotal"):
            continue

        part_no = row.get(PART_NO_COL)
        info = part_info.get(_normalize_part_key(part_no), {})
        meta["partInfo"] = {
            "leadTime": info.get("leadTime"),
            "noOfOperations": row.get(NO_OF_OPERATIONS_COL),
            "tools": info.get("tools") or "",
            "rmId": info.get("rmId"),
            "rmName": info.get("rmName") or "",
            "conVal": info.get("conVal") or 0.0,
            "rmAvailable": info.get("rmAvailable") or 0.0,
            "spm": info.get("spm") or 0.0,
            "cavity": info.get("cavity") or 0.0,
        }
    return part_info


def _shift_production_days_by_lead_time(
    payload: Dict[str, Any],
    part_info: Dict[str, Dict[str, Any]],
) -> None:
    """Shift day quantities earlier by CO_LEADTIME from dispatch schedule.

    Uses the full scheduled dispatch qty for every day (ignores dispatched/legend
    status). Opening stock is then applied in dispatch-day order so earlier
    schedules consume opening balance before later ones.
    """
    columns = list(payload.get("columns") or [])
    day_cols = _parse_day_cols(columns)
    if not day_cols:
        return

    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []
    part_day_dispatch = payload.get("partDayDispatch") or {}

    shifted_grand_scheduled: Dict[int, float] = {d: 0.0 for _, d in day_cols}

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            continue

        part_no = _normalize_part_key(row.get(PART_NO_COL))
        info = part_info.get(part_no, {})
        lead_time = int(_to_float(info.get("leadTime")))

        current_pdd = part_day_dispatch.get(part_no) or {}
        current_qtys = {d: _to_float(row.get(c)) for c, d in day_cols}
        current_status = meta.get("dayStatus") or {}

        for c, _ in day_cols:
            row[c] = None
        meta["dayStatus"] = {}
        shifted_pdd: Dict[str, Any] = {}

        opening_remaining = _to_float(row.get(OPENING_STOCK_COL))

        for c, d in day_cols:
            scheduled = current_qtys.get(d, 0.0)
            if scheduled <= 0:
                continue

            if opening_remaining >= scheduled:
                opening_remaining -= scheduled
                continue

            net = round(scheduled - opening_remaining, 4)
            opening_remaining = 0.0
            if net <= 0:
                continue

            target_day = max(1, d - lead_time) if lead_time > 0 else d

            target_col: Optional[str] = None
            for tc, td in day_cols:
                if td == target_day:
                    target_col = tc
                    break
            t_day_str = str(target_day)

            if target_col:
                existing = _to_float(row.get(target_col))
                row[target_col] = round(existing + net, 4)

            st = current_status.get(str(d))
            if st:
                meta["dayStatus"][t_day_str] = st

            pdd_cell = current_pdd.get(str(d)) or {"scheduledQty": scheduled, "dispatched": 0.0}
            existing_pdd = shifted_pdd.get(t_day_str, {"scheduledQty": 0.0, "dispatched": 0.0})
            existing_pdd["scheduledQty"] += net
            existing_pdd["dispatched"] = _to_float(pdd_cell.get("dispatched"))
            shifted_pdd[t_day_str] = existing_pdd

        part_day_dispatch[part_no] = shifted_pdd

        for _, d in day_cols:
            qty = _to_float(row.get(f"day {d}"))
            if qty > 0:
                shifted_grand_scheduled[d] += qty

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            for c, d in day_cols:
                g_val = shifted_grand_scheduled.get(d, 0.0)
                row[c] = round(g_val, 4) if g_val > 0 else None
            break


def _compute_net_pending_days(
    payload: Dict[str, Any],
    daily_production: Dict[str, Dict[str, float]],
) -> None:
    """Keep only days that genuinely need new production.

    For each part, walks day columns left-to-right consuming available stock
    (FG + WIP combined) sequentially.  A day cell is set to None if:
    - Dispatch status is 'dispatched' (already shipped), OR
    - Combined remaining FG + WIP stock covers the day's need.
    Otherwise the cell shows the shortfall that requires fresh production.
    """
    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []
    day_cols = _all_day_cols_for_payload(payload)
    if not day_cols:
        return

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            continue

        day_status = meta.get("dayStatus") or {}
        stock_available = _to_float(meta.get("stockFg")) + _to_float(meta.get("stockWip"))

        original_scheduled: Dict[str, float] = {}

        for col_name, day_num in day_cols:
            scheduled = _to_float(row.get(col_name))
            if scheduled <= 0:
                continue

            original_scheduled[str(day_num)] = scheduled

            day_str = str(day_num)
            status_info = day_status.get(day_str, {})
            status = status_info.get("status", "") if isinstance(status_info, dict) else ""

            if status == "dispatched":
                row[col_name] = None
                continue

            if stock_available >= scheduled:
                stock_available -= scheduled
                row[col_name] = None
            elif stock_available > 0:
                shortfall = scheduled - stock_available
                stock_available = 0.0
                row[col_name] = round(shortfall, 4)
            else:
                pass  # keep cell as-is (full qty needs production)

        meta["originalScheduled"] = original_scheduled
        if idx < len(row_meta):
            row_meta[idx] = meta

    grand_sums: Dict[int, float] = {d: 0.0 for _, d in day_cols}
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            continue
        for col_name, day_num in day_cols:
            grand_sums[day_num] += _to_float(row.get(col_name))

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            for col_name, day_num in day_cols:
                val = grand_sums.get(day_num, 0.0)
                row[col_name] = round(val, 4) if val > 0 else None
            break

    payload["pendingOnly"] = True


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def get_production_kpi(month: int, year: int) -> Dict[str, Any]:
    """Grand-total KPI aligned with the Production Calendar toolbar."""
    payload = build_dispatch_calendar_payload(month, year)
    opening_stock_map = _fetch_opening_stock_map(month, year)
    daily_production = _fetch_daily_production_map(month, year)
    monthly_produced = _monthly_produced_from_daily(daily_production)
    return _insert_production_summary_columns(
        payload, opening_stock_map, monthly_produced
    )


def build_production_calendar_payload(month: int, year: int) -> Dict[str, Any]:
    """Return production calendar payload with planned/opening stock columns and day schedule."""
    payload = build_dispatch_calendar_payload(month, year)

    part_info = _attach_part_info(payload)

    opening_stock_map = _fetch_opening_stock_map(month, year)
    daily_production = _fetch_daily_production_map(month, year)
    monthly_produced = _monthly_produced_from_daily(daily_production)
    production_kpi = _insert_production_summary_columns(
        payload, opening_stock_map, monthly_produced
    )
    _insert_estimated_time_column(payload, part_info)

    _shift_production_days_by_lead_time(payload, part_info)
    _compute_net_pending_days(payload, daily_production)
    _filter_inactive_production_rows(payload)

    _set_visible_production_columns(payload)
    payload["productionKpi"] = production_kpi
    payload["partDailyProduction"] = daily_production
    payload["daysInMonth"] = payload.get("daysInMonth") or calendar.monthrange(year, month)[1]
    return payload
