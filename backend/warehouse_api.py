"""Warehouse & QR Tag Management API Blueprint.

Ported from qrcode-app/warehouse_system.py, refactored to use the
unified auth system and dual-DB helpers.
"""

from __future__ import annotations

import base64
import io
import socket
import uuid
from urllib.parse import quote

import qrcode
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, g, jsonify, request, session

from .auth import api_login_required
from .db import (
    fetch_all,
    fetch_one,
    wh_execute,
    wh_fetch_all,
    wh_fetch_one,
    get_warehouse_connection,
)

warehouse_bp = Blueprint("warehouse", __name__)


@warehouse_bp.before_request
def _auth():
    denied = api_login_required()
    if denied:
        return denied


# ── Helpers ─────────────────────────────────────────────────────────────

def _normalize_po_line_item_id(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, bool)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, Decimal):
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(Decimal(s))
    except (InvalidOperation, ValueError):
        return None


def _decimal_safe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Decimal values to float for JSON serialization."""
    for row in rows:
        for k, v in row.items():
            if isinstance(v, Decimal):
                row[k] = float(v)
            elif hasattr(v, "isoformat"):
                row[k] = str(v)
    return rows


def _json_safe_scalar(v: Any) -> Any:
    """Single value safe for jsonify (datetime, date, Decimal, etc.)."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "isoformat") and callable(getattr(v, "isoformat")):
        return v.isoformat()
    return v


# ═══════════════════════════════════════════════════════════════════════
# MASTER DASHBOARD — 4-Pillar KPIs
# ═══════════════════════════════════════════════════════════════════════

@warehouse_bp.get("/master_kpis")
def master_kpis() -> Any:
    try:
        pillars: Dict[str, Any] = {
            "customer_parts": {"metric": "Scheduled Today", "required": 0, "produced": 0, "balance": 0, "status": "healthy"},
            "raw_material":   {"metric": "Items in Shortage", "required": 0, "produced": 0, "balance": 0, "status": "healthy"},
            "tools":          {"metric": "Critical Dies", "required": 0, "produced": 0, "balance": 0, "status": "healthy"},
            "machines":       {"metric": "Active Machines", "required": 0, "produced": 0, "balance": 0, "status": "healthy"},
        }

        # Components (warehouse_db)
        comp = wh_fetch_one("""
            SELECT SUM(target_qty) AS total_scheduled, SUM(produced_qty) AS total_produced
            FROM production_schedule WHERE status IN ('PENDING', 'IN_PROGRESS')
        """)
        if comp and comp.get("total_scheduled"):
            sch = float(comp["total_scheduled"])
            prod = float(comp.get("total_produced") or 0)
            bal = sch - prod
            pillars["customer_parts"].update(required=sch, produced=prod, balance=bal)
            if bal > sch * 0.8:
                pillars["customer_parts"]["status"] = "critical"
            elif bal > sch * 0.5:
                pillars["customer_parts"]["status"] = "warning"

        # Raw Materials (warehouse_db)
        rm = wh_fetch_one("""
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
        """)
        if rm:
            crit = int(rm.get("critical_items") or 0)
            warn = int(rm.get("warning_items") or 0)
            pillars["raw_material"]["required"] = "No Shortages" if crit == 0 else f"{crit} Critical"
            pillars["raw_material"]["status"] = "critical" if crit > 0 else ("warning" if warn > 0 else "healthy")

        # Machines (warehouse_db)
        mach = wh_fetch_one("""
            SELECT COUNT(DISTINCT machine_id) AS active_count
            FROM production_schedule WHERE status = 'IN_PROGRESS'
        """)
        if mach:
            pillars["machines"]["produced"] = int(mach.get("active_count") or 0)
            pillars["machines"]["status"] = "healthy" if int(mach.get("active_count") or 0) > 0 else "warning"

        # Tools (ERP db)
        tool = fetch_one("""
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
        """)
        if tool:
            ct = int(tool.get("critical_tools") or 0)
            wt = int(tool.get("warning_tools") or 0)
            pillars["tools"].update(required=int(tool.get("total_tools") or 0), balance=ct)
            pillars["tools"]["status"] = "critical" if ct > 0 else ("warning" if wt > 0 else "healthy")

        return jsonify({"last_updated": datetime.now().strftime("%I:%M %p"), "pillars": pillars})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# DRILLDOWN APIs
# ═══════════════════════════════════════════════════════════════════════

@warehouse_bp.get("/drilldown/tools")
def drilldown_tools() -> Any:
    try:
        rows = fetch_all("""
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
        """)
        for t in rows:
            t["PM_next_stroke"] = int(t.get("PM_next_stroke") or 0)
            t["current_strokes"] = int(t.get("current_strokes") or 0)
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/drilldown/raw_materials")
def drilldown_raw_materials() -> Any:
    try:
        rows = wh_fetch_all("""
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
        """)
        return jsonify(_decimal_safe(rows))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# SUPPLIERS / PO / GRN
# ═══════════════════════════════════════════════════════════════════════

@warehouse_bp.get("/suppliers")
def suppliers() -> Any:
    try:
        rows = fetch_all("""
            SELECT DISTINCT p.SUPPLIER_ID, s.ss_Name
            FROM po_supplier p
            JOIN supplier s ON p.SUPPLIER_ID = s.ss_Id
            WHERE p.SUPPLIER_TYPE_ID = 1
        """)
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/pos_by_supplier/<int:supplier_id>")
def pos_by_supplier(supplier_id: int) -> Any:
    try:
        rows = fetch_all(
            "SELECT PO_NO FROM po_supplier WHERE SUPPLIER_ID = %s ORDER BY CREATED_DATE DESC",
            (supplier_id,),
        )
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/fetch_po/<path:po_no>")
def fetch_po(po_no: str) -> Any:
    clean_po = po_no.strip()
    try:
        erp_items = fetch_all("""
            SELECT h.PO_ID, h.SUPPLIER_ID, i.ITEM_CODE, i.ITEM_DESC, i.QTY AS ORDERED_QTY, i.LIN_ITEM_ID, i.UOM
            FROM po_supplier h
            JOIN po_supplier_lin_item i ON h.PO_ID = i.PO_ID
            WHERE h.PO_NO = %s
        """, (clean_po,))
        if not erp_items:
            return jsonify({"error": "PO Not Found in ERP"}), 404

        wh_rows = wh_fetch_all("""
            SELECT t.po_line_item_id, SUM(t.qty_received) AS total_received
            FROM inventory_grn_item_tag t
            JOIN inventory_grn_master m ON t.grn_id = m.grn_id
            WHERE m.po_no = %s
            GROUP BY t.po_line_item_id
        """, (clean_po,))
        received: Dict[int, float] = {}
        for row in wh_rows:
            lid = _normalize_po_line_item_id(row.get("po_line_item_id"))
            if lid is not None:
                received[lid] = float(row.get("total_received") or 0)

        for item in erp_items:
            ordered = float(item["ORDERED_QTY"])
            already = received.get(_normalize_po_line_item_id(item.get("LIN_ITEM_ID")), 0.0)
            item["REMAINING_QTY"] = max(0, ordered - already)
            item["ALREADY_RECEIVED"] = already
        return jsonify(_decimal_safe(erp_items))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.post("/generate_grn")
def generate_grn() -> Any:
    data = request.get_json(silent=True) or {}
    po_no = str(data.get("po_no", "")).strip()
    items = data.get("items", [])
    tags_created: List[Dict[str, Any]] = []
    try:
        try:
            import qrcode
        except ImportError:
            return jsonify({"error": "qrcode library is not installed"}), 500

        conn = get_warehouse_connection()
        cursor = conn.cursor()
        grn_id = str(uuid.uuid4())
        grn_no = f"GRN-{uuid.uuid4().hex[:4].upper()}"
        supplier_id = items[0].get("SUPPLIER_ID", 0) if items else 0
        user_id = g.current_user.get("userId") or g.current_user.get("user_id")

        cursor.execute("""
            INSERT INTO inventory_grn_master (grn_id, grn_no, po_no, supplier_id, received_by_user_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (grn_id, grn_no, po_no, supplier_id, user_id))

        for item in items:
            for skid in item.get("skids", []):
                received_qty = float(skid.get("qty", 0))
                coils = skid.get("coils")
                if coils is not None and str(coils).strip():
                    coils = int(coils)
                else:
                    coils = None
                if received_qty > 0:
                    tag_id = str(uuid.uuid4())
                    qr_img = qrcode.make(f"tag:{tag_id}")
                    buf = io.BytesIO()
                    qr_img.save(buf)
                    qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    line_id = _normalize_po_line_item_id(item.get("LIN_ITEM_ID"))
                    cursor.execute("""
                        INSERT INTO inventory_grn_item_tag
                        (tag_id, grn_id, item_code, item_desc, qty_received, status, po_line_item_id, uom, original_coils)
                        VALUES (%s, %s, %s, %s, %s, 'RECEIVED', %s, %s, %s)
                    """, (tag_id, grn_id, item["ITEM_CODE"], item["ITEM_DESC"], received_qty, line_id, item.get("UOM"), coils))
                    tags_created.append({
                        "item_code": item["ITEM_CODE"],
                        "qty": received_qty, "coils": coils,
                        "uom": item.get("UOM"), "qr": qr_base64, "tag_id": tag_id,
                    })
        conn.commit()
        conn.close()
        return jsonify(tags_created)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# TAG LIFECYCLE (Scan, Inspect, Rack, Issue, Return)
# ═══════════════════════════════════════════════════════════════════════

@warehouse_bp.get("/scan/<tag_id>")
def scan_tag(tag_id: str) -> Any:
    try:
        tag = wh_fetch_one("""
            SELECT t.*,
                   (SELECT GROUP_CONCAT(CONCAT(rack_number,' (',current_qty,')') SEPARATOR ', ')
                    FROM inventory_tag_locations WHERE tag_id = t.tag_id) AS rack_number
            FROM inventory_grn_item_tag t WHERE t.tag_id = %s
        """, (tag_id,))
        if not tag:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_decimal_safe([tag])[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.post("/process_tag")
def process_tag() -> Any:
    try:
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        tag_id = data.get("tag_id")

        conn = get_warehouse_connection()
        cursor = conn.cursor(dictionary=True) if hasattr(conn, "cursor") else conn.cursor()

        if action == "INSPECT":
            passed = float(data.get("passed_qty") or 0)
            rejected = float(data.get("rejected_qty") or 0)
            cursor.execute("SELECT * FROM inventory_grn_item_tag WHERE tag_id = %s", (tag_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return jsonify({"error": "Tag not found"}), 404
            qty_received = float(row["qty_received"])
            if abs((passed + rejected) - qty_received) > 0.01:
                conn.close()
                return jsonify({"error": f"Passed + Rejected must equal {qty_received}"}), 400

            if passed > 0 and rejected > 0:
                cursor.execute("""
                    UPDATE inventory_grn_item_tag SET qty_received = %s, passed_qty = %s, rejected_qty = 0, status = 'INSPECTED'
                    WHERE tag_id = %s
                """, (passed, passed, tag_id))
                child_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO inventory_grn_item_tag
                    (tag_id, grn_id, item_code, item_desc, qty_received, passed_qty, rejected_qty, status, po_line_item_id, uom, parent_tag_id)
                    VALUES (%s, %s, %s, %s, %s, 0, %s, 'REJECTED', %s, %s, %s)
                """, (child_id, row["grn_id"], row["item_code"], row["item_desc"], rejected, rejected, row.get("po_line_item_id"), row.get("uom"), tag_id))
            elif passed == 0:
                cursor.execute("UPDATE inventory_grn_item_tag SET passed_qty = 0, rejected_qty = %s, status = 'REJECTED' WHERE tag_id = %s", (rejected, tag_id))
            else:
                cursor.execute("UPDATE inventory_grn_item_tag SET passed_qty = %s, rejected_qty = 0, status = 'INSPECTED' WHERE tag_id = %s", (passed, tag_id))

        elif action == "RACK":
            locations = data.get("locations", [])
            if not locations:
                conn.close()
                return jsonify({"error": "No rack locations provided"}), 400
            cursor.execute("UPDATE inventory_grn_item_tag SET status = 'RACKED' WHERE tag_id = %s", (tag_id,))
            for loc in locations:
                cursor.execute("""
                    INSERT INTO inventory_tag_locations (tag_id, rack_number, current_qty) VALUES (%s, %s, %s)
                """, (tag_id, loc["rack"], float(loc["qty"])))

        elif action == "ISSUE":
            issue_qty = float(data.get("issue_qty", 0))
            issue_rack = str(data.get("issue_rack", "")).strip()
            cursor.execute("SELECT location_id, current_qty FROM inventory_tag_locations WHERE tag_id = %s AND rack_number = %s", (tag_id, issue_rack))
            loc_row = cursor.fetchone()
            if not loc_row or float(loc_row["current_qty"]) < issue_qty:
                conn.close()
                return jsonify({"error": f"Not enough stock in {issue_rack}"}), 400
            new_qty = float(loc_row["current_qty"]) - issue_qty
            if new_qty > 0:
                cursor.execute("UPDATE inventory_tag_locations SET current_qty = %s WHERE location_id = %s", (new_qty, loc_row["location_id"]))
            else:
                cursor.execute("DELETE FROM inventory_tag_locations WHERE location_id = %s", (loc_row["location_id"],))
            cursor.execute("SELECT passed_qty, issued_qty FROM inventory_grn_item_tag WHERE tag_id = %s", (tag_id,))
            tag_row = cursor.fetchone()
            new_issued = float(tag_row["issued_qty"]) + issue_qty
            new_status = "ISSUED" if new_issued >= float(tag_row["passed_qty"]) else "PARTIALLY ISSUED"
            cursor.execute("UPDATE inventory_grn_item_tag SET issued_qty = %s, status = %s WHERE tag_id = %s", (new_issued, new_status, tag_id))

        elif action == "RETURN":
            return_qty = float(data.get("return_qty", 0))
            return_rack = str(data.get("return_rack", "")).strip()
            cursor.execute("SELECT passed_qty, issued_qty FROM inventory_grn_item_tag WHERE tag_id = %s", (tag_id,))
            row = cursor.fetchone()
            if return_qty > float(row["issued_qty"]):
                conn.close()
                return jsonify({"error": "Cannot return more than is currently issued."}), 400
            new_issued = float(row["issued_qty"]) - return_qty
            new_status = "RACKED" if new_issued <= 0 else "PARTIALLY ISSUED"
            cursor.execute("UPDATE inventory_grn_item_tag SET issued_qty = %s, status = %s WHERE tag_id = %s", (new_issued, new_status, tag_id))
            cursor.execute("SELECT location_id, current_qty FROM inventory_tag_locations WHERE tag_id = %s AND rack_number = %s", (tag_id, return_rack))
            loc_row = cursor.fetchone()
            if loc_row:
                cursor.execute("UPDATE inventory_tag_locations SET current_qty = %s WHERE location_id = %s", (float(loc_row["current_qty"]) + return_qty, loc_row["location_id"]))
            else:
                cursor.execute("INSERT INTO inventory_tag_locations (tag_id, rack_number, current_qty) VALUES (%s, %s, %s)", (tag_id, return_rack, return_qty))

        elif action == "RETURN_SCRAP":
            scrap_qty = float(data.get("scrap_qty", 0))
            cursor.execute("SELECT * FROM inventory_grn_item_tag WHERE tag_id = %s", (tag_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return jsonify({"error": "Tag not found"}), 404
            if scrap_qty > float(row["issued_qty"]):
                conn.close()
                return jsonify({"error": "Cannot scrap more than is currently on the floor."}), 400
            new_issued = float(row["issued_qty"]) - scrap_qty
            new_status = "RACKED" if new_issued <= 0 else "PARTIALLY ISSUED"
            cursor.execute("UPDATE inventory_grn_item_tag SET issued_qty = %s, status = %s WHERE tag_id = %s",
                           (new_issued, new_status, tag_id))
            child_tag_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO inventory_grn_item_tag
                (tag_id, grn_id, item_code, item_desc, qty_received, rejected_qty, status, po_line_item_id, uom, parent_tag_id)
                VALUES (%s, %s, %s, %s, %s, %s, 'SCRAPPED', %s, %s, %s)
            """, (child_tag_id, row["grn_id"], row["item_code"], row["item_desc"],
                  scrap_qty, scrap_qty,
                  row.get("po_line_item_id"), row.get("uom"), tag_id))

        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# SCHEDULER — Machines, Components, Jobs
# ═══════════════════════════════════════════════════════════════════════

@warehouse_bp.get("/machines")
def machines_list() -> Any:
    try:
        rows = fetch_all("""
            SELECT MCM_Id, CONCAT(MCM_Name, ' (', IFNULL(MCM_Capacity, 'Unknown'), ')') AS MCM_Name
            FROM machinemaster WHERE MCM_ACTIVEYN = 'Y'
        """)
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/components")
def components_list() -> Any:
    try:
        rows = fetch_all("SELECT CO_ID, CO_PARTNO, CO_PARTNAME FROM components WHERE CO_ACTIVEYN = 'Y'")
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/sales_orders/<int:comp_id>")
def sales_orders(comp_id: int) -> Any:
    try:
        rows = fetch_all("""
            SELECT s.SO_NO, s.INV_BALANCE_QTY AS pending_qty
            FROM sales_order s
            JOIN components c ON c.CO_PARTNO = s.PART_NO
            WHERE c.CO_ID = %s AND s.INV_BALANCE_QTY > 0
            ORDER BY s.SO_DATE ASC
        """, (comp_id,))
        return jsonify(_decimal_safe(rows))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/component_details/<int:comp_id>")
def component_details(comp_id: int) -> Any:
    try:
        det = fetch_one("""
            SELECT c.CO_ID, c.CO_PARTNO, c.CO_PARTNAME, c.CO_WEIGHT,
                   t.CT_ID, t.CT_TOOLNO, t.CT_RMID, m.MM_RawMtPartNo
            FROM components c
            JOIN components_tool t ON c.CO_ID = t.CT_COMPID
            JOIN materialmaster m ON t.CT_RMID = m.MM_Id
            WHERE c.CO_ID = %s AND t.CT_ACTIVEYN = 'Y' LIMIT 1
        """, (comp_id,))
        if not det:
            return jsonify({"error": "No active tool or raw material mapping found."}), 404
        stock = wh_fetch_one("""
            SELECT SUM(passed_qty - issued_qty) AS total_avail
            FROM inventory_grn_item_tag
            WHERE item_code = %s AND status IN ('RACKED', 'PARTIALLY ISSUED')
        """, (det["MM_RawMtPartNo"],))
        det["RM_AVAILABLE"] = float((stock or {}).get("total_avail") or 0)
        return jsonify(_decimal_safe([det])[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.post("/schedule_job")
def schedule_job() -> Any:
    data = request.get_json(silent=True) or {}
    try:
        job_id = str(uuid.uuid4())
        job_no = f"JOB-{uuid.uuid4().hex[:6].upper()}"
        user_id = g.current_user.get("userId") or g.current_user.get("user_id")
        conn = get_warehouse_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO production_schedule
            (job_id, job_no, scheduled_date, machine_id, machine_name, component_id, part_no, part_name,
             sales_order_no, tool_id, tool_no, raw_material_part_no, target_qty, rm_required_qty, rm_issued_qty,
             status, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0.00,'PENDING',%s)
        """, (
            job_id, job_no, data["scheduled_date"], data["machine_id"], data["machine_name"],
            data["component_id"], data["part_no"], data["part_name"], data.get("sales_order", ""),
            data["tool_id"], data["tool_no"], data["rm_part_no"], data["target_qty"],
            data["rm_required"], user_id,
        ))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "job_no": job_no})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/machine_queue/<int:machine_id>")
def machine_queue(machine_id: int) -> Any:
    try:
        rows = wh_fetch_all("""
            SELECT * FROM production_schedule
            WHERE machine_id = %s AND status IN ('PENDING', 'IN_PROGRESS')
            ORDER BY scheduled_date ASC, created_at ASC
        """, (machine_id,))
        return jsonify(_decimal_safe(rows))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.post("/update_job")
def update_job() -> Any:
    data = request.get_json(silent=True) or {}
    try:
        new_status = "COMPLETED" if data.get("action") == "COMPLETE" else "IN_PROGRESS"
        conn = get_warehouse_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE production_schedule
            SET produced_qty = produced_qty + %s, strokes_consumed = strokes_consumed + %s,
                rm_issued_qty = rm_issued_qty + %s, status = %s, operator_remarks = %s
            WHERE job_id = %s
        """, (
            float(data.get("produced_qty", 0)), int(data.get("strokes_qty", 0)),
            float(data.get("rm_issued_qty", 0)), new_status, data.get("remarks", ""),
            data["job_id"],
        ))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.delete("/delete_job/<job_id>")
def delete_job(job_id: str) -> Any:
    try:
        conn = get_warehouse_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM production_schedule WHERE job_id = %s AND status = 'PENDING'", (job_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            return jsonify({"status": "success"})
        return jsonify({"error": "Cannot delete — job is already in progress or completed."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/daily_schedule/<date>")
def daily_schedule(date: str) -> Any:
    try:
        rows = wh_fetch_all("""
            SELECT job_id, job_no, machine_name, part_no, part_name, sales_order_no,
                   target_qty, produced_qty, status, operator_remarks
            FROM production_schedule WHERE scheduled_date = %s
            ORDER BY status DESC, machine_name ASC
        """, (date,))
        return jsonify(_decimal_safe(rows))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/board_data/<base_date>")
def board_data(base_date: str) -> Any:
    try:
        rows = wh_fetch_all("""
            SELECT job_id, job_no, machine_name, part_no, part_name, sales_order_no,
                   tool_no, raw_material_part_no, rm_required_qty, rm_issued_qty, target_qty,
                   produced_qty, strokes_consumed, status, operator_remarks, scheduled_date
            FROM production_schedule
            WHERE scheduled_date BETWEEN DATE_SUB(%s, INTERVAL 1 DAY) AND DATE_ADD(%s, INTERVAL 1 DAY)
            ORDER BY scheduled_date ASC, machine_name ASC
        """, (base_date, base_date))
        return jsonify(_decimal_safe(rows))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# WAREHOUSE STATS / Dashboard
# ═══════════════════════════════════════════════════════════════════════

@warehouse_bp.get("/stats")
def warehouse_stats() -> Any:
    try:
        def _val(sql: str) -> Any:
            r = wh_fetch_one(sql)
            return int(r.get("total") or 0) if r else 0

        awaiting = _val("SELECT COUNT(*) AS total FROM inventory_grn_item_tag WHERE status = 'RECEIVED'")
        putaway  = _val("SELECT COUNT(*) AS total FROM inventory_grn_item_tag WHERE status = 'INSPECTED'")
        avail    = wh_fetch_one("SELECT SUM(passed_qty - issued_qty) AS total FROM inventory_grn_item_tag WHERE status IN ('RACKED','PARTIALLY ISSUED')")
        rejected = wh_fetch_one("SELECT SUM(rejected_qty) AS total FROM inventory_grn_item_tag WHERE status != 'SCRAPPED'")
        scrap    = wh_fetch_one("SELECT SUM(rejected_qty) AS total FROM inventory_grn_item_tag WHERE status = 'SCRAPPED'")
        issued   = wh_fetch_one("SELECT SUM(issued_qty) AS total FROM inventory_grn_item_tag")

        inv = wh_fetch_all("""
            SELECT t.item_code, t.tag_id, t.qty_received, t.status, t.passed_qty, t.rejected_qty, t.issued_qty, t.uom,
                   (SELECT GROUP_CONCAT(CONCAT(rack_number,' (',current_qty,')') SEPARATOR ', ')
                    FROM inventory_tag_locations WHERE tag_id = t.tag_id) AS rack_number,
                   m.po_no
            FROM inventory_grn_item_tag t
            JOIN inventory_grn_master m ON t.grn_id = m.grn_id
            ORDER BY t.tag_id DESC LIMIT 50
        """)
        return jsonify({
            "awaiting_inspection": awaiting,
            "awaiting_putaway": putaway,
            "available_stock": float((avail or {}).get("total") or 0),
            "rejected_units": float((rejected or {}).get("total") or 0),
            "scrap_units": float((scrap or {}).get("total") or 0),
            "issued_units": float((issued or {}).get("total") or 0),
            "inventory": _decimal_safe(inv),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ═══════════════════════════════════════════════════════════════════════
# MACHINE PORTAL / DIGITAL TWIN
# ═══════════════════════════════════════════════════════════════════════

@warehouse_bp.get("/machine_portal/<int:machine_id>")
def machine_portal_data(machine_id: int) -> Any:
    try:
        # 1. Basic Machine Info (ERP)
        m_info = fetch_one("SELECT MCM_Id, MCM_Name FROM machinemaster WHERE MCM_Id = %s", (machine_id,))
        if not m_info:
            return jsonify({"error": "Machine not found"}), 404

        # 2. Active Job (Warehouse)
        job = wh_fetch_one("""
            SELECT * FROM production_schedule
            WHERE machine_id = %s AND status = 'IN_PROGRESS'
            LIMIT 1
        """, (machine_id,))

        # 3. Tool Health (ERP) — if job exists
        tool_health = None
        if job and job.get("tool_no"):
            t_no = job["tool_no"]
            tool_health = fetch_one("""
                WITH LatestPM AS (
                    SELECT PM_tool_number, PM_current_stroke, PM_next_stroke, PM_date,
                           ROW_NUMBER() OVER(PARTITION BY PM_tool_number ORDER BY PM_date DESC) AS rn
                    FROM preventive_maintenance WHERE PM_tool_number = %s
                ),
                RecentProduction AS (
                    SELECT pd.PD_TOOLID, SUM(pd.PD_PRODQTY) AS new_parts
                    FROM production_details pd
                    JOIN components_tool ct ON pd.PD_TOOLID = ct.CT_ID
                    JOIN LatestPM pm ON ct.CT_TOOLNO = pm.PM_tool_number AND pm.rn = 1
                    WHERE ct.CT_TOOLNO = %s AND pd.PD_DATE >= pm.PM_date
                    GROUP BY pd.PD_TOOLID
                )
                SELECT pm.PM_tool_number, pm.PM_next_stroke,
                       (COALESCE(pm.PM_current_stroke,0) + COALESCE(rp.new_parts,0)/COALESCE(NULLIF(ct.CT_NO_OF_CAVITY,0),1)) AS current_strokes
                FROM latestPM pm
                LEFT JOIN RecentProduction rp ON 1=1
                LEFT JOIN components_tool ct ON ct.CT_TOOLNO = pm.PM_tool_number AND ct.CT_ACTIVEYN = 'Y'
                WHERE pm.rn = 1 LIMIT 1
            """, (t_no, t_no))

        return jsonify({
            "machine": m_info,
            "job": _decimal_safe([job])[0] if job else None,
            "tool": tool_health if tool_health else None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@warehouse_bp.get("/runway_predictor")
def runway_predictor() -> Any:
    try:
        # 1. Fetch all In-Progress jobs
        jobs = wh_fetch_all("""
            SELECT job_id, machine_name, part_no, part_name, target_qty, produced_qty, 
                   rm_required_qty, rm_issued_qty, raw_material_part_no
            FROM production_schedule WHERE status = 'IN_PROGRESS'
        """)
        
        results = []
        for j in jobs:
            # Fetch RM conversion value from ERP (grams per part)
            tool = fetch_one("""
                SELECT ct.CT_COMPID, ct.CT_RMID, mm.MM_RAWMTPARTNO, c.CO_WEIGHT
                FROM components_tool ct
                JOIN components c ON ct.CT_COMPID = c.CO_ID
                JOIN materialmaster mm ON ct.CT_RMID = mm.MM_Id
                WHERE TRIM(c.CO_PARTNO) = %s AND ct.CT_ACTIVEYN = 'Y'
                LIMIT 1
            """, (j["part_no"],))
            
            weight = float(tool["CO_WEIGHT"]) if tool and tool.get("CO_WEIGHT") else 0
            issued = float(j["rm_issued_qty"] or 0)
            produced = float(j["produced_qty"] or 0)
            
            # Remaining RM in Kgs
            rm_consumed = produced * (weight / 1000.0) 
            rm_remaining = issued - rm_consumed
            
            # Usage rate: Assume a standard rate of 100 parts/hr if not available
            target = float(j["target_qty"] or 1)
            hourly_rate = target / 8.0 
            rm_usage_per_hour = hourly_rate * (weight / 1000.0)
            
            minutes_left = (rm_remaining / rm_usage_per_hour * 60) if rm_usage_per_hour > 0 else 999
            
            results.append({
                "job_id": j["job_id"],
                "machine_name": j["machine_name"],
                "part_no": j["part_no"],
                "rm_part_no": j["raw_material_part_no"],
                "rm_remaining_kg": round(rm_remaining, 2),
                "minutes_remaining": int(minutes_left),
                "status": "critical" if minutes_left < 30 else ("warning" if minutes_left < 90 else "healthy")
            })
            
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/activity_pulse")
def activity_pulse() -> Any:
    """Legacy: GRN + warehouse jobs + production. Hub uses `/api/hub/pulse` (ERP-only) instead."""
    try:
        grns: List[Dict[str, Any]] = []
        prods: List[Dict[str, Any]] = []
        jobs: List[Dict[str, Any]] = []
        try:
            # Master row has no created_at in this schema; use latest tag rows for recency.
            grns = wh_fetch_all(
                """
                SELECT m.grn_no AS grn_no, t.tag_id AS tag_id, 'GRN' AS type
                FROM inventory_grn_item_tag t
                INNER JOIN inventory_grn_master m ON m.grn_id = t.grn_id
                ORDER BY t.tag_id DESC
                LIMIT 5
                """
            )
        except Exception as e:
            current_app.logger.warning("activity_pulse GRNs: %s", e)
        try:
            # Part number lives on components, not production_details (no PD_PARTNO).
            prods = fetch_all(
                """
                SELECT TRIM(co.CO_PARTNO) AS part_no, pd.PD_PRODQTY AS qty, pd.PD_DATE AS date,
                       'PROD' AS type
                FROM production_details pd
                INNER JOIN components_tool ct ON pd.PD_TOOLID = ct.CT_ID
                INNER JOIN components co ON ct.CT_COMPID = co.CO_ID
                ORDER BY pd.PD_DATE DESC
                LIMIT 5
                """
            )
        except Exception as e:
            current_app.logger.warning("activity_pulse production_details: %s", e)
        try:
            jobs = wh_fetch_all(
                "SELECT job_no, status, 'JOB' as type, created_at FROM production_schedule "
                "ORDER BY created_at DESC LIMIT 5"
            )
        except Exception as e:
            current_app.logger.warning("activity_pulse jobs: %s", e)

        pulse: List[Dict[str, Any]] = []
        for g in grns:
            pulse.append(
                {
                    "id": g["grn_no"],
                    "text": f"New GRN {g['grn_no']} generated",
                    "time": _json_safe_scalar(g.get("tag_id")),
                }
            )
        for p in prods:
            qraw = p.get("qty")
            try:
                qn = int(float(qraw)) if qraw is not None and str(qraw).strip() != "" else 0
            except (TypeError, ValueError):
                qn = 0
            pulse.append(
                {
                    "id": f"p-{p['part_no']}",
                    "text": f"Produced {qn} of {p['part_no']}",
                    "time": _json_safe_scalar(p.get("date")),
                }
            )
        for j in jobs:
            pulse.append(
                {
                    "id": j["job_no"],
                    "text": f"Job {j['job_no']} is {j['status']}",
                    "time": _json_safe_scalar(j.get("created_at")),
                }
            )

        pulse.sort(key=lambda x: str(x["time"] or ""), reverse=True)
        return jsonify(pulse[:10])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# QR CODE LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════

def _get_local_ip() -> str:
    """Best-effort get the LAN IP for QR URL generation."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _receiver_port() -> str:
    return request.host.split(":")[-1] if ":" in request.host else "5000"


def machine_qr_payload(machine_id: str) -> Dict[str, str]:
    """PNG (base64, no data: prefix) and full receiver URL for any machine id (including string codes)."""
    mid = str(machine_id).strip()
    base_url = f"http://{_get_local_ip()}:{_receiver_port()}/receiver"
    scan_url = f"{base_url}?machine_id={quote(mid, safe='')}"
    qr_img = qrcode.make(scan_url)
    buf = io.BytesIO()
    qr_img.save(buf)
    qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return {"qr_base64": qr_base64, "scan_url": scan_url}


@warehouse_bp.get("/get_qr/<tag_id>")
def get_qr(tag_id: str) -> Any:
    """Generate a QR code image (base64) for a warehouse tag.
    The QR encodes a URL that opens the receiver/scanner page.
    """
    try:
        base_url = f"http://{_get_local_ip()}:{request.host.split(':')[-1] if ':' in request.host else '5000'}/receiver"
        qr_img = qrcode.make(f"{base_url}?tag_id={tag_id}")
        buf = io.BytesIO()
        qr_img.save(buf)
        qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return jsonify({"qr": qr_base64})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/get_machine_qr/<int:machine_id>")
def get_machine_qr(machine_id: int) -> Any:
    """Generate a QR code image (base64) for a machine.
    The QR encodes a URL that opens the receiver/scanner page
    with machine_id context for the operator job queue.
    """
    try:
        p = machine_qr_payload(str(machine_id))
        return jsonify({"qr": p["qr_base64"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.get("/get_machine_qr_s/<path:machine_id>")
def get_machine_qr_s(machine_id: str) -> Any:
    """Same as get_machine_qr for non-numeric or string machine identifiers (DPR, etc.)."""
    try:
        p = machine_qr_payload(machine_id)
        return jsonify({"qr": p["qr_base64"], "scan_url": p["scan_url"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@warehouse_bp.delete("/delete_tag/<tag_id>")
def delete_tag(tag_id: str) -> Any:
    """Permanently delete a warehouse tag and its location records."""
    try:
        conn = get_warehouse_connection()
        cursor = conn.cursor(dictionary=True) if hasattr(conn, "cursor") else conn.cursor()
        cursor.execute("DELETE FROM inventory_tag_locations WHERE tag_id = %s", (tag_id,))
        cursor.execute("DELETE FROM inventory_grn_item_tag WHERE tag_id = %s", (tag_id,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
