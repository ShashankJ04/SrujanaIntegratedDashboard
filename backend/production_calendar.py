"""Production Calendar — production-specific view built on Dispatch Calendar payload."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .db import fetch_all
from .dispatch_calendar import (
    NO_OF_OPERATIONS_COL,
    PART_NO_COL,
    TOTAL_DISPATCHED_QTY_COL,
    TOTAL_QTY_COL,
    build_dispatch_calendar_payload,
)

REMAINING_PRODUCTION_COL = "Remaining Production"


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_part_key(part_no: Any) -> str:
    return str(part_no or "").strip().lower()


def _fetch_part_info() -> Dict[str, Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            c.CO_PARTNO AS partNo,
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
            c.CO_PARTNO AS partNo,
            m.MM_RawMtPartNo AS rmName,
            m.MM_Id AS rmId,
            ((1 / ((mt.MT_Density * m.MM_Thickness) * m.MM_StripWidth)) * ((1000 * ct.CT_NO_OF_CAVITY) / ct.CT_Pitch)) AS conVal
        FROM components c
        INNER JOIN components_tool ct ON ct.CT_COMPID = c.CO_ID
        INNER JOIN materialmaster m ON ct.CT_RMID = m.MM_Id
        INNER JOIN materialtypemaster mt ON m.MM_MTID = mt.MT_Id
        WHERE ct.CT_ActiveYN = 'Y'
          AND ct.CT_PPC = 'Y'
          AND ct.CT_PITCH > 0
          AND ct.CT_NO_OF_CAVITY > 0
        """,
        (),
    )

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

    rm_lookup = {}
    for r in rm_rows:
        pk = _normalize_part_key(r.get("partNo"))
        if pk and pk not in rm_lookup:
            rm_id = r.get("rmId")
            rm_lookup[pk] = {
                "rmId": rm_id,
                "rmName": r.get("rmName"),
                "conVal": _to_float(r.get("conVal")),
                "rmAvailable": avail_lookup.get(rm_id, 0.0),
            }

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _normalize_part_key(row.get("partNo"))
        if not key:
            continue
        rd = rm_lookup.get(key, {})
        out[key] = {
            "leadTime": row.get("leadTime"),
            "tools": row.get("tools") or "",
            "rmId": rd.get("rmId"),
            "rmName": rd.get("rmName"),
            "conVal": rd.get("conVal"),
            "rmAvailable": rd.get("rmAvailable"),
        }
    return out


def _insert_remaining_production_column(payload: Dict[str, Any]) -> None:
    columns = list(payload.get("columns") or [])
    if not columns:
        return

    if REMAINING_PRODUCTION_COL not in columns:
        try:
            insert_at = columns.index(TOTAL_DISPATCHED_QTY_COL) + 1
        except ValueError:
            insert_at = len(columns)
        columns.insert(insert_at, REMAINING_PRODUCTION_COL)
        payload["columns"] = columns

    row_meta = payload.get("rowMeta") or []
    for idx, row in enumerate(payload.get("rows") or []):
        if not isinstance(row, dict):
            continue

        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        stock_fg = _to_float(meta.get("stockFg"))
        stock_wip = _to_float(meta.get("stockWip"))
        if meta.get("isGrandTotal"):
            grand_stock = meta.get("grandTotalStock") or {}
            stock_fg = _to_float(grand_stock.get("stockFg"))
            stock_wip = _to_float(grand_stock.get("stockWip"))

        total_scheduled = _to_float(row.get(TOTAL_QTY_COL))
        total_dispatched = _to_float(row.get(TOTAL_DISPATCHED_QTY_COL))
        raw_remaining = total_scheduled - total_dispatched - stock_fg - stock_wip
        row[REMAINING_PRODUCTION_COL] = max(0.0, round(raw_remaining, 4))


def _set_visible_production_columns(payload: Dict[str, Any]) -> None:
    columns = list(payload.get("columns") or [])
    day_cols = [
        col
        for col in columns
        if re.match(r"^\s*day\s+\d+\s*$", str(col or ""), flags=re.IGNORECASE)
    ]
    day_cols.sort(key=lambda col: int(re.search(r"\d+", str(col)).group(0)))

    visible = [PART_NO_COL, REMAINING_PRODUCTION_COL] + day_cols
    payload["columns"] = [col for col in visible if col in columns]


def _attach_part_info(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
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
        }
    return part_info


def _shift_production_days_by_lead_time(payload: Dict[str, Any], part_info: Dict[str, Dict[str, Any]]) -> None:
    columns = list(payload.get("columns") or [])
    day_cols: List[Tuple[str, int]] = []
    for col in columns:
        m = re.match(r"^\s*day\s+(\d+)\s*$", str(col or ""), flags=re.IGNORECASE)
        if m:
            day_cols.append((col, int(m.group(1))))

    if not day_cols:
        return

    day_cols.sort(key=lambda x: x[1])

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

        current_qtys = {d: _to_float(row.get(c)) for c, d in day_cols}

        if lead_time > 0:
            current_status = meta.get("dayStatus") or {}
            current_pdd = part_day_dispatch.get(part_no) or {}

            for c, d in day_cols:
                row[c] = None
            meta["dayStatus"] = {}
            shifted_pdd: Dict[str, Any] = {}

            for c, d in day_cols:
                qty = current_qtys.get(d, 0.0)
                st = current_status.get(str(d))
                pdd = current_pdd.get(str(d))

                if qty <= 0 and not st and not pdd:
                    continue

                target_day = d - lead_time
                if target_day < 1:
                    target_day = 1

                target_col = None
                for tc, td in day_cols:
                    if td == target_day:
                        target_col = tc
                        break

                t_day_str = str(target_day)

                if target_col:
                    existing = _to_float(row.get(target_col))
                    row[target_col] = round(existing + qty, 4) if (existing + qty) > 0 else None

                if st:
                    meta["dayStatus"][t_day_str] = st

                if pdd:
                    existing_pdd = shifted_pdd.get(t_day_str, {"scheduledQty": 0.0, "dispatched": 0.0})
                    existing_pdd["scheduledQty"] += _to_float(pdd.get("scheduledQty"))
                    existing_pdd["dispatched"] += _to_float(pdd.get("dispatched"))
                    shifted_pdd[t_day_str] = existing_pdd

            part_day_dispatch[part_no] = shifted_pdd
            current_qtys = {d: _to_float(row.get(c)) for c, d in day_cols}

        for _, d in day_cols:
            qty = current_qtys.get(d, 0.0)
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


def _compute_cumulative_rm(payload: Dict[str, Any], part_info: Dict[str, Dict[str, Any]]) -> None:
    columns = list(payload.get("columns") or [])
    day_cols: List[Tuple[str, int]] = []
    for col in columns:
        m = re.match(r"^\s*day\s+(\d+)\s*$", str(col or ""), flags=re.IGNORECASE)
        if m:
            day_cols.append((col, int(m.group(1))))

    if not day_cols:
        return

    day_cols.sort(key=lambda x: x[1])

    current_rm = {}
    for pk, info in part_info.items():
        rm_id = info.get("rmId")
        if rm_id and rm_id not in current_rm:
            current_rm[rm_id] = _to_float(info.get("rmAvailable"))

    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []

    for c, d in day_cols:
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
            if meta.get("isGrandTotal"):
                continue

            qty = _to_float(row.get(c))
            p_info = meta.get("partInfo") or {}
            rm_id = p_info.get("rmId")
            con_val = _to_float(p_info.get("conVal"))

            if qty > 0 and rm_id and con_val > 0:
                req_rm = qty / con_val
                current_rm[rm_id] -= req_rm

            if "cumRmAvailable" not in meta:
                meta["cumRmAvailable"] = {}

            if rm_id:
                meta["cumRmAvailable"][str(d)] = current_rm.get(rm_id, 0.0)


def build_production_calendar_payload(month: int, year: int) -> Dict[str, Any]:
    """Return production calendar payload with remaining production quantity."""
    payload = build_dispatch_calendar_payload(month, year)
    _insert_remaining_production_column(payload)
    _set_visible_production_columns(payload)
    part_info = _attach_part_info(payload)
    _shift_production_days_by_lead_time(payload, part_info)
    _compute_cumulative_rm(payload, part_info)
    return payload
