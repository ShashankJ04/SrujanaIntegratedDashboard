"""RM Variance API Blueprint.

Port of dashboards/backend/src/routes/rmVariance.ts.
Exact copy of the original SQL query with correct table names.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from .auth import api_login_required
from .rbac import require_access
from .db import fetch_all

rm_variance_bp = Blueprint("rm_variance_bp", __name__, url_prefix="/api/rm-variance")


@rm_variance_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


# ── GET /<month>/<year>/<plant_id> — RM variance report ─────────────────

@rm_variance_bp.route("/<int:month>/<int:year>/<int:plant_id>", methods=["GET"])
@require_access("rm_variance")
def rm_variance(month, year, plant_id):
    try:
        rows = fetch_all(
            """
            SELECT
                co.CO_PARTNO AS partno,
                mm.MM_RawMtPartNo AS RM,
                ct.CT_TOOLNO AS tool,
                COALESCE(cust.custReqQty, 0) AS custReqQty,
                SUM(sp.PS_QTY) AS schQty,
                SUM(sp.PS_QTYKG) AS schKg,
                COALESCE(prd.prodQty, 0) AS prodQty,
                COALESCE(u.usedQty, 0) AS usedQty,
                COALESCE(prd.prodQty, 0) / cV.conVal AS theoKg
            FROM schedule_master sm
            JOIN schedule_details sd ON sd.SC_SMID = sm.SM_ID
            JOIN components co ON sd.SC_COMPID = co.CO_ID
            JOIN scheduled_production sp
                ON sp.PS_SMID = sm.SM_ID
                AND sp.PS_PARENTCOMPID = co.CO_ID
            JOIN components_tool ct ON sp.PS_TOOLID = ct.CT_ID
            JOIN materialmaster mm ON ct.CT_RMID = mm.MM_ID AND ct.CT_COMPID = co.CO_ID
            LEFT JOIN (
                SELECT CS_SCID, CS_PLANTID, SUM(CS_QTY) AS custReqQty
                FROM scheduled_customer
                GROUP BY CS_SCID, CS_PLANTID
            ) cust ON cust.CS_SCID = sd.SC_ID AND cust.CS_PLANTID = sp.PS_PLANTID
            LEFT JOIN (
                SELECT sp2.PS_PARENTCOMPID, sp2.PS_SMID, sp2.PS_PLANTID,
                    SUM(pd.PD_PRODQTY) AS prodQty
                FROM production_details pd
                JOIN scheduled_production sp2 ON pd.PD_PSID = sp2.PS_ID
                GROUP BY sp2.PS_PARENTCOMPID, sp2.PS_SMID, sp2.PS_PLANTID
            ) prd ON prd.PS_PARENTCOMPID = co.CO_ID
                AND prd.PS_SMID = sm.SM_ID
                AND prd.PS_PLANTID = sp.PS_PLANTID
            LEFT JOIN (
                SELECT rd.rd_rmid, rd.rd_compid, rd.rd_smid, ri.RI_ISSUEPLANT,
                    SUM(CASE WHEN ri.RI_MOVEMENT = 'O' THEN rd.RD_ACCEPTEDQTY ELSE 0 END) -
                    SUM(CASE WHEN ri.RI_MOVEMENT = 'I' THEN rd.RD_ACCEPTEDQTY ELSE 0 END) AS usedQty
                FROM rm_inwarddetails rd
                JOIN rm_inwardmaster ri ON ri.RI_ID = rd.RD_RIID
                WHERE ri.RI_MOVEMENTTYPE = 3
                GROUP BY rd.rd_rmid, rd.rd_compid, rd.rd_smid, ri.RI_ISSUEPLANT
            ) u ON u.rd_rmid = ct.CT_RMID
                AND u.rd_compid = co.CO_ID
                AND u.rd_smid = sm.SM_ID
                AND u.RI_ISSUEPLANT = sp.PS_PLANTID
            JOIN (
                SELECT CT_COMPID, CT_ID AS ctid,
                    ((1 / ((MT_Density * MM_Thickness) * MM_StripWidth)) * ((1000 * CT_NO_OF_CAVITY) / CT_Pitch)) AS conVal
                FROM components_tool
                INNER JOIN materialmaster ON CT_RMID = MM_Id
                INNER JOIN materialtypemaster ON MM_MTID = MT_Id
                WHERE CT_ActiveYN = 'Y' AND CT_PPC = 'Y' AND CT_PITCH > 0 AND CT_NO_OF_CAVITY > 0
            ) cV ON cV.CT_COMPID = co.CO_ID AND ct.CT_ID = cV.ctid
            WHERE sm.SM_YEAR = %s
                AND sm.SM_MONTH = %s
                AND sp.PS_PLANTID = %s
            GROUP BY co.CO_PARTNO, mm.MM_RawMtPartNo, ct.CT_TOOLNO,
                cust.custReqQty, prd.prodQty, u.usedQty, cV.conVal
            ORDER BY co.CO_PARTNO, mm.MM_RawMtPartNo, ct.CT_TOOLNO
            """,
            (year, month, plant_id),
        )

        entries = []
        totals = {
            "custReqQty": 0,
            "schQty": 0,
            "schKg": 0.0,
            "prodQty": 0,
            "usedQty": 0.0,
            "theoKg": 0.0,
            "variance": 0.0,
        }

        for r in rows:
            used = float(r["usedQty"] or 0)
            theo = float(r["theoKg"] or 0)
            variance = used - theo
            variance_pct = ((used / theo) * 100 - 100) if theo != 0 else 0

            entry = {
                "partno": r["partno"] or "",
                "rm": r["RM"] or "",
                "tool": r["tool"] or "",
                "custReqQty": int(r["custReqQty"] or 0),
                "schQty": int(r["schQty"] or 0),
                "schKg": float(r["schKg"] or 0),
                "prodQty": int(r["prodQty"] or 0),
                "usedQty": used,
                "theoKg": theo,
                "variance": variance,
                "variancePer": variance_pct,
            }
            entries.append(entry)

            totals["custReqQty"] += entry["custReqQty"]
            totals["schQty"] += entry["schQty"]
            totals["schKg"] += entry["schKg"]
            totals["prodQty"] += entry["prodQty"]
            totals["usedQty"] += entry["usedQty"]
            totals["theoKg"] += entry["theoKg"]
            totals["variance"] += entry["variance"]

        return jsonify({
            "month": month,
            "year": year,
            "plantId": plant_id,
            "count": len(entries),
            "totals": totals,
            "entries": entries,
        })

    except Exception as e:
        return jsonify({"error": "Database query failed", "details": str(e)}), 500
