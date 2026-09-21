"""Non-Returnable DC Stock — per-part Srujana stock, transit, and supplier stock."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .db import fetch_all, fetch_one


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def search_nr_parts(query: str, limit: int = 30) -> List[Dict[str, str]]:
    """Search parts that have at least one NR DC outward record."""
    q = str(query or "").strip()
    limit = max(1, min(int(limit or 30), 100))
    if not q:
        rows = fetch_all(
            """
            SELECT DISTINCT TRIM(c.CO_PARTNO) AS part_no, TRIM(c.CO_PARTNAME) AS part_name
            FROM components c
            INNER JOIN nrcomp_outwardmaster m ON m.NRC_COID = c.CO_ID
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
            INNER JOIN nrcomp_outwardmaster m ON m.NRC_COID = c.CO_ID
            WHERE c.CO_ACTIVEYN = 'Y'
              AND c.CO_ID = c.CO_PARENTID
              AND (c.CO_PARTNO LIKE %s OR c.CO_PARTNAME LIKE %s)
            ORDER BY part_no
            LIMIT %s
            """,
            (like, like, limit),
        )
    return [
        {
            "partNo": str(r.get("part_no") or "").strip(),
            "partName": str(r.get("part_name") or "").strip(),
        }
        for r in rows
        if str(r.get("part_no") or "").strip()
    ]


def _resolve_component(part_no: str) -> Optional[Dict[str, Any]]:
    """Find the parent component by part number."""
    pno = str(part_no or "").strip()
    if not pno:
        return None
    row = fetch_one(
        """
        SELECT
            c.CO_ID AS comp_id,
            TRIM(c.CO_PARTNO) AS part_no,
            TRIM(c.CO_PARTNAME) AS part_name
        FROM components c
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
    }


def _fetch_srujana_stock(comp_id: int) -> int:
    """Total current stock in Srujana (supplier ID = 0) across all stages."""
    row = fetch_one(
        """
        SELECT COALESCE(SUM(CS_QTY), 0) AS total
        FROM comp_stock
        WHERE CS_COMPID = %s AND CS_SUPPLIERID = 0
        """,
        (comp_id,),
    )
    return _to_int(row.get("total")) if row else 0


def _fetch_transit(comp_id: int) -> List[Dict[str, Any]]:
    """
    In-transit quantities: outward DCs where qty has not been fully received.

    Transit = outward (O) sent_qty minus any received qty from the matching
    inward (I, linked via NRC_OUTWARDID).  Rows with zero or negative
    difference are excluded.
    """
    rows = fetch_all(
        """
        SELECT
            o.NRC_ID,
            TRIM(ds.ss_Name)  AS from_supplier,
            TRIM(dls.ss_Name) AS to_supplier,
            os.OS_NAME        AS purpose,
            SUM(d.NRD_QTY)    AS sent_qty,
            COALESCE((
                SELECT SUM(id.NRD_RECEIVEDQTY)
                FROM nrcomp_outwardmaster im
                JOIN nrcomp_outwarddetails id ON id.NRD_NRCID = im.NRC_ID
                WHERE im.NRC_OUTWARDID = o.NRC_ID
                  AND im.NRC_MOVEMENT   = 'I'
            ), 0) AS received_qty
        FROM nrcomp_outwardmaster o
        JOIN nrcomp_outwarddetails d   ON d.NRD_NRCID = o.NRC_ID
        LEFT JOIN comp_opstages os     ON os.OS_ID     = o.NRC_OPSTAGE
        LEFT JOIN supplier ds          ON ds.ss_Id     = o.NRC_DISPATCHSUPPLIER
        LEFT JOIN supplier dls         ON dls.ss_Id    = o.NRC_DELIVERSUPPLIER
        WHERE o.NRC_COID     = %s
          AND o.NRC_MOVEMENT = 'O'
        GROUP BY o.NRC_ID, ds.ss_Name, dls.ss_Name, os.OS_NAME
        HAVING sent_qty - received_qty > 0
        ORDER BY o.NRC_ID
        """,
        (comp_id,),
    )
    return [
        {
            "from": str(r.get("from_supplier") or "").strip(),
            "to": str(r.get("to_supplier") or "").strip(),
            "qty": _to_int(r.get("sent_qty")) - _to_int(r.get("received_qty")),
            "purpose": str(r.get("purpose") or "").strip(),
        }
        for r in rows
    ]


def _fetch_supplier_stock(comp_id: int) -> List[Dict[str, Any]]:
    """
    Stock held at external suppliers (CS_SUPPLIERID > 0) with qty > 0.

    Each row = supplier + stage combination.
    """
    rows = fetch_all(
        """
        SELECT
            TRIM(s.ss_Name) AS supplier_name,
            cs.CS_QTY       AS qty,
            os.OS_NAME      AS stage_name
        FROM comp_stock cs
        LEFT JOIN supplier s       ON s.ss_Id  = cs.CS_SUPPLIERID
        LEFT JOIN comp_opstages os ON os.OS_ID  = cs.CS_STAGEID
        WHERE cs.CS_COMPID      = %s
          AND cs.CS_SUPPLIERID  > 0
          AND cs.CS_QTY         > 0
        ORDER BY s.ss_Name, os.OS_NAME
        """,
        (comp_id,),
    )
    return [
        {
            "supplier": str(r.get("supplier_name") or "").strip(),
            "qty": _to_int(r.get("qty")),
            "readyForStage": str(r.get("stage_name") or "").strip(),
        }
        for r in rows
    ]


def build_nr_dc_payload(part_no: str) -> Dict[str, Any]:
    """Build the full NR DC Stock payload for a given part number."""
    comp = _resolve_component(part_no)
    if not comp:
        raise ValueError(f"Part number '{part_no}' not found.")

    comp_id = comp["compId"]

    in_srujana = _fetch_srujana_stock(comp_id)
    transit = _fetch_transit(comp_id)
    suppliers = _fetch_supplier_stock(comp_id)

    return {
        "partNo": comp["partNo"],
        "partName": comp["partName"],
        "inSrujana": in_srujana,
        "transit": transit,
        "suppliers": suppliers,
    }
