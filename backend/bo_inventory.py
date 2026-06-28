"""BO sub-assembly parts — inventory stock (no ERP lot / no QA)."""

from __future__ import annotations

from typing import Any, Optional

from .db import fetch_all, fetch_one

SA_CATEGORY_CODE = "SA"
BO_CATEGORY_CODE = "BO"

_BO_UNDER_SA_SQL = """
    FROM bom_lin_item bl
    INNER JOIN bom b ON b.bom_id = bl.bom_id AND b.is_latest_version = 'Y'
    INNER JOIN bom_lin_item sa
        ON sa.bom_id = bl.bom_id
       AND sa.ITEM_ID = bl.PARENT_ITEM_ID
       AND UPPER(TRIM(sa.CATEGORY_CODE)) = %s
    WHERE UPPER(TRIM(bl.CATEGORY_CODE)) = %s
"""


def _normalize_part(part_no: Any) -> str:
    return str(part_no or "").strip()


def is_bo_sub_assembly_part(part_no: Any) -> bool:
    """True when part is a BO child of an SA sub-assembly on a latest-version BOM."""
    part = _normalize_part(part_no)
    if not part:
        return False
    row = fetch_one(
        f"""
        SELECT 1 AS ok
        {_BO_UNDER_SA_SQL}
          AND TRIM(bl.PART_NO) = %s
        LIMIT 1
        """,
        (SA_CATEGORY_CODE, BO_CATEGORY_CODE, part),
    )
    return bool(row)


def fetch_bo_parts_for_inspection() -> list[dict[str, Any]]:
    """BO parts under SA sub-assemblies that have inventory stock."""
    rows = fetch_all(
        f"""
        SELECT DISTINCT TRIM(bl.PART_NO) AS part_no, TRIM(bl.PART_NAME) AS part_name
        {_BO_UNDER_SA_SQL}
          AND EXISTS (
            SELECT 1 FROM inventory inv
            WHERE TRIM(inv.ITEM_CODE) = TRIM(bl.PART_NO) AND inv.QTY > 0
          )
        ORDER BY part_no
        """,
        (SA_CATEGORY_CODE, BO_CATEGORY_CODE),
    )
    return [
        {
            "part_no": str(r.get("part_no") or "").strip(),
            "part_name": str(r.get("part_name") or "").strip(),
        }
        for r in rows
        if str(r.get("part_no") or "").strip()
    ]


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
