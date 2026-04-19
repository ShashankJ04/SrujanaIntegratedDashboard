"""Production API Blueprint.

Port of dashboards/backend/src/routes/production.ts.
Corrected table names: components → CO_, customer → CU_Id/CU_Name,
materialmaster → MM_, comp_stock → CS_, scheduled_production → PS_.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from .auth import api_login_required
from .rbac import require_access
from .db import fetch_all

production_bp = Blueprint("production_bp", __name__, url_prefix="/api/production")


@production_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


# ── GET /<ddmmyyyy> — production data for a date ────────────────────────

@production_bp.route("/<date_param>", methods=["GET"])
@require_access("production")
def production_by_date(date_param):
    iso_date = ""
    if len(date_param) == 10 and date_param[4] == "-" and date_param[7] == "-":
        iso_date = date_param
    elif len(date_param) == 8 and date_param.isdigit():
        dd = date_param[0:2]
        mm = date_param[2:4]
        yyyy = date_param[4:8]
        iso_date = f"{yyyy}-{mm}-{dd}"
    else:
        return jsonify({"message": "Invalid date format. Expected DDMMYYYY or YYYY-MM-DD"}), 400

    rows = fetch_all(
        """
        SELECT
            cu.CU_Name                AS customer,
            co.CO_PARTNO              AS partno,
            co.CO_PARTNAME            AS partname,
            mm.MM_RawMtPartNo         AS raw_material,
            ps.PS_DATE                AS scheduled_date,
            ps.PS_QTY                 AS scheduled_qty,
            pd.PD_PRODQTY             AS prod_qty,
            pd.PD_QTYKG              AS qty_kg,
            pd.PD_SWQTY              AS setup_wastage,
            pd.PD_SFREJECT           AS sf_rejection,
            pd.PD_NETQTY             AS net_qty,
            ps.PS_QTYKG              AS issued_qty,
            pd.PD_QTYKG             AS required_qty,
            COALESCE(stk.fg_stock, 0)    AS fg_stock,
            COALESCE(stk.wip_stock, 0)   AS wip_stock,
            COALESCE(stk.total_stock, 0) AS total_stock
        FROM production_details pd
            JOIN scheduled_production ps ON pd.PD_PSID   = ps.PS_ID
            JOIN components_tool ct      ON pd.PD_TOOLID  = ct.CT_ID
            JOIN components co           ON ct.CT_COMPID  = co.CO_ID
            JOIN customer cu             ON co.CO_CUSTID  = cu.CU_Id
            LEFT JOIN materialmaster mm  ON pd.PD_RMID    = mm.MM_Id
            LEFT JOIN (
                SELECT
                    CS_COMPID,
                    SUM(CASE WHEN CS_STAGEID = 6 THEN CS_QTY ELSE 0 END) AS fg_stock,
                    SUM(CASE WHEN CS_STAGEID != 6 THEN CS_QTY ELSE 0 END) AS wip_stock,
                    SUM(CS_QTY) AS total_stock
                FROM comp_stock
                GROUP BY CS_COMPID
            ) stk ON stk.CS_COMPID = co.CO_ID
        WHERE DATE(pd.PD_DATE) = %s
        ORDER BY cu.CU_Name, co.CO_PARTNO
        """,
        (iso_date,),
    )

    entries = []
    totals = {
        "scheduledQty": 0,
        "prodQty": 0,
        "qtyKg": 0.0,
        "setupWastage": 0,
        "sfRejection": 0,
        "netQty": 0,
        "issuedQty": 0.0,
        "requiredQty": 0.0,
        "variance": 0,
    }

    for r in rows:
        sched_qty = int(r["scheduled_qty"] or 0)
        prod_qty = int(r["prod_qty"] or 0)
        variance = prod_qty - sched_qty

        entry = {
            "customer": r["customer"] or "",
            "partno": r["partno"] or "",
            "partname": r["partname"] or "",
            "rawMaterial": r["raw_material"] or "",
            "scheduledDate": str(r["scheduled_date"]) if r["scheduled_date"] else "",
            "scheduledQty": sched_qty,
            "prodQty": prod_qty,
            "qtyKg": float(r["qty_kg"] or 0),
            "variance": variance,
            "setupWastage": int(r["setup_wastage"] or 0),
            "sfRejection": int(r["sf_rejection"] or 0),
            "netQty": int(r["net_qty"] or 0),
            "issuedQty": float(r["issued_qty"] or 0),
            "requiredQty": float(r["required_qty"] or 0),
            "fgStock": int(r["fg_stock"]),
            "wipStock": int(r["wip_stock"]),
            "totalStock": int(r["total_stock"]),
        }
        entries.append(entry)

        totals["scheduledQty"] += entry["scheduledQty"]
        totals["prodQty"] += entry["prodQty"]
        totals["qtyKg"] += entry["qtyKg"]
        totals["variance"] += entry["variance"]
        totals["setupWastage"] += entry["setupWastage"]
        totals["sfRejection"] += entry["sfRejection"]
        totals["netQty"] += entry["netQty"]
        totals["issuedQty"] += entry["issuedQty"]
        totals["requiredQty"] += entry["requiredQty"]

    return jsonify({
        "date": iso_date,
        "entries": entries,
        "totals": totals,
    })
