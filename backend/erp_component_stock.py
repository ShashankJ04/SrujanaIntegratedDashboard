"""ERP component stock helpers for Laser Welding child-parts inspect.

Mirrors ComponentServiceImpl.reduceStock() and FG segregation writes.
Validated against live comp_transaction rows where CT_SOURCE = 18.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import Config
from .db import fetch_all, fetch_one

LW_ERP_PLANT_ID = int(getattr(Config, "LW_ERP_PLANT_ID", 1))
LW_FG_STAGE_ID = int(getattr(Config, "LW_FG_STAGE_ID", 6))
LW_FG_NEXT_STAGES = (6, 106, 206, 306)
CT_SOURCE_STOCK_TRANSFER = int(getattr(Config, "LW_CT_SOURCE_STOCK_TRANSFER", 18))
CR_SRC_FG_SEGREGATION = int(getattr(Config, "LW_CR_SRC_FG_SEGREGATION", 9))


def _now() -> datetime:
    return datetime.now()


def _user_id(user_id: Optional[int]) -> int:
    return int(user_id) if user_id is not None else 0


def resolve_comp_id(part_number: str, cursor: Any = None) -> int:
    part = str(part_number or "").strip()
    if not part:
        raise ValueError("Part number is required")
    sql = """
        SELECT CO_ID AS comp_id
        FROM components
        WHERE TRIM(CO_PARTNO) = %s AND CO_ACTIVEYN = 'Y'
        LIMIT 1
    """
    if cursor is not None:
        cursor.execute(sql, (part,))
        row = cursor.fetchone()
    else:
        row = fetch_one(sql, (part,))
    if not row or not row.get("comp_id"):
        raise ValueError(
            f"No active component record for part {part!r} — "
            "ITEM_MASTER SS part must exist in components"
        )
    return int(row["comp_id"])


def fetch_lot_inventory(
    comp_id: int,
    plant_id: int = LW_ERP_PLANT_ID,
    cursor: Any = None,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            CT_LOT_DC AS lot_no,
            COALESCE(SUM(
                CASE
                    WHEN CT_MOVEMENT = 'I' THEN CT_QTY
                    WHEN CT_MOVEMENT = 'O' THEN -CT_QTY
                END
            ), 0) AS qty
        FROM comp_transaction
        WHERE CT_COMPID = %s
          AND CT_PLANTID = %s
          AND CT_NEXTSTAGE IN (6, 106, 206, 306)
        GROUP BY CT_LOT_DC
        HAVING qty > 0
        ORDER BY CT_LOT_DC
    """
    params: Tuple[Any, ...] = (comp_id, plant_id)
    if cursor is not None:
        cursor.execute(sql, params)
        rows = cursor.fetchall() or []
    else:
        rows = fetch_all(sql, params)
    return [
        {
            "lotNo": str(r.get("lot_no") or "").strip(),
            "availableQty": int(float(r.get("qty") or 0)),
        }
        for r in rows
        if str(r.get("lot_no") or "").strip()
    ]


def lot_inventory_map(
    comp_id: int,
    plant_id: int = LW_ERP_PLANT_ID,
    cursor: Any = None,
) -> Dict[str, int]:
    return {
        row["lotNo"]: row["availableQty"]
        for row in fetch_lot_inventory(comp_id, plant_id, cursor)
    }


def validate_lot_lines(
    part_number: str,
    lines: Sequence[Dict[str, Any]],
    *,
    plant_id: int = LW_ERP_PLANT_ID,
    cursor: Any = None,
) -> None:
    comp_id = resolve_comp_id(part_number, cursor)
    inv = lot_inventory_map(comp_id, plant_id, cursor)
    for line in lines:
        lot_no = str(
            line.get("sourceLotNo")
            or line.get("source_lot_no")
            or ""
        ).strip()
        if not lot_no:
            continue
        insp = int(line.get("inspectedQty") or line.get("inspected_qty") or 0)
        qa = int(line.get("qaQty") or line.get("qa_qty") or 0)
        if insp <= 0 and qa <= 0:
            continue
        available = inv.get(lot_no)
        if available is None:
            raise ValueError(f"Lot {lot_no} has no FG stock for part {part_number}")
        if insp > available:
            raise ValueError(
                f"Inspected QTY ({insp}) exceeds available FG stock ({available}) "
                f"for lot {lot_no}"
            )
        if qa > insp:
            raise ValueError(f"QA cannot exceed Inspected QTY for lot {lot_no}")


def _lock_lot_stock(cursor: Any, lot_no: str) -> Dict[str, Any]:
    cursor.execute(
        """
        SELECT *
        FROM comp_lotstock
        WHERE CL_LOTNO = %s
        FOR UPDATE
        """,
        (lot_no,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Lot stock record not found for lot {lot_no}")
    return row


def _lock_component_stock(
    cursor: Any,
    comp_id: int,
    plant_id: int,
    stage_id: int,
) -> Dict[str, Any]:
    cursor.execute(
        """
        SELECT *
        FROM comp_stock
        WHERE CS_COMPID = %s AND CS_PLANTID = %s AND CS_STAGEID = %s
        FOR UPDATE
        """,
        (comp_id, plant_id, stage_id),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(
            f"Component stock not found for comp_id={comp_id}, "
            f"plant={plant_id}, stage={stage_id}"
        )
    return row


def _insert_outward_transaction(
    cursor: Any,
    *,
    comp_id: int,
    plant_id: int,
    stage_id: int,
    lot_no: str,
    qty: int,
    user_id: Optional[int],
    txn_time: datetime,
) -> None:
    """Insert outward row matching Java saveComponentTransaction (CT_SOURCE=18)."""
    if qty <= 0:
        return
    fg_flag = "Y" if stage_id == LW_FG_STAGE_ID else "N"
    uid = _user_id(user_id)
    cursor.execute(
        """
        INSERT INTO comp_transaction (
            CT_PLANTID, CT_COMPID, CT_MOVEMENT, CT_QTY,
            CT_OPSTAGE, CT_NEXTSTAGE, CT_FG, CT_SOURCE,
            CT_LOT_DC, CT_CDID, CT_PDID, CT_QAID,
            CT_DATE, CT_LASTUPDATEDBY, CT_LASTUPDATED
        ) VALUES (%s, %s, 'O', %s, %s, %s, %s, %s, %s, 0, 0, 0, %s, %s, %s)
        """,
        (
            plant_id,
            comp_id,
            qty,
            stage_id,
            stage_id,
            fg_flag,
            CT_SOURCE_STOCK_TRANSFER,
            lot_no,
            txn_time,
            uid,
            txn_time,
        ),
    )


def _update_lot_despatch(cursor: Any, lot_no: str, qty: int) -> None:
    if qty <= 0:
        return
    row = _lock_lot_stock(cursor, lot_no)
    despatch = int(row.get("CL_DESPATCH") or 0) + qty
    production = int(row.get("CL_PRODUCTION") or 0)
    adjustment = int(row.get("CL_ADJUSTMENT") or 0)
    scrap = int(row.get("CL_SCRAP") or 0)
    total = (production + adjustment) - (scrap + despatch)
    if total < 0:
        total = 0
    cursor.execute(
        """
        UPDATE comp_lotstock SET
            CL_DESPATCH = %s,
            CL_TOTAL = %s
        WHERE CL_LOTNO = %s
        """,
        (despatch, total, lot_no),
    )


def _reduce_component_stock(
    cursor: Any,
    comp_id: int,
    plant_id: int,
    stage_id: int,
    qty: int,
) -> None:
    if qty <= 0:
        return
    row = _lock_component_stock(cursor, comp_id, plant_id, stage_id)
    current = int(float(row.get("CS_QTY") or 0))
    new_qty = current - qty
    if new_qty < 0:
        new_qty = 0
    cursor.execute(
        """
        UPDATE comp_stock SET CS_QTY = %s
        WHERE CS_COMPID = %s AND CS_PLANTID = %s AND CS_STAGEID = %s
        """,
        (new_qty, comp_id, plant_id, stage_id),
    )


def reduce_stock(
    cursor: Any,
    comp_id: int,
    plant_id: int,
    stage_id: int,
    lot_lines: Sequence[Dict[str, Any]],
    user_id: Optional[int] = None,
) -> None:
    """Outward stock transfer — mirrors ComponentServiceImpl.reduceStock."""
    txn_time = _now()
    total_qty = 0
    for line in lot_lines:
        lot_no = str(line.get("lotNo") or line.get("lot_no") or "").strip()
        qty = int(line.get("qty") or 0)
        if not lot_no or qty <= 0:
            continue
        total_qty += qty
        _insert_outward_transaction(
            cursor,
            comp_id=comp_id,
            plant_id=plant_id,
            stage_id=stage_id,
            lot_no=lot_no,
            qty=qty,
            user_id=user_id,
            txn_time=txn_time,
        )
        _update_lot_despatch(cursor, lot_no, qty)

    if total_qty <= 0:
        raise ValueError("No quantity to reduce from stock")

    _reduce_component_stock(cursor, comp_id, plant_id, stage_id, total_qty)


def fg_segregate(
    cursor: Any,
    comp_id: int,
    plant_id: int,
    lot_no: str,
    qty: int,
    user_id: Optional[int] = None,
) -> None:
    """FG Segregation — QA pending reject row + CL_FG adjustment.

    Inspected QTY already includes QA, so reduce_stock posts the single outward
    movement for the full inspected amount. FG segregation only records the QA
    subset in comp_rejectdetails and reduces CL_FG — no second transaction or
    comp_stock hit.
    """
    lot_no = str(lot_no or "").strip()
    qty = int(qty or 0)
    if not lot_no or qty <= 0:
        return

    txn_time = _now()
    stage_id = LW_FG_STAGE_ID
    uid = _user_id(user_id)

    cursor.execute(
        "SELECT CO_WEIGHT AS weight FROM components WHERE CO_ID = %s LIMIT 1",
        (comp_id,),
    )
    comp_row = cursor.fetchone() or {}
    weight = float(comp_row.get("weight") or 0)
    qty_kg = round(qty * weight, 4)

    cursor.execute(
        """
        INSERT INTO comp_rejectdetails (
            CR_PLANT, CR_SOURCE, CR_SRC, CR_PDID, CR_CMID, CR_QAID,
            CR_COMPID, CR_OPSTAGE, CR_LOTNO, CR_NEXTSTAGE,
            CR_QTY, CR_QTYKG, CR_STATUS, CR_DATE, CR_LASTUPDATEDBY, CR_LASTUPDATED
        ) VALUES (%s, 'F', %s, 0, 0, 0, %s, %s, %s, %s, %s, %s, 'P', %s, %s, %s)
        """,
        (
            plant_id,
            CR_SRC_FG_SEGREGATION,
            comp_id,
            stage_id,
            lot_no,
            stage_id,
            qty,
            qty_kg,
            txn_time,
            uid,
            txn_time,
        ),
    )

    row = _lock_lot_stock(cursor, lot_no)
    cl_fg = int(row.get("CL_FG") or 0) - qty
    cursor.execute(
        "UPDATE comp_lotstock SET CL_FG = %s WHERE CL_LOTNO = %s",
        (cl_fg, lot_no),
    )
