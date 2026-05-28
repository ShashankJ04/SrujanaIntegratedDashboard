"""Tool schedule resolution from Production Calendar (optional via TOOL_SCHEDULE_SOURCE)."""

from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any, Dict, List

from flask import current_app

from .db import fetch_all
from .production_calendar import PART_NO_COL, build_production_calendar_payload

_CALENDAR_PAYLOAD_CACHE_LOCK = threading.Lock()
_CALENDAR_PAYLOAD_CACHE: Dict[str, Any] = {"ts": 0.0, "key": "", "payload": None}

_PLACEHOLDER_MACHINE: Dict[str, Any] = {
    "machineId": 0,
    "machineName": "—",
    "machineCapacity": "",
    "machineMake": "",
}


def _normalize_part_key(part_no: Any) -> str:
    return str(part_no or "").strip().lower()


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _day_column_key(day: int) -> str:
    return f"day {day}"


def _get_production_calendar_payload(month: int, year: int) -> Dict[str, Any]:
    cache_seconds = int(
        current_app.config.get("TOOL_SCHEDULE_CACHE_SECONDS", 30) or 30
    )
    cache_key = f"{year}-{month:02d}"
    now = time.monotonic()
    if cache_seconds > 0:
        with _CALENDAR_PAYLOAD_CACHE_LOCK:
            cached_key = str(_CALENDAR_PAYLOAD_CACHE.get("key") or "")
            cached_ts = float(_CALENDAR_PAYLOAD_CACHE.get("ts") or 0.0)
            cached_payload = _CALENDAR_PAYLOAD_CACHE.get("payload")
            if (
                cached_payload is not None
                and cached_key == cache_key
                and (now - cached_ts) < cache_seconds
            ):
                return dict(cached_payload)

    payload = build_production_calendar_payload(month, year)
    if cache_seconds > 0:
        with _CALENDAR_PAYLOAD_CACHE_LOCK:
            _CALENDAR_PAYLOAD_CACHE["key"] = cache_key
            _CALENDAR_PAYLOAD_CACHE["ts"] = now
            _CALENDAR_PAYLOAD_CACHE["payload"] = dict(payload)
    return payload


def _part_qty_for_day(payload: Dict[str, Any], day: int) -> Dict[str, float]:
    """Normalized part_no -> scheduled qty for a calendar day."""
    day_col = _day_column_key(day)
    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []
    out: Dict[str, float] = {}
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            continue
        qty = _to_float(row.get(day_col))
        if qty <= 0:
            continue
        pk = _normalize_part_key(row.get(PART_NO_COL))
        if not pk:
            continue
        out[pk] = out.get(pk, 0.0) + qty
    return out


def _fetch_active_tools_for_parts(part_nos: List[str]) -> List[Dict[str, Any]]:
    cleaned = [str(p or "").strip() for p in part_nos if str(p or "").strip()]
    if not cleaned:
        return []
    placeholders = ", ".join(["%s"] * len(cleaned))
    sql = f"""
        SELECT
            ct.CT_ID AS toolId,
            ct.CT_TOOLNO AS toolNo,
            ct.CT_DRAWINGNO AS drawingNo,
            TRIM(c.CO_PARTNO) AS partNo,
            TRIM(c.CO_PARTNAME) AS partName,
            GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1) AS cavity
        FROM components_tool ct
        INNER JOIN components c ON c.CO_ID = ct.CT_COMPID
        WHERE ct.CT_ACTIVEYN = 'Y'
          AND TRIM(c.CO_PARTNO) IN ({placeholders})
        ORDER BY ct.CT_TOOLNO, TRIM(c.CO_PARTNO)
    """
    return list(fetch_all(sql, tuple(cleaned)))


def _build_tools_response(
    target_date: date,
    part_qty: Dict[str, float],
    tool_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    qty_by_part_pk = {_normalize_part_key(k): float(v) for k, v in part_qty.items()}
    tools_map: Dict[int, Dict[str, Any]] = {}

    for r in tool_rows:
        pk = _normalize_part_key(r.get("partNo"))
        qty = qty_by_part_pk.get(pk, 0.0)
        if qty <= 0:
            continue

        tid = int(r["toolId"])
        cavity = max(int(r.get("cavity") or 1), 1)
        scheduled_qty = int(round(qty))
        scheduled_strokes = int(scheduled_qty / cavity)

        if tid not in tools_map:
            tools_map[tid] = {
                "toolId": tid,
                "toolNo": r.get("toolNo") or "",
                "drawingNo": r.get("drawingNo") or "",
                "partNo": r.get("partNo") or "",
                "partName": r.get("partName") or "",
                "cavity": cavity,
                "machineCount": 1,
                "totalScheduledQty": 0,
                "totalScheduledStrokes": 0,
                "machines": [],
            }

        tool = tools_map[tid]
        tool["totalScheduledQty"] += scheduled_qty
        tool["totalScheduledStrokes"] += scheduled_strokes

        existing = tool["machines"][0] if tool["machines"] else None
        if existing:
            existing["scheduledQty"] += scheduled_qty
            existing["scheduledStrokes"] += scheduled_strokes
        else:
            tool["machines"].append(
                {
                    **_PLACEHOLDER_MACHINE,
                    "scheduledQty": scheduled_qty,
                    "scheduledStrokes": scheduled_strokes,
                }
            )

    tools_list = list(tools_map.values())
    return {
        "date": target_date.isoformat(),
        "count": len(tools_map),
        "tools": tools_list,
    }


def get_tools_for_date_from_production_calendar(target_date: date) -> Dict[str, Any]:
    """Tools scheduled for a date from Production Calendar day columns."""
    payload = _get_production_calendar_payload(target_date.month, target_date.year)
    part_qty = _part_qty_for_day(payload, target_date.day)
    if not part_qty:
        return {
            "date": target_date.isoformat(),
            "count": 0,
            "tools": [],
        }

    part_nos = []
    seen: set[str] = set()
    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            continue
        pk = _normalize_part_key(row.get(PART_NO_COL))
        if not pk or pk not in part_qty or pk in seen:
            continue
        seen.add(pk)
        part_nos.append(str(row.get(PART_NO_COL) or "").strip())

    tool_rows = _fetch_active_tools_for_parts(part_nos)
    return _build_tools_response(target_date, part_qty, tool_rows)
