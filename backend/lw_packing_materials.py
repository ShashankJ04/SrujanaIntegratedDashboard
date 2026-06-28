"""Tray/carton nomenclature, ITEM_MASTER inserts, and part mappings for laser welding packing."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple

from .db import execute, fetch_all, fetch_one, get_cursor

MATERIAL_LEGEND: List[Dict[str, Any]] = [
    {"digit": 1, "label": "PET"},
    {"digit": 2, "label": "HIPS"},
    {"digit": 3, "label": "PVC"},
    {"digit": 4, "label": "LDPE"},
    {"digit": 5, "label": "PP"},
    {"digit": 6, "label": "PS"},
    {"digit": 7, "label": "OTHER"},
]

DEFAULT_MATERIAL_DIGIT = 1

_TRAY_CODE_RE = re.compile(r"^SE-(\d)-((?:\d+P|S))-(\d+)C-(\d+)$")
_CARTON_CODE_RE = re.compile(r"^SE-C-(\d{3})(\d{3})(\d{3})$")
_BIN_CODE_RE = re.compile(r"^SE-B-(\d{3})(\d{3})(\d{3})-(\d+)$")


def _norm_part(part: Any) -> str:
    return str(part or "").strip().replace("\xa0", "")


def get_legend() -> Dict[str, Any]:
    return {
        "defaultMaterialDigit": DEFAULT_MATERIAL_DIGIT,
        "trayTypeModes": [
            {"mode": "S", "label": "Single (S)"},
            {"mode": "P", "label": "Multiple parts (nP)"},
        ],
        "boxTypeModes": [
            {"mode": "C", "label": "Carton (SE-C)"},
            {"mode": "B", "label": "Bin (SE-B)"},
        ],
        "trayPattern": "SE-{material}-{type}-{cavity}C-{seq}",
        "cartonPattern": "SE-C-{LLL}{WWW}{HHH}",
        "binPattern": "SE-B-{LLL}{WWW}{HHH}-{seq}",
        "customerBinDefaults": {"ATHER": 1, "REML": 2},
    }


def normalize_tray_type(type_mode: str, no_parts: Optional[int] = None) -> str:
    mode = str(type_mode or "S").strip().upper()
    if mode == "S":
        return "S"
    if mode in ("P", "M", "MULTI", "MULTIPLE"):
        n = int(no_parts or 0)
        if n < 2:
            raise ValueError("No. parts must be at least 2 for Multiple (P)")
        return f"{n}P"
    ttype = mode
    if ttype == "S" or re.fullmatch(r"\d+P", ttype):
        return ttype
    raise ValueError("Tray type must be Single (S) or Multiple (P)")


def _box_kind_from_type(box_type: str) -> str:
    k = str(box_type or "C").strip().upper()
    if k in ("B", "BIN"):
        return "bin"
    return "carton"


def _customer_name(cust_id: Optional[int]) -> str:
    if cust_id is None:
        return ""
    row = fetch_one(
        "SELECT TRIM(CU_Name) AS n FROM customer WHERE CU_Id = %s LIMIT 1",
        (int(cust_id),),
    )
    return str((row or {}).get("n") or "")


def default_bin_seq_for_customer(cust_id: Optional[int]) -> Optional[int]:
    name = _customer_name(cust_id).upper()
    if "ATHER" in name:
        return 1
    if "REML" in name:
        return 2
    return None


_MAP_SELECT_SQL = """
    SELECT m.*,
           COALESCE(TRIM(comp.CO_PARTNO), TRIM(b.bom_no), '') AS part_number,
           COALESCE(TRIM(comp.CO_PARTNAME), TRIM(b.product_name), '') AS part_name,
           COALESCE(cu.CU_Name, '') AS customer_name,
           t.cavity AS tray_cavity_attr,
           t.type AS tray_type_attr
    FROM lw_packing_part_map m
    LEFT JOIN components comp ON comp.CO_ID = m.co_id
    LEFT JOIN bom b ON b.bom_id = m.bom_id AND b.is_latest_version = 'Y'
    LEFT JOIN customer cu ON cu.CU_Id = m.cust_id
    LEFT JOIN lw_packing_tray t ON TRIM(t.tray_item_code) = TRIM(m.tray_item_code)
"""


def list_matching_trays(
    cust_id: Optional[int],
    tray_type: str,
    cavity: int,
) -> List[Dict[str, Any]]:
    ttype = str(tray_type or "").strip().upper()
    cav = int(cavity)
    if not ttype or cav <= 0:
        return []
    sql = """
        SELECT tray_item_code, type, cavity, material, cust_id
        FROM lw_packing_tray
        WHERE type = %s AND cavity = %s
    """
    params: List[Any] = [ttype, cav]
    if cust_id is not None:
        sql += " AND cust_id = %s"
        params.append(int(cust_id))
    sql += " ORDER BY tray_item_code"
    rows = fetch_all(sql, tuple(params))
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get("tray_item_code") or "")
        seq = None
        m = _TRAY_CODE_RE.match(code)
        if m:
            seq = int(m.group(4))
        out.append({
            "itemCode": code,
            "trayType": r.get("type") or "",
            "cavity": int(r["cavity"]) if r.get("cavity") is not None else None,
            "seq": seq,
        })
    return out


def list_matching_boxes(
    cust_id: Optional[int],
    box_type: str,
    length_mm: int,
    width_mm: int,
    height_mm: int,
) -> List[Dict[str, Any]]:
    """Cartons are shared by dimensions — return all matching codes (not customer-scoped)."""
    del cust_id  # kept for API compatibility
    kind = _box_kind_from_type(box_type)
    l, w, h = int(length_mm), int(width_mm), int(height_mm)
    if l <= 0 or w <= 0 or h <= 0:
        return []
    sql = """
        SELECT c.carton_item_code, c.length_mm, c.width_mm, c.height_mm
        FROM lw_packing_carton c
        WHERE c.length_mm = %s AND c.width_mm = %s AND c.height_mm = %s
    """
    params: List[Any] = [l, w, h]
    if kind == "bin":
        sql += " AND c.carton_item_code LIKE 'SE-B-%'"
    else:
        sql += " AND c.carton_item_code LIKE 'SE-C-%'"
    sql += " ORDER BY c.carton_item_code"
    rows = fetch_all(sql, tuple(params))
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get("carton_item_code") or "")
        bin_seq = None
        if kind == "bin":
            m = _BIN_CODE_RE.match(code)
            if m:
                bin_seq = int(m.group(4))
        out.append({
            "itemCode": code,
            "kind": kind,
            "lengthMm": int(r["length_mm"]),
            "widthMm": int(r["width_mm"]),
            "heightMm": int(r["height_mm"]),
            "binSeq": bin_seq,
        })
    return out


def generate_tray_code(
    material_digit: int,
    tray_type: str,
    cavity: int,
    seq: Optional[int] = None,
    *,
    cursor: Any = None,
) -> str:
    m = int(material_digit)
    if m < 1 or m > 7:
        raise ValueError("Material digit must be 1–7")
    ttype = str(tray_type or "").strip().upper()
    if ttype != "S" and not re.fullmatch(r"\d+P", ttype):
        raise ValueError("Tray type must be S or nP (e.g. 2P, 4P)")
    cav = int(cavity)
    if cav <= 0:
        raise ValueError("Tray cavity must be greater than 0")
    base = f"SE-{m}-{ttype}-{cav}C"
    if seq is not None:
        return f"{base}-{int(seq)}"
    next_seq = _next_tray_seq(base, cursor=cursor)
    return f"{base}-{next_seq}"


def _next_tray_seq(base: str, *, cursor: Any = None) -> int:
    pattern = f"{base}-%"
    sql = """
        SELECT tray_item_code FROM lw_packing_tray
        WHERE tray_item_code LIKE %s
    """
    if cursor is not None:
        cursor.execute(sql, (pattern,))
        rows = cursor.fetchall() or []
    else:
        rows = fetch_all(sql, (pattern,))
    max_seq = 0
    for r in rows:
        m = _TRAY_CODE_RE.match(str(r.get("tray_item_code") or ""))
        if m:
            max_seq = max(max_seq, int(m.group(4)))
    return max_seq + 1


def generate_box_code(
    kind: str,
    length_mm: int,
    width_mm: int,
    height_mm: int,
    bin_seq: Optional[int] = None,
    *,
    cursor: Any = None,
) -> str:
    k = str(kind or "").strip().lower()
    if k not in ("carton", "bin"):
        raise ValueError("Box kind must be carton or bin")
    l, w, h = int(length_mm), int(width_mm), int(height_mm)
    for label, val in (("length", l), ("width", w), ("height", h)):
        if val < 0 or val > 999:
            raise ValueError(f"{label} must be 0–999 mm")
    dims = f"{l:03d}{w:03d}{h:03d}"
    if k == "carton":
        return f"SE-C-{dims}"
    seq = int(bin_seq) if bin_seq is not None else _next_bin_seq(dims, cursor=cursor)
    return f"SE-B-{dims}-{seq}"


def _next_bin_seq(dims: str, *, cursor: Any = None) -> int:
    pattern = f"SE-B-{dims}-%"
    sql = """
        SELECT carton_item_code FROM lw_packing_carton
        WHERE carton_item_code LIKE %s
    """
    if cursor is not None:
        cursor.execute(sql, (pattern,))
        rows = cursor.fetchall() or []
    else:
        rows = fetch_all(sql, (pattern,))
    max_seq = 0
    for r in rows:
        m = _BIN_CODE_RE.match(str(r.get("carton_item_code") or ""))
        if m:
            max_seq = max(max_seq, int(m.group(4)))
    return max_seq + 1


def parse_tray_code(item_code: str) -> Dict[str, Any]:
    m = _TRAY_CODE_RE.match(_norm_part(item_code))
    if not m:
        raise ValueError(f"Invalid tray code: {item_code}")
    return {
        "materialDigit": int(m.group(1)),
        "trayType": m.group(2),
        "cavity": int(m.group(3)),
        "seq": int(m.group(4)),
    }


def parse_box_code(item_code: str) -> Dict[str, Any]:
    code = _norm_part(item_code)
    m = _CARTON_CODE_RE.match(code)
    if m:
        return {
            "kind": "carton",
            "lengthMm": int(m.group(1)),
            "widthMm": int(m.group(2)),
            "heightMm": int(m.group(3)),
            "binSeq": None,
        }
    m = _BIN_CODE_RE.match(code)
    if m:
        return {
            "kind": "bin",
            "lengthMm": int(m.group(1)),
            "widthMm": int(m.group(2)),
            "heightMm": int(m.group(3)),
            "binSeq": int(m.group(4)),
        }
    raise ValueError(f"Invalid carton/bin code: {item_code}")


def preview_tray(attrs: Dict[str, Any]) -> Dict[str, Any]:
    existing = _norm_part(attrs.get("existingItemCode") or attrs.get("existing_item_code"))
    if existing:
        return {"itemCode": existing, "kind": "tray", "reused": True}

    type_mode = str(attrs.get("typeMode") or attrs.get("type_mode") or "S").upper()
    no_parts = attrs.get("noParts") if attrs.get("noParts") is not None else attrs.get("no_parts")
    tray_type = str(attrs.get("trayType") or attrs.get("tray_type") or "").strip().upper()
    if not tray_type:
        tray_type = normalize_tray_type(type_mode, int(no_parts) if no_parts is not None else None)

    material_digit = int(attrs.get("materialDigit") or attrs.get("material_digit") or DEFAULT_MATERIAL_DIGIT)
    cavity = int(attrs.get("cavity") or 0)
    seq = attrs.get("seq")
    cust_id = attrs.get("custId") or attrs.get("cust_id")
    cust_id = int(cust_id) if cust_id is not None and str(cust_id).strip() != "" else None

    if type_mode == "S":
        seq = None

    code = generate_tray_code(material_digit, tray_type, cavity, seq)
    try:
        options = list_matching_trays(cust_id, tray_type, cavity) if type_mode == "P" else []
    except Exception:
        options = []
    return {"itemCode": code, "kind": "tray", "existingOptions": options}


def preview_box(attrs: Dict[str, Any]) -> Dict[str, Any]:
    existing = _norm_part(attrs.get("existingItemCode") or attrs.get("existing_item_code"))
    if existing:
        parsed = parse_box_code(existing)
        return {"itemCode": existing, "kind": parsed["kind"], "reused": True}

    box_type = attrs.get("boxType") or attrs.get("box_type") or "C"
    if str(box_type).strip().lower() in ("box",):
        box_type = "C"
    kind = _box_kind_from_type(str(box_type))
    length_mm = int(attrs.get("lengthMm") or attrs.get("length_mm") or 0)
    width_mm = int(attrs.get("widthMm") or attrs.get("width_mm") or 0)
    height_mm = int(attrs.get("heightMm") or attrs.get("height_mm") or 0)
    cust_id = attrs.get("custId") or attrs.get("cust_id")
    cust_id = int(cust_id) if cust_id is not None and str(cust_id).strip() != "" else None

    bin_seq = attrs.get("binSeq") or attrs.get("bin_seq")
    if kind == "bin" and bin_seq is None:
        bin_seq = default_bin_seq_for_customer(cust_id)

    code = generate_box_code(kind, length_mm, width_mm, height_mm, bin_seq)
    try:
        options = list_matching_boxes(cust_id, box_type, length_mm, width_mm, height_mm)
    except Exception:
        options = []
    return {"itemCode": code, "kind": kind, "binSeq": bin_seq, "existingOptions": options}


def _item_master_exists(cursor: Any, item_code: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = %s LIMIT 1",
        (item_code,),
    )
    return bool(cursor.fetchone())


def _insert_item_master(
    cursor: Any,
    item_code: str,
    *,
    kind: str,
    cust_id: Optional[int],
) -> None:
    code = _norm_part(item_code)
    if not code:
        raise ValueError("ITEM_CODE is required")
    if _item_master_exists(cursor, code):
        return
    item_name = "Tray" if kind == "tray" else "Carton"
    master_id = str(uuid.uuid4())
    today = date.today()
    cursor.execute(
        """
        INSERT INTO ITEM_MASTER (
            ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID,
            CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            master_id,
            code,
            item_name,
            int(cust_id) if cust_id is not None else None,
            "BO",
            "1",
            "NOS",
            today,
        ),
    )


def ensure_inventory_row(cursor: Any, item_code: str, *, cust_id: Optional[int] = None) -> None:
    code = _norm_part(item_code)
    if not code:
        return
    cursor.execute(
        """
        SELECT INVENTORY_ID FROM inventory
        WHERE TRIM(ITEM_CODE) = %s
        ORDER BY INVENTORY_ID LIMIT 1
        FOR UPDATE
        """,
        (code,),
    )
    if cursor.fetchone():
        return
    cursor.execute(
        "SELECT TRIM(ITEM_NAME) AS n FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = %s LIMIT 1",
        (code,),
    )
    im = cursor.fetchone() or {}
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
            im.get("n") or code,
            0.0,
            "NOS",
            cust_id,
            "BO",
            "1",
            1,
        ),
    )


def _tray_row_exists(item_code: str, *, cursor: Any = None) -> bool:
    sql = "SELECT 1 FROM lw_packing_tray WHERE TRIM(tray_item_code) = %s LIMIT 1"
    if cursor is not None:
        cursor.execute(sql, (item_code,))
        return bool(cursor.fetchone())
    return bool(fetch_one(sql, (item_code,)))


def _carton_row_exists(item_code: str, *, cursor: Any = None) -> bool:
    sql = "SELECT 1 FROM lw_packing_carton WHERE TRIM(carton_item_code) = %s LIMIT 1"
    if cursor is not None:
        cursor.execute(sql, (item_code,))
        return bool(cursor.fetchone())
    return bool(fetch_one(sql, (item_code,)))


def _packing_code_exists(item_code: str, *, cursor: Any = None) -> bool:
    return _tray_row_exists(item_code, cursor=cursor) or _carton_row_exists(item_code, cursor=cursor)


def _upsert_tray_row(
    cursor: Any,
    *,
    item_code: str,
    material: int,
    tray_type: str,
    cavity: int,
    cust_id: Optional[int],
    created_by: Optional[int],
) -> None:
    code = _norm_part(item_code)
    if _tray_row_exists(code, cursor=cursor):
        return
    cursor.execute(
        """
        INSERT INTO lw_packing_tray (
            tray_item_code, material, type, cavity, cust_id, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (code, int(material), str(tray_type), int(cavity), cust_id, created_by),
    )


def _upsert_carton_row(
    cursor: Any,
    *,
    item_code: str,
    length_mm: int,
    width_mm: int,
    height_mm: int,
    created_by: Optional[int],
) -> None:
    code = _norm_part(item_code)
    if _carton_row_exists(code, cursor=cursor):
        return
    cursor.execute(
        """
        INSERT INTO lw_packing_carton (
            carton_item_code, length_mm, width_mm, height_mm, created_by
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (code, int(length_mm), int(width_mm), int(height_mm), created_by),
    )


def _resolve_bom_row(
    part_number: str,
    *,
    cust_id: Optional[int] = None,
    bom_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    if bid:
        return fetch_one(
            """
            SELECT bom_id, bom_no, product_name, cust_id
            FROM bom
            WHERE bom_id = %s AND is_latest_version = 'Y'
            LIMIT 1
            """,
            (bid,),
        )
    part = _norm_part(part_number)
    if not part:
        return None
    sql = """
        SELECT bom_id, bom_no, product_name, cust_id
        FROM bom
        WHERE is_latest_version = 'Y' AND TRIM(bom_no) = %s
    """
    params: List[Any] = [part]
    if cust_id is not None:
        sql += " AND cust_id = %s"
        params.append(int(cust_id))
    sql += " ORDER BY cust_id LIMIT 1"
    return fetch_one(sql, tuple(params))


def resolve_co_id(
    part_number: str,
    *,
    cust_id: Optional[int] = None,
    bom_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve ERP component id for a part, preferring customer-scoped matches."""
    part = _norm_part(part_number)
    if not part and not bom_id:
        return None

    bom_row = _resolve_bom_row(part, cust_id=cust_id, bom_id=bom_id)
    if bom_row:
        part = _norm_part(bom_row.get("bom_no") or part)
        if cust_id is None and bom_row.get("cust_id") is not None:
            cust_id = int(bom_row["cust_id"])
    cid = int(cust_id) if cust_id is not None else None
    bid = str(bom_row.get("bom_id")) if bom_row and bom_row.get("bom_id") else (
        str(bom_id).strip() if bom_id else None
    )

    def _hit(
        row: Dict[str, Any],
        *,
        out_cust: Optional[int] = None,
        out_bom: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "coId": int(row["co_id"]),
            "partNumber": row.get("part_no") or part,
            "partName": row.get("part_name") or "",
            "custId": out_cust if out_cust is not None else (
                int(row["cust_id"]) if row.get("cust_id") is not None else cid
            ),
            "bomId": out_bom or bid,
        }

    if cid is not None and part:
        row = fetch_one(
            """
            SELECT c.CO_ID AS co_id, TRIM(c.CO_PARTNO) AS part_no,
                   TRIM(c.CO_PARTNAME) AS part_name, c.CO_CUSTID AS cust_id
            FROM components c
            WHERE TRIM(c.CO_PARTNO) = %s AND c.CO_ACTIVEYN = 'Y' AND c.CO_CUSTID = %s
            ORDER BY c.CO_ID DESC
            LIMIT 1
            """,
            (part, cid),
        )
        if row:
            return _hit(row, out_cust=cid)

        row = fetch_one(
            """
            SELECT c.CO_ID AS co_id, TRIM(c.CO_PARTNO) AS part_no,
                   TRIM(c.CO_PARTNAME) AS part_name, p.CO_CUSTID AS cust_id
            FROM components c
            INNER JOIN components p ON p.CO_ID = c.CO_PARENTID AND p.CO_ACTIVEYN = 'Y'
            WHERE TRIM(c.CO_PARTNO) = %s AND c.CO_ACTIVEYN = 'Y' AND p.CO_CUSTID = %s
            ORDER BY c.CO_ID DESC
            LIMIT 1
            """,
            (part, cid),
        )
        if row:
            return _hit(row, out_cust=cid)

        row = fetch_one(
            """
            SELECT c.CO_ID AS co_id, TRIM(c.CO_PARTNO) AS part_no,
                   TRIM(c.CO_PARTNAME) AS part_name, b.cust_id, b.bom_id
            FROM components c
            INNER JOIN bom b ON b.is_latest_version = 'Y'
                AND TRIM(b.bom_no) = TRIM(c.CO_PARTNO) AND b.cust_id = %s
            WHERE TRIM(c.CO_PARTNO) = %s AND c.CO_ACTIVEYN = 'Y'
            ORDER BY c.CO_ID DESC
            LIMIT 1
            """,
            (cid, part),
        )
        if row:
            return _hit(
                row,
                out_cust=cid,
                out_bom=str(row.get("bom_id")) if row.get("bom_id") else bid,
            )

        row = fetch_one(
            """
            SELECT c.CO_ID AS co_id, TRIM(c.CO_PARTNO) AS part_no,
                   TRIM(c.CO_PARTNAME) AS part_name, b.cust_id, b.bom_id
            FROM bom b
            INNER JOIN components c ON TRIM(c.CO_PARTNO) = TRIM(b.bom_no)
            WHERE b.is_latest_version = 'Y' AND TRIM(b.bom_no) = %s AND b.cust_id = %s
            ORDER BY CASE WHEN c.CO_ACTIVEYN = 'Y' THEN 0 ELSE 1 END, c.CO_ID DESC
            LIMIT 1
            """,
            (part, cid),
        )
        if row:
            return _hit(
                row,
                out_cust=cid,
                out_bom=str(row.get("bom_id")) if row.get("bom_id") else bid,
            )

    if part:
        row = fetch_one(
            """
            SELECT CO_ID AS co_id, TRIM(CO_PARTNO) AS part_no,
                   TRIM(CO_PARTNAME) AS part_name, CO_CUSTID AS cust_id
            FROM components
            WHERE TRIM(CO_PARTNO) = %s AND CO_ACTIVEYN = 'Y'
            ORDER BY CO_ID DESC
            LIMIT 1
            """,
            (part,),
        )
        if row:
            return _hit(row)

    if bom_row:
        row = fetch_one(
            """
            SELECT CO_ID AS co_id, TRIM(CO_PARTNO) AS part_no,
                   TRIM(CO_PARTNAME) AS part_name
            FROM components
            WHERE TRIM(CO_PARTNO) = %s
            ORDER BY CASE WHEN CO_ACTIVEYN = 'Y' THEN 0 ELSE 1 END, CO_ID DESC
            LIMIT 1
            """,
            (_norm_part(bom_row.get("bom_no") or part),),
        )
        if row:
            return _hit(
                row,
                out_cust=int(bom_row["cust_id"]) if bom_row.get("cust_id") is not None else cid,
                out_bom=str(bom_row.get("bom_id")) if bom_row.get("bom_id") else None,
            )

    return None


def resolve_part_for_mapping(
    part_number: str,
    *,
    cust_id: Optional[int] = None,
    bom_id: Optional[str] = None,
    co_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve component and/or BOM identity for a trays/carton mapping."""
    if co_id:
        row = fetch_one(
            """
            SELECT CO_ID AS co_id, TRIM(CO_PARTNO) AS part_no,
                   TRIM(CO_PARTNAME) AS part_name, CO_CUSTID AS cust_id
            FROM components
            WHERE CO_ID = %s
            LIMIT 1
            """,
            (int(co_id),),
        )
        if row:
            return {
                "coId": int(row["co_id"]),
                "partNumber": row.get("part_no") or _norm_part(part_number),
                "partName": row.get("part_name") or "",
                "custId": int(cust_id) if cust_id is not None else (
                    int(row["cust_id"]) if row.get("cust_id") is not None else None
                ),
                "bomId": str(bom_id).strip() if bom_id else None,
            }

    resolved = resolve_co_id(part_number, cust_id=cust_id, bom_id=bom_id)
    if resolved:
        return resolved

    bom_row = _resolve_bom_row(part_number, cust_id=cust_id, bom_id=bom_id)
    if not bom_row:
        return None
    return {
        "coId": None,
        "bomId": str(bom_row["bom_id"]),
        "partNumber": _norm_part(bom_row.get("bom_no") or part_number),
        "partName": str(bom_row.get("product_name") or "").strip(),
        "custId": int(bom_row["cust_id"]) if bom_row.get("cust_id") is not None else (
            int(cust_id) if cust_id is not None else None
        ),
    }


def resolve_cust_id_by_name(company: str) -> Optional[int]:
    name = str(company or "").strip()
    if not name:
        return None
    row = fetch_one(
        "SELECT CU_Id AS cust_id FROM customer WHERE TRIM(CU_Name) = %s LIMIT 1",
        (name,),
    )
    if row and row.get("cust_id") is not None:
        return int(row["cust_id"])
    row = fetch_one(
        "SELECT CU_Id AS cust_id FROM customer WHERE TRIM(CU_Name) LIKE %s LIMIT 1",
        (f"%{name}%",),
    )
    return int(row["cust_id"]) if row and row.get("cust_id") is not None else None


def list_all_tray_entries() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT tray_item_code
        FROM lw_packing_tray
        ORDER BY tray_item_code
        """
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get("tray_item_code") or "").strip()
        if not code:
            continue
        entry = _material_entry(code, "tray")
        if entry:
            out.append(entry)
    return out


def list_all_carton_entries() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT carton_item_code
        FROM lw_packing_carton
        ORDER BY carton_item_code
        """
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get("carton_item_code") or "").strip()
        if not code:
            continue
        entry = _material_entry(code, "carton")
        if entry:
            out.append(entry)
    return out


def list_all_cartons() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT carton_item_code, length_mm, width_mm, height_mm
        FROM lw_packing_carton
        ORDER BY carton_item_code
        """
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r.get("carton_item_code") or "").strip()
        if not code:
            continue
        out.append({
            "itemCode": code,
            "lengthMm": int(r["length_mm"]) if r.get("length_mm") is not None else 0,
            "widthMm": int(r["width_mm"]) if r.get("width_mm") is not None else 0,
            "heightMm": int(r["height_mm"]) if r.get("height_mm") is not None else 0,
        })
    return out


def all_packing_material_codes() -> Set[str]:
    trays = fetch_all("SELECT tray_item_code FROM lw_packing_tray")
    cartons = fetch_all("SELECT carton_item_code FROM lw_packing_carton")
    codes: Set[str] = set()
    for r in trays:
        c = _norm_part(r.get("tray_item_code"))
        if c:
            codes.add(c)
    for r in cartons:
        c = _norm_part(r.get("carton_item_code"))
        if c:
            codes.add(c)
    return codes


def get_part_map_by_part_number(
    part_number: str,
    *,
    cust_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    part = _norm_part(part_number)
    if not part:
        return None
    sql = f"""
        {_MAP_SELECT_SQL}
        WHERE m.is_active = 1
          AND (TRIM(comp.CO_PARTNO) = %s OR TRIM(b.bom_no) = %s)
    """
    params: List[Any] = [part, part]
    if cust_id is not None:
        sql += " AND m.cust_id = %s"
        params.append(int(cust_id))
    sql += " ORDER BY m.map_id DESC LIMIT 1"
    row = fetch_one(sql, tuple(params))
    return _map_row_to_dict(row) if row else None


def get_part_map_by_co_id(co_id: int) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        f"""
        {_MAP_SELECT_SQL}
        WHERE m.is_active = 1 AND m.co_id = %s
        LIMIT 1
        """,
        (int(co_id),),
    )
    return _map_row_to_dict(row) if row else None


def _map_row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    tray_cavity = row.get("tray_cavity_attr")
    if tray_cavity is None and row.get("tray_cavity") is not None:
        tray_cavity = row.get("tray_cavity")
    return {
        "mapId": int(row["map_id"]),
        "coId": int(row["co_id"]) if row.get("co_id") is not None else None,
        "bomId": str(row["bom_id"]) if row.get("bom_id") else None,
        "partNumber": row.get("part_number") or "",
        "partName": row.get("part_name") or "",
        "custId": int(row["cust_id"]) if row.get("cust_id") is not None else None,
        "customerName": row.get("customer_name") or "",
        "trayItemCode": row.get("tray_item_code") or "",
        "cartonItemCode": row.get("carton_item_code") or "",
        "trayCavity": int(tray_cavity) if tray_cavity is not None else None,
        "trayCapacity": int(row["tray_capacity"]) if row.get("tray_capacity") is not None else None,
        "cartonCapacity": int(row["carton_capacity"]) if row.get("carton_capacity") is not None else None,
        "isActive": bool(int(row.get("is_active") or 0)),
    }


def list_part_maps() -> List[Dict[str, Any]]:
    rows = fetch_all(
        f"""
        {_MAP_SELECT_SQL}
        WHERE m.is_active = 1
        ORDER BY part_number
        """
    )
    return [_map_row_to_dict(r) for r in rows]


def _material_entry(item_code: str, kind: str) -> Optional[Dict[str, Any]]:
    code = _norm_part(item_code)
    if not code:
        return None
    row = fetch_one(
        "SELECT COALESCE(QTY, 0) AS qty FROM inventory WHERE TRIM(ITEM_CODE) = %s ORDER BY INVENTORY_ID LIMIT 1",
        (code,),
    )
    avail = int(float((row or {}).get("qty") or 0))
    return {
        "type": "tray" if kind == "tray" else "carton",
        "itemCode": code,
        "label": code,
        "availableQty": avail,
    }


def get_pack_materials_for_part(part_number: str) -> Dict[str, Any]:
    pmap = get_part_map_by_part_number(part_number)
    if not pmap:
        trays = list_all_tray_entries()
        cartons = list_all_carton_entries()
        return {
            "trays": trays,
            "cartons": cartons,
            "materials": trays + cartons,
            "hasMapping": False,
        }
    trays: List[Dict[str, Any]] = []
    cartons: List[Dict[str, Any]] = []
    if pmap.get("trayItemCode"):
        entry = _material_entry(pmap["trayItemCode"], "tray")
        if entry:
            trays.append(entry)
    if pmap.get("cartonItemCode"):
        entry = _material_entry(pmap["cartonItemCode"], "carton")
        if entry:
            cartons.append(entry)
    return {
        "trays": trays,
        "cartons": cartons,
        "materials": trays + cartons,
        "hasMapping": True,
        "mapping": pmap,
    }


def resolve_packing_material_for_part(
    item_code: Optional[str],
    kind: str,
    part_number: str,
) -> str:
    code = _norm_part(item_code)
    if not code:
        raise ValueError(f"Select a {kind} item code")
    if code not in all_packing_material_codes():
        raise ValueError(f"Unknown pack material code: {code}")

    pmap = get_part_map_by_part_number(part_number)
    if not pmap:
        if kind == "tray":
            if not _tray_row_exists(code):
                raise ValueError(f"Unknown tray code: {code}")
        elif not _carton_row_exists(code):
            raise ValueError(f"Unknown carton/bin code: {code}")
        return code

    if kind == "tray":
        expected = _norm_part(pmap.get("trayItemCode"))
        if code != expected:
            raise ValueError(f"Tray {code} is not mapped for part {part_number}")
    else:
        expected = _norm_part(pmap.get("cartonItemCode"))
        if not expected:
            raise ValueError(f"No carton mapped for part {part_number}")
        if code != expected:
            raise ValueError(f"Carton {code} is not mapped for part {part_number}")
    return code


def _ensure_tray_material(
    cursor: Any,
    attrs: Dict[str, Any],
    *,
    cust_id: Optional[int],
    created_by: Optional[int],
) -> str:
    existing = _norm_part(attrs.get("existingItemCode") or attrs.get("existing_item_code"))

    if existing:
        if not _tray_row_exists(existing, cursor=cursor):
            raise ValueError(f"Tray {existing} not found — pick a valid existing code")
        ensure_inventory_row(cursor, existing, cust_id=cust_id)
        return existing

    type_mode = str(attrs.get("typeMode") or attrs.get("type_mode") or "S").upper()
    no_parts = attrs.get("noParts") if attrs.get("noParts") is not None else attrs.get("no_parts")
    tray_type = str(attrs.get("trayType") or attrs.get("tray_type") or "").strip().upper()
    if not tray_type:
        tray_type = normalize_tray_type(type_mode, int(no_parts) if no_parts is not None else None)

    material_digit = int(attrs.get("materialDigit") or attrs.get("material_digit") or DEFAULT_MATERIAL_DIGIT)
    cavity = int(attrs["cavity"])
    seq = attrs.get("seq")
    if type_mode == "S":
        seq = None

    code = generate_tray_code(
        material_digit,
        tray_type,
        cavity,
        int(seq) if seq is not None else None,
        cursor=cursor,
    )
    parsed = parse_tray_code(code)
    _insert_item_master(cursor, code, kind="tray", cust_id=cust_id)
    ensure_inventory_row(cursor, code, cust_id=cust_id)
    _upsert_tray_row(
        cursor,
        item_code=code,
        material=parsed["materialDigit"],
        tray_type=parsed["trayType"],
        cavity=parsed["cavity"],
        cust_id=cust_id,
        created_by=created_by,
    )
    return code


def _ensure_box_material(
    cursor: Any,
    attrs: Dict[str, Any],
    *,
    cust_id: Optional[int],
    created_by: Optional[int],
) -> str:
    existing = _norm_part(attrs.get("existingItemCode") or attrs.get("existing_item_code"))
    if existing:
        if not _carton_row_exists(existing, cursor=cursor):
            raise ValueError(f"Carton/bin {existing} not found — pick a valid existing code")
        ensure_inventory_row(cursor, existing, cust_id=cust_id)
        return existing

    box_type = attrs.get("boxType") or attrs.get("box_type") or attrs.get("kind") or "C"
    kind = _box_kind_from_type(str(box_type))
    bin_seq = attrs.get("binSeq") or attrs.get("bin_seq")
    if kind == "bin" and bin_seq is None:
        bin_seq = default_bin_seq_for_customer(cust_id)

    code = generate_box_code(
        kind,
        int(attrs["lengthMm"]),
        int(attrs["widthMm"]),
        int(attrs["heightMm"]),
        bin_seq,
        cursor=cursor,
    )
    parsed = parse_box_code(code)
    _insert_item_master(cursor, code, kind=kind, cust_id=cust_id)
    ensure_inventory_row(cursor, code, cust_id=cust_id)
    _upsert_carton_row(
        cursor,
        item_code=code,
        length_mm=parsed["lengthMm"],
        width_mm=parsed["widthMm"],
        height_mm=parsed["heightMm"],
        created_by=created_by,
    )
    return code


def create_trays_carton_mapping(
    body: Dict[str, Any],
    *,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    raw_co_id = body.get("coId") if body.get("coId") is not None else body.get("co_id")
    co_id = int(raw_co_id) if raw_co_id not in (None, "", 0, "0") else None
    raw_bom_id = body.get("bomId") if body.get("bomId") is not None else body.get("bom_id")
    bom_id = str(raw_bom_id).strip() if raw_bom_id not in (None, "") else None
    part_number = _norm_part(body.get("partNumber") or body.get("part_no"))
    part_name = str(body.get("partName") or body.get("part_name") or "").strip()
    cust_id = body.get("custId") or body.get("cust_id")
    cust_id = int(cust_id) if cust_id is not None and str(cust_id).strip() != "" else None

    if not co_id and part_number:
        resolved = resolve_part_for_mapping(
            part_number,
            cust_id=cust_id,
            bom_id=bom_id,
            co_id=co_id,
        )
        if resolved:
            co_id = int(resolved["coId"]) if resolved.get("coId") else None
            bom_id = str(resolved.get("bomId") or bom_id or "").strip() or None
            part_number = resolved.get("partNumber") or part_number
            part_name = part_name or str(resolved.get("partName") or "")
            if cust_id is None and resolved.get("custId") is not None:
                cust_id = int(resolved["custId"])
    if not co_id and not bom_id:
        raise ValueError("Part (co_id) is required — select a valid component/BOM part")
    if not part_number:
        raise ValueError("Part number is required")
    if not co_id and not cust_id:
        raise ValueError("Customer is required for BOM-only parts")

    tray_attrs = body.get("tray") or {}
    box_attrs = body.get("carton") or body.get("box") or {}
    has_tray = bool(tray_attrs)
    lm = box_attrs.get("lengthMm") if box_attrs.get("lengthMm") is not None else box_attrs.get("length_mm")
    wm = box_attrs.get("widthMm") if box_attrs.get("widthMm") is not None else box_attrs.get("width_mm")
    hm = box_attrs.get("heightMm") if box_attrs.get("heightMm") is not None else box_attrs.get("height_mm")
    has_box = lm is not None and wm is not None and hm is not None

    if not has_tray:
        raise ValueError("Tray attributes are required")

    tray_cavity = int(tray_attrs.get("cavity") or 0)
    type_mode = str(tray_attrs.get("typeMode") or tray_attrs.get("type_mode") or "S").upper()
    no_parts = tray_attrs.get("noParts") if tray_attrs.get("noParts") is not None else tray_attrs.get("no_parts")
    tray_type = str(tray_attrs.get("trayType") or tray_attrs.get("tray_type") or "").strip().upper()
    if not tray_type:
        tray_type = normalize_tray_type(type_mode, int(no_parts) if no_parts is not None else None)

    carton_capacity = body.get("cartonCapacity") or body.get("carton_capacity")
    if carton_capacity is not None and str(carton_capacity).strip() != "":
        carton_capacity = int(carton_capacity)
    else:
        carton_capacity = None
    tray_capacity = body.get("trayCapacity") or body.get("tray_capacity")
    if tray_capacity is None and tray_attrs:
        tray_capacity = tray_attrs.get("trayCapacity") or tray_attrs.get("tray_capacity")
    if tray_capacity is not None and str(tray_capacity).strip() != "":
        tray_capacity = int(tray_capacity)
    else:
        tray_capacity = None

    with get_cursor() as cursor:
        tray_code = _ensure_tray_material(
            cursor,
            {
                "typeMode": type_mode,
                "noParts": no_parts,
                "trayType": tray_type,
                "materialDigit": int(tray_attrs.get("materialDigit") or tray_attrs.get("material_digit") or DEFAULT_MATERIAL_DIGIT),
                "cavity": tray_cavity,
                "seq": tray_attrs.get("seq"),
                "existingItemCode": tray_attrs.get("existingItemCode") or tray_attrs.get("existing_item_code"),
            },
            cust_id=cust_id,
            created_by=created_by,
        )
        carton_code: Optional[str] = None
        if has_box:
            box_type = box_attrs.get("boxType") or box_attrs.get("box_type") or box_attrs.get("kind") or "C"
            carton_code = _ensure_box_material(
                cursor,
                {
                    "boxType": box_type,
                    "lengthMm": int(box_attrs.get("lengthMm") or box_attrs.get("length_mm")),
                    "widthMm": int(box_attrs.get("widthMm") or box_attrs.get("width_mm")),
                    "heightMm": int(box_attrs.get("heightMm") or box_attrs.get("height_mm")),
                    "binSeq": box_attrs.get("binSeq") or box_attrs.get("bin_seq"),
                    "existingItemCode": box_attrs.get("existingItemCode") or box_attrs.get("existing_item_code"),
                },
                cust_id=cust_id,
                created_by=created_by,
            )

        existing = None
        if co_id is not None:
            existing = fetch_one(
                """
                SELECT map_id FROM lw_packing_part_map
                WHERE co_id = %s AND (cust_id = %s OR (%s IS NULL AND cust_id IS NULL))
                LIMIT 1
                """,
                (co_id, cust_id, cust_id),
            )
        elif bom_id and cust_id is not None:
            existing = fetch_one(
                """
                SELECT map_id FROM lw_packing_part_map
                WHERE bom_id = %s AND cust_id = %s
                LIMIT 1
                """,
                (bom_id, cust_id),
            )
        if existing:
            cursor.execute(
                """
                UPDATE lw_packing_part_map SET
                    co_id = %s,
                    bom_id = %s,
                    cust_id = %s,
                    tray_item_code = %s, carton_item_code = %s,
                    tray_capacity = %s, carton_capacity = %s,
                    is_active = 1
                WHERE map_id = %s
                """,
                (
                    co_id,
                    bom_id,
                    cust_id,
                    tray_code,
                    carton_code,
                    tray_capacity,
                    carton_capacity,
                    int(existing["map_id"]),
                ),
            )
            map_id = int(existing["map_id"])
        else:
            cursor.execute(
                """
                INSERT INTO lw_packing_part_map (
                    co_id, bom_id, cust_id,
                    tray_item_code, carton_item_code,
                    tray_capacity, carton_capacity,
                    created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    co_id,
                    bom_id,
                    cust_id,
                    tray_code,
                    carton_code,
                    tray_capacity,
                    carton_capacity,
                    created_by,
                ),
            )
            map_id = int(cursor.lastrowid or 0)

    if co_id is not None:
        result = get_part_map_by_co_id(co_id) or {}
    elif bom_id and cust_id is not None:
        result = get_part_map_by_part_number(part_number, cust_id=cust_id) or {}
    else:
        result = {}
    result["trayItemCode"] = tray_code
    result["cartonItemCode"] = carton_code or ""
    result["mapId"] = map_id
    return result


def update_trays_carton_mapping(
    map_id: int,
    body: Dict[str, Any],
    *,
    updated_by: Optional[int] = None,
) -> Dict[str, Any]:
    existing = fetch_one(
        "SELECT * FROM lw_packing_part_map WHERE map_id = %s",
        (int(map_id),),
    )
    if not existing:
        raise ValueError("Mapping not found")
    merged = {
        "coId": existing.get("co_id"),
        "bomId": existing.get("bom_id"),
        "partNumber": body.get("partNumber"),
        "partName": body.get("partName"),
        "custId": body.get("custId") if "custId" in body else existing.get("cust_id"),
        "tray": body.get("tray") or {},
        "carton": body.get("carton") or body.get("box") or {},
        "trayCapacity": body.get("trayCapacity", existing.get("tray_capacity")),
        "cartonCapacity": body.get("cartonCapacity", existing.get("carton_capacity")),
    }
    if not merged["tray"] and existing.get("tray_item_code"):
        merged["tray"] = parse_tray_code(str(existing["tray_item_code"]))
    if not merged["carton"] and existing.get("carton_item_code"):
        merged["carton"] = parse_box_code(str(existing["carton_item_code"]))
    return create_trays_carton_mapping(merged, created_by=updated_by)
