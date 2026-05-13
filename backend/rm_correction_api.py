"""RM Correction API — parity with dashboards/backend/src/routes/rmCorrection.ts.

Endpoints (all require API auth + rm_correction or rm_variance):
  GET  /api/rm-correction           — list stock adjustment candidates
  GET  /api/rm-correction/batch/<batch>
  GET  /api/rm-correction/history/<batch>/<rmid>
  POST /api/rm-correction/submit   — append rm_prodcorrection / rm_scrapcorrection rows
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional

from flask import Blueprint, g, jsonify, request

from .auth import api_login_required
from .rbac import require_any_access
from .db import execute, fetch_all

logger = logging.getLogger(__name__)

rm_correction_bp = Blueprint("rm_correction_bp", __name__, url_prefix="/api/rm-correction")


@rm_correction_bp.before_request
def _auth() -> Optional[Any]:
    result = api_login_required()
    if result is not None:
        return result
    return None


def _parse_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _item_has_finite_actual(item: Dict[str, Any]) -> bool:
    return _parse_float(item.get("actualRm")) is not None or _parse_float(item.get("actualScrap")) is not None


# ── POST /submit (register before GET "/" so "submit" is not captured as batch) ──


@rm_correction_bp.route("/submit", methods=["POST"])
@require_any_access(["rm_correction", "rm_variance"])
def submit_corrections() -> Any:
    user = g.current_user
    user_id = int(user.get("userId") or 0)

    body = request.get_json(silent=True) or {}
    raw_items = body.get("items", [])

    # Match TS: if (!Array.isArray(rawItems) || items.length === 0)
    if not isinstance(raw_items, list):
        return jsonify({"error": "No rows with Actual RM or Actual Scrap provided"}), 400

    items: List[Dict[str, Any]] = [i for i in raw_items if isinstance(i, dict) and _item_has_finite_actual(i)]

    if len(items) == 0:
        return jsonify({"error": "No rows with Actual RM or Actual Scrap provided"}), 400

    inserted_rm = 0
    inserted_scrap = 0

    try:
        for item in items:
            batch = str(item.get("batch", "")).strip()
            try:
                rmid = int(item["rmid"])
            except (KeyError, ValueError, TypeError):
                return jsonify({"error": "Invalid correction payload"}), 400

            if not batch:
                return jsonify({"error": "Invalid correction payload"}), 400
            if len(batch) > 45:
                return jsonify({"error": "Batch value exceeds 45 characters"}), 400

            actual_rm = _parse_float(item.get("actualRm"))
            actual_scrap = _parse_float(item.get("actualScrap"))
            has_rm = actual_rm is not None
            has_scrap = actual_scrap is not None

            if has_rm:
                remarks = str(item.get("rmRemarks", "")).strip()
                theo_rm = _parse_float(item.get("theoRmRemaining"))
                if not remarks or theo_rm is None:
                    return jsonify({"error": "Invalid RM correction payload"}), 400
                if len(remarks) > 50:
                    return jsonify({"error": "RM Remarks cannot exceed 50 characters"}), 400
                correction = round(theo_rm - actual_rm, 2)  # type: ignore[operator]
                execute(
                    """
                    INSERT INTO rm_prodcorrection
                      (rc_batchno, rc_rmid, rc_theo, rc_correction, rc_remarks, rc_createddt, rc_userid)
                    VALUES
                      (%s, %s, %s, %s, %s, NOW(), %s)
                    """,
                    (batch, rmid, theo_rm, correction, remarks, user_id),
                )
                inserted_rm += 1

            if has_scrap:
                scrap_before = _parse_float(item.get("scrapBefore"))
                scrap_remarks = str(item.get("scrapRemarks", "")).strip()
                if scrap_before is None or not scrap_remarks:
                    return jsonify({"error": "Invalid Scrap correction payload"}), 400
                if len(scrap_remarks) > 50:
                    return jsonify({"error": "Scrap Remarks cannot exceed 50 characters"}), 400
                scrap_correction = round(scrap_before - actual_scrap, 2)  # type: ignore[operator]
                execute(
                    """
                    INSERT INTO rm_scrapcorrection
                      (rc_batchno, rc_rmid, rc_QtyBefore, rc_correction, rc_remarks, rc_createddt, rc_userid, rc_movementtype)
                    VALUES
                      (%s, %s, %s, %s, %s, NOW(), %s, 'P')
                    """,
                    (batch, rmid, scrap_before, scrap_correction, scrap_remarks, user_id),
                )
                inserted_scrap += 1

        return jsonify(
            {
                "inserted": inserted_rm + inserted_scrap,
                "insertedRm": inserted_rm,
                "insertedScrap": inserted_scrap,
            }
        )

    except Exception as e:
        logger.exception("RM Correction submit error: %s", e)
        return (
            jsonify(
                {
                    "message": "Database insert failed",
                    "error": "Database insert failed",
                    "details": str(e),
                }
            ),
            500,
        )


# ── GET /batch/<batch> ───────────────────────────────────────────────────


@rm_correction_bp.route("/batch/<path:batch>", methods=["GET"])
@require_any_access(["rm_correction", "rm_variance"])
def batch_details(batch: str) -> Any:
    batch = (batch or "").strip()
    if not batch:
        return jsonify({"error": "Batch is required"}), 400

    sql = """
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
    """

    try:
        rows = fetch_all(sql, (batch,))
    except Exception as e:
        logger.exception("RM Correction batch details query error: %s", e)
        return jsonify({"error": "Database query failed", "details": str(e)}), 500

    entries = []
    for r in rows:
        entries.append(
            {
                "productionDate": r["productionDate"] or "",
                "partNo": r["partNo"] or "",
                "lotNo": r["lotNo"] or "",
                "tool": r["tool"] or "",
                "calCompWt": float(r["calCompWt"] or 0),
                "noOfComp": float(r["noOfComp"] or 0),
                "sfRejNos": float(r["sfRejNos"] or 0),
                "suWastageNos": float(r["suWastageNos"] or 0),
                "scrapKg": float(r["scrapKg"] or 0),
                "partWtKg": float(r["partWtKg"] or 0),
                "theoRmKg": float(r["theoRmKg"] or 0),
            }
        )

    return jsonify({"count": len(entries), "entries": entries})


# ── GET /history/<batch>/<rmid> ─────────────────────────────────────────


@rm_correction_bp.route("/history/<int:rmid>/<path:batch>", methods=["GET"])
@require_any_access(["rm_correction", "rm_variance"])
def correction_history(rmid: int, batch: str) -> Any:
    batch = (batch or "").strip()
    if not batch:
        return jsonify({"error": "Valid batch and RM id are required"}), 400

    sql = """
        SELECT
            historyRows.type,
            historyRows.qtyBefore,
            historyRows.correction,
            historyRows.remarks,
            DATE_FORMAT(historyRows.sortAt, '%%d-%%m-%%Y %%H:%%i:%%s') AS createdAt,
            historyRows.userLogin,
            historyRows.sortAt
        FROM (
            SELECT
                'RM' AS type,
                COALESCE(p.rc_theo, 0) AS qtyBefore,
                COALESCE(p.rc_correction, 0) AS correction,
                p.rc_remarks AS remarks,
                p.rc_createddt AS sortAt,
                u.US_login AS userLogin
            FROM rm_prodcorrection p
            LEFT JOIN users u ON u.US_id = p.rc_userid
            WHERE TRIM(p.rc_batchno) = TRIM(%s)
              AND p.rc_rmid = %s

            UNION ALL

            SELECT
                'SCRAP' AS type,
                COALESCE(s.rc_QtyBefore, 0) AS qtyBefore,
                COALESCE(s.rc_correction, 0) AS correction,
                s.rc_remarks AS remarks,
                s.rc_createddt AS sortAt,
                u.US_login AS userLogin
            FROM rm_scrapcorrection s
            LEFT JOIN users u ON u.US_id = s.rc_userid
            WHERE TRIM(s.rc_batchno) = TRIM(%s)
              AND s.rc_rmid = %s
              AND UPPER(COALESCE(s.rc_movementtype, 'P')) = 'P'
        ) historyRows
        ORDER BY historyRows.sortAt DESC
    """

    try:
        rows = fetch_all(sql, (batch, rmid, batch, rmid))
    except Exception as e:
        logger.exception("RM Correction history query error: %s", e)
        return jsonify({"error": "Database query failed", "details": str(e)}), 500

    entries = []
    for r in rows:
        entries.append(
            {
                "type": r["type"],
                "qtyBefore": float(r["qtyBefore"] or 0),
                "correction": float(r["correction"] or 0),
                "remarks": r["remarks"] or "",
                "createdAt": r["createdAt"] or "",
                "userLogin": r["userLogin"] or "",
            }
        )

    return jsonify({"count": len(entries), "entries": entries})


# ── GET / — stock adjustment candidates ───────────────────────────────────


_LIST_SQL_TEMPLATE = """
    SELECT
        COALESCE(prodQ.MM_RawMtPartNo, '') AS rawMaterial,
        TRIM(prodRM.batch) AS batch,
        prodRM.rd_rmid AS rmid,
        ROUND(COALESCE(inwardTotals.totalInwarded, 0), 2) AS totalInwarded,
        ROUND(COALESCE(prodRM.ProdQty, 0), 2) AS rmGiven,

        ROUND(
            COALESCE((prodRM.ProdQty - prodQ.ThRMForProduction), 0) -
            COALESCE(corrections.totalCorrection, 0),
            2
        ) AS rmRemaining,

        ROUND(
            COALESCE(prodQ.pdscrap, 0) - COALESCE(scrapCorrections.totalScrapCorrection, 0),
            2
        ) AS scrap
    FROM (
        SELECT
            RD_BATCHNO AS batch,
            rd_rmid,
            ROUND(
                SUM(CASE WHEN ri_movement = 'O' THEN rd_qty ELSE 0 END) -
                SUM(CASE WHEN ri_movement = 'I' THEN rd_acceptedqty ELSE 0 END),
                2
            ) AS ProdQty
        FROM rm_inwarddetails
        JOIN rm_inwardmaster ON rd_riid = ri_id
        WHERE RI_MOVEMENTTYPE = 3
        GROUP BY RD_BATCHNO, rd_rmid
    ) prodRM
    JOIN (
        SELECT DISTINCT PD_BATCHNO AS batch
        FROM production_details
        WHERE DATE(PD_DATE) >= COALESCE({start_expr}, DATE_SUB(CURDATE(), INTERVAL 10 DAY))
          AND DATE(PD_DATE) <= CURDATE()
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
            TRIM(rc_batchno) AS rc_batchno,
            rc_rmid,
            ROUND(SUM(COALESCE(rc_correction, 0)), 2) AS totalCorrection
        FROM rm_prodcorrection
        GROUP BY rc_batchno, rc_rmid
    ) corrections ON corrections.rc_batchno = TRIM(prodRM.batch) AND corrections.rc_rmid = prodRM.rd_rmid
    LEFT JOIN (
        SELECT
            TRIM(rc_batchno) AS rc_batchno,
            rc_rmid,
            ROUND(SUM(COALESCE(rc_correction, 0)), 2) AS totalScrapCorrection
        FROM rm_scrapcorrection
        WHERE UPPER(COALESCE(rc_movementtype, 'P')) = 'P'
        GROUP BY rc_batchno, rc_rmid
    ) scrapCorrections ON scrapCorrections.rc_batchno = TRIM(prodRM.batch) AND scrapCorrections.rc_rmid = prodRM.rd_rmid
    LEFT JOIN (
        SELECT
            pd_batchno AS batch,
            MM_RawMtPartNo,
            mm_id,
            ROUND(SUM((PD_PRODQTY) / conVal), 2) AS ThRMForProduction,
            SUM(PD_SCRAPQTY) AS pdscrap
        FROM production_details
        LEFT JOIN scheduled_production ON pd_psid = ps_id
        LEFT JOIN (
            SELECT
                CT_COMPID, ct_id,
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
        ) t ON CT_COMPID = PS_PARENTCOMPID AND ct_id = PD_TOOLID
        GROUP BY pd_batchno, mm_id, MM_RawMtPartNo
    ) prodQ ON prodQ.batch = prodRM.batch AND prodQ.mm_id = prodRM.rd_rmid
    WHERE NOT (
        ROUND(
            COALESCE((prodRM.ProdQty - prodQ.ThRMForProduction), 0) -
            COALESCE(corrections.totalCorrection, 0),
            2
        ) = 0
        AND ROUND(
            COALESCE(prodQ.pdscrap, 0) - COALESCE(scrapCorrections.totalScrapCorrection, 0),
            2
        ) = 0
    )
    ORDER BY rawMaterial, batch
"""


@rm_correction_bp.route("/", methods=["GET"])
@require_any_access(["rm_correction", "rm_variance"])
def list_entries() -> Any:
    start_date_param = (request.args.get("startDate") or "").strip()
    is_valid = bool(re.match(r"^\d{4}-\d{2}-\d{2}$", start_date_param))

    if is_valid:
        sql = _LIST_SQL_TEMPLATE.format(start_expr="%s")
        params: tuple = (start_date_param,)
    else:
        sql = _LIST_SQL_TEMPLATE.format(start_expr="DATE_SUB(CURDATE(), INTERVAL 10 DAY)")
        params = ()

    try:
        rows = fetch_all(sql, params if params else None)
    except Exception as e:
        logger.exception("RM Correction list query error: %s", e)
        return jsonify({"error": "Database query failed", "details": str(e)}), 500

    entries = []
    for r in rows:
        entries.append(
            {
                "rawMaterial": r["rawMaterial"] or "",
                "batch": r["batch"],
                "rmid": int(r["rmid"] or 0),
                "totalInwarded": float(r["totalInwarded"] or 0),
                "rmGiven": float(r["rmGiven"] or 0),
                "rmRemaining": float(r["rmRemaining"] or 0),
                "scrap": float(r["scrap"] or 0),
            }
        )

    return jsonify({"count": len(entries), "entries": entries})
