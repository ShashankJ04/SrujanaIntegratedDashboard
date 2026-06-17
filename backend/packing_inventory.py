"""ERP inventory upsert for laser-welding BOM packing."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from .db import fetch_one


def _normalize_part(part_no: Any) -> str:
    return str(part_no or "").strip()


def _lookup_item_master(cursor: Any, item_code: str) -> dict:
    cursor.execute(
        """
        SELECT TRIM(ITEM_CODE) AS item_code,
               TRIM(ITEM_NAME) AS item_name,
               TRIM(COALESCE(UOM, '')) AS uom,
               TRIM(COALESCE(CATEGORY_CODE, '')) AS category_code
        FROM ITEM_MASTER
        WHERE TRIM(ITEM_CODE) = %s
        LIMIT 1
        """,
        (item_code,),
    )
    return cursor.fetchone() or {}


def add_inventory_qty(
    cursor: Any,
    item_code: str,
    qty: int,
    *,
    item_name: str = "",
    uom: str = "",
    plant_id: Optional[int] = 1,
    cust_id: Optional[int] = None,
    category_code: str = "",
    revision: Any = None,
) -> None:
    """Add packed qty to ERP inventory for a BOM (ITEM_CODE = bom_no)."""
    code = _normalize_part(item_code)
    if not code:
        raise ValueError("ITEM_CODE is required for inventory update")
    if qty <= 0:
        raise ValueError("Pack quantity must be greater than 0")

    cursor.execute(
        """
        SELECT INVENTORY_ID, ITEM_CODE, QTY
        FROM inventory
        WHERE TRIM(ITEM_CODE) = %s
        ORDER BY INVENTORY_ID
        LIMIT 1
        FOR UPDATE
        """,
        (code,),
    )
    existing = cursor.fetchone()
    if existing:
        cursor.execute(
            "UPDATE inventory SET QTY = QTY + %s WHERE INVENTORY_ID = %s",
            (qty, existing["INVENTORY_ID"]),
        )
        return

    im = _lookup_item_master(cursor, code)
    name = item_name or im.get("item_name") or code
    unit = uom or im.get("uom") or "NOS"
    category = category_code or im.get("category_code") or ""
    inv_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO inventory (
            INVENTORY_ID, ITEM_CODE, ITEM_NAME, QTY, UOM,
            CUST_ID, CATEGORY_CODE, REVISION, PLANT_ID
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            inv_id,
            code,
            name,
            float(qty),
            unit,
            cust_id,
            category or None,
            revision,
            plant_id,
        ),
    )


def resolve_bom_inventory_meta(bom_id: str, cursor: Any = None) -> dict:
    """BOM metadata for new inventory rows."""
    bid = str(bom_id or "").strip()
    if not bid:
        return {}
    sql = """
        SELECT b.bom_no, b.product_name, b.cust_id, b.VERSION_NO
        FROM bom b
        WHERE b.bom_id = %s AND b.is_latest_version = 'Y'
        LIMIT 1
    """
    if cursor is not None:
        cursor.execute(sql, (bid,))
        row = cursor.fetchone()
    else:
        row = fetch_one(sql, (bid,))
    if not row:
        return {}
    return {
        "item_code": str(row.get("bom_no") or "").strip(),
        "item_name": str(row.get("product_name") or "").strip(),
        "cust_id": int(row["cust_id"]) if row.get("cust_id") is not None else None,
        "revision": row.get("VERSION_NO"),
    }
