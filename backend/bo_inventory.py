"""BO sub-assembly parts — inventory stock (no ERP lot / no QA)."""

from __future__ import annotations

from typing import Any, Optional

from .db import fetch_all, fetch_one

SUB_ASSEMBLY_PARENT_ITEM_ID = 2
BO_CATEGORY_CODE = "BO"


def _normalize_part(part_no: Any) -> str:
    return str(part_no or "").strip()


def is_bo_sub_assembly_part(part_no: Any) -> bool:
    """True when part is a BO sub-assembly child on a qualified BOM."""
    part = _normalize_part(part_no)
    if not part:
        return False
    row = fetch_one(
        """
        SELECT 1 AS ok
        FROM bom_lin_item bl
        INNER JOIN bom b ON b.bom_id = bl.bom_id AND b.is_latest_version = 'Y'
        WHERE TRIM(bl.PART_NO) = %s
          AND bl.PARENT_ITEM_ID = %s
          AND bl.CATEGORY_CODE = %s
          AND (
            SELECT COUNT(*) FROM bom_lin_item x
            WHERE x.bom_id = bl.bom_id AND x.PARENT_ITEM_ID = %s
          ) > 1
        LIMIT 1
        """,
        (part, SUB_ASSEMBLY_PARENT_ITEM_ID, BO_CATEGORY_CODE, SUB_ASSEMBLY_PARENT_ITEM_ID),
    )
    return bool(row)


def fetch_bo_available_qty(part_no: Any, cursor: Any = None) -> int:
    part = _normalize_part(part_no)
    if not part:
        return 0
    sql = """
        SELECT COALESCE(SUM(QTY), 0) AS qty
        FROM inventory
        WHERE TRIM(ITEM_CODE) = %s
    """
    if cursor is not None:
        cursor.execute(sql, (part,))
        row = cursor.fetchone()
    else:
        row = fetch_one(sql, (part,))
    return int((row or {}).get("qty") or 0)


def validate_bo_qty(part_no: Any, qty: int, cursor: Any = None) -> None:
    if qty <= 0:
        return
    available = fetch_bo_available_qty(part_no, cursor=cursor)
    part = _normalize_part(part_no)
    if qty > available:
        raise ValueError(
            f"Inspected QTY ({qty}) exceeds available inventory ({available}) for part {part}"
        )


def reduce_bo_inventory(cursor: Any, part_no: Any, qty: int) -> None:
    """Reduce inventory.QTY for a BO part; caller must hold a transaction."""
    part = _normalize_part(part_no)
    if not part:
        raise ValueError("Part number is required")
    if qty <= 0:
        return

    validate_bo_qty(part, qty, cursor=cursor)

    cursor.execute(
        """
        SELECT ITEM_CODE, QTY
        FROM inventory
        WHERE TRIM(ITEM_CODE) = %s AND QTY > 0
        FOR UPDATE
        """,
        (part,),
    )
    rows = cursor.fetchall() or []
    if not rows:
        raise ValueError(f"No inventory stock found for part {part}")

    remaining = qty
    for row in rows:
        if remaining <= 0:
            break
        available = int(row.get("QTY") or 0)
        if available <= 0:
            continue
        take = min(available, remaining)
        item_code = row.get("ITEM_CODE")
        cursor.execute(
            "UPDATE inventory SET QTY = QTY - %s WHERE TRIM(ITEM_CODE) = TRIM(%s) AND QTY >= %s",
            (take, item_code, take),
        )
        if cursor.rowcount <= 0:
            raise ValueError(f"Failed to reduce inventory for part {part}")
        remaining -= take

    if remaining > 0:
        raise ValueError(
            f"Insufficient inventory for part {part} — could not reduce {qty} units"
        )
