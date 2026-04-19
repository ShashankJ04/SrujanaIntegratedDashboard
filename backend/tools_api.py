"""Tools API Blueprint.

Port of dashboards/backend/src/routes/tools.ts.
Corrected table names: components → CO_ prefix, machinemaster → MCM_ prefix,
scheduled_production → PS_ prefix, components_tool → CT_ prefix.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from .auth import api_login_required
from .rbac import require_access, require_any_access
from .db import fetch_all, fetch_one

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
    rows = fetch_all(
        """
        SELECT
            MIN(ct.CT_ID) AS id,
            ct.CT_TOOLNO AS toolNo,
            COALESCE(c.CO_PARTNO, '') AS partNo
        FROM components_tool ct
        LEFT JOIN components c ON ct.CT_COMPID = c.CO_ID
        WHERE ct.CT_ACTIVEYN = 'Y'
        GROUP BY ct.CT_TOOLNO, c.CO_PARTNO
        ORDER BY ct.CT_TOOLNO
        """
    )
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "toolNo": r["toolNo"],
            "partNo": r["partNo"],
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
            "toolNo": r["toolNo"],
            "partNo": r["partNo"],
        })
    return jsonify(result)


# ── Tools for date helper ───────────────────────────────────────────────

def _get_tools_for_date(date_str: str):
    """Get tools scheduled for a given date (YYYY-MM-DD).

    Uses the correct table/column names from the original:
    scheduled_production (PS_), components_tool (CT_), components (CO_), machinemaster (MCM_).
    """
    rows = fetch_all(
        """
        SELECT
            ps.PS_TOOLID AS toolId,
            ct.CT_TOOLNO AS toolNo,
            ct.CT_DRAWINGNO AS drawingNo,
            COALESCE(c.CO_PARTNO, '') AS partNo,
            COALESCE(c.CO_PARTNAME, '') AS partName,
            GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1) AS cavity,
            ps.PS_MCID AS machineId,
            COALESCE(mm.MCM_Name, CONCAT('Machine #', ps.PS_MCID)) AS machineName,
            COALESCE(mm.MCM_Capacity, '') AS machineCapacity,
            COALESCE(mm.MCM_Make, '') AS machineMake,
            ps.PS_QTY AS scheduledQty,
            ps.PS_QTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1) AS scheduledStrokes
        FROM scheduled_production ps
        INNER JOIN components_tool ct ON ct.CT_ID = ps.PS_TOOLID
        INNER JOIN components c ON c.CO_ID = ct.CT_COMPID
        INNER JOIN machinemaster mm ON mm.MCM_Id = ps.PS_MCID
        WHERE DATE(ps.PS_DATE) = %s
        ORDER BY ct.CT_TOOLNO, mm.MCM_Name
        """,
        (date_str,),
    )

    # Group by tool
    tools_map = {}
    for r in rows:
        tid = r["toolId"]
        tool_no = r["toolNo"]

        cavity = max(int(r["cavity"]), 1)
        scheduled_qty = int(r["scheduledQty"])
        scheduled_strokes = int(r["scheduledStrokes"])

        if tool_no not in tools_map:
            tools_map[tool_no] = {
                "toolId": tid,
                "toolNo": tool_no,
                "drawingNo": r.get("drawingNo", ""),
                "partNo": r["partNo"],
                "partName": r["partName"],
                "cavity": cavity,
                "machines": [],
            }

        tools_map[tool_no]["machines"].append({
            "machineId": r["machineId"],
            "machineName": r["machineName"],
            "machineCapacity": r["machineCapacity"],
            "machineMake": r["machineMake"],
            "scheduledQty": scheduled_qty,
            "scheduledStrokes": scheduled_strokes,
        })

    tools_list = list(tools_map.values())
    total_count = sum(len(t["machines"]) for t in tools_list)

    return {
        "date": date_str,
        "count": total_count,
        "tools": tools_list,
    }


# ── GET /today ──────────────────────────────────────────────────────────

@tools_bp.route("/today", methods=["GET"])
@require_access("tools")
def tools_today():
    from datetime import date
    date_str = request.args.get("date")
    if not date_str:
        date_str = date.today().isoformat()
    return jsonify(_get_tools_for_date(date_str))


# ── GET /tomorrow ───────────────────────────────────────────────────────

@tools_bp.route("/tomorrow", methods=["GET"])
@require_access("tools")
def tools_tomorrow():
    from datetime import date, timedelta
    date_str = request.args.get("date")
    if not date_str:
        date_str = (date.today() + timedelta(days=1)).isoformat()
    return jsonify(_get_tools_for_date(date_str))


# ── GET /for-date/<date_str> ────────────────────────────────────────────

@tools_bp.route("/for-date/<date_str>", methods=["GET"])
@require_access("tools")
def tools_for_date(date_str):
    return jsonify(_get_tools_for_date(date_str))
