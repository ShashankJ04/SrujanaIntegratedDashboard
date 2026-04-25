"""RM Correction API Blueprint.

Port of dashboards/backend/src/routes/rmCorrection.ts.
Provides stock-adjustment candidates with RM remaining and scrap,
plus batch production detail drill-down.
"""

from __future__ import annotations

import re

from flask import Blueprint, jsonify, request

from .auth import api_login_required
from .rbac import require_any_access
from .db import fetch_all

rm_correction_bp = Blueprint("rm_correction_bp", __name__, url_prefix="/api/rm-correction")


@rm_correction_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


# ── GET / — stock adjustment candidates ─────────────────────────────────

@rm_correction_bp.route("/", methods=["GET"])
@require_any_access(["rm_correction", "rm_variance"])
def list_entries():
    start_date_param = (request.args.get("startDate") or "").strip()
    is_valid = bool(re.match(r"^\d{4}-\d{2}-\d{2}$", start_date_param))

    if is_valid:
        start_date_expr = "%s"
        params = (start_date_param,)
    else:
        start_date_expr = "DATE_SUB(CURDATE(), INTERVAL 10 DAY)"
        params = ()

    sql = f"""
        SELECT
            COALESCE(prodQ.MM_RawMtPartNo, '') AS rawMaterial,
            prodRM.batch AS batch,
            ROUND(COALESCE(inwardTotals.totalInwarded, 0), 2) AS totalInwarded,
            ROUND(COALESCE(prodRM.RMGiven, 0), 2) AS rmGiven,
            ROUND(COALESCE((prodRM.RMGiven - prodQ.ThRMForProduction), 0), 2) AS rmRemaining,
            ROUND(COALESCE(prodQ.pdscrap, 0), 2) AS scrap
        FROM (
            SELECT
                RD_BATCHNO AS batch,
                rd_rmid,
                ROUND(
                    SUM(CASE WHEN ri_movement = 'O' THEN rd_qty ELSE 0 END) -
                    SUM(CASE WHEN ri_movement = 'I' THEN rd_acceptedqty ELSE 0 END),
                    2
                ) AS RMGiven
            FROM rm_inwarddetails
            JOIN rm_inwardmaster ON rd_riid = ri_id
            WHERE RI_MOVEMENTTYPE = 3
            GROUP BY RD_BATCHNO, rd_rmid
        ) prodRM
        JOIN (
            SELECT DISTINCT PD_BATCHNO AS batch
            FROM production_details
            WHERE PD_DATE >= COALESCE({start_date_expr}, DATE_SUB(CURDATE(), INTERVAL 10 DAY))
              AND PD_DATE <= CURDATE()
        ) recentBatches ON recentBatches.batch = prodRM.batch
        LEFT JOIN (
            SELECT
                RD_BATCHNO AS batch,
                rd_rmid,
                ROUND(SUM(CASE WHEN ri_movement = 'I' AND RI_MOVEMENTTYPE = 1 THEN rd_acceptedqty ELSE 0 END), 2) AS totalInwarded
            FROM rm_inwarddetails
            JOIN rm_inwardmaster ON rd_riid = ri_id
            GROUP BY RD_BATCHNO, rd_rmid
        ) inwardTotals ON inwardTotals.batch = prodRM.batch AND inwardTotals.rd_rmid = prodRM.rd_rmid
        LEFT JOIN (
            SELECT
                pd_batchno AS batch,
                MM_RawMtPartNo,
                mm_id,
                ROUND(SUM(PD_PRODQTY / conVal), 2) AS ThRMForProduction,
                SUM(PD_SCRAPQTY) AS pdscrap
            FROM production_details
            LEFT JOIN scheduled_production ON pd_psid = ps_id
            LEFT JOIN (
                SELECT
                    CT_COMPID,
                    mm_id,
                    MM_RawMtPartNo,
                    ((1 / ((MT_Density * MM_Thickness) * MM_StripWidth)) * ((1000 * CT_NO_OF_CAVITY) / CT_Pitch)) AS conVal
                FROM components_tool
                INNER JOIN materialmaster ON CT_RMID = MM_Id
                INNER JOIN materialtypemaster ON MM_MTID = MT_Id
                WHERE CT_ActiveYN = 'Y'
                  AND CT_PPC = 'Y'
                  AND CT_PITCH > 0
                  AND CT_NO_OF_CAVITY > 0
            ) t ON CT_COMPID = PS_PARENTCOMPID
            GROUP BY pd_batchno, mm_id, MM_RawMtPartNo
        ) prodQ ON prodQ.batch = prodRM.batch AND prodQ.mm_id = prodRM.rd_rmid
        WHERE NOT (
            ROUND(COALESCE((prodRM.RMGiven - prodQ.ThRMForProduction), 0), 2) = 0
            AND ROUND(COALESCE(prodQ.pdscrap, 0), 2) = 0
        )
        ORDER BY rawMaterial, batch
    """

    try:
        rows = fetch_all(sql, params if params else None)
    except Exception as e:
        return jsonify({"error": "Database query failed", "details": str(e)}), 500

    entries = []
    for r in rows:
        entries.append({
            "rawMaterial": r["rawMaterial"] or "",
            "batch": r["batch"],
            "totalInwarded": float(r["totalInwarded"] or 0),
            "rmGiven": float(r["rmGiven"] or 0),
            "rmRemaining": float(r["rmRemaining"] or 0),
            "scrap": float(r["scrap"] or 0),
        })

    return jsonify({"count": len(entries), "entries": entries})


# ── GET /batch/<batch> — production details for a specific batch ────────

@rm_correction_bp.route("/batch/<batch>", methods=["GET"])
@require_any_access(["rm_correction", "rm_variance"])
def batch_details(batch):
    batch = (batch or "").strip()
    if not batch:
        return jsonify({"error": "Batch is required"}), 400

    try:
        rows = fetch_all(
            """
            SELECT
                DATE_FORMAT(pd_date, '%%d-%%m-%%Y') AS productionDate,
                CO_PARTNO AS partNo,
                PD_LotNo AS lotNo,
                CT_TOOLNO AS tool,
                ROUND((COALESCE(CO_WEIGHT, 0) * COALESCE(pd_prodqty, 0)) / 1000, 4) AS calCompWt,
                pd_prodqty AS noOfComp,
                PD_SFREJECT AS sfRejNos,
                PD_SWQTY AS suWastageNos,
                PD_SCRAPQTY AS scrapKg,
                PD_QTYKG AS partWtKg,
                ROUND(pd_prodqty / NULLIF(conVal, 0), 4) AS theoRmKg
            FROM production_details
            LEFT JOIN materialmaster ON mm_id = pd_rmid
            LEFT JOIN components_tool ON ct_id = pd_toolid
            LEFT JOIN scheduled_production ON pd_psid = ps_id
            LEFT JOIN components ON PS_PARENTCOMPID = CO_ID
            LEFT JOIN (
                SELECT
                    CT_ID AS ctid,
                    ((1 / ((MT_Density * MM_Thickness) * MM_StripWidth)) * ((1000 * CT_NO_OF_CAVITY) / CT_Pitch)) AS conVal
                FROM components_tool
                INNER JOIN materialmaster ON CT_RMID = MM_Id
                INNER JOIN materialtypemaster ON MM_MTID = MT_Id
                WHERE CT_ActiveYN = 'Y' AND CT_PITCH > 0 AND CT_NO_OF_CAVITY > 0
            ) toolConv ON ctid = ct_id
            WHERE pd_batchno = %s
            ORDER BY pd_date DESC
            """,
            (batch,),
        )
    except Exception as e:
        return jsonify({"error": "Database query failed", "details": str(e)}), 500

    entries = []
    for r in rows:
        entries.append({
            "productionDate": r["productionDate"] or "",
            "partNo": r["partNo"] or "",
            "lotNo": r["lotNo"] or "",
            "tool": r["tool"] or "",
            "calCompWt": float(r["calCompWt"] or 0),
            "noOfComp": int(r["noOfComp"] or 0),
            "sfRejNos": int(r["sfRejNos"] or 0),
            "suWastageNos": int(r["suWastageNos"] or 0),
            "scrapKg": float(r["scrapKg"] or 0),
            "partWtKg": float(r["partWtKg"] or 0),
            "theoRmKg": float(r["theoRmKg"] or 0),
        })

    return jsonify({"count": len(entries), "entries": entries})
