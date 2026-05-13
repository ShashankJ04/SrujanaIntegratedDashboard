"""RM Correction API Blueprint.

Port of dashboards/backend/src/routes/rmCorrection.ts.
Provides stock-adjustment candidates with RM remaining and scrap,
plus batch production detail drill-down, correction submission,
and correction history.
"""

from __future__ import annotations

import math
import re

from flask import Blueprint, g, jsonify, request

from .auth import api_login_required
from .rbac import require_any_access
from .db import fetch_all, execute

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

    # Full query matching legacy rmCorrection.ts GET /
    # Key differences from the partial port:
    #   1. Selects rmid (prodRM.rd_rmid)
    #   2. TRIM on batch for consistent matching
    #   3. Subtracts rm_prodcorrection totals from RM Remaining
    #   4. Subtracts rm_scrapcorrection totals from Scrap
    #   5. Adds ct_id = PD_TOOLID join condition in prodQ subquery
    sql = f"""
        SELECT
            COALESCE(prodQ.MM_RawMtPartNo, '') AS rawMaterial,
            TRIM(prodRM.batch) AS batch,
            prodRM.rd_rmid AS rmid,
            ROUND(COALESCE(inwardTotals.totalInwarded, 0), 2) AS totalInwarded,
            ROUND(COALESCE(prodRM.RMGiven, 0), 2) AS rmGiven,

            ROUND(
              COALESCE((prodRM.RMGiven - prodQ.ThRMForProduction), 0) -
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
                ) AS RMGiven
            FROM rm_inwarddetails
            JOIN rm_inwardmaster ON rd_riid = ri_id
            WHERE RI_MOVEMENTTYPE = 3
            GROUP BY RD_BATCHNO, rd_rmid
        ) prodRM
        JOIN (
            SELECT DISTINCT PD_BATCHNO AS batch
            FROM production_details
            WHERE DATE(PD_DATE) >= COALESCE({start_date_expr}, DATE_SUB(CURDATE(), INTERVAL 10 DAY))
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
              COALESCE((prodRM.RMGiven - prodQ.ThRMForProduction), 0) -
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

    try:
        rows = fetch_all(sql, params if params else None)
    except Exception as e:
        return jsonify({"error": "Database query failed", "details": str(e)}), 500

    entries = []
    for r in rows:
        entries.append({
            "rawMaterial": r["rawMaterial"] or "",
            "batch": r["batch"],
            "rmid": int(r["rmid"] or 0),
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


# ── POST /submit — submit RM and/or Scrap corrections ───────────────────

@rm_correction_bp.route("/submit", methods=["POST"])
@require_any_access(["rm_correction", "rm_variance"])
def submit_corrections():
    """Port of rmCorrection.ts POST /submit.

    Accepts { items: [ { batch, rmid, theoRmRemaining?, actualRm?, rmRemarks?,
                          scrapBefore?, actualScrap?, scrapRemarks? }, ... ] }
    and inserts into rm_prodcorrection / rm_scrapcorrection.
    """
    user = g.current_user
    user_id = user.get("userId", 0)

    body = request.get_json(silent=True) or {}
    raw_items = body.get("items", [])

    if not isinstance(raw_items, list):
        return jsonify({"error": "items must be an array"}), 400

    # Filter to items that have at least one actual value
    def _has_correction(item):
        try:
            ar = float(item.get("actualRm", ""))
            if ar == ar:  # not NaN
                return True
        except (ValueError, TypeError):
            pass
        try:
            asc = float(item.get("actualScrap", ""))
            if asc == asc:
                return True
        except (ValueError, TypeError):
            pass
        return False

    items = [i for i in raw_items if isinstance(i, dict) and _has_correction(i)]

    if len(items) == 0:
        return jsonify({"error": "No rows with Actual RM or Actual Scrap provided"}), 400

    try:
        inserted_rm = 0
        inserted_scrap = 0

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

            # RM correction
            has_rm = False
            try:
                actual_rm = float(item.get("actualRm", ""))
                has_rm = math.isfinite(actual_rm)
            except (ValueError, TypeError):
                pass

            if has_rm:
                remarks = str(item.get("rmRemarks", "")).strip()
                try:
                    theo_rm_remaining = float(item.get("theoRmRemaining", ""))
                    if not math.isfinite(theo_rm_remaining):
                        raise ValueError()
                except (ValueError, TypeError):
                    return jsonify({"error": "Invalid RM correction payload"}), 400

                if not remarks:
                    return jsonify({"error": "Invalid RM correction payload"}), 400
                if len(remarks) > 50:
                    return jsonify({"error": "RM Remarks cannot exceed 50 characters"}), 400

                correction = round(theo_rm_remaining - actual_rm, 2)

                execute(
                    """
                    INSERT INTO rm_prodcorrection
                      (rc_batchno, rc_rmid, rc_theo, rc_correction, rc_remarks, rc_createddt, rc_userid)
                    VALUES
                      (%s, %s, %s, %s, %s, NOW(), %s)
                    """,
                    (batch, rmid, theo_rm_remaining, correction, remarks, user_id),
                )
                inserted_rm += 1

            # Scrap correction
            has_scrap = False
            try:
                actual_scrap = float(item.get("actualScrap", ""))
                has_scrap = math.isfinite(actual_scrap)
            except (ValueError, TypeError):
                pass

            if has_scrap:
                try:
                    scrap_before = float(item.get("scrapBefore", ""))
                    if not math.isfinite(scrap_before):
                        raise ValueError()
                except (ValueError, TypeError):
                    return jsonify({"error": "Invalid Scrap correction payload"}), 400

                scrap_remarks = str(item.get("scrapRemarks", "")).strip()
                if not scrap_remarks:
                    return jsonify({"error": "Invalid Scrap correction payload"}), 400
                if len(scrap_remarks) > 50:
                    return jsonify({"error": "Scrap Remarks cannot exceed 50 characters"}), 400

                scrap_correction = round(scrap_before - actual_scrap, 2)

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

        return jsonify({
            "inserted": inserted_rm + inserted_scrap,
            "insertedRm": inserted_rm,
            "insertedScrap": inserted_scrap,
        })

    except Exception as e:
        return jsonify({
            "message": "Database insert failed",
            "error": "Database insert failed",
            "details": str(e),
        }), 500


# ── GET /history/<batch>/<rmid> — correction history ────────────────────

@rm_correction_bp.route("/history/<batch>/<int:rmid>", methods=["GET"])
@require_any_access(["rm_correction", "rm_variance"])
def correction_history(batch, rmid):
    """Port of rmCorrection.ts GET /history/:batch/:rmid.

    Returns UNION of rm_prodcorrection (type='RM') and
    rm_scrapcorrection (type='SCRAP', movementtype='P') entries.
    """
    batch = (batch or "").strip()
    if not batch:
        return jsonify({"error": "Valid batch and RM id are required"}), 400

    try:
        rows = fetch_all(
            """
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
            """,
            (batch, rmid, batch, rmid),
        )
    except Exception as e:
        return jsonify({"error": "Database query failed", "details": str(e)}), 500

    entries = []
    for r in rows:
        entries.append({
            "type": r["type"],
            "qtyBefore": float(r["qtyBefore"] or 0),
            "correction": float(r["correction"] or 0),
            "remarks": r["remarks"] or "",
            "createdAt": r["createdAt"] or "",
            "userLogin": r["userLogin"] or "",
        })

    return jsonify({"count": len(entries), "entries": entries})
