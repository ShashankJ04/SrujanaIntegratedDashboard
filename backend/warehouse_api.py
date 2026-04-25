"""Warehouse APIs used by required Hub sections.

This module is intentionally minimal and keeps only Executive View endpoints.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from flask import Blueprint, jsonify

from .auth import api_login_required
from .db import fetch_all, fetch_one, wh_fetch_all, wh_fetch_one

warehouse_bp = Blueprint("warehouse", __name__)


@warehouse_bp.before_request
def _auth():
    denied = api_login_required()
    if denied:
        return denied


def _decimal_safe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for row in rows:
        for k, v in row.items():
            if isinstance(v, Decimal):
                row[k] = float(v)
            elif hasattr(v, "isoformat"):
                row[k] = str(v)
    return rows


@warehouse_bp.get("/master_kpis")
def master_kpis() -> Any:
    try:
        pillars: Dict[str, Any] = {
            "customer_parts": {"metric": "Scheduled Today", "required": 0, "produced": 0, "balance": 0, "status": "healthy"},
            "raw_material": {"metric": "Items in Shortage", "required": 0, "produced": 0, "balance": 0, "status": "healthy"},
            "tools": {"metric": "Critical Dies", "required": 0, "produced": 0, "balance": 0, "status": "healthy"},
            "machines": {"metric": "Active Machines", "required": 0, "produced": 0, "balance": 0, "status": "healthy"},
        }

        comp = wh_fetch_one(
            "SELECT SUM(target_qty) AS total_scheduled, SUM(produced_qty) AS total_produced "
            "FROM production_schedule WHERE status IN ('PENDING', 'IN_PROGRESS')"
        )
        if comp and comp.get("total_scheduled"):
            sch = float(comp["total_scheduled"])
            prod = float(comp.get("total_produced") or 0)
            bal = sch - prod
            pillars["customer_parts"].update(required=sch, produced=prod, balance=bal)
            if bal > sch * 0.8:
                pillars["customer_parts"]["status"] = "critical"
            elif bal > sch * 0.5:
                pillars["customer_parts"]["status"] = "warning"

        rm = wh_fetch_one(
            """
            WITH ActiveDemand AS (
                SELECT raw_material_part_no, SUM(rm_required_qty - rm_issued_qty) AS total_rm_needed
                FROM production_schedule WHERE status IN ('PENDING', 'IN_PROGRESS') GROUP BY raw_material_part_no
            ),
            AvailableStock AS (
                SELECT item_code, SUM(passed_qty - issued_qty) AS total_rm_available
                FROM inventory_grn_item_tag WHERE status IN ('RACKED', 'PARTIALLY ISSUED') GROUP BY item_code
            )
            SELECT
                SUM(CASE WHEN COALESCE(s.total_rm_available, 0) < d.total_rm_needed THEN 1 ELSE 0 END) AS critical_items,
                SUM(CASE WHEN COALESCE(s.total_rm_available, 0) <= d.total_rm_needed * 1.10
                          AND COALESCE(s.total_rm_available, 0) >= d.total_rm_needed THEN 1 ELSE 0 END) AS warning_items
            FROM ActiveDemand d
            LEFT JOIN AvailableStock s ON d.raw_material_part_no = s.item_code
            """
        )
        if rm:
            crit = int(rm.get("critical_items") or 0)
            warn = int(rm.get("warning_items") or 0)
            pillars["raw_material"]["required"] = "No Shortages" if crit == 0 else f"{crit} Critical"
            pillars["raw_material"]["status"] = "critical" if crit > 0 else ("warning" if warn > 0 else "healthy")

        mach = wh_fetch_one(
            "SELECT COUNT(DISTINCT machine_id) AS active_count "
            "FROM production_schedule WHERE status = 'IN_PROGRESS'"
        )
        if mach:
            pillars["machines"]["produced"] = int(mach.get("active_count") or 0)
            pillars["machines"]["status"] = "healthy" if int(mach.get("active_count") or 0) > 0 else "warning"

        tool = fetch_one(
            """
            WITH LatestPM AS (
                SELECT PM_tool_id, PM_current_stroke, PM_next_stroke, PM_date,
                       ROW_NUMBER() OVER(PARTITION BY PM_tool_id ORDER BY PM_date DESC) AS rn
                FROM preventive_maintenance
            ),
            RecentProduction AS (
                SELECT pd.PD_TOOLID, SUM(pd.PD_PRODQTY) AS new_parts
                FROM production_details pd JOIN LatestPM pm ON pd.PD_TOOLID = pm.PM_tool_id AND pm.rn = 1
                WHERE pd.PD_DATE >= pm.PM_date GROUP BY pd.PD_TOOLID
            ),
            ToolCavities AS (
                SELECT CT_PPCTOOLID, MAX(CT_NO_OF_CAVITY) AS cavities
                FROM components_tool WHERE CT_ACTIVEYN = 'Y' GROUP BY CT_PPCTOOLID
            )
            SELECT
                SUM(CASE WHEN (COALESCE(pm.PM_current_stroke,0) + COALESCE(rp.new_parts,0)/COALESCE(NULLIF(ct.cavities,0),1)) >= pm.PM_next_stroke THEN 1 ELSE 0 END) AS critical_tools,
                SUM(CASE WHEN (COALESCE(pm.PM_current_stroke,0) + COALESCE(rp.new_parts,0)/COALESCE(NULLIF(ct.cavities,0),1)) >= (pm.PM_next_stroke - tl.TL_preventive_maintenance_strokes * 0.10)
                          AND (COALESCE(pm.PM_current_stroke,0) + COALESCE(rp.new_parts,0)/COALESCE(NULLIF(ct.cavities,0),1)) < pm.PM_next_stroke THEN 1 ELSE 0 END) AS warning_tools,
                COUNT(tl.TL_tool_id) AS total_tools
            FROM tool_life tl
            LEFT JOIN LatestPM pm ON tl.TL_tool_id = pm.PM_tool_id AND pm.rn = 1
            LEFT JOIN RecentProduction rp ON tl.TL_tool_id = rp.PD_TOOLID
            LEFT JOIN ToolCavities ct ON tl.TL_tool_id = ct.CT_PPCTOOLID
            """
        )
        if tool:
            ct = int(tool.get("critical_tools") or 0)
            wt = int(tool.get("warning_tools") or 0)
            pillars["tools"].update(required=int(tool.get("total_tools") or 0), balance=ct)
            pillars["tools"]["status"] = "critical" if ct > 0 else ("warning" if wt > 0 else "healthy")

        return jsonify({"last_updated": datetime.now().strftime("%I:%M %p"), "pillars": pillars})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/drilldown/tools")
def drilldown_tools() -> Any:
    try:
        rows = fetch_all(
            """
            WITH LatestPM AS (
                SELECT PM_tool_id, PM_current_stroke, PM_next_stroke, PM_date,
                       ROW_NUMBER() OVER(PARTITION BY PM_tool_id ORDER BY PM_date DESC) AS rn
                FROM preventive_maintenance
            ),
            RecentProduction AS (
                SELECT pd.PD_TOOLID, SUM(pd.PD_PRODQTY) AS new_parts
                FROM production_details pd JOIN LatestPM pm ON pd.PD_TOOLID = pm.PM_tool_id AND pm.rn = 1
                WHERE pd.PD_DATE >= pm.PM_date GROUP BY pd.PD_TOOLID
            ),
            ToolCavities AS (
                SELECT CT_PPCTOOLID, MAX(CT_NO_OF_CAVITY) AS cavities
                FROM components_tool WHERE CT_ACTIVEYN = 'Y' GROUP BY CT_PPCTOOLID
            ),
            ToolStatus AS (
                SELECT tl.TL_tool_number,
                       pm.PM_next_stroke,
                       (COALESCE(pm.PM_current_stroke,0) + COALESCE(rp.new_parts,0)/COALESCE(NULLIF(ct.cavities,0),1)) AS current_strokes,
                       CASE
                           WHEN pm.PM_next_stroke IS NULL THEN 'Missing PM'
                           WHEN (COALESCE(pm.PM_current_stroke,0) + COALESCE(rp.new_parts,0)/COALESCE(NULLIF(ct.cavities,0),1)) >= pm.PM_next_stroke THEN 'Critical'
                           WHEN (COALESCE(pm.PM_current_stroke,0) + COALESCE(rp.new_parts,0)/COALESCE(NULLIF(ct.cavities,0),1)) >= (pm.PM_next_stroke - tl.TL_preventive_maintenance_strokes * 0.10) THEN 'Warning'
                           ELSE 'Healthy'
                       END AS status
                FROM tool_life tl
                LEFT JOIN LatestPM pm ON tl.TL_tool_id = pm.PM_tool_id AND pm.rn = 1
                LEFT JOIN RecentProduction rp ON tl.TL_tool_id = rp.PD_TOOLID
                LEFT JOIN ToolCavities ct ON tl.TL_tool_id = ct.CT_PPCTOOLID
            )
            SELECT * FROM ToolStatus WHERE status IN ('Critical','Warning')
            ORDER BY CASE status WHEN 'Critical' THEN 1 ELSE 2 END, current_strokes DESC
            """
        )
        for t in rows:
            t["PM_next_stroke"] = int(t.get("PM_next_stroke") or 0)
            t["current_strokes"] = int(t.get("current_strokes") or 0)
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/drilldown/raw_materials")
def drilldown_raw_materials() -> Any:
    try:
        rows = wh_fetch_all(
            """
            WITH ActiveDemand AS (
                SELECT raw_material_part_no, SUM(rm_required_qty - rm_issued_qty) AS total_rm_needed
                FROM production_schedule WHERE status IN ('PENDING','IN_PROGRESS') GROUP BY raw_material_part_no
            ),
            AvailableStock AS (
                SELECT item_code, SUM(passed_qty - issued_qty) AS total_rm_available
                FROM inventory_grn_item_tag WHERE status IN ('RACKED','PARTIALLY ISSUED') GROUP BY item_code
            )
            SELECT * FROM (
                SELECT d.raw_material_part_no AS item_code, d.total_rm_needed,
                       COALESCE(s.total_rm_available, 0) AS total_rm_available,
                       CASE WHEN COALESCE(s.total_rm_available,0) < d.total_rm_needed THEN 'Critical'
                            WHEN COALESCE(s.total_rm_available,0) <= d.total_rm_needed * 1.10 THEN 'Warning'
                            ELSE 'Healthy' END AS status
                FROM ActiveDemand d LEFT JOIN AvailableStock s ON d.raw_material_part_no = s.item_code
            ) t WHERE status IN ('Critical','Warning')
            ORDER BY CASE status WHEN 'Critical' THEN 1 ELSE 2 END, (total_rm_needed - total_rm_available) DESC
            """
        )
        return jsonify(_decimal_safe(rows))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
