"""Component Stock — per-part ready, in-progress, and QA stock (Hub section)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .db import fetch_all, fetch_one


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def get_plant_options() -> List[Dict[str, Any]]:
    """Distinct ERP plant ids used by component-stock queries (same :plant as original reports)."""
    rows = fetch_all(
        """
        SELECT DISTINCT plant_id AS id
        FROM (
            SELECT CS_PLANTID AS plant_id
            FROM comp_stock
            WHERE CS_PLANTID IS NOT NULL AND CS_PLANTID > 0
            UNION
            SELECT CM_PLANT AS plant_id
            FROM comp_inwardmaster
            WHERE CM_PLANT IS NOT NULL AND CM_PLANT > 0
            UNION
            SELECT CM_DELIVERPLANT AS plant_id
            FROM comp_inwardmaster
            WHERE CM_DELIVERPLANT IS NOT NULL AND CM_DELIVERPLANT > 0
            UNION
            SELECT PS_PLANTID AS plant_id
            FROM scheduled_production
            WHERE PS_PLANTID IS NOT NULL AND PS_PLANTID > 0
        ) plants
        ORDER BY plant_id
        """
    )
    seen: set[int] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        pid = int(row.get("id") or 0)
        if pid <= 0 or pid in seen:
            continue
        seen.add(pid)
        out.append({"id": pid, "label": f"Unit {pid}"})
    # This deployment uses plant 1 / 2 as Unit 1 / Unit 2 (see LW_ERP_PLANT_ID config).
    for pid in (1, 2):
        if pid not in seen:
            out.append({"id": pid, "label": f"Unit {pid}"})
    out.sort(key=lambda p: int(p["id"]))
    return out


def search_parts(query: str, limit: int = 30) -> List[Dict[str, str]]:
    q = str(query or "").strip()
    limit = max(1, min(int(limit or 30), 100))
    if not q:
        rows = fetch_all(
            """
            SELECT DISTINCT TRIM(c.CO_PARTNO) AS part_no, TRIM(c.CO_PARTNAME) AS part_name
            FROM components c
            WHERE c.CO_ACTIVEYN = 'Y'
              AND c.CO_ID = c.CO_PARENTID
            ORDER BY part_no
            LIMIT %s
            """,
            (limit,),
        )
    else:
        like = f"%{q}%"
        rows = fetch_all(
            """
            SELECT DISTINCT TRIM(c.CO_PARTNO) AS part_no, TRIM(c.CO_PARTNAME) AS part_name
            FROM components c
            WHERE c.CO_ACTIVEYN = 'Y'
              AND c.CO_ID = c.CO_PARENTID
              AND (c.CO_PARTNO LIKE %s OR c.CO_PARTNAME LIKE %s)
            ORDER BY part_no
            LIMIT %s
            """,
            (like, like, limit),
        )
    return [
        {"partNo": str(r.get("part_no") or "").strip(), "partName": str(r.get("part_name") or "").strip()}
        for r in rows
        if str(r.get("part_no") or "").strip()
    ]


def _resolve_parent_component(part_no: str) -> Optional[Dict[str, Any]]:
    pno = str(part_no or "").strip()
    if not pno:
        return None
    row = fetch_one(
        """
        SELECT
            c.CO_ID AS comp_id,
            TRIM(c.CO_PARTNO) AS part_no,
            TRIM(c.CO_PARTNAME) AS part_name,
            COALESCE(mt.MT_Name, '') AS class_name
        FROM components c
        LEFT JOIN materialtypemaster mt ON mt.MT_Id = c.CO_MATERIALTYPEID
        WHERE c.CO_ACTIVEYN = 'Y'
          AND c.CO_ID = c.CO_PARENTID
          AND TRIM(c.CO_PARTNO) = %s
        LIMIT 1
        """,
        (pno,),
    )
    if not row:
        return None
    return {
        "compId": int(row["comp_id"]),
        "partNo": str(row.get("part_no") or "").strip(),
        "partName": str(row.get("part_name") or "").strip(),
        "className": str(row.get("class_name") or "").strip(),
    }


def _fetch_stages() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT OS_ID AS id, TRIM(OS_NAME) AS name
        FROM comp_opstages
        WHERE OS_ID IS NOT NULL
        ORDER BY OS_ID
        """
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        sid = int(row.get("id") or 0)
        name = str(row.get("name") or "").strip()
        if sid <= 0 or not name:
            continue
        out.append({"id": sid, "name": name})
    return out


def _stage_placeholders(stage_ids: Sequence[int]) -> str:
    return ", ".join(["%s"] * len(stage_ids))


def _fetch_ready_map(plant_id: int, comp_id: int, stage_ids: Sequence[int]) -> Dict[int, float]:
    if not stage_ids:
        return {}
    ph = _stage_placeholders(stage_ids)
    sql = f"""
        SELECT CS_STAGEID AS stage_id, SUM(CS_QTY) AS qty
        FROM comp_stock
        WHERE CS_PLANTID = %s
          AND CS_COMPID = %s
          AND CS_STAGEID IN ({ph})
        GROUP BY CS_STAGEID
    """
    rows = fetch_all(sql, (plant_id, comp_id, *stage_ids))
    return {int(r["stage_id"]): _to_float(r.get("qty")) for r in rows}


def _supplier_plant_clause() -> str:
    """
    Supplier in-progress is tied to the destination unit (CM_DELIVERPLANT).
    When deliver plant is unset (0), fall back to CM_PLANT — same outward row.
    """
    return "(CM_DELIVERPLANT = %s OR (CM_DELIVERPLANT = 0 AND CM_PLANT = %s))"


def _fetch_inprogress_for_stage(plant_id: int, comp_id: int, stage_id: int) -> Dict[str, float]:
    """
    Per-stage in-progress (ReportDaoImpl.getComponentStockListInProgress).

    - SUPPLIER  = outward to external supplier minus inward received (SupplierId != 0)
    - IN-HOUSE  = outward in-house minus production (SupplierId = 0, CM_PLANT)

    Supplier rows are scoped by CM_DELIVERPLANT (destination unit), not CM_PLANT alone,
    so Unit 1 / Unit 2 supplier WIP does not bleed across units.
    """
    plant_clause = _supplier_plant_clause()
    supplier_row = fetch_one(
        f"""
        SELECT
            COALESCE((
                SELECT SUM(CD_QTY)
                FROM comp_inwarddetails
                INNER JOIN comp_inwardmaster ON CD_CMID = CM_ID
                WHERE {plant_clause}
                  AND CD_COMPID = %s
                  AND CM_ReceivePlant = 0
                  AND CM_MOVEMENT = 'O'
                  AND CM_SupplierId != 0
                  AND cd_opstage = %s
            ), 0)
            - COALESCE((
                SELECT SUM(
                    CASE WHEN QD_Status = 'P' THEN CD_QTY ELSE QD_ReceivedQty END
                    + COALESCE(SD_QTY, 0) + COALESCE(CR_Qty, 0)
                )
                FROM comp_inwarddetails
                INNER JOIN comp_inwardmaster ON CD_CMID = CM_ID
                LEFT JOIN qa_details ON QD_CMID = CM_Id AND QD_CRID = 0
                LEFT JOIN comp_scrapdetails
                    ON SD_RefNo = CM_ID AND SD_SOURCE = 'S' AND CM_SupplierId != 0
                LEFT JOIN comp_rejectdetails
                    ON CR_CMID = CM_ID AND CR_Source = 'S' AND CR_Plant = CM_Plant
                WHERE {plant_clause}
                  AND CD_COMPID = %s
                  AND CM_MOVEMENT = 'I'
                  AND cd_opstage = %s
                  AND CD_Source = 'C'
                  AND CM_ReceivePlant = 0
            ), 0) AS supplier_qty
        """,
        (
            plant_id,
            plant_id,
            comp_id,
            stage_id,
            plant_id,
            plant_id,
            comp_id,
            stage_id,
        ),
    )
    inhouse_row = fetch_one(
        """
        SELECT COALESCE(SUM(CD_QTY) - COALESCE(SUM(c.qty), 0), 0) AS inhouse_qty
        FROM comp_inwarddetails
        INNER JOIN comp_inwardmaster ON CD_CMID = CM_ID
        LEFT JOIN (
            SELECT SUM(PD_ProdQty + PD_SWQty) AS qty, PD_CMID
            FROM production_details
            WHERE PD_PlantId = %s
            GROUP BY PD_CMID
        ) c ON c.PD_CMID = CD_CMID
        WHERE CM_PLANT = %s
          AND CD_COMPID = %s
          AND CM_ReceivePlant = 0
          AND CM_MOVEMENT = 'O'
          AND CM_SupplierId = 0
          AND cd_opstage = %s
        """,
        (plant_id, plant_id, comp_id, stage_id),
    )
    return {
        "inhouse": _to_float(inhouse_row.get("inhouse_qty") if inhouse_row else 0),
        "supplier": _to_float(supplier_row.get("supplier_qty") if supplier_row else 0),
    }


def _fetch_inprogress_map(plant_id: int, comp_id: int, stage_ids: Sequence[int]) -> Dict[int, Dict[str, float]]:
    """In-house vs supplier in-progress for every stage (ListInProgress per stage)."""
    out: Dict[int, Dict[str, float]] = {}
    for stage_id in stage_ids:
        out[int(stage_id)] = _fetch_inprogress_for_stage(plant_id, comp_id, int(stage_id))
    return out


def _fetch_qa_pending_split(plant_id: int, comp_id: int) -> Dict[str, float]:
    """
  QA PENDING split for With QA panel (matches Component Stock / dispatch calendar).

  - SUPPLIER  = pending QA on supplier inward (comp_inwardmaster + qa_details)
  - IN-HOUSE  = pending QA on production lots + reject QA (getQaPending other branches)
    """
    supplier_row = fetch_one(
        """
        SELECT COALESCE(SUM(QD_OFFEREDQTY), 0) AS qty
        FROM comp_inwardmaster
        INNER JOIN comp_inwarddetails ON CM_ID = CD_CMID
        INNER JOIN qa_details ON QD_CMID = CM_ID
        WHERE CM_PLANT = %s
          AND QD_STATUS = 'P'
          AND CD_COMPID = %s
          AND QD_CRID = 0
        """,
        (plant_id, comp_id),
    )
    inhouse_row = fetch_one(
        """
        SELECT COALESCE(SUM(t.cdQty), 0) AS qty
        FROM (
            SELECT COALESCE(SUM(QD_OFFEREDQTY), 0) AS cdQty
            FROM production_details
            INNER JOIN scheduled_production ON PS_ID = PD_PSID
            INNER JOIN qa_details ON QD_PDID = PD_ID
            WHERE PD_PLANTID = %s
              AND QD_STATUS = 'P'
              AND PS_PARENTCOMPID = %s
            UNION ALL
            SELECT COALESCE(SUM(COALESCE(t.qty, 0)), 0) AS cdQty
            FROM production_details
            INNER JOIN scheduled_production ON PS_ID = PD_PSID
            LEFT JOIN (
                SELECT PD_LOTNo AS lot, QD_OFFEREDQTY AS qty
                FROM qa_details
                INNER JOIN production_details ON QD_PDID = PD_ID
                WHERE QD_Status = 'P'
                  AND PD_PLANTID = %s
                  AND PD_Operation > 1
            ) t ON t.lot = PD_LOTNo
            WHERE PS_PARENTCOMPID = %s
              AND PD_Operation = 1
            UNION ALL
            SELECT COALESCE(SUM(QD_OFFEREDQTY), 0) AS cdQty
            FROM comp_rejectdetails
            INNER JOIN qa_details ON CR_ID = QD_CRID
            WHERE CR_PLANT = %s
              AND QD_STATUS = 'P'
              AND CR_COMPID = %s
        ) t
        """,
        (plant_id, comp_id, plant_id, comp_id, plant_id, comp_id),
    )
    return {
        "inhouse": _to_float(inhouse_row.get("qty") if inhouse_row else 0),
        "supplier": _to_float(supplier_row.get("qty") if supplier_row else 0),
    }


def _fetch_qa_breakdown(plant_id: int, comp_id: int) -> Dict[str, float]:
    row = fetch_one(
        """
        SELECT
            SUM(qa_pending) AS qa_pending,
            SUM(qa_disp_pending) AS qa_disp_pending,
            SUM(rw_pending) AS rw_pending,
            SUM(supplier_rw_inprogress) AS supplier_rw_inprogress,
            SUM(inhouse_rw_inprogress) AS inhouse_rw_inprogress
        FROM (
            SELECT CD_COMPID AS comp_id,
                   COALESCE(SUM(QD_OFFEREDQTY), 0) AS qa_pending,
                   0 AS qa_disp_pending,
                   0 AS rw_pending,
                   0 AS supplier_rw_inprogress,
                   0 AS inhouse_rw_inprogress
            FROM comp_inwardmaster
            INNER JOIN comp_inwarddetails ON CM_ID = CD_CMID
            INNER JOIN qa_details ON QD_CMID = CM_ID
            WHERE CM_PLANT = %s
              AND QD_STATUS = 'P'
              AND QD_CRID = 0
              AND CD_COMPID = %s
            GROUP BY CD_COMPID
            UNION ALL
            SELECT PS_PARENTCOMPID AS comp_id,
                   COALESCE(SUM(QD_OFFEREDQTY), 0) AS qa_pending,
                   0 AS qa_disp_pending,
                   0 AS rw_pending,
                   0 AS supplier_rw_inprogress,
                   0 AS inhouse_rw_inprogress
            FROM scheduled_production
            INNER JOIN production_details ON ps_id = pd_psid
            INNER JOIN qa_details ON pd_id = qd_pdid
            WHERE pd_plantid = %s
              AND QD_STATUS = 'P'
              AND QD_CRID = 0
              AND PS_PARENTCOMPID = %s
            GROUP BY PS_PARENTCOMPID
            UNION ALL
            SELECT CR_COMPID AS comp_id,
                   0 AS qa_pending,
                   COALESCE(SUM(CR_QTY), 0) AS qa_disp_pending,
                   0 AS rw_pending,
                   0 AS supplier_rw_inprogress,
                   0 AS inhouse_rw_inprogress
            FROM comp_rejectdetails
            WHERE CR_PLANT = %s
              AND CR_COMPID = %s
              AND CR_STATUS = 'P'
            GROUP BY CR_COMPID
            UNION ALL
            SELECT CR_COMPID AS comp_id,
                   0 AS qa_pending,
                   0 AS qa_disp_pending,
                   COALESCE(SUM(CR_QTY - COALESCE(t.rdQty, 0)), 0) AS rw_pending,
                   0 AS supplier_rw_inprogress,
                   0 AS inhouse_rw_inprogress
            FROM comp_rejectdetails
            LEFT JOIN (
                SELECT RD_CRID AS crId, SUM(RD_QTY) AS rdQty
                FROM comp_rejinvdetails
                INNER JOIN comp_rejinvmaster ON RD_RJID = RJ_ID
                INNER JOIN comp_rejectdetails ON CR_ID = RD_CRID
                WHERE RJ_MOVEMENT = 'O'
                  AND CR_PLANT = %s
                  AND CR_COMPID = %s
                  AND CR_STATUS = 'R'
                GROUP BY RD_CRID
            ) t ON t.crId = CR_ID
            WHERE CR_PLANT = %s
              AND CR_COMPID = %s
              AND CR_STATUS = 'R'
            GROUP BY CR_COMPID
            UNION ALL
            SELECT CR_COMPID AS comp_id,
                   0 AS qa_pending,
                   0 AS qa_disp_pending,
                   0 AS rw_pending,
                   COALESCE(SUM(RD_QTY - COALESCE(t.crQty, 0)), 0) AS supplier_rw_inprogress,
                   0 AS inhouse_rw_inprogress
            FROM comp_rejectdetails
            INNER JOIN comp_rejinvdetails ON RD_CRID = CR_ID
            INNER JOIN comp_rejinvmaster ON RD_RJID = RJ_ID
            LEFT JOIN (
                SELECT
                    COALESCE(SUM(
                        CASE WHEN RJ_InspectionYN = 'Y' THEN QD_ReceivedQty ELSE RD_QTY END
                        + COALESCE(SD_Qty, 0)
                        + COALESCE(c1.CR_Qty, 0)
                    ), 0) AS crQty,
                    RD_OUTWARDID AS outwardId
                FROM comp_rejectdetails c
                INNER JOIN comp_rejinvdetails ON RD_CRID = CR_ID
                INNER JOIN comp_rejinvmaster ON RD_RJID = RJ_ID
                LEFT JOIN qa_details ON QD_CMID = RJ_ID AND QD_CRID = RD_CRID
                LEFT JOIN comp_scrapdetails ON SD_RefNo = RJ_ID AND SD_Source IN ('SR', 'PR', 'HR')
                LEFT JOIN comp_rejectdetails c1
                    ON c1.CR_COMPID = c.CR_COMPID
                   AND c1.CR_SOURCE = 'SR'
                   AND c1.CR_PLANT = %s
                   AND c1.CR_CMID = RJ_ID
                WHERE c.CR_PLANT = %s
                  AND RJ_MOVEMENT = 'I'
                  AND RJ_SupplierId != 0
                  AND c.CR_COMPID = %s
                GROUP BY RD_OUTWARDID
            ) t ON t.outwardId = RD_ID
            WHERE CR_PLANT = %s
              AND CR_COMPID = %s
              AND RJ_MOVEMENT = 'O'
              AND RJ_SupplierId != 0
              AND CR_STATUS IN ('R', 'RC')
            GROUP BY CR_COMPID
            UNION ALL
            SELECT CR_COMPID AS comp_id,
                   0 AS qa_pending,
                   0 AS qa_disp_pending,
                   0 AS rw_pending,
                   0 AS supplier_rw_inprogress,
                   COALESCE(SUM(RD_QTY - COALESCE(t.crQty, 0)), 0) AS inhouse_rw_inprogress
            FROM comp_rejectdetails
            INNER JOIN comp_rejinvdetails ON RD_CRID = CR_ID
            INNER JOIN comp_rejinvmaster ON RD_RJID = RJ_ID
            LEFT JOIN (
                SELECT
                    RD_OUTWARDID AS outwardId,
                    SUM(
                        CASE WHEN RJ_InspectionYN = 'Y' THEN QD_ReceivedQty ELSE RD_QTY END
                        + COALESCE(SD_Qty, 0)
                        + COALESCE(c1.CR_Qty, 0)
                    ) AS crQty
                FROM comp_rejectdetails c
                INNER JOIN comp_rejinvdetails ON RD_CRID = CR_ID
                INNER JOIN comp_rejinvmaster ON RD_RJID = RJ_ID
                LEFT JOIN qa_details ON QD_CMID = RJ_ID AND QD_CRID = RD_CRID
                LEFT JOIN comp_scrapdetails ON SD_RefNo = RJ_ID AND SD_Source IN ('SR', 'PR', 'HR')
                LEFT JOIN comp_rejectdetails c1
                    ON c1.CR_COMPID = c.CR_COMPID
                   AND c1.CR_SOURCE = 'SR'
                   AND c1.CR_PLANT = %s
                   AND c1.CR_CMID = RJ_ID
                WHERE c.CR_PLANT = %s
                  AND RJ_MOVEMENT = 'I'
                  AND RJ_SupplierId = 0
                  AND c.CR_COMPID = %s
                GROUP BY RD_OUTWARDID
            ) t ON t.outwardId = RD_ID
            WHERE CR_PLANT = %s
              AND CR_COMPID = %s
              AND RJ_MOVEMENT = 'O'
              AND RJ_SupplierId = 0
              AND CR_STATUS IN ('R', 'RC')
            GROUP BY CR_COMPID
        ) combined
        """,
        (
            plant_id, comp_id,
            plant_id, comp_id,
            plant_id, comp_id,
            plant_id, comp_id, plant_id, comp_id,
            plant_id, plant_id, comp_id, plant_id, comp_id,
            plant_id, plant_id, comp_id, plant_id, comp_id,
        ),
    )
    if not row:
        return {
            "qaDispPending": 0.0,
            "rwPending": 0.0,
            "supplierRwInprogress": 0.0,
            "inhouseRwInprogress": 0.0,
        }
    return {
        "qaDispPending": _to_float(row.get("qa_disp_pending")),
        "rwPending": _to_float(row.get("rw_pending")),
        "supplierRwInprogress": _to_float(row.get("supplier_rw_inprogress")),
        "inhouseRwInprogress": _to_float(row.get("inhouse_rw_inprogress")),
    }


def build_component_stock_payload(plant_id: int, part_no: str) -> Dict[str, Any]:
    if plant_id <= 0:
        raise ValueError("plantId is required")
    part_meta = _resolve_parent_component(part_no)
    if not part_meta:
        raise ValueError("Part not found")

    comp_id = int(part_meta["compId"])
    stages = _fetch_stages()
    stage_ids = [s["id"] for s in stages]

    ready_map = _fetch_ready_map(plant_id, comp_id, stage_ids)
    inprogress_map = _fetch_inprogress_map(plant_id, comp_id, stage_ids)
    qa_pending = _fetch_qa_pending_split(plant_id, comp_id)
    qa_breakdown = _fetch_qa_breakdown(plant_id, comp_id)

    ready_rows: List[Dict[str, Any]] = []
    ready_total = 0.0
    for idx, stage in enumerate(stages, start=1):
        stock = ready_map.get(stage["id"], 0.0)
        ready_total += stock
        ready_rows.append({
            "slNo": idx,
            "stage": stage["name"],
            "stock": stock,
        })

    inprogress_rows: List[Dict[str, Any]] = []
    inprogress_total = 0.0
    for idx, stage in enumerate(stages, start=1):
        ip = inprogress_map.get(stage["id"], {"inhouse": 0.0, "supplier": 0.0})
        inhouse = ip["inhouse"]
        supplier = ip["supplier"]
        inprogress_total += inhouse + supplier
        inprogress_rows.append({
            "slNo": idx,
            "stage": f"{stage['name']} In-Progress",
            "inhouse": inhouse,
            "supplier": supplier,
        })

    qa_rows = [
        {
            "stage": "QA PENDING",
            "inhouse": qa_pending["inhouse"],
            "supplier": qa_pending["supplier"],
        },
        {
            "stage": "QA DISPOSITION PENDING",
            "inhouse": qa_breakdown["qaDispPending"],
            "supplier": 0.0,
        },
        {
            "stage": "REWORK PENDING",
            "inhouse": qa_breakdown["rwPending"],
            "supplier": 0.0,
        },
        {
            "stage": "REWORK IN-PROGRESS",
            "inhouse": qa_breakdown["inhouseRwInprogress"],
            "supplier": qa_breakdown["supplierRwInprogress"],
        },
    ]
    qa_total = sum(r["inhouse"] + r["supplier"] for r in qa_rows)

    return {
        "plantId": plant_id,
        "partNo": part_meta["partNo"],
        "partName": part_meta["partName"],
        "className": part_meta["className"],
        "grossTotal": ready_total + inprogress_total + qa_total,
        "ready": {
            "total": ready_total,
            "rows": ready_rows,
        },
        "inProgress": {
            "total": inprogress_total,
            "rows": inprogress_rows,
        },
        "qa": {
            "total": qa_total,
            "rows": qa_rows,
        },
    }
