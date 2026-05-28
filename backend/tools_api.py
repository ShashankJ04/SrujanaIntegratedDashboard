"""Tools API Blueprint.

Port of dashboards/backend/src/routes/tools.ts.
Corrected table names: components → CO_ prefix, machinemaster → MCM_ prefix,
scheduled_production → PS_ prefix, components_tool → CT_ prefix.
"""

from __future__ import annotations

from datetime import date as dt_date, timedelta

from flask import Blueprint, current_app, jsonify, request

from .auth import api_login_required
from .rbac import require_access, require_any_access
from .db import fetch_all, fetch_one
from .pm_api import _norm_tool_no
from .tool_schedule import get_tools_for_date_from_production_calendar

tools_bp = Blueprint("tools_bp", __name__, url_prefix="/api/tools")


@tools_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


# ── GET /count — distinct active tool count ─────────────────────────────

@tools_bp.route("/count", methods=["GET"])
@require_access("tools")
def tools_count():
    row = fetch_one(
        """
        SELECT COUNT(DISTINCT ct.CT_TOOLNO) AS total
        FROM components_tool ct
        WHERE ct.CT_ACTIVEYN = 'Y'
        """
    )
    return jsonify({"total": int(row["total"]) if row else 0})


# ── GET /all — all active tools ─────────────────────────────────────────

@tools_bp.route("/all", methods=["GET"])
@require_any_access(["tools", "preventive_maintenance"])
def all_tools():
    expand = str(request.args.get("per_component", "0")).lower() in ("1", "true", "yes")
    from . import pm_api

    if expand:
        rows = fetch_all(pm_api._PM_COMPONENT_TOOL_ROWS_SQL)
    else:
        rows = fetch_all(pm_api._PM_GROUPED_TOOL_ROWS_SQL)
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "toolNo": r["toolNo"],
            "partNo": r["partNo"] or "",
        })
    return jsonify(result)


# ── GET /search — search by tool number ─────────────────────────────────

@tools_bp.route("/search", methods=["GET"])
@require_any_access(["tools", "preventive_maintenance"])
def search_tools():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])

    rows = fetch_all(
        """
        SELECT
            MIN(ct.CT_ID) AS id,
            ct.CT_TOOLNO AS toolNo,
            COALESCE(c.CO_PARTNO, '') AS partNo
        FROM components_tool ct
        LEFT JOIN components c ON ct.CT_COMPID = c.CO_ID
        WHERE ct.CT_ACTIVEYN = 'Y' AND ct.CT_TOOLNO LIKE %s
        GROUP BY ct.CT_TOOLNO, c.CO_PARTNO
        ORDER BY ct.CT_TOOLNO
        LIMIT 20
        """,
        (f"%{q}%",),
    )
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "toolNo": _norm_tool_no(r["toolNo"]),
            "partNo": r["partNo"],
        })
    return jsonify(result)


# ── Tools for date helpers ──────────────────────────────────────────────

def _resolve_target_date(base_date: str | None, offset: int) -> dt_date:
    if base_date:
        return dt_date.fromisoformat(base_date) + timedelta(days=offset)
    return dt_date.today() + timedelta(days=offset)


def _get_tools_for_date_from_scheduled_production(
    base_date: str | None = None,
    offset: int = 0,
):
    """Legacy: tools from scheduled_production for a given date."""

    if base_date:
        date_expr = f"DATE_ADD(%s, INTERVAL {int(offset)} DAY)"
        params = (base_date,)
    elif offset > 0:
        date_expr = f"DATE_ADD(CURDATE(), INTERVAL {int(offset)} DAY)"
        params = ()
    else:
        date_expr = "CURDATE()"
        params = ()

    sql = f"""
        SELECT
            DATE_FORMAT(ps.PS_DATE, '%%Y-%%m-%%d') AS `date`,
            ps.PS_TOOLID AS toolId,
            ct.CT_TOOLNO AS toolNo,
            ct.CT_DRAWINGNO AS drawingNo,
            c.CO_PARTNO AS partNo,
            c.CO_PARTNAME AS partName,
            GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1) AS cavity,
            ps.PS_MCID AS machineId,
            mm.MCM_Name AS machineName,
            mm.MCM_Capacity AS machineCapacity,
            mm.MCM_Make AS machineMake,
            ps.PS_QTY AS scheduledQty,
            ps.PS_QTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1) AS scheduledStrokes
        FROM scheduled_production ps
        INNER JOIN components_tool ct ON ct.CT_ID = ps.PS_TOOLID
        INNER JOIN components c ON c.CO_ID = ct.CT_COMPID
        INNER JOIN machinemaster mm ON mm.MCM_Id = ps.PS_MCID
        WHERE ps.PS_DATE = {date_expr}
        ORDER BY ct.CT_TOOLNO, mm.MCM_Name
    """

    rows = fetch_all(sql, params if params else None)

    tools_map = {}
    for r in rows:
        tid = r["toolId"]

        cavity = max(int(r["cavity"]), 1)
        scheduled_qty = int(r["scheduledQty"])
        scheduled_strokes = int(r["scheduledStrokes"])

        if tid not in tools_map:
            tools_map[tid] = {
                "toolId": tid,
                "toolNo": r["toolNo"],
                "drawingNo": r.get("drawingNo") or "",
                "partNo": r["partNo"] or "",
                "partName": r["partName"] or "",
                "cavity": cavity,
                "machineCount": 0,
                "totalScheduledQty": 0,
                "totalScheduledStrokes": 0,
                "machines": [],
            }

        tools_map[tid]["machines"].append({
            "machineId": r["machineId"],
            "machineName": r["machineName"] or "",
            "machineCapacity": r["machineCapacity"] or "",
            "machineMake": r["machineMake"] or "",
            "scheduledQty": scheduled_qty,
            "scheduledStrokes": scheduled_strokes,
        })
        tools_map[tid]["totalScheduledQty"] += scheduled_qty
        tools_map[tid]["totalScheduledStrokes"] += scheduled_strokes

    for tool in tools_map.values():
        tool["machineCount"] = len(set(m["machineId"] for m in tool["machines"]))

    tools_list = list(tools_map.values())

    if rows:
        date_str = rows[0]["date"]
    else:
        date_str = _resolve_target_date(base_date, offset).isoformat()

    return {
        "date": date_str,
        "count": len(tools_map),
        "tools": tools_list,
    }


def _get_tools_for_date(mode: str = "today", base_date: str | None = None, offset: int = 0):
    """Get tools scheduled for a given date (source controlled by TOOL_SCHEDULE_SOURCE)."""
    target_date = _resolve_target_date(base_date, offset)
    source = str(
        current_app.config.get("TOOL_SCHEDULE_SOURCE") or "scheduled_production"
    ).strip().lower()
    if source == "production_calendar":
        return get_tools_for_date_from_production_calendar(target_date)
    return _get_tools_for_date_from_scheduled_production(base_date, offset)


def _is_valid_date(s: str | None) -> bool:
    """Check if string is a valid YYYY-MM-DD date."""
    import re
    return bool(s and re.match(r"^\d{4}-\d{2}-\d{2}$", s))


# ── GET /today ──────────────────────────────────────────────────────────

@tools_bp.route("/today", methods=["GET"])
@require_access("tools")
def tools_today():
    date_param = request.args.get("date")
    base_date = date_param if _is_valid_date(date_param) else None
    return jsonify(_get_tools_for_date("today", base_date, offset=0))


# ── GET /tomorrow ───────────────────────────────────────────────────────

@tools_bp.route("/tomorrow", methods=["GET"])
@require_access("tools")
def tools_tomorrow():
    date_param = request.args.get("date")
    base_date = date_param if _is_valid_date(date_param) else None
    return jsonify(_get_tools_for_date("tomorrow", base_date, offset=1))


# ── GET /for-date/<date_str> ────────────────────────────────────────────

@tools_bp.route("/for-date/<date_str>", methods=["GET"])
@require_access("tools")
def tools_for_date(date_str):
    if _is_valid_date(date_str):
        return jsonify(_get_tools_for_date("today", date_str, offset=0))
    else:
        return jsonify(_get_tools_for_date("today", offset=0))
