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
LW_FG_NEXT_STAGES = (
    LW_FG_STAGE_ID,
    LW_FG_STAGE_ID + 100,
    LW_FG_STAGE_ID + 200,
    LW_FG_STAGE_ID + 300,
)
LW_WHITELIST_ERP_PLANT_ID = int(getattr(Config, "LW_WHITELIST_ERP_PLANT_ID", 2))
LW_WHITELIST_PART_INSPECTION_STAGE_ID = int(
    getattr(Config, "LW_WHITELIST_PART_INSPECTION_STAGE_ID", 19)
)
LW_WHITELIST_PART_INSPECTION_NEXT_STAGES = (
    LW_WHITELIST_PART_INSPECTION_STAGE_ID,
    LW_WHITELIST_PART_INSPECTION_STAGE_ID + 100,
    LW_WHITELIST_PART_INSPECTION_STAGE_ID + 200,
    LW_WHITELIST_PART_INSPECTION_STAGE_ID + 300,
)
LW_FG_STAGE_IDS = (
    LW_FG_STAGE_ID,
    LW_WHITELIST_PART_INSPECTION_STAGE_ID,
)
LW_PACKING_ERP_PLANT_ID = int(getattr(Config, "LW_PACKING_ERP_PLANT_ID", 2))
LW_PACKING_INWARD_STAGE_ID = int(getattr(Config, "LW_PACKING_INWARD_STAGE_ID", 6))
LW_WHITELIST_QA_OUTWARD_STAGE_ID = int(
    getattr(Config, "LW_WHITELIST_QA_OUTWARD_STAGE_ID", 6)
)
LW_WHITELIST_PACK_INWARD_OP_STAGE = int(
    getattr(Config, "LW_WHITELIST_PACK_INWARD_OP_STAGE", 19)
)
LW_WHITELIST_PACK_INWARD_NEXT_STAGE = int(
    getattr(Config, "LW_WHITELIST_PACK_INWARD_NEXT_STAGE", 6)
)
CT_SOURCE_STOCK_TRANSFER = int(getattr(Config, "LW_CT_SOURCE_STOCK_TRANSFER", 18))
CT_SOURCE_WHITELIST_REDUCE = int(getattr(Config, "LW_WHITELIST_CT_SOURCE_REDUCE", 1))
LW_WHITELIST_REDUCE_OP_STAGE = int(getattr(Config, "LW_WHITELIST_REDUCE_OP_STAGE", 1))
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
    *,
    next_stages: Optional[Sequence[int]] = None,
) -> List[Dict[str, Any]]:
    stages = tuple(next_stages or LW_FG_NEXT_STAGES)
    stage_placeholders = ", ".join(["%s"] * len(stages))
    sql = f"""
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
          AND CT_NEXTSTAGE IN ({stage_placeholders})
        GROUP BY CT_LOT_DC
        HAVING qty > 0
        ORDER BY CT_LOT_DC
    """
    params: Tuple[Any, ...] = (comp_id, plant_id, *stages)
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
    *,
    next_stages: Optional[Sequence[int]] = None,
) -> Dict[str, int]:
    return {
        row["lotNo"]: row["availableQty"]
        for row in fetch_lot_inventory(
            comp_id, plant_id, cursor, next_stages=next_stages
        )
    }


def validate_lot_lines(
    part_number: str,
    lines: Sequence[Dict[str, Any]],
    *,
    plant_id: int = LW_ERP_PLANT_ID,
    cursor: Any = None,
    next_stages: Optional[Sequence[int]] = None,
) -> None:
    comp_id = resolve_comp_id(part_number, cursor)
    inv = lot_inventory_map(
        comp_id, plant_id, cursor, next_stages=next_stages
    )
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
            raise ValueError(f"Lot {lot_no} has no available stock for part {part_number}")
        if insp > available:
            raise ValueError(
                f"Inspected QTY ({insp}) exceeds available stock ({available}) "
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
    op_stage: Optional[int] = None,
    next_stage: Optional[int] = None,
    ct_source: Optional[int] = None,
) -> None:
    """Insert outward comp_transaction row (CT_SOURCE 18 stock transfer or 9 FG segregation)."""
    if qty <= 0:
        return
    op = int(op_stage if op_stage is not None else stage_id)
    nxt = int(next_stage if next_stage is not None else stage_id)
    fg_flag = "Y" if op in LW_FG_STAGE_IDS else "N"
    source = int(ct_source if ct_source is not None else CT_SOURCE_STOCK_TRANSFER)
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
            op,
            nxt,
            fg_flag,
            source,
            lot_no,
            txn_time,
            uid,
            txn_time,
        ),
    )


def _insert_fg_segregation_outward(
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
    """FG segregation outward — CT_SOURCE=9, stage → stage, QA qty only."""
    _insert_outward_transaction(
        cursor,
        comp_id=comp_id,
        plant_id=plant_id,
        stage_id=stage_id,
        lot_no=lot_no,
        qty=qty,
        user_id=user_id,
        txn_time=txn_time,
        op_stage=stage_id,
        next_stage=stage_id,
        ct_source=CR_SRC_FG_SEGREGATION,
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
    """Outward stock transfer — comp_transaction (insp-qa), lotstock/stock (full insp)."""
    txn_time = _now()
    total_stock_qty = 0
    for line in lot_lines:
        lot_no = str(line.get("lotNo") or line.get("lot_no") or "").strip()
        stock_qty = int(line.get("qty") or 0)
        txn_qty = int(line.get("txnQty", stock_qty) or 0)
        if not lot_no or stock_qty <= 0:
            continue
        total_stock_qty += stock_qty
        if txn_qty > 0:
            _insert_outward_transaction(
                cursor,
                comp_id=comp_id,
                plant_id=plant_id,
                stage_id=stage_id,
                lot_no=lot_no,
                qty=txn_qty,
                user_id=user_id,
                txn_time=txn_time,
            )
        _update_lot_despatch(cursor, lot_no, stock_qty)

    if total_stock_qty <= 0:
        raise ValueError("No quantity to reduce from stock")

    _reduce_component_stock(cursor, comp_id, plant_id, stage_id, total_stock_qty)


def whitelist_reduce_stock(
    cursor: Any,
    comp_id: int,
    plant_id: int,
    lot_lines: Sequence[Dict[str, Any]],
    user_id: Optional[int] = None,
) -> None:
    """Whitelist inspect step 1 — txn (source 1, op 1→19) + comp_stock stage 19↓; no lotstock."""
    txn_time = _now()
    total_stock_qty = 0
    stock_stage = LW_WHITELIST_PART_INSPECTION_STAGE_ID
    for line in lot_lines:
        lot_no = str(line.get("lotNo") or line.get("lot_no") or "").strip()
        stock_qty = int(line.get("qty") or 0)
        if not lot_no or stock_qty <= 0:
            continue
        total_stock_qty += stock_qty
        _insert_outward_transaction(
            cursor,
            comp_id=comp_id,
            plant_id=plant_id,
            stage_id=stock_stage,
            lot_no=lot_no,
            qty=stock_qty,
            user_id=user_id,
            txn_time=txn_time,
            op_stage=LW_WHITELIST_REDUCE_OP_STAGE,
            next_stage=stock_stage,
            ct_source=CT_SOURCE_WHITELIST_REDUCE,
        )

    if total_stock_qty <= 0:
        raise ValueError("No quantity to reduce from stock")

    _reduce_component_stock(cursor, comp_id, plant_id, stock_stage, total_stock_qty)


def _insert_inward_transaction(
    cursor: Any,
    *,
    comp_id: int,
    plant_id: int,
    stage_id: int,
    lot_no: str,
    qty: int,
    user_id: Optional[int],
    txn_time: datetime,
    op_stage: Optional[int] = None,
    next_stage: Optional[int] = None,
) -> None:
    """Insert inward row — mirror of outward stock transfer (CT_MOVEMENT=I)."""
    if qty <= 0:
        return
    op = int(op_stage if op_stage is not None else stage_id)
    nxt = int(next_stage if next_stage is not None else stage_id)
    fg_flag = "Y" if op in LW_FG_STAGE_IDS else "N"
    uid = _user_id(user_id)
    cursor.execute(
        """
        INSERT INTO comp_transaction (
            CT_PLANTID, CT_COMPID, CT_MOVEMENT, CT_QTY,
            CT_OPSTAGE, CT_NEXTSTAGE, CT_FG, CT_SOURCE,
            CT_LOT_DC, CT_CDID, CT_PDID, CT_QAID,
            CT_DATE, CT_LASTUPDATEDBY, CT_LASTUPDATED
        ) VALUES (%s, %s, 'I', %s, %s, %s, %s, %s, %s, 0, 0, 0, %s, %s, %s)
        """,
        (
            plant_id,
            comp_id,
            qty,
            op,
            nxt,
            fg_flag,
            CT_SOURCE_STOCK_TRANSFER,
            lot_no,
            txn_time,
            uid,
            txn_time,
        ),
    )


def _update_lot_inward(cursor: Any, lot_no: str, qty: int) -> None:
    """Reverse despatch effect — return qty to lot availability."""
    if qty <= 0:
        return
    row = _lock_lot_stock(cursor, lot_no)
    despatch = int(row.get("CL_DESPATCH") or 0) - qty
    if despatch < 0:
        despatch = 0
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


def _increase_component_stock(
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
    cursor.execute(
        """
        UPDATE comp_stock SET CS_QTY = %s
        WHERE CS_COMPID = %s AND CS_PLANTID = %s AND CS_STAGEID = %s
        """,
        (current + qty, comp_id, plant_id, stage_id),
    )


def add_stock(
    cursor: Any,
    comp_id: int,
    plant_id: int,
    stage_id: int,
    lot_no: str,
    qty: int,
    user_id: Optional[int] = None,
) -> None:
    """Inward stock transfer — mirror of reduce_stock for packing whitelist parts."""
    lot_no = str(lot_no or "").strip()
    qty = int(qty or 0)
    if not lot_no or qty <= 0:
        raise ValueError("Lot number and quantity are required for inward stock")
    txn_time = _now()
    _insert_inward_transaction(
        cursor,
        comp_id=comp_id,
        plant_id=plant_id,
        stage_id=stage_id,
        lot_no=lot_no,
        qty=qty,
        user_id=user_id,
        txn_time=txn_time,
    )
    _update_lot_inward(cursor, lot_no, qty)
    _increase_component_stock(cursor, comp_id, plant_id, stage_id, qty)


def fg_segregate(
    cursor: Any,
    comp_id: int,
    plant_id: int,
    lot_no: str,
    qty: int,
    user_id: Optional[int] = None,
    *,
    stage_id: Optional[int] = None,
    update_lot_fg: bool = True,
) -> None:
    """FG Segregation — comp_transaction (source 9), reject row, optional CL_FG."""
    lot_no = str(lot_no or "").strip()
    qty = int(qty or 0)
    if not lot_no or qty <= 0:
        return

    txn_time = _now()
    effective_stage_id = int(stage_id if stage_id is not None else LW_FG_STAGE_ID)
    uid = _user_id(user_id)

    _insert_fg_segregation_outward(
        cursor,
        comp_id=comp_id,
        plant_id=plant_id,
        stage_id=effective_stage_id,
        lot_no=lot_no,
        qty=qty,
        user_id=user_id,
        txn_time=txn_time,
    )

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
            effective_stage_id,
            lot_no,
            effective_stage_id,
            qty,
            qty_kg,
            txn_time,
            uid,
            txn_time,
        ),
    )

    if update_lot_fg:
        cursor.execute(
            """
            SELECT CL_FG
            FROM comp_lotstock
            WHERE CL_LOTNO = %s
            FOR UPDATE
            """,
            (lot_no,),
        )
        row = cursor.fetchone()
        if row:
            cl_fg = int(row.get("CL_FG") or 0) - qty
            cursor.execute(
                "UPDATE comp_lotstock SET CL_FG = %s WHERE CL_LOTNO = %s",
                (cl_fg, lot_no),
            )


def whitelist_pack_inward(
    cursor: Any,
    comp_id: int,
    plant_id: int,
    lot_no: str,
    pack_qty: int,
    user_id: Optional[int] = None,
) -> None:
    """Whitelist pack — inward txn (op 19→6) + comp_stock stage 6↑ only."""
    lot_no = str(lot_no or "").strip()
    qty = int(pack_qty or 0)
    if not lot_no or qty <= 0:
        raise ValueError("Lot number and quantity are required for whitelist pack inward")
    op_stage = LW_WHITELIST_PACK_INWARD_OP_STAGE
    next_stage = LW_WHITELIST_PACK_INWARD_NEXT_STAGE
    stock_plant = LW_WHITELIST_ERP_PLANT_ID
    _insert_inward_transaction(
        cursor,
        comp_id=comp_id,
        plant_id=plant_id,
        stage_id=op_stage,
        lot_no=lot_no,
        qty=qty,
        user_id=user_id,
        txn_time=_now(),
        op_stage=op_stage,
        next_stage=next_stage,
    )
    _increase_component_stock(cursor, comp_id, stock_plant, next_stage, qty)
