"""Laser Welding — lot-centric workflow (Child Parts, QA Disposition, Rework)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .config import Config
from .db import execute, execute_insert, fetch_all, fetch_one, get_cursor
from . import bo_inventory
from . import erp_component_stock as erp_stock
from . import packing_inventory as pack_inv

LINE_PART_INSPECTION = "Part_Inspection"
LINE_ASSEMBLY_INSPECTION = "Assembly_Inspection"
LINE_WELDING_CONSUME = "Welding_Consume"
LINE_WELDING_REWORK = "Welding_Rework"
LINE_REWORK = "Rework"
LINE_SUB_ASSEMBLY_CONSUME = "SubAssembly_Consume"
LINE_SUB_ASSEMBLY_REWORK = "SubAssembly_Rework"
LINE_QA_DISPOSITION = "QA_Disposition"
LINE_PACKING = "Packing"
# Legacy consume line types still present in some databases.
LINE_WELDING_CONSUME_LEGACY = ("Assembly_Consume", "assembly_consume")
SESSION_SOURCE_LOT = "__session__"
SUB_ASSEMBLY_CATEGORY_CODE = "SA"

# Part Inspection ERP writes (strict):
# SS (plant 1): reduce_stock (txn 18, insp-qa / stock insp) + fg_segregate (QA, stage 6).
# Whitelist (plant 2): whitelist_reduce_stock (txn 1, op 1→19, full insp) + fg_segregate (QA, stage 6, no lotstock).
# Whitelist pack: inward txn 19→6 + comp_stock stage 6↑ only.


def _part_inspection_part_no(part_number: str) -> str:
    return str(part_number or "").strip()


def _part_inspection_parent_ids() -> Tuple[int, ...]:
    return tuple(getattr(Config, "LW_PART_INSPECTION_PARENT_IDS", ()) or ())


def _part_inspection_parent_id_placeholders() -> str:
    ids = _part_inspection_parent_ids()
    return ", ".join(["%s"] * len(ids)) if ids else ""


def _resolve_component_parent_id(part_number: str, cursor: Any = None) -> Optional[int]:
    part = _part_inspection_part_no(part_number)
    if not part:
        return None
    sql = """
        SELECT CO_PARENTID AS parent_id
        FROM components
        WHERE TRIM(CO_PARTNO) = %s AND CO_ACTIVEYN = 'Y'
        ORDER BY CO_ID DESC
        LIMIT 1
    """
    if cursor is not None:
        cursor.execute(sql, (part,))
        row = cursor.fetchone()
    else:
        row = fetch_one(sql, (part,))
    if not row or row.get("parent_id") is None:
        return None
    return int(row["parent_id"])


def _is_part_inspection_part(part_number: str, cursor: Any = None) -> bool:
    parent_id = _resolve_component_parent_id(part_number, cursor)
    if parent_id is None:
        return False
    return parent_id in _part_inspection_parent_ids()


def _part_inspection_display_name(part_number: str, cursor: Any = None) -> str:
    part = _part_inspection_part_no(part_number)
    if not part:
        return ""
    sql = """
        SELECT TRIM(CO_PARTNAME) AS part_name
        FROM components
        WHERE TRIM(CO_PARTNO) = %s AND CO_ACTIVEYN = 'Y'
        ORDER BY CO_ID DESC
        LIMIT 1
    """
    if cursor is not None:
        cursor.execute(sql, (part,))
        row = cursor.fetchone()
    else:
        row = fetch_one(sql, (part,))
    return str((row or {}).get("part_name") or "").strip()


def _part_inspection_stage_placeholders() -> str:
    return ", ".join(["%s"] * len(erp_stock.LW_WHITELIST_PART_INSPECTION_NEXT_STAGES))


def _fg_stage_placeholders() -> str:
    return ", ".join(["%s"] * len(erp_stock.LW_FG_NEXT_STAGES))


def _erp_stages_for_part(part_number: str) -> Tuple[int, Tuple[int, ...]]:
    if _is_part_inspection_part(part_number):
        return (
            erp_stock.LW_WHITELIST_PART_INSPECTION_STAGE_ID,
            erp_stock.LW_WHITELIST_PART_INSPECTION_NEXT_STAGES,
        )
    return erp_stock.LW_FG_STAGE_ID, erp_stock.LW_FG_NEXT_STAGES


def _erp_plant_for_part(part_number: str) -> int:
    if _is_part_inspection_part(part_number):
        return erp_stock.LW_WHITELIST_ERP_PLANT_ID
    return erp_stock.LW_ERP_PLANT_ID


def _parse_date(value: Any) -> Optional[str]:
    """Parse dd-mm-yyyy or yyyy-mm-dd to yyyy-mm-dd."""
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _format_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%Y")
    return str(value)


def _fy_lot_prefix(for_date: Optional[date] = None) -> str:
    d = for_date or date.today()
    start_year = d.year if d.month >= 4 else d.year - 1
    yy = start_year % 100
    return f"LW/{yy:02d}-{(yy + 1) % 100:02d}/"


def _generate_next_lot_no(for_date: date, cursor: Any) -> str:
    prefix = _fy_lot_prefix(for_date)
    cursor.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(new_lot_no, '/', -1) AS UNSIGNED)), 0) AS mx "
        "FROM laser_welding_lot WHERE new_lot_no LIKE %s",
        (prefix + "%",),
    )
    row = cursor.fetchone()
    mx = int((row or {}).get("mx") or 0)
    return f"{prefix}{mx + 1}"


def _sa_fy_lot_prefix(for_date: Optional[date] = None) -> str:
    d = for_date or date.today()
    start_year = d.year if d.month >= 4 else d.year - 1
    yy = start_year % 100
    return f"SA/{yy:02d}-{(yy + 1) % 100:02d}/"


def _generate_next_sub_assembly_lot_no(for_date: date, cursor: Any) -> str:
    prefix = _sa_fy_lot_prefix(for_date)
    cursor.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(new_lot_no, '/', -1) AS UNSIGNED)), 0) AS mx "
        "FROM laser_welding_lot WHERE new_lot_no LIKE %s",
        (prefix + "%",),
    )
    row = cursor.fetchone()
    mx = int((row or {}).get("mx") or 0)
    return f"{prefix}{mx + 1}"


def _lbo_fy_lot_prefix(for_date: Optional[date] = None) -> str:
    d = for_date or date.today()
    start_year = d.year if d.month >= 4 else d.year - 1
    yy = start_year % 100
    return f"LBO/{yy:02d}-{(yy + 1) % 100:02d}/"


def _generate_next_lbo_lot_no(for_date: date, cursor: Any) -> str:
    prefix = _lbo_fy_lot_prefix(for_date)
    cursor.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(new_lot_no, '/', -1) AS UNSIGNED)), 0) AS mx "
        "FROM laser_welding_lot WHERE new_lot_no LIKE %s",
        (prefix + "%",),
    )
    row = cursor.fetchone()
    mx = int((row or {}).get("mx") or 0)
    return f"{prefix}{mx + 1}"


def _bom_no_for_id(bom_id: Any) -> str:
    bid = str(bom_id or "").strip()
    if not bid:
        return ""
    bom = fetch_one("SELECT bom_no FROM bom WHERE bom_id = %s", (bid,))
    return str(bom.get("bom_no") or "").strip() if bom else ""


def _is_sub_assembly_lot_row(lot: Dict[str, Any], bom_no: Optional[str] = None) -> bool:
    bom_id = lot.get("bom_id")
    if not bom_id:
        return False
    part_no = str(lot.get("part_number") or "").strip()
    if not part_no:
        return False
    bn = bom_no if bom_no is not None else _bom_no_for_id(bom_id)
    if not bn:
        return False
    return part_no != bn


def _is_final_assembly_lot_row(lot: Dict[str, Any], bom_no: Optional[str] = None) -> bool:
    bom_id = lot.get("bom_id")
    if not bom_id:
        return False
    part_no = str(lot.get("part_number") or "").strip()
    bn = bom_no if bom_no is not None else _bom_no_for_id(bom_id)
    return bool(bn and part_no == bn)


def _validate_lw_consumable_child_lot(child: Dict[str, Any], part_no: str) -> None:
    if not child:
        raise ValueError(f"Child lot not found for part {part_no}")
    if str(child.get("part_number") or "").strip() != part_no:
        raise ValueError(f"Child lot does not match part {part_no}")
    if child.get("bom_id") is None:
        return
    if not _is_sub_assembly_lot_row(child):
        raise ValueError(f"Lot is not a consumable part-inspection or sub-assembly lot for {part_no}")


def _validate_sa_consumable_child_lot(child: Dict[str, Any], part_no: str) -> None:
    if not child:
        raise ValueError(f"Child lot not found for part {part_no}")
    if child.get("bom_id") is not None:
        raise ValueError(f"Lot is not a part-inspection lot for {part_no}")
    if str(child.get("part_number") or "").strip() != part_no:
        raise ValueError(f"Child lot does not match part {part_no}")


def _operator_label(row: Dict[str, Any]) -> str:
    name = str(row.get("name") or "").strip()
    ecno = str(row.get("ecno") or "").strip()
    if name and ecno and name.lower() != ecno.lower():
        return f"{name} ({ecno})"
    return name or ecno


def _fetch_operator(operator_id: Any) -> Optional[Dict[str, Any]]:
    try:
        oid = int(operator_id)
    except (TypeError, ValueError):
        return None
    return fetch_one(
        """
        SELECT
            OP_ID AS id,
            COALESCE(OP_ECNO, '') AS ecno,
            COALESCE(OP_NAME, '') AS name
        FROM operators
        WHERE OP_ACTIVEYN = 'Y' AND OP_OTID = 3 AND OP_ID = %s
        """,
        (oid,),
    )


def _fetch_lw_machine(machine_id: Any, cursor: Any = None) -> Optional[Dict[str, Any]]:
    try:
        mid = int(machine_id)
    except (TypeError, ValueError):
        return None
    sql = """
        SELECT MCM_Id AS id, COALESCE(MCM_Name, '') AS name
        FROM machinemaster
        WHERE MCM_Id = %s AND MCM_Type = 3 AND MCM_ACTIVEYN = 'Y'
    """
    if cursor is not None:
        cursor.execute(sql, (mid,))
        return cursor.fetchone()
    return fetch_one(sql, (mid,))


def _machine_label(row: Dict[str, Any]) -> str:
    return str(row.get("name") or "").strip()


def _row_machine_from_lines(line_dicts: List[Dict[str, Any]]) -> Dict[str, Any]:
    first = next((ln for ln in line_dicts if ln.get("machineId")), None)
    if not first:
        return {"machineId": None, "machineName": ""}
    return {
        "machineId": first.get("machineId"),
        "machineName": first.get("machineName") or "",
    }


def _part_name(part_number: str) -> str:
    row = fetch_one(
        "SELECT TRIM(CO_PARTNAME) AS part_name FROM components "
        "WHERE TRIM(CO_PARTNO) = %s AND CO_ACTIVEYN = 'Y' LIMIT 1",
        (part_number.strip(),),
    )
    return (row or {}).get("part_name") or ""


def _is_processed(row: Dict[str, Any]) -> bool:
    return bool(row.get("new_lot_no"))


def _is_qa_approved(row: Dict[str, Any]) -> bool:
    return bool(row.get("qa_approved_at"))


def _line_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    lot_id = row.get("lot_id")
    child_lot_id = row.get("child_lot_id")
    op_id = row.get("operator_id")
    op_row = _fetch_operator(op_id) if op_id is not None else None
    machine_id = row.get("machine_id")
    machine_row = _fetch_lw_machine(machine_id) if machine_id is not None else None
    return {
        "lineId": int(row["line_id"]),
        "partNumber": row.get("part_number") or "",
        "lotId": int(lot_id) if lot_id is not None else None,
        "childLotId": int(child_lot_id) if child_lot_id is not None else None,
        "bomId": str(row["bom_id"]) if row.get("bom_id") else None,
        "lineType": row.get("line_type") or LINE_PART_INSPECTION,
        "sourceLotNo": row.get("source_lot_no") or "",
        "productionDate": _format_date(row.get("production_date")),
        "inspectedQty": int(row.get("inspected_qty") or 0),
        "qaQty": int(row.get("qa_qty") or 0),
        "scrapQty": int(row.get("scrap_qty") or 0),
        "operatorId": int(op_id) if op_id is not None else None,
        "operatorName": _operator_label(op_row) if op_row else "",
        "machineId": int(machine_id) if machine_id is not None else None,
        "machineName": _machine_label(machine_row) if machine_row else "",
        "timeTakenMinutes": int(row["time_taken_minutes"]) if row.get("time_taken_minutes") is not None else None,
        "isDraft": lot_id is None,
        "isSessionMarker": (
            lot_id is None
            and int(row.get("inspected_qty") or 0) == 0
            and str(row.get("source_lot_no") or "") == SESSION_SOURCE_LOT
        ),
    }


def _lot_to_dict(row: Dict[str, Any], lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    wd = row.get("work_date")
    work_date_str = wd.strftime("%Y-%m-%d") if hasattr(wd, "strftime") else str(wd or "")
    processed = _is_processed(row)
    qa_approved = _is_qa_approved(row)
    bom_id = row.get("bom_id")
    part_no = row["part_number"] or ""
    part_name = row.get("part_name") or row.get("product_name") or ""
    if not part_name and not bom_id:
        part_name = _part_name(part_no)
    line_list = lines if lines is not None else []
    first_op = next((ln for ln in line_list if ln.get("operatorId")), None)
    return {
        "lotId": int(row["lot_id"]),
        "partNumber": part_no,
        "partName": part_name,
        "bomId": str(bom_id) if bom_id is not None else None,
        "productName": row.get("product_name") or "",
        "operatorId": first_op.get("operatorId") if first_op else None,
        "operatorName": first_op.get("operatorName") if first_op else "",
        "newLotNo": row.get("new_lot_no"),
        "workDate": work_date_str,
        "totalInwarded": int(row.get("total_inwarded") or 0),
        "totalQa": int(row.get("total_qa") or 0),
        "totalOkayed": int(row.get("total_okayed") or 0),
        "scrap": int(row.get("scrap") or 0),
        "reworkPending": int(row.get("rework_pending") or 0),
        "reworkPool": int(row.get("rework_pool") or 0),
        "inspectionPending": int(row.get("inspection_pending") or 0),
        "isAssembly": bom_id is not None,
        "isProcessed": processed,
        "isPending": not processed,
        "isQaApproved": qa_approved,
        "processedAt": (
            row["processed_at"].isoformat()
            if row.get("processed_at") and hasattr(row["processed_at"], "isoformat")
            else (str(row["processed_at"]) if row.get("processed_at") else None)
        ),
        "lines": line_list,
    }


def _fetch_lot(lot_id: int, include_lines: bool = True) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        "SELECT * FROM laser_welding_lot WHERE lot_id = %s",
        (lot_id,),
    )
    if not row:
        return None
    if not include_lines:
        return _lot_to_dict(row, [])
    lines = fetch_all(
        "SELECT * FROM laser_welding_line WHERE lot_id = %s ORDER BY line_id",
        (lot_id,),
    )
    return _lot_to_dict(row, [_line_to_dict(ln) for ln in lines])


def _aggregate_lines(lines: List[Dict[str, Any]]) -> Dict[str, int]:
    inspected = sum(int(v.get("inspected_qty") or v.get("inspectedQty") or 0) for v in lines)
    qa = sum(int(v.get("qa_qty") or v.get("qaQty") or 0) for v in lines)
    scrap = sum(int(v.get("scrap_qty") or v.get("scrapQty") or 0) for v in lines)
    return {
        "total_inspected": inspected,
        "total_qa": qa,
        "total_scrap": scrap,
        "total_okayed": inspected - qa - scrap,
    }


def _get_or_add_part_inspection_lot(
    cursor: Any,
    *,
    part: str,
    source_lot_no: str,
    wd: str,
    inspected: int,
    qa: int,
    scrap: int,
    processed_by: Optional[int],
) -> int:
    """Create or extend laser_welding_lot using the FG source lot number as new_lot_no."""
    okayed = inspected - qa - scrap
    inwarded = okayed + scrap
    cursor.execute(
        "SELECT lot_id, part_number FROM laser_welding_lot WHERE new_lot_no = %s FOR UPDATE",
        (source_lot_no,),
    )
    existing = cursor.fetchone()
    if existing:
        lot_id = int(existing["lot_id"])
        if str(existing.get("part_number") or "").strip() != part:
            raise ValueError(
                f"Lot {source_lot_no} is already tracked for a different part in Laser Welding"
            )
        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                total_inwarded = total_inwarded + %s,
                total_okayed = total_okayed + %s,
                scrap = scrap + %s,
                work_date = %s,
                processed_at = NOW()
            WHERE lot_id = %s
            """,
            (inwarded, okayed, scrap, wd, lot_id),
        )
        return lot_id

    cursor.execute(
        """
        INSERT INTO laser_welding_lot (
            part_number, new_lot_no, work_date,
            total_inwarded, total_qa, total_okayed, scrap,
            processed_at, processed_by, qa_approved_at, qa_approved_by, created_by
        ) VALUES (%s, %s, %s, %s, 0, %s, %s, NOW(), %s, NOW(), %s, %s)
        """,
        (
            part,
            source_lot_no,
            wd,
            inwarded,
            okayed,
            scrap,
            processed_by,
            processed_by,
            processed_by,
        ),
    )
    lot_id = int(cursor.lastrowid or 0)
    if not lot_id:
        raise ValueError(f"Failed to create inspected lot for {source_lot_no}")
    return lot_id


def _find_bo_part_inspection_lot(
    cursor: Any,
    *,
    part: str,
    production_date: str,
    operator_id: int,
) -> Optional[Dict[str, Any]]:
    """Existing LBO lot for same part, operator, and work date."""
    cursor.execute(
        """
        SELECT l.lot_id, l.new_lot_no, l.part_number
        FROM laser_welding_lot l
        INNER JOIN laser_welding_line ln ON ln.lot_id = l.lot_id
        WHERE TRIM(l.part_number) = %s
          AND l.bom_id IS NULL
          AND l.new_lot_no LIKE %s
          AND ln.line_type = %s
          AND ln.production_date = %s
          AND ln.operator_id = %s
        ORDER BY l.lot_id DESC
        LIMIT 1
        FOR UPDATE
        """,
        (part, "LBO/%", LINE_PART_INSPECTION, production_date, operator_id),
    )
    return cursor.fetchone()


def _create_bo_part_inspection_lot(
    cursor: Any,
    *,
    part: str,
    lbo_lot_no: str,
    wd: str,
    inspected: int,
    scrap: int,
    processed_by: Optional[int],
) -> int:
    """Create a new part-inspection lot for BO parts (LBO prefix, no QA)."""
    okayed = inspected - scrap
    inwarded = inspected
    cursor.execute(
        """
        INSERT INTO laser_welding_lot (
            part_number, new_lot_no, work_date,
            total_inwarded, total_qa, total_okayed, scrap,
            processed_at, processed_by, created_by
        ) VALUES (%s, %s, %s, %s, 0, %s, %s, NOW(), %s, %s)
        """,
        (
            part,
            lbo_lot_no,
            wd,
            inwarded,
            okayed,
            scrap,
            processed_by,
            processed_by,
        ),
    )
    lot_id = int(cursor.lastrowid or 0)
    if not lot_id:
        raise ValueError(f"Failed to create BO inspected lot for {part}")
    return lot_id


def _get_or_add_bo_part_inspection_lot(
    cursor: Any,
    *,
    part: str,
    wd: str,
    inspected: int,
    scrap: int,
    operator_id: int,
    work_d: date,
    processed_by: Optional[int],
) -> Tuple[int, str]:
    """Reuse LBO lot for same part/operator/day; otherwise allocate a new number."""
    existing = _find_bo_part_inspection_lot(
        cursor,
        part=part,
        production_date=wd,
        operator_id=operator_id,
    )
    okayed = inspected - scrap
    inwarded = inspected
    if existing:
        lot_id = int(existing["lot_id"])
        lbo_lot_no = str(existing.get("new_lot_no") or "").strip()
        if str(existing.get("part_number") or "").strip() != part:
            raise ValueError(
                f"Lot {lbo_lot_no} is already tracked for a different part in Laser Welding"
            )
        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                total_inwarded = total_inwarded + %s,
                total_okayed = total_okayed + %s,
                scrap = scrap + %s,
                work_date = %s,
                processed_at = NOW(),
                processed_by = %s
            WHERE lot_id = %s
            """,
            (inwarded, okayed, scrap, wd, processed_by, lot_id),
        )
        return lot_id, lbo_lot_no

    lbo_lot_no = _generate_next_lbo_lot_no(work_d, cursor)
    lot_id = _create_bo_part_inspection_lot(
        cursor,
        part=part,
        lbo_lot_no=lbo_lot_no,
        wd=wd,
        inspected=inspected,
        scrap=scrap,
        processed_by=processed_by,
    )
    return lot_id, lbo_lot_no


def _upsert_part_inspection_line(
    cursor: Any,
    *,
    part: str,
    lot_id: int,
    source_lot_no: str,
    production_date: str,
    inspected: int,
    qa: int,
    scrap: int,
    operator_id: int,
    time_taken_minutes: int,
) -> int:
    """Insert or merge Part_Inspection line (key: part, lot, source lot, work date, operator)."""
    cursor.execute(
        """
        SELECT line_id FROM laser_welding_line
        WHERE part_number = %s
          AND lot_id = %s
          AND line_type = %s
          AND source_lot_no = %s
          AND production_date = %s
          AND operator_id <=> %s
        FOR UPDATE
        """,
        (
            part,
            lot_id,
            LINE_PART_INSPECTION,
            source_lot_no,
            production_date,
            operator_id,
        ),
    )
    existing = cursor.fetchone()
    if existing:
        line_id = int(existing["line_id"])
        cursor.execute(
            """
            UPDATE laser_welding_line SET
                inspected_qty = inspected_qty + %s,
                qa_qty = qa_qty + %s,
                scrap_qty = scrap_qty + %s,
                time_taken_minutes = COALESCE(time_taken_minutes, 0) + %s
            WHERE line_id = %s
            """,
            (inspected, qa, scrap, time_taken_minutes, line_id),
        )
        return line_id

    cursor.execute(
        """
        INSERT INTO laser_welding_line
        (part_number, lot_id, line_type, source_lot_no, production_date,
         inspected_qty, qa_qty, scrap_qty, operator_id, time_taken_minutes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            part,
            lot_id,
            LINE_PART_INSPECTION,
            source_lot_no,
            production_date,
            inspected,
            qa,
            scrap,
            operator_id,
            time_taken_minutes,
        ),
    )
    line_id = int(cursor.lastrowid or 0)
    if not line_id:
        raise ValueError(f"Failed to save inspection line for lot {source_lot_no}")
    return line_id


def _validate_line(item: Dict[str, Any], *, require_lot: bool = True) -> Dict[str, Any]:
    lot_no = str(item.get("sourceLotNo") or "").strip()
    if require_lot and not lot_no:
        raise ValueError("Source lot number is required")
    inspected = int(item.get("inspectedQty") or 0)
    qa = int(item.get("qaQty") or 0)
    scrap = int(item.get("scrapQty") or 0)
    no_of_comp = int(item.get("noOfComp") or 0)
    if qa + scrap > inspected:
        raise ValueError(f"QA + Scrap cannot exceed Inspected QTY for lot {lot_no or '(line)'}")
    if no_of_comp > 0 and inspected > no_of_comp:
        raise ValueError(f"Inspected QTY cannot exceed No of Comp for lot {lot_no}")
    prod_date = _parse_date(item.get("productionDate"))
    return {
        "sourceLotNo": lot_no,
        "productionDate": prod_date,
        "inspectedQty": inspected,
        "qaQty": qa,
        "scrapQty": scrap,
        "targetLotId": int(item["targetLotId"]) if item.get("targetLotId") else None,
    }


def _draft_session_row_from_line(
    line: Dict[str, Any],
    batch_mode: str,
    *,
    bom: Optional[Dict[str, Any]] = None,
    customer_name: str = "",
) -> Dict[str, Any]:
    part_no = line.get("part_number") or ""
    op_id = line.get("operator_id")
    op_row = _fetch_operator(op_id) if op_id is not None else None
    machine_id = line.get("machine_id")
    machine_row = _fetch_lw_machine(machine_id) if machine_id is not None else None
    pd = line.get("production_date")
    work_date = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")
    bom_id = line.get("bom_id") or (bom.get("bom_id") if bom else None)
    product_name = (bom or {}).get("product_name") or line.get("product_name") or part_no
    part_name = product_name if batch_mode in ("cleaning", "assembly") else _part_name(part_no)
    return {
        "rowKey": f"draft:{batch_mode}:{line['line_id']}",
        "lineId": int(line["line_id"]),
        "draftLineId": int(line["line_id"]),
        "lotId": None,
        "partNumber": part_no,
        "partName": part_name,
        "productName": product_name,
        "bomId": str(bom_id) if bom_id else None,
        "customerName": customer_name or line.get("customer_name") or "",
        "operatorId": int(op_id) if op_id is not None else None,
        "operatorName": _operator_label(op_row) if op_row else "",
        "machineId": int(machine_id) if machine_id is not None else None,
        "machineName": _machine_label(machine_row) if machine_row else "",
        "newLotNo": None,
        "workDate": work_date,
        "inspectedQty": 0,
        "qaQty": 0,
        "scrapQty": 0,
        "isDraft": True,
        "isPending": True,
        "isProcessed": False,
        "batchMode": batch_mode,
        "lines": [],
    }


def delete_pending_draft_line(line_id: int) -> None:
    """Delete a single open session draft row (no inspect/weld/assembly recorded yet)."""
    lid = int(line_id or 0)
    if not lid:
        raise ValueError("Draft line id is required")
    row = fetch_one(
        """
        SELECT * FROM laser_welding_line
        WHERE line_id = %s AND lot_id IS NULL AND source_lot_no = %s
        """,
        (lid, SESSION_SOURCE_LOT),
    )
    if not row:
        raise ValueError("Pending row not found or already completed")
    if (
        int(row.get("inspected_qty") or 0) > 0
        or int(row.get("qa_qty") or 0) > 0
        or int(row.get("scrap_qty") or 0) > 0
        or int(row.get("time_taken_minutes") or 0) > 0
    ):
        raise ValueError("Cannot remove a row that already has recorded work")
    execute("DELETE FROM laser_welding_line WHERE line_id = %s", (lid,))


def get_meta(work_date: str) -> Dict[str, Any]:
    wd = _parse_date(work_date) or date.today().strftime("%Y-%m-%d")
    child_count = fetch_one(
        "SELECT COUNT(*) AS cnt FROM laser_welding_lot WHERE work_date = %s",
        (wd,),
    )
    qa_count = fetch_one(
        "SELECT COUNT(*) AS cnt FROM laser_welding_lot "
        "WHERE total_qa > 0",
    )
    rework_count = fetch_one(
        "SELECT COUNT(*) AS cnt FROM laser_welding_lot WHERE rework_pending > 0",
    )
    return {
        "workDate": wd,
        "childPartsCount": int((child_count or {}).get("cnt") or 0),
        "qaPendingCount": int((qa_count or {}).get("cnt") or 0),
        "reworkPendingCount": int((rework_count or {}).get("cnt") or 0),
    }


def get_parts(mode: Optional[str] = None) -> List[Dict[str, str]]:
    m = str(mode or "production").strip().lower()
    if m == "rework":
        sql = """
            SELECT DISTINCT TRIM(c.CO_PARTNO) AS part_no, TRIM(c.CO_PARTNAME) AS part_name
            FROM laser_welding_lot l
            INNER JOIN components c
                ON TRIM(c.CO_PARTNO) = TRIM(l.part_number) AND c.CO_ACTIVEYN = 'Y'
            WHERE l.rework_pool > 0
            ORDER BY part_no
        """
        rows = fetch_all(sql)
        return [
            {
                "part_no": r["part_no"],
                "part_name": r["part_name"] or "",
                "partNo": r["part_no"],
                "partName": r["part_name"] or "",
            }
            for r in rows
        ]
    if m == "cleaning":
        rows = fetch_all(
            """
            SELECT DISTINCT b.bom_id, b.bom_no AS part_no, b.product_name AS part_name,
                   0 AS is_sub_assembly
            FROM bom b
            INNER JOIN laser_welding_lot l ON l.bom_id = b.bom_id
            WHERE b.is_latest_version = 'Y'
              AND l.new_lot_no IS NOT NULL
              AND l.inspection_pending > 0
              AND TRIM(l.part_number) = TRIM(b.bom_no)
            UNION
            SELECT DISTINCT b.bom_id, l.part_number AS part_no,
                   COALESCE(l.product_name, l.part_number) AS part_name,
                   1 AS is_sub_assembly
            FROM bom b
            INNER JOIN laser_welding_lot l ON l.bom_id = b.bom_id
            WHERE b.is_latest_version = 'Y'
              AND l.new_lot_no IS NOT NULL
              AND l.inspection_pending > 0
              AND TRIM(l.part_number) != TRIM(b.bom_no)
            ORDER BY part_no
            """
        )
        return [
            {
                "part_no": r["part_no"],
                "part_name": r["part_name"] or r["part_no"],
                "partNo": r["part_no"],
                "partName": r["part_name"] or r["part_no"],
                "bomId": str(r["bom_id"]),
                "isSubAssembly": bool(int(r.get("is_sub_assembly") or 0)),
                "subAssemblyPartNo": (
                    str(r["part_no"]) if int(r.get("is_sub_assembly") or 0) else None
                ),
            }
            for r in rows
        ]

    whitelist_plant_id = erp_stock.LW_WHITELIST_ERP_PLANT_ID
    plant_id = erp_stock.LW_ERP_PLANT_ID
    result_by_part: Dict[str, Dict[str, str]] = {}

    fg_stage_placeholders = _fg_stage_placeholders()
    parent_ids = _part_inspection_parent_ids()
    parent_placeholders = _part_inspection_parent_id_placeholders()
    ss_exclude_parent_sql = ""
    ss_params: Tuple[Any, ...] = (plant_id,) + erp_stock.LW_FG_NEXT_STAGES
    if parent_ids:
        ss_exclude_parent_sql = f" AND c.CO_PARENTID NOT IN ({parent_placeholders})"
        ss_params = parent_ids + ss_params
    sql_ss = f"""
        SELECT TRIM(im.ITEM_CODE) AS part_no, TRIM(c.CO_PARTNAME) AS part_name
        FROM ITEM_MASTER im
        INNER JOIN components c
            ON TRIM(c.CO_PARTNO) = TRIM(im.ITEM_CODE) AND c.CO_ACTIVEYN = 'Y'
        WHERE im.CATEGORY_CODE = 'SS'
          {ss_exclude_parent_sql}
          AND EXISTS (
            SELECT 1
            FROM comp_transaction ct
            WHERE ct.CT_COMPID = c.CO_ID
              AND ct.CT_PLANTID = %s
              AND ct.CT_NEXTSTAGE IN ({fg_stage_placeholders})
            GROUP BY ct.CT_LOT_DC
            HAVING SUM(
                CASE
                    WHEN ct.CT_MOVEMENT = 'I' THEN ct.CT_QTY
                    WHEN ct.CT_MOVEMENT = 'O' THEN -ct.CT_QTY
                END
            ) > 0
          )
        ORDER BY im.ITEM_CODE
    """
    for r in fetch_all(sql_ss, ss_params):
        part_no = str(r["part_no"] or "").strip()
        if not part_no:
            continue
        result_by_part[part_no] = {
            "part_no": part_no,
            "part_name": r.get("part_name") or "",
            "partNo": part_no,
            "partName": r.get("part_name") or "",
        }

    if parent_ids:
        stage_placeholders = _part_inspection_stage_placeholders()
        sql_pi = f"""
            SELECT TRIM(c.CO_PARTNO) AS part_no, TRIM(c.CO_PARTNAME) AS part_name
            FROM components c
            WHERE c.CO_ACTIVEYN = 'Y'
              AND c.CO_PARENTID IN ({parent_placeholders})
              AND EXISTS (
                SELECT 1
                FROM comp_transaction ct
                WHERE ct.CT_COMPID = c.CO_ID
                  AND ct.CT_PLANTID = %s
                  AND ct.CT_NEXTSTAGE IN ({stage_placeholders})
                GROUP BY ct.CT_LOT_DC
                HAVING SUM(
                    CASE
                        WHEN ct.CT_MOVEMENT = 'I' THEN ct.CT_QTY
                        WHEN ct.CT_MOVEMENT = 'O' THEN -ct.CT_QTY
                    END
                ) > 0
              )
            ORDER BY c.CO_PARTNO
        """
        rows_pi = fetch_all(
            sql_pi,
            parent_ids
            + (whitelist_plant_id,)
            + erp_stock.LW_WHITELIST_PART_INSPECTION_NEXT_STAGES,
        )
        for r in rows_pi:
            part_no = str(r.get("part_no") or "").strip()
            if not part_no:
                continue
            part_name = str(r.get("part_name") or "").strip()
            result_by_part[part_no] = {
                "part_no": part_no,
                "part_name": part_name,
                "partNo": part_no,
                "partName": part_name,
            }

    for r in bo_inventory.fetch_bo_parts_for_inspection():
        part_no = str(r.get("part_no") or "").strip()
        if not part_no:
            continue
        result_by_part[part_no] = {
            "part_no": part_no,
            "part_name": r.get("part_name") or part_no,
            "partNo": part_no,
            "partName": r.get("part_name") or part_no,
            "isBoPart": True,
        }

    return sorted(result_by_part.values(), key=lambda x: x["partNo"])


def get_source_lots(part_number: str) -> Dict[str, Any]:
    part = _part_inspection_part_no(part_number)
    if not part:
        return {"boMode": False, "availableQty": 0, "lots": []}
    if bo_inventory.is_bo_sub_assembly_part(part):
        qty = bo_inventory.fetch_bo_available_qty(part)
        return {"boMode": True, "availableQty": qty, "lots": []}
    _, next_stages = _erp_stages_for_part(part)
    comp_id = erp_stock.resolve_comp_id(part)
    plant_id = _erp_plant_for_part(part)
    rows = erp_stock.fetch_lot_inventory(
        comp_id, plant_id, next_stages=next_stages
    )
    lots = []
    for r in rows:
        avail = r["availableQty"]
        if avail <= 0:
            continue
        lots.append(
            {
                "lotNo": r["lotNo"],
                "availableQty": avail,
                "noOfComp": avail,
                "productionDate": "",
            }
        )
    return {"boMode": False, "availableQty": 0, "lots": lots}


def get_rework_lots(part_number: str) -> List[Dict[str, Any]]:
    part = str(part_number or "").strip()
    if not part:
        return []
    rows = fetch_all(
        """
        SELECT lot_id, new_lot_no, rework_pool
        FROM laser_welding_lot
        WHERE TRIM(part_number) = %s AND rework_pool > 0 AND new_lot_no IS NOT NULL
        ORDER BY lot_id DESC
        """,
        (part,),
    )
    return [
        {
            "lotId": int(r["lot_id"]),
            "newLotNo": r["new_lot_no"],
            "reworkPool": int(r["rework_pool"] or 0),
        }
        for r in rows
    ]


def _rework_row_from_line(r: Dict[str, Any], wd: str, is_draft: bool) -> Dict[str, Any]:
    pd = r.get("production_date")
    prod_date = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or wd)
    part_no = r.get("part_number") or ""
    parent_lot_id = r.get("parent_lot_id")
    new_lot_no = r.get("parent_new_lot_no") or r.get("source_lot_no") or ""
    pool = int(r.get("rework_pool") or 0)
    return {
        "rowKey": f"rework:{'draft' if is_draft else 'committed'}:{r['line_id']}",
        "lineId": int(r["line_id"]),
        "lotId": int(parent_lot_id) if parent_lot_id else None,
        "partNumber": part_no,
        "partName": r.get("part_name") or _part_name(part_no),
        "newLotNo": new_lot_no,
        "workDate": prod_date,
        "inspectedQty": int(r.get("inspected_qty") or 0),
        "qaQty": int(r.get("qa_qty") or 0),
        "reworkPool": pool,
        "isDraft": is_draft,
        "isReinspected": not is_draft,
        "isProcessed": not is_draft,
        "batchMode": "rework",
        "lines": [_line_to_dict(r)],
    }


def get_rework_inspect_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    rows = fetch_all(
        """
        SELECT ln.*
        FROM laser_welding_line ln
        WHERE ln.line_type = %s AND ln.production_date = %s
        ORDER BY ln.source_lot_no, ln.lot_id IS NULL, ln.line_id
        """,
        (LINE_REWORK, wd),
    )
    result = []
    for r in rows:
        is_draft = r.get("lot_id") is None
        if is_draft:
            parent = fetch_one(
                "SELECT lot_id, new_lot_no, rework_pool FROM laser_welding_lot "
                "WHERE new_lot_no = %s LIMIT 1",
                (r.get("source_lot_no"),),
            )
            if parent:
                r["parent_lot_id"] = parent["lot_id"]
                r["parent_new_lot_no"] = parent["new_lot_no"]
                r["rework_pool"] = parent["rework_pool"]
        else:
            parent = fetch_one(
                "SELECT lot_id, new_lot_no, rework_pool FROM laser_welding_lot WHERE lot_id = %s",
                (r.get("lot_id"),),
            )
            if parent:
                r["parent_lot_id"] = parent["lot_id"]
                r["parent_new_lot_no"] = parent["new_lot_no"]
                r["rework_pool"] = parent["rework_pool"]
        result.append(_rework_row_from_line(r, wd, is_draft))

    result.sort(key=lambda x: (
        str(x.get("partNumber") or ""),
        str(x.get("newLotNo") or ""),
        0 if x.get("isReinspected") else 1,
    ))
    return result


def get_operators() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            OP_ID AS id,
            COALESCE(OP_ECNO, '') AS ecno,
            COALESCE(OP_NAME, '') AS name
        FROM operators
        WHERE OP_ACTIVEYN = 'Y' AND OP_OTID = 3
        ORDER BY OP_NAME, OP_ECNO
        """
    )
    return [
        {
            "id": int(r["id"]),
            "ecno": r.get("ecno") or "",
            "name": r.get("name") or "",
            "label": _operator_label(r),
        }
        for r in rows
    ]


def get_lw_machines() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT MCM_Id AS id, COALESCE(MCM_Name, '') AS name
        FROM machinemaster
        WHERE MCM_Type = 3 AND MCM_ACTIVEYN = 'Y'
        ORDER BY MCM_Name
        """
    )
    return [
        {
            "id": int(r["id"]),
            "name": r.get("name") or "",
            "label": _machine_label(r),
            "machineId": int(r["id"]),
            "machineName": r.get("name") or "",
        }
        for r in rows
    ]


def _production_row_from_operator_session(
    part: str,
    operator_id: int,
    lines: List[Dict[str, Any]],
    wd: str,
) -> Dict[str, Any]:
    part_no = str(part or "").strip()
    op_row = _fetch_operator(operator_id)
    line_dicts = [_line_to_dict(ln) for ln in lines]
    times = [
        int(ln.get("time_taken_minutes") or 0)
        for ln in lines
        if int(ln.get("time_taken_minutes") or 0) > 0
    ]
    max_time = max(times) if times else None
    return {
        "rowKey": f"prod:{part_no}:{int(operator_id)}:{wd}",
        "partNumber": part_no,
        "partName": _part_name(part_no),
        "operatorId": int(operator_id),
        "operatorName": _operator_label(op_row) if op_row else "",
        "workDate": wd,
        "inspectedQty": 0,
        "qaQty": 0,
        "scrapQty": 0,
        "isDraft": False,
        "isPending": False,
        "isProcessed": True,
        "batchMode": "production",
        "lines": line_dicts,
        "timeTakenMinutes": max_time,
    }


def _production_row_from_lot(lot: Dict[str, Any], lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if lines is None:
        lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = %s
            ORDER BY line_id
            """,
            (lot["lot_id"], LINE_PART_INSPECTION),
        )
    processed = _is_processed(lot)
    line_dicts = [_line_to_dict(ln) for ln in lines]
    d = _lot_to_dict(lot, line_dicts)
    d["rowKey"] = f"lot:{lot['lot_id']}"
    d["isDraft"] = False
    d["isPending"] = False
    d["isProcessed"] = processed
    d["inspectedQty"] = int(lot.get("total_inwarded") or 0)
    d["qaQty"] = int(lot.get("total_qa") or 0)
    d["scrapQty"] = int(lot.get("scrap") or 0)
    d["batchMode"] = "production"
    first_time = next((ln for ln in line_dicts if ln.get("timeTakenMinutes")), None)
    if first_time:
        d["timeTakenMinutes"] = first_time.get("timeTakenMinutes")
    return d


def get_production_inspect_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")

    result: List[Dict[str, Any]] = []

    draft_lines = fetch_all(
        """
        SELECT * FROM laser_welding_line
        WHERE lot_id IS NULL
          AND line_type = %s
          AND production_date = %s
          AND source_lot_no = %s
          AND inspected_qty = 0
        ORDER BY line_id DESC
        """,
        (LINE_PART_INSPECTION, wd, SESSION_SOURCE_LOT),
    )
    for line in draft_lines:
        result.append(_draft_session_row_from_line(line, "production"))

    committed_lines = fetch_all(
        """
        SELECT ln.*
        FROM laser_welding_line ln
        INNER JOIN laser_welding_lot l ON l.lot_id = ln.lot_id
        WHERE ln.line_type = %s
          AND ln.lot_id IS NOT NULL
          AND ln.production_date = %s
          AND l.bom_id IS NULL
        ORDER BY ln.part_number, ln.operator_id, ln.line_id
        """,
        (LINE_PART_INSPECTION, wd),
    )
    sessions: Dict[tuple, List[Dict[str, Any]]] = {}
    for ln in committed_lines:
        part_no = str(ln.get("part_number") or "").strip()
        op_id = int(ln.get("operator_id") or 0)
        if not part_no or not op_id:
            continue
        sessions.setdefault((part_no, op_id), []).append(ln)
    for (part_no, op_id), lines in sessions.items():
        result.append(_production_row_from_operator_session(part_no, op_id, lines, wd))

    return result


def create_pending_lot(
    part_number: str,
    operator_id: int,
    work_date: str,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Insert draft session line (no laser_welding_lot row)."""
    part = _part_inspection_part_no(part_number)
    wd = _parse_date(work_date)
    if not part or not wd:
        raise ValueError("Part number and work date are required")

    op = _fetch_operator(operator_id)
    if not op:
        raise ValueError("Invalid operator — select an active laser-welding operator")

    if not get_source_lots(part)["lots"] and not (
        bo_inventory.is_bo_sub_assembly_part(part)
        and bo_inventory.fetch_bo_available_qty(part) > 0
    ):
        raise ValueError(
            f"No lots with available stock for part {part} — "
            "cannot add to inspection list"
        )

    existing = fetch_one(
        """
        SELECT line_id FROM laser_welding_line
        WHERE lot_id IS NULL AND line_type = %s AND part_number = %s
          AND operator_id = %s AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_PART_INSPECTION, part, int(operator_id), wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open inspection row already exists for this part and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_id
        ) VALUES (%s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (part, LINE_PART_INSPECTION, SESSION_SOURCE_LOT, wd, int(operator_id)),
    )
    if not line_id:
        raise ValueError("Failed to create pending inspection row — please try again")
    line = fetch_one("SELECT * FROM laser_welding_line WHERE line_id = %s", (line_id,))
    if not line:
        raise ValueError("Pending inspection row could not be loaded — refresh and try again")
    return _draft_session_row_from_line(line, "production")


def get_child_parts_rows(work_date: str, batch_mode: str = "production") -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    mode = str(batch_mode or "production").strip().lower()
    if mode == "rework":
        return get_rework_inspect_rows(wd)
    if mode == "cleaning":
        return get_cleaning_rows(wd)
    return get_production_inspect_rows(wd)


def save_child_parts(
    part_number: str,
    work_date: str,
    batch_mode: str,
    lines: List[Dict[str, Any]],
    lot_id: Optional[int] = None,
    operator_id: Optional[int] = None,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    part = str(part_number or "").strip()
    wd = _parse_date(work_date)
    if not part or not wd:
        raise ValueError("Part number and work date are required")
    mode = str(batch_mode or "production").strip().lower()
    if mode not in ("production", "rework"):
        raise ValueError("Invalid batch mode")

    validated = [_validate_line(it) for it in (lines or []) if str(it.get("sourceLotNo") or "").strip()]

    if mode == "rework":
        if not lot_id:
            raise ValueError("lotId is required for rework save")
        lot = fetch_one("SELECT * FROM laser_welding_lot WHERE lot_id = %s", (lot_id,))
        if not lot:
            raise ValueError("LW lot not found")
        if not _is_processed(lot):
            raise ValueError("Rework re-inspect applies only to processed LW lots")
        if str(lot.get("part_number") or "").strip() != part:
            raise ValueError("Part number does not match the selected LW lot")
        if len(validated) != 1:
            raise ValueError("Rework save allows exactly one lot line")

        v = validated[0]
        new_lot_no = str(lot.get("new_lot_no") or "").strip()
        if v["sourceLotNo"] != new_lot_no:
            v = {**v, "sourceLotNo": new_lot_no}

        insp = int(v["inspectedQty"])
        qa = int(v["qaQty"])
        existing = fetch_one(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Rework'
              AND source_lot_no = %s AND production_date = %s
            """,
            (part, new_lot_no, wd),
        )
        if insp <= 0:
            if existing:
                execute(
                    "DELETE FROM laser_welding_line WHERE line_id = %s",
                    (existing["line_id"],),
                )
                return {"lotId": lot_id, "saved": 0, "deleted": True}
            return {"lotId": lot_id, "saved": 0}
        if qa > insp:
            raise ValueError("QA cannot exceed Inspected QTY")
        pool_avail = int(lot.get("rework_pool") or 0)
        if insp > pool_avail:
            raise ValueError("Inspected QTY cannot exceed available rework pool")

        if existing:
            execute(
                """
                UPDATE laser_welding_line SET
                    inspected_qty = %s,
                    qa_qty = %s
                WHERE line_id = %s
                """,
                (insp, qa, existing["line_id"]),
            )
            line_id = int(existing["line_id"])
        else:
            line_id = execute_insert(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, line_type, source_lot_no, production_date, inspected_qty, qa_qty)
                VALUES (%s, NULL, 'Rework', %s, %s, %s, %s)
                """,
                (part, new_lot_no, wd, insp, qa),
            )
            if not line_id:
                raise ValueError("Failed to save rework line — please try again")

        saved_line = fetch_one("SELECT * FROM laser_welding_line WHERE line_id = %s", (line_id,))
        return {
            "lotId": lot_id,
            "lineId": line_id,
            "saved": 1,
            "line": _line_to_dict(saved_line) if saved_line else None,
        }

    non_zero = [v for v in validated if v["inspectedQty"] > 0 or v["qaQty"] > 0]
    if not non_zero:
        if operator_id is not None:
            execute(
                """
                DELETE FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND production_date = %s AND operator_id = %s
                """,
                (part, wd, int(operator_id)),
            )
        else:
            execute(
                """
                DELETE FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND production_date = %s
                """,
                (part, wd),
            )
        return {"lotId": None, "saved": 0, "lines": []}

    _, next_stages = _erp_stages_for_part(part)
    erp_stock.validate_lot_lines(
        part,
        non_zero,
        plant_id=_erp_plant_for_part(part),
        next_stages=next_stages,
    )

    kept_source = set()
    saved = 0
    for v in non_zero:
        kept_source.add(v["sourceLotNo"])
        if operator_id is not None:
            existing = fetch_one(
                """
                SELECT * FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND source_lot_no = %s AND production_date = %s
                  AND operator_id = %s
                """,
                (part, v["sourceLotNo"], wd, int(operator_id)),
            )
        else:
            existing = fetch_one(
                """
                SELECT * FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND source_lot_no = %s AND production_date = %s
                """,
                (part, v["sourceLotNo"], wd),
            )
        if existing:
            execute(
                """
                UPDATE laser_welding_line SET
                    inspected_qty = %s,
                    qa_qty = %s
                WHERE line_id = %s
                """,
                (v["inspectedQty"], v["qaQty"], existing["line_id"]),
            )
        else:
            if operator_id is not None:
                execute(
                    """
                    INSERT INTO laser_welding_line
                    (part_number, lot_id, line_type, source_lot_no, production_date,
                     inspected_qty, qa_qty, operator_id)
                    VALUES (%s, NULL, 'Part_Inspection', %s, %s, %s, %s, %s)
                    """,
                    (part, v["sourceLotNo"], wd, v["inspectedQty"], v["qaQty"], int(operator_id)),
                )
            else:
                execute(
                    """
                    INSERT INTO laser_welding_line
                    (part_number, lot_id, line_type, source_lot_no, production_date, inspected_qty, qa_qty)
                    VALUES (%s, NULL, 'Part_Inspection', %s, %s, %s, %s)
                    """,
                    (part, v["sourceLotNo"], wd, v["inspectedQty"], v["qaQty"]),
                )
        saved += 1

    if kept_source:
        placeholders = ",".join(["%s"] * len(kept_source))
        if operator_id is not None:
            execute(
                f"""
                DELETE FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND production_date = %s AND operator_id = %s
                  AND source_lot_no NOT IN ({placeholders})
                """,
                (part, wd, int(operator_id), *kept_source),
            )
        else:
            execute(
                f"""
                DELETE FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND production_date = %s AND source_lot_no NOT IN ({placeholders})
                """,
                (part, wd, *kept_source),
            )

    if operator_id is not None:
        saved_lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
              AND production_date = %s AND operator_id = %s
            ORDER BY line_id
            """,
            (part, wd, int(operator_id)),
        )
    else:
        saved_lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
              AND production_date = %s
            ORDER BY line_id
            """,
            (part, wd),
        )
    return {
        "lotId": None,
        "saved": saved,
        "lines": [_line_to_dict(ln) for ln in saved_lines],
    }


def inspect_production(
    draft_line_id: int,
    work_date: str,
    lines: List[Dict[str, Any]],
    time_taken_minutes: int,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = %s
              AND source_lot_no = %s
            FOR UPDATE
            """,
            (draft_line_id, LINE_PART_INSPECTION, SESSION_SOURCE_LOT),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Pending inspection row not found — add part and operator first")

        part = _part_inspection_part_no(draft.get("part_number") or "")
        operator_id = int(draft.get("operator_id") or 0)
        if not operator_id:
            raise ValueError("Operator is required on the pending inspection row")
        pd = draft.get("production_date")
        draft_wd = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")[:10]
        if draft_wd != wd:
            raise ValueError("Work date does not match the pending row")

        is_bo = bo_inventory.is_bo_sub_assembly_part(part)
        if is_bo:
            validated: List[Dict[str, Any]] = []
            for it in lines or []:
                v = _validate_line(it, require_lot=False)
                v["qaQty"] = 0
                if v["scrapQty"] > v["inspectedQty"]:
                    raise ValueError("Scrap cannot exceed Inspected QTY")
                if v["inspectedQty"] > 0:
                    validated.append(v)
            non_zero = validated
            if not non_zero:
                raise ValueError("Enter at least one line with Inspected QTY > 0")

            total_insp = sum(int(v["inspectedQty"]) for v in non_zero)
            total_scrap = sum(int(v["scrapQty"]) for v in non_zero)
            bo_inventory.validate_bo_qty(part, total_insp, cursor=cursor)

            work_d = datetime.strptime(wd, "%Y-%m-%d").date()
            lot_id, lbo_lot_no = _get_or_add_bo_part_inspection_lot(
                cursor,
                part=part,
                wd=wd,
                inspected=total_insp,
                scrap=total_scrap,
                operator_id=operator_id,
                work_d=work_d,
                processed_by=processed_by,
            )
            _upsert_part_inspection_line(
                cursor,
                part=part,
                lot_id=lot_id,
                source_lot_no=lbo_lot_no,
                production_date=wd,
                inspected=total_insp,
                qa=0,
                scrap=total_scrap,
                operator_id=operator_id,
                time_taken_minutes=time_taken_minutes,
            )
            created_lots = [
                {
                    "lotId": lot_id,
                    "newLotNo": lbo_lot_no,
                    "lot": _fetch_lot(lot_id),
                }
            ]

            bo_inventory.reduce_bo_inventory(cursor, part, total_insp)
            cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

            first = created_lots[0] if created_lots else {}
            return {
                "lots": created_lots,
                "newLotNo": first.get("newLotNo"),
                "lotId": first.get("lotId"),
                "lot": first.get("lot"),
            }

        validated = [
            _validate_line(it)
            for it in (lines or [])
            if str(it.get("sourceLotNo") or "").strip()
        ]
        non_zero = [v for v in validated if v["inspectedQty"] > 0]
        if not non_zero:
            raise ValueError("Enter at least one line with Inspected QTY > 0")

        stage_id, next_stages = _erp_stages_for_part(part)
        plant_id = _erp_plant_for_part(part)
        comp_id = erp_stock.resolve_comp_id(part, cursor)
        erp_stock.validate_lot_lines(
            part,
            non_zero,
            plant_id=plant_id,
            cursor=cursor,
            next_stages=next_stages,
        )

        if _is_part_inspection_part(part):
            wl_lot_lines = [
                {"lotNo": v["sourceLotNo"], "qty": v["inspectedQty"]}
                for v in non_zero
            ]
            erp_stock.whitelist_reduce_stock(
                cursor,
                comp_id,
                plant_id,
                wl_lot_lines,
                processed_by,
            )
            for v in non_zero:
                qa_qty = int(v["qaQty"])
                if qa_qty <= 0:
                    continue
                erp_stock.fg_segregate(
                    cursor,
                    comp_id,
                    plant_id,
                    v["sourceLotNo"],
                    qa_qty,
                    processed_by,
                    stage_id=erp_stock.LW_WHITELIST_QA_OUTWARD_STAGE_ID,
                    update_lot_fg=False,
                )
        else:
            lot_lines = [
                {
                    "lotNo": v["sourceLotNo"],
                    "qty": v["inspectedQty"],
                    "txnQty": max(0, int(v["inspectedQty"]) - int(v["qaQty"])),
                }
                for v in non_zero
            ]
            erp_stock.reduce_stock(
                cursor,
                comp_id,
                plant_id,
                stage_id,
                lot_lines,
                processed_by,
            )
            for v in non_zero:
                qa_qty = int(v["qaQty"])
                if qa_qty <= 0:
                    continue
                erp_stock.fg_segregate(
                    cursor,
                    comp_id,
                    plant_id,
                    v["sourceLotNo"],
                    qa_qty,
                    processed_by,
                    stage_id=stage_id,
                )

        created_lots: List[Dict[str, Any]] = []
        for v in non_zero:
            source_lot_no = v["sourceLotNo"]
            insp = int(v["inspectedQty"])
            qa = int(v["qaQty"])
            scrap = int(v["scrapQty"])
            lot_id = _get_or_add_part_inspection_lot(
                cursor,
                part=part,
                source_lot_no=source_lot_no,
                wd=wd,
                inspected=insp,
                qa=qa,
                scrap=scrap,
                processed_by=processed_by,
            )
            _upsert_part_inspection_line(
                cursor,
                part=part,
                lot_id=lot_id,
                source_lot_no=source_lot_no,
                production_date=wd,
                inspected=insp,
                qa=qa,
                scrap=scrap,
                operator_id=operator_id,
                time_taken_minutes=time_taken_minutes,
            )
            created_lots.append(
                {
                    "lotId": lot_id,
                    "newLotNo": source_lot_no,
                    "lot": _fetch_lot(lot_id),
                }
            )

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

    first = created_lots[0] if created_lots else {}
    return {
        "lots": created_lots,
        "newLotNo": first.get("newLotNo"),
        "lotId": first.get("lotId"),
        "lot": first.get("lot"),
    }


def process_production(
    part_number: str,
    work_date: str,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Legacy entry point — draft-line flow; UI uses inspect_production instead."""
    part = _part_inspection_part_no(part_number)
    wd = _parse_date(work_date)
    if not part or not wd:
        raise ValueError("Part number and work date are required")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
              AND production_date = %s
            FOR UPDATE
            """,
            (part, wd),
        )
        draft_lines = [
            ln for ln in (cursor.fetchall() or [])
            if str(ln.get("source_lot_no") or "").strip() != SESSION_SOURCE_LOT
            and int(ln.get("inspected_qty") or 0) > 0
        ]
        if not draft_lines:
            raise ValueError("Save at least one line with Inspected QTY > 0 before processing")

        stage_id, next_stages = _erp_stages_for_part(part)
        plant_id = _erp_plant_for_part(part)
        comp_id = erp_stock.resolve_comp_id(part, cursor)
        erp_stock.validate_lot_lines(
            part,
            draft_lines,
            plant_id=plant_id,
            cursor=cursor,
            next_stages=next_stages,
        )

        if _is_part_inspection_part(part):
            wl_lot_lines = [
                {
                    "lotNo": str(ln.get("source_lot_no") or "").strip(),
                    "qty": int(ln.get("inspected_qty") or 0),
                }
                for ln in draft_lines
            ]
            erp_stock.whitelist_reduce_stock(
                cursor,
                comp_id,
                plant_id,
                wl_lot_lines,
                processed_by,
            )
            for ln in draft_lines:
                qa_qty = int(ln.get("qa_qty") or 0)
                if qa_qty <= 0:
                    continue
                erp_stock.fg_segregate(
                    cursor,
                    comp_id,
                    plant_id,
                    str(ln.get("source_lot_no") or "").strip(),
                    qa_qty,
                    processed_by,
                    stage_id=erp_stock.LW_WHITELIST_QA_OUTWARD_STAGE_ID,
                    update_lot_fg=False,
                )
        else:
            lot_lines = [
                {
                    "lotNo": str(ln.get("source_lot_no") or "").strip(),
                    "qty": int(ln.get("inspected_qty") or 0),
                    "txnQty": max(
                        0,
                        int(ln.get("inspected_qty") or 0) - int(ln.get("qa_qty") or 0),
                    ),
                }
                for ln in draft_lines
            ]
            erp_stock.reduce_stock(
                cursor,
                comp_id,
                plant_id,
                stage_id,
                lot_lines,
                processed_by,
            )
            for ln in draft_lines:
                qa_qty = int(ln.get("qa_qty") or 0)
                if qa_qty <= 0:
                    continue
                erp_stock.fg_segregate(
                    cursor,
                    comp_id,
                    plant_id,
                    str(ln.get("source_lot_no") or "").strip(),
                    qa_qty,
                    processed_by,
                    stage_id=stage_id,
                )

        created_lots: List[Dict[str, Any]] = []
        for ln in draft_lines:
            source_lot_no = str(ln.get("source_lot_no") or "").strip()
            insp = int(ln.get("inspected_qty") or 0)
            qa = int(ln.get("qa_qty") or 0)
            scrap = int(ln.get("scrap_qty") or 0)
            lot_id = _get_or_add_part_inspection_lot(
                cursor,
                part=part,
                source_lot_no=source_lot_no,
                wd=wd,
                inspected=insp,
                qa=qa,
                scrap=scrap,
                processed_by=processed_by,
            )
            cursor.execute(
                """
                UPDATE laser_welding_line SET lot_id = %s
                WHERE line_id = %s
                """,
                (lot_id, ln["line_id"]),
            )
            created_lots.append(
                {"lotId": lot_id, "newLotNo": source_lot_no, "lot": _fetch_lot(lot_id)}
            )

    first = created_lots[0] if created_lots else {}
    return {
        "lots": created_lots,
        "newLotNo": first.get("newLotNo"),
        "lotId": first.get("lotId"),
        "lot": first.get("lot"),
    }


def process_reinspect(
    lot_id: int,
    work_date: str,
    line_id: int,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    if not line_id:
        raise ValueError("lineId (draft line) is required for re-inspect")

    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
            (lot_id,),
        )
        lot = cursor.fetchone()
        if not lot:
            raise ValueError("Lot not found")
        if not _is_processed(lot):
            raise ValueError("Rework re-inspect applies only to processed LW lots")

        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = 'Rework'
            FOR UPDATE
            """,
            (line_id,),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Draft rework line not found — save before re-inspect")

        new_lot_no = str(lot.get("new_lot_no") or "").strip()
        if str(draft.get("source_lot_no") or "").strip() != new_lot_no:
            raise ValueError("Draft line does not match the selected LW lot")

        insp = int(draft.get("inspected_qty") or 0)
        qa = int(draft.get("qa_qty") or 0)
        if insp <= 0:
            raise ValueError("Inspected QTY must be greater than 0 before re-inspect")
        if qa > insp:
            raise ValueError("QA cannot exceed Inspected QTY for rework re-inspect")

        pool_avail = int(lot.get("rework_pool") or 0)
        if insp > pool_avail:
            raise ValueError("Inspected QTY cannot exceed available rework pool")

        cycle_okayed = insp - qa
        auto_approve = qa == 0

        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = 'Rework' AND production_date = %s
            FOR UPDATE
            """,
            (lot_id, wd),
        )
        committed = cursor.fetchone()

        if committed:
            cursor.execute(
                """
                UPDATE laser_welding_line SET
                    inspected_qty = inspected_qty + %s,
                    qa_qty = qa_qty + %s,
                    source_lot_no = %s
                WHERE line_id = %s
                """,
                (insp, qa, new_lot_no, committed["line_id"]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, line_type, source_lot_no, production_date, inspected_qty, qa_qty)
                VALUES (%s, %s, 'Rework', %s, %s, %s, %s)
                """,
                (
                    draft.get("part_number") or lot.get("part_number"),
                    lot_id,
                    new_lot_no,
                    wd,
                    insp,
                    qa,
                ),
            )

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (line_id,))

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                rework_pool = rework_pool - %s,
                total_qa = total_qa + %s,
                total_okayed = total_okayed + %s,
                processed_at = NOW(),
                processed_by = %s,
                qa_approved_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                qa_approved_by = CASE WHEN %s THEN %s ELSE NULL END
            WHERE lot_id = %s
            """,
            (
                insp,
                qa,
                cycle_okayed,
                processed_by,
                auto_approve,
                auto_approve,
                processed_by,
                lot_id,
            ),
        )

    return {"lot": _fetch_lot(lot_id)}


def get_lot_by_id(lot_id: int) -> Optional[Dict[str, Any]]:
    return _fetch_lot(lot_id)


def get_qa_rows() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT l.*
        FROM laser_welding_lot l
        WHERE l.total_qa > 0
        ORDER BY l.processed_at DESC, l.lot_id DESC
        """
    )
    return [_lot_to_dict(r, []) for r in rows]


def approve_qa(
    lot_id: int,
    qa_passed: int,
    scrap: int,
    rework: int,
    approved_by: Optional[int] = None,
) -> Dict[str, Any]:
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
            (lot_id,),
        )
        lot = cursor.fetchone()
        if not lot:
            raise ValueError("Lot not found")
        if int(lot.get("total_qa") or 0) <= 0:
            raise ValueError("This lot has no QTY for QA")

        qp = max(0, int(qa_passed or 0))
        sc = max(0, int(scrap or 0))
        rw = max(0, int(rework or 0))
        total_qa = int(lot.get("total_qa") or 0)
        if qp + sc + rw != total_qa:
            raise ValueError(
                f"QA Passed + Scrap + Rework must equal QTY for QA ({total_qa}); "
                f"got {qp + sc + rw}"
            )

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                total_okayed = total_okayed + %s,
                total_qa = 0,
                scrap = scrap + %s,
                rework_pending = rework_pending + %s,
                qa_approved_at = NOW(),
                qa_approved_by = %s
            WHERE lot_id = %s
            """,
            (qp, sc, rw, approved_by, lot_id),
        )
        cursor.execute(
            """
            INSERT INTO laser_welding_line (
                part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
                inspected_qty, qa_qty, scrap_qty, operator_id
            ) VALUES (%s, %s, %s, %s, %s, CURDATE(), %s, %s, %s, %s)
            """,
            (
                lot.get("part_number"),
                lot.get("bom_id"),
                lot_id,
                LINE_QA_DISPOSITION,
                lot.get("new_lot_no") or "",
                total_qa,
                qp,
                sc,
                approved_by,
            ),
        )
    return {"lot": _fetch_lot(lot_id, include_lines=False)}


def get_packing_rows() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT l.*, b.bom_no, b.product_name
        FROM laser_welding_lot l
        LEFT JOIN bom b ON b.bom_id = l.bom_id AND b.is_latest_version = 'Y'
        WHERE l.total_okayed > 0
          AND l.new_lot_no IS NOT NULL
          AND TRIM(l.new_lot_no) != ''
          AND l.new_lot_no NOT LIKE %s
          AND l.new_lot_no NOT LIKE %s
        ORDER BY l.processed_at DESC, l.lot_id DESC
        """,
        ("SA/%", "LBO/%"),
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        part_no = str(row.get("part_number") or "").strip()
        bom_no = str(row.get("bom_no") or "").strip()
        if _is_final_assembly_lot_row(row, bom_no):
            out.append(
                {
                    "lotId": int(row["lot_id"]),
                    "packType": "bom",
                    "partNo": bom_no or part_no,
                    "partName": str(row.get("product_name") or "").strip(),
                    "bomId": str(row["bom_id"]) if row.get("bom_id") else None,
                    "newLotNo": row.get("new_lot_no") or "",
                    "totalOkayed": int(row.get("total_okayed") or 0),
                }
            )
        elif row.get("bom_id") is None and _is_part_inspection_part(part_no):
            out.append(
                {
                    "lotId": int(row["lot_id"]),
                    "packType": "whitelist",
                    "partNo": part_no,
                    "partName": _part_inspection_display_name(part_no) or str(row.get("product_name") or "").strip(),
                    "bomId": None,
                    "newLotNo": row.get("new_lot_no") or "",
                    "totalOkayed": int(row.get("total_okayed") or 0),
                }
            )
    return out


def pack_lot(
    lot_id: int,
    pack_qty: int,
    work_date: Optional[str] = None,
    packed_by: Optional[int] = None,
) -> Dict[str, Any]:
    qty = int(pack_qty or 0)
    wd = _parse_date(work_date) or date.today().strftime("%Y-%m-%d")
    pack_type = ""

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT l.*, b.bom_no, b.product_name, b.cust_id
            FROM laser_welding_lot l
            LEFT JOIN bom b ON b.bom_id = l.bom_id AND b.is_latest_version = 'Y'
            WHERE l.lot_id = %s
            FOR UPDATE
            """,
            (lot_id,),
        )
        lot = cursor.fetchone()
        if not lot:
            raise ValueError("Lot not found")

        available = int(lot.get("total_okayed") or 0)
        if available <= 0:
            raise ValueError("This lot has no quantity available for packing")
        if qty <= 0 or qty > available:
            raise ValueError(f"Pack quantity must be between 1 and {available}")

        new_lot_no = str(lot.get("new_lot_no") or "").strip()
        if not new_lot_no:
            raise ValueError("Lot has no LW lot number")
        if new_lot_no.startswith("SA/") or new_lot_no.startswith("LBO/"):
            raise ValueError("This lot is not eligible for packing")

        part_no = str(lot.get("part_number") or "").strip()
        bom_no = str(lot.get("bom_no") or "").strip()

        if _is_final_assembly_lot_row(lot, bom_no):
            pack_type = "bom"
            item_code = bom_no or part_no
            if not item_code:
                raise ValueError("BOM number not found for this lot")
            meta = pack_inv.resolve_bom_inventory_meta(lot.get("bom_id"), cursor)
            pack_inv.add_inventory_qty(
                cursor,
                item_code,
                qty,
                item_name=meta.get("item_name") or lot.get("product_name") or "",
                cust_id=meta.get("cust_id"),
                plant_id=1,
                revision=meta.get("revision"),
            )
        elif lot.get("bom_id") is None and _is_part_inspection_part(part_no):
            pack_type = "whitelist"
            comp_id = erp_stock.resolve_comp_id(part_no, cursor)
            erp_stock.whitelist_pack_inward(
                cursor,
                comp_id,
                erp_stock.LW_WHITELIST_ERP_PLANT_ID,
                new_lot_no,
                qty,
                user_id=packed_by,
            )
        else:
            raise ValueError("This lot is not eligible for packing")

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                total_okayed = total_okayed - %s,
                processed_at = NOW(),
                processed_by = %s
            WHERE lot_id = %s
            """,
            (qty, packed_by, lot_id),
        )
        cursor.execute(
            """
            INSERT INTO laser_welding_line (
                part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
                inspected_qty, qa_qty, scrap_qty, operator_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, %s)
            """,
            (
                part_no,
                lot.get("bom_id"),
                lot_id,
                LINE_PACKING,
                new_lot_no,
                wd,
                qty,
                packed_by,
            ),
        )

    return {
        "lot": _fetch_lot(lot_id, include_lines=False),
        "packType": pack_type,
        "packQty": qty,
    }


# --- BOM & Final Assembly ---


def get_bom_customers() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT DISTINCT b.cust_id, COALESCE(c.CU_Name, '') AS customer_name
        FROM bom b
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE b.is_latest_version = 'Y' AND b.cust_id IS NOT NULL
        ORDER BY customer_name
        """
    )
    return [
        {
            "custId": int(r["cust_id"]),
            "customerName": r.get("customer_name") or "",
        }
        for r in rows
        if r.get("cust_id") is not None
    ]


def get_boms(cust_id: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = """
        SELECT b.bom_id, b.bom_no, b.product_name, b.cust_id,
               COALESCE(c.CU_Name, '') AS customer_name
        FROM bom b
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE b.is_latest_version = 'Y'
    """
    params: List[Any] = []
    if cust_id is not None:
        sql += " AND b.cust_id = %s"
        params.append(int(cust_id))
    sql += " ORDER BY b.bom_no"
    rows = fetch_all(sql, tuple(params) if params else None)
    return [
        {
            "bomId": str(r["bom_id"]),
            "bomNo": r.get("bom_no") or "",
            "productName": r.get("product_name") or "",
            "custId": int(r["cust_id"]) if r.get("cust_id") is not None else None,
            "customerName": r.get("customer_name") or "",
            "label": f"{r.get('bom_no') or ''} — {r.get('product_name') or ''}".strip(" —"),
        }
        for r in rows
    ]


def _sa_rows_for_bom(bom_id: str) -> List[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    if not bid:
        return []
    return fetch_all(
        """
        SELECT PART_NO, PART_NAME, qty, ITEM_ID
        FROM bom_lin_item
        WHERE bom_id = %s AND UPPER(TRIM(CATEGORY_CODE)) = %s
        ORDER BY PART_NO
        """,
        (bid, SUB_ASSEMBLY_CATEGORY_CODE),
    )


def _sa_item_ids_for_bom(bom_id: str) -> List[int]:
    ids: List[int] = []
    for row in _sa_rows_for_bom(bom_id):
        item_id = row.get("ITEM_ID")
        if item_id is not None:
            ids.append(int(item_id))
    return ids


def _sa_item_id_for_part(bom_id: str, part_no: str) -> int:
    bid = str(bom_id or "").strip()
    pn = str(part_no or "").strip()
    if not bid or not pn:
        raise ValueError("BOM and sub-assembly part are required")
    row = fetch_one(
        """
        SELECT ITEM_ID
        FROM bom_lin_item
        WHERE bom_id = %s AND UPPER(TRIM(CATEGORY_CODE)) = %s
          AND TRIM(PART_NO) = %s
        LIMIT 1
        """,
        (bid, SUB_ASSEMBLY_CATEGORY_CODE, pn),
    )
    if not row or row.get("ITEM_ID") is None:
        raise ValueError(f"Sub-assembly part {pn!r} not found on BOM")
    return int(row["ITEM_ID"])


def bom_has_sub_assembly(bom_id: str) -> bool:
    bid = str(bom_id or "").strip()
    if not bid:
        return False
    row = fetch_one(
        """
        SELECT 1 AS ok
        FROM bom_lin_item sa
        WHERE sa.bom_id = %s AND UPPER(TRIM(sa.CATEGORY_CODE)) = %s
          AND EXISTS (
            SELECT 1 FROM bom_lin_item ch
            WHERE ch.bom_id = sa.bom_id AND ch.PARENT_ITEM_ID = sa.ITEM_ID
          )
        LIMIT 1
        """,
        (bid, SUB_ASSEMBLY_CATEGORY_CODE),
    )
    return bool(row)


def get_sub_assembly_children(
    bom_id: str,
    sub_assembly_part_no: str,
) -> List[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    sa_part = str(sub_assembly_part_no or "").strip()
    if not bid or not sa_part or not bom_has_sub_assembly(bid):
        return []
    sa_item_id = _sa_item_id_for_part(bid, sa_part)
    rows = fetch_all(
        """
        SELECT PART_NO, PART_NAME, qty, CATEGORY_CODE
        FROM bom_lin_item
        WHERE bom_id = %s AND PARENT_ITEM_ID = %s
        ORDER BY PART_NO
        """,
        (bid, sa_item_id),
    )
    return [
        {
            "partNo": r.get("PART_NO") or "",
            "partName": r.get("PART_NAME") or "",
            "qty": int(r.get("qty") or 0),
            "categoryCode": str(r.get("CATEGORY_CODE") or "").strip(),
            "isBoPart": str(r.get("CATEGORY_CODE") or "").strip().upper() == "BO",
        }
        for r in rows
    ]


def get_sub_assembly_parts(bom_id: str) -> List[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    if not bid or not bom_has_sub_assembly(bid):
        return []
    return [
        {
            "partNo": r.get("PART_NO") or "",
            "partName": r.get("PART_NAME") or "",
            "qty": int(r.get("qty") or 0),
        }
        for r in _sa_rows_for_bom(bid)
    ]


def get_laser_welding_bom_children(bom_id: str) -> List[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    if not bid:
        return []
    has_sub_assembly = bom_has_sub_assembly(bid)
    if has_sub_assembly:
        sa_item_ids = _sa_item_ids_for_bom(bid)
        if sa_item_ids:
            id_placeholders = ", ".join(["%s"] * len(sa_item_ids))
            direct = fetch_all(
                f"""
                SELECT PART_NO, PART_NAME, qty
                FROM bom_lin_item
                WHERE bom_id = %s AND CATEGORY_CODE = 'SS'
                  AND PARENT_ITEM_ID != 0
                  AND PARENT_ITEM_ID NOT IN ({id_placeholders})
                ORDER BY PART_NO
                """,
                (bid, *sa_item_ids),
            )
        else:
            direct = []
        sub_parts = get_sub_assembly_parts(bid)
    else:
        direct = fetch_all(
            """
            SELECT PART_NO, PART_NAME, qty
            FROM bom_lin_item
            WHERE bom_id = %s AND CATEGORY_CODE = 'SS'
              AND PARENT_ITEM_ID != 0
            ORDER BY PART_NO
            """,
            (bid,),
        )
        sub_parts = []
    result: List[Dict[str, Any]] = []
    seen: set = set()
    for r in list(direct) + sub_parts:
        pn = str(r.get("PART_NO") or r.get("partNo") or "").strip()
        if not pn or pn in seen:
            continue
        seen.add(pn)
        result.append({
            "partNo": pn,
            "partName": r.get("PART_NAME") or r.get("partName") or "",
            "qty": int(r.get("qty") or 0),
        })
    return sorted(result, key=lambda x: x["partNo"])


def get_bom_children(bom_id: str) -> List[Dict[str, Any]]:
    return get_laser_welding_bom_children(bom_id)


def _assembly_row_from_lot(lot: Dict[str, Any], lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if lines is None:
        lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = %s
            ORDER BY line_id
            """,
            (lot["lot_id"], LINE_WELDING_CONSUME),
        )
    processed = _is_processed(lot)
    line_dicts = [_line_to_dict(ln) for ln in lines]
    d = _lot_to_dict(lot, line_dicts)
    d.update(_row_machine_from_lines(line_dicts))
    d["rowKey"] = f"asm:{lot['lot_id']}"
    d["isDraft"] = not processed
    d["isPending"] = not processed
    d["isAssembly"] = True
    d["batchMode"] = "assembly"
    d["weldQty"] = int(lot.get("inspection_pending") or 0) if processed else 0
    d["customerName"] = lot.get("customer_name") or ""
    return d


def get_assembly_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")

    result: List[Dict[str, Any]] = []

    draft_lines = fetch_all(
        """
        SELECT ln.*, b.product_name, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.lot_id IS NULL
          AND ln.line_type = %s
          AND ln.production_date = %s
          AND ln.source_lot_no = %s
          AND ln.inspected_qty = 0
        ORDER BY ln.line_id DESC
        """,
        (LINE_WELDING_CONSUME, wd, SESSION_SOURCE_LOT),
    )
    for line in draft_lines:
        bom = None
        if line.get("bom_id"):
            bom = {
                "bom_id": line["bom_id"],
                "product_name": line.get("product_name"),
            }
        result.append(
            _draft_session_row_from_line(
                line,
                "assembly",
                bom=bom,
                customer_name=str(line.get("customer_name") or ""),
            )
        )

    lots = fetch_all(
        """
        SELECT l.*, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_lot l
        LEFT JOIN bom b ON b.bom_id = l.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE l.work_date = %s AND l.bom_id IS NOT NULL AND l.new_lot_no IS NOT NULL
          AND TRIM(l.part_number) = TRIM(b.bom_no)
        ORDER BY l.lot_id DESC
        """,
        (wd,),
    )
    for lot in lots:
        result.append(_assembly_row_from_lot(lot))

    return result


def create_pending_assembly(
    bom_id: str,
    operator_id: int,
    machine_id: int,
    work_date: str,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    bid = str(bom_id or "").strip()
    if not bid:
        raise ValueError("BOM is required")
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    op = _fetch_operator(operator_id)
    if not op:
        raise ValueError("Invalid operator — select an active laser-welding operator")
    machine = _fetch_lw_machine(machine_id)
    if not machine:
        raise ValueError("Invalid machine — select an active laser welding machine")

    bom = fetch_one(
        "SELECT bom_id, bom_no, product_name, cust_id FROM bom WHERE bom_id = %s AND is_latest_version = 'Y'",
        (bid,),
    )
    if not bom:
        raise ValueError("BOM not found")

    children = get_bom_children(bid)
    if not children:
        raise ValueError("BOM has no SS child parts for welding")

    bom_no = str(bom["bom_no"] or "").strip()
    existing = fetch_one(
        """
        SELECT line_id FROM laser_welding_line
        WHERE lot_id IS NULL AND line_type = %s AND bom_id = %s
          AND operator_id = %s AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_WELDING_CONSUME, bid, int(operator_id), wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open assembly row already exists for this BOM and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_id, machine_id
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s, %s)
        """,
        (bom_no, bid, LINE_WELDING_CONSUME, SESSION_SOURCE_LOT, wd, int(operator_id), int(machine_id)),
    )
    if not line_id:
        raise ValueError("Failed to create pending assembly row — please try again")
    line = fetch_one(
        """
        SELECT ln.*, b.product_name, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.line_id = %s
        """,
        (line_id,),
    )
    if not line:
        raise ValueError("Pending assembly row could not be loaded — refresh and try again")
    return _draft_session_row_from_line(
        line,
        "assembly",
        bom={"bom_id": bid, "product_name": bom.get("product_name")},
        customer_name=str(line.get("customer_name") or ""),
    )


def get_assembly_child_lots(part_number: str) -> List[Dict[str, Any]]:
    part = str(part_number or "").strip()
    if not part:
        return []
    rows = fetch_all(
        """
        SELECT * FROM laser_welding_lot
        WHERE TRIM(part_number) = %s
          AND new_lot_no IS NOT NULL
          AND total_okayed > 0
        ORDER BY lot_id DESC
        """,
        (part,),
    )
    filtered = [
        r for r in rows
        if r.get("bom_id") is None or _is_sub_assembly_lot_row(r)
    ]
    return [
        {
            "lotId": int(r["lot_id"]),
            "newLotNo": r["new_lot_no"],
            "totalOkayed": int(r["total_okayed"] or 0),
        }
        for r in filtered
    ]


def weld_assembly(
    draft_line_id: int,
    work_date: str,
    weld_qty: int,
    time_taken_minutes: int,
    consumptions: List[Dict[str, Any]],
    operator_id: Optional[int] = None,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if weld_qty <= 0:
        raise ValueError("Weld QTY must be greater than 0")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = %s
              AND source_lot_no = %s
            FOR UPDATE
            """,
            (draft_line_id, LINE_WELDING_CONSUME, SESSION_SOURCE_LOT),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Pending assembly row not found — add BOM and operator first")

        pd = draft.get("production_date")
        draft_wd = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")[:10]
        if draft_wd != wd:
            raise ValueError("Work date does not match the pending row")

        bom_id = str(draft.get("bom_id") or "").strip()
        line_operator = int(operator_id or draft.get("operator_id") or 0)
        if not line_operator:
            raise ValueError("Operator is required")
        line_machine = int(draft.get("machine_id") or 0)
        if not line_machine:
            raise ValueError("Machine is required — add BOM, operator, and machine first")

        bom = fetch_one(
            "SELECT bom_id, bom_no, product_name FROM bom WHERE bom_id = %s AND is_latest_version = 'Y'",
            (bom_id,),
        )
        if not bom:
            raise ValueError("BOM not found")

        cursor.execute(
            """
            INSERT INTO laser_welding_lot (
                part_number, bom_id, product_name, new_lot_no, work_date,
                total_inwarded, total_qa, total_okayed, created_by
            ) VALUES (%s, %s, %s, NULL, %s, 0, 0, 0, %s)
            """,
            (
                bom["bom_no"],
                bom_id,
                bom.get("product_name") or "",
                wd,
                processed_by,
            ),
        )
        lot_id = int(cursor.lastrowid or 0)
        if not lot_id:
            raise ValueError("Failed to create assembly lot — please try again")

        cursor.execute(
            "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
            (lot_id,),
        )
        asm_lot = cursor.fetchone()
        bom_children = get_laser_welding_bom_children(bom_id)
        if not bom_children:
            raise ValueError("BOM has no weldable child parts")

        required: Dict[str, int] = {}
        for bc in bom_children:
            pn = str(bc.get("partNo") or "").strip()
            required[pn] = int(bc.get("qty") or 0) * weld_qty

        welded_by_part: Dict[str, int] = {}
        lots_by_part: Dict[str, set] = {}

        for c in consumptions or []:
            part_no = str(c.get("partNumber") or "").strip()
            child_lot_id = int(c.get("childLotId") or 0)
            consumed = int(c.get("consumedQty") or c.get("usedQty") or 0)
            qa = int(c.get("qaQty") or 0)
            scrap = int(c.get("scrapQty") or 0)
            if not part_no or not child_lot_id:
                continue
            if consumed <= 0:
                continue
            if qa + scrap > consumed:
                raise ValueError(f"QA + Scrap cannot exceed Consumed for part {part_no}")
            welded = consumed - qa - scrap
            if welded < 0:
                raise ValueError(f"Invalid quantities for part {part_no}")
            if part_no not in required:
                raise ValueError(f"Part {part_no} is not in this BOM")
            part_lots = lots_by_part.setdefault(part_no, set())
            if child_lot_id in part_lots:
                raise ValueError(f"Duplicate child lot for part {part_no}")
            part_lots.add(child_lot_id)

            cursor.execute(
                "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
                (child_lot_id,),
            )
            child = cursor.fetchone()
            _validate_lw_consumable_child_lot(child, part_no)

            okayed = int(child.get("total_okayed") or 0)
            if consumed > okayed:
                raise ValueError(
                    f"Consumed ({consumed}) exceeds available okayed ({okayed}) "
                    f"for {part_no} lot {child.get('new_lot_no')}"
                )

            cursor.execute(
                """
                UPDATE laser_welding_lot SET
                    total_okayed = total_okayed - %s,
                    total_qa = total_qa + %s,
                    scrap = scrap + %s
                WHERE lot_id = %s
                """,
                (consumed, qa, scrap, child_lot_id),
            )

            welded_by_part[part_no] = welded_by_part.get(part_no, 0) + welded

            cursor.execute(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, child_lot_id, line_type, source_lot_no,
                 production_date, inspected_qty, qa_qty, scrap_qty, operator_id, machine_id, time_taken_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    part_no,
                    lot_id,
                    child_lot_id,
                    LINE_WELDING_CONSUME,
                    child.get("new_lot_no") or "",
                    wd,
                    consumed,
                    qa,
                    scrap,
                    line_operator,
                    line_machine,
                    time_taken_minutes,
                ),
            )

        for pn, req in required.items():
            got = welded_by_part.get(pn, 0)
            if got != req:
                raise ValueError(
                    f"Part {pn}: required welded qty {req} (BOM × weld qty), got {got}"
                )

        work_d = datetime.strptime(wd, "%Y-%m-%d").date()
        new_lot = _generate_next_lot_no(work_d, cursor)

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                new_lot_no = %s,
                inspection_pending = %s,
                processed_at = NOW(),
                processed_by = %s
            WHERE lot_id = %s
            """,
            (new_lot, weld_qty, processed_by, lot_id),
        )

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

    result = _fetch_lot(lot_id)
    return {"newLotNo": new_lot, "lotId": lot_id, "lot": result}


def _resolve_consume_child_lot_id(
    cursor: Any,
    part_number: str,
    child_lot_id: Optional[int],
    source_lot_no: str,
) -> int:
    if child_lot_id:
        return int(child_lot_id)
    source = str(source_lot_no or "").strip()
    pn = str(part_number or "").strip()
    if not source or not pn:
        return 0
    cursor.execute(
        """
        SELECT lot_id FROM laser_welding_lot
        WHERE TRIM(part_number) = %s AND new_lot_no = %s AND bom_id IS NULL
        LIMIT 1
        """,
        (pn, source),
    )
    row = cursor.fetchone()
    return int(row["lot_id"]) if row else 0


def _allocate_removed_scrap_for_part(
    cursor: Any,
    assembly_lot_id: int,
    part_number: str,
    removed_qty: int,
) -> None:
    remaining = int(removed_qty or 0)
    if remaining <= 0:
        return

    pn = str(part_number or "").strip()
    legacy_types = ", ".join(f"'{t}'" for t in LINE_WELDING_CONSUME_LEGACY)
    # Historical Welding_Consume + prior Welding_Rework only (new rework lines inserted after).
    cursor.execute(
        f"""
        SELECT line_id, child_lot_id, part_number, source_lot_no, line_type,
               inspected_qty, qa_qty, scrap_qty
        FROM laser_welding_line
        WHERE lot_id = %s
          AND TRIM(part_number) = %s
          AND line_type IN (%s, %s, %s, %s, {legacy_types})
          AND (child_lot_id IS NOT NULL OR TRIM(source_lot_no) != '')
        ORDER BY updated_at ASC, line_id ASC
        """,
        (assembly_lot_id, pn, LINE_WELDING_CONSUME, LINE_WELDING_REWORK, LINE_SUB_ASSEMBLY_CONSUME, LINE_SUB_ASSEMBLY_REWORK),
    )
    history = cursor.fetchall() or []
    for row in history:
        if remaining <= 0:
            break
        child_lot_id = _resolve_consume_child_lot_id(
            cursor,
            pn,
            row.get("child_lot_id"),
            str(row.get("source_lot_no") or ""),
        )
        if not child_lot_id:
            continue
        good = (
            int(row.get("inspected_qty") or 0)
            - int(row.get("qa_qty") or 0)
            - int(row.get("scrap_qty") or 0)
        )
        if good <= 0:
            continue
        take = min(remaining, good)
        line_id = int(row.get("line_id") or 0)
        cursor.execute(
            "SELECT lot_id FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
            (child_lot_id,),
        )
        if not cursor.fetchone():
            raise ValueError(
                f"Child lot {child_lot_id} not found for scrap allocation ({pn})"
            )
        cursor.execute(
            "UPDATE laser_welding_lot SET scrap = scrap + %s WHERE lot_id = %s",
            (take, child_lot_id),
        )
        if line_id:
            cursor.execute(
                "UPDATE laser_welding_line SET scrap_qty = scrap_qty + %s WHERE line_id = %s",
                (take, line_id),
            )
        cursor.execute(
            """
            INSERT INTO lw_re_work_scrap (part_number, lot_id, scrap_qty, line_id)
            VALUES (%s, %s, %s, %s)
            """,
            (pn, child_lot_id, take, line_id),
        )
        remaining -= take

    if remaining > 0:
        raise ValueError(
            f"Could not allocate all removed qty ({removed_qty}) for part {pn} — "
            f"{remaining} remaining on assembly lot {assembly_lot_id}"
        )


def _allocate_removed_scrap(
    cursor: Any,
    assembly_lot_id: int,
    welded_by_part: Dict[str, int],
    required_by_part: Dict[str, int],
) -> None:
    """FIFO scrap on historical child lots per SS part (BOM × rework qty when welded is 0)."""
    for pn, req in required_by_part.items():
        removed = int(welded_by_part.get(pn) or 0)
        if removed <= 0:
            removed = int(req or 0)
        if removed > 0:
            _allocate_removed_scrap_for_part(cursor, assembly_lot_id, pn, removed)


def get_rework_weld_boms(cust_id: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = """
        SELECT DISTINCT
            b.bom_id,
            b.bom_no,
            b.product_name,
            b.cust_id,
            COALESCE(c.CU_Name, '') AS customer_name
        FROM bom b
        INNER JOIN laser_welding_lot l ON l.bom_id = b.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE b.is_latest_version = 'Y'
          AND l.new_lot_no IS NOT NULL
          AND l.rework_pending > 0
    """
    params: List[Any] = []
    if cust_id is not None:
        sql += " AND b.cust_id = %s"
        params.append(int(cust_id))
    sql += " ORDER BY b.bom_no"
    rows = fetch_all(sql, tuple(params) if params else None)
    return [
        {
            "bomId": str(r["bom_id"]),
            "bomNo": r.get("bom_no") or "",
            "productName": r.get("product_name") or "",
            "custId": int(r["cust_id"]) if r.get("cust_id") is not None else None,
            "customerName": r.get("customer_name") or "",
            "label": f"{r.get('bom_no') or ''} — {r.get('product_name') or ''}".strip(" —"),
        }
        for r in rows
    ]


def get_rework_weld_target_lots(bom_id: str) -> List[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    if not bid:
        return []
    rows = fetch_all(
        """
        SELECT l.lot_id, l.new_lot_no, l.rework_pending
        FROM laser_welding_lot l
        INNER JOIN bom b ON b.bom_id = l.bom_id
        WHERE l.bom_id = %s AND l.new_lot_no IS NOT NULL AND l.rework_pending > 0
          AND TRIM(l.part_number) = TRIM(b.bom_no)
        ORDER BY l.lot_id DESC
        """,
        (bid,),
    )
    return [
        {
            "lotId": int(r["lot_id"]),
            "newLotNo": r["new_lot_no"],
            "reworkPending": int(r["rework_pending"] or 0),
        }
        for r in rows
    ]


def _rework_weld_row_from_lot(
    lot: Dict[str, Any],
    lines: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if lines is None:
        lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = %s
            ORDER BY line_id
            """,
            (lot["lot_id"], LINE_WELDING_REWORK),
        )
    line_dicts = [_line_to_dict(ln) for ln in lines]
    d = _lot_to_dict(lot, line_dicts)
    d.update(_row_machine_from_lines(line_dicts))
    d["rowKey"] = f"rweld:lot:{lot['lot_id']}"
    d["isDraft"] = False
    d["isPending"] = False
    d["isProcessed"] = True
    d["isAssembly"] = True
    d["batchMode"] = "rework_welding"
    d["customerName"] = lot.get("customer_name") or ""
    if line_dicts and not d.get("operatorName"):
        d["operatorName"] = line_dicts[0].get("operatorName") or ""
        d["operatorId"] = line_dicts[0].get("operatorId")
    return d


def get_rework_weld_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")

    result: List[Dict[str, Any]] = []
    draft_lines = fetch_all(
        """
        SELECT ln.*, b.product_name, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.lot_id IS NULL
          AND ln.line_type = %s
          AND ln.production_date = %s
          AND ln.source_lot_no = %s
          AND ln.inspected_qty = 0
        ORDER BY ln.line_id DESC
        """,
        (LINE_WELDING_REWORK, wd, SESSION_SOURCE_LOT),
    )
    for line in draft_lines:
        bom = None
        if line.get("bom_id"):
            bom = {
                "bom_id": line["bom_id"],
                "product_name": line.get("product_name"),
            }
        row = _draft_session_row_from_line(
            line,
            "rework_welding",
            bom=bom,
            customer_name=str(line.get("customer_name") or ""),
        )
        row["batchMode"] = "rework_welding"
        result.append(row)

    committed_lots = fetch_all(
        """
        SELECT DISTINCT l.*, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        INNER JOIN laser_welding_lot l ON l.lot_id = ln.lot_id
        LEFT JOIN bom b ON b.bom_id = l.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.line_type = %s
          AND ln.production_date = %s
          AND ln.lot_id IS NOT NULL
          AND ln.inspected_qty > 0
        ORDER BY l.lot_id DESC
        """,
        (LINE_WELDING_REWORK, wd),
    )
    seen: set = set()
    for lot in committed_lots:
        lid = int(lot["lot_id"])
        if lid in seen:
            continue
        seen.add(lid)
        rw_lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = %s AND production_date = %s
            ORDER BY line_id
            """,
            (lid, LINE_WELDING_REWORK, wd),
        )
        result.append(_rework_weld_row_from_lot(lot, rw_lines))

    return result


def create_pending_rework_weld(
    bom_id: str,
    operator_id: int,
    machine_id: int,
    work_date: str,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    bid = str(bom_id or "").strip()
    if not bid:
        raise ValueError("BOM is required")
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    op = _fetch_operator(operator_id)
    if not op:
        raise ValueError("Invalid operator — select an active laser-welding operator")
    machine = _fetch_lw_machine(machine_id)
    if not machine:
        raise ValueError("Invalid machine — select an active laser welding machine")

    bom = fetch_one(
        "SELECT bom_id, bom_no, product_name, cust_id FROM bom WHERE bom_id = %s AND is_latest_version = 'Y'",
        (bid,),
    )
    if not bom:
        raise ValueError("BOM not found")

    if not get_rework_weld_target_lots(bid):
        raise ValueError("No assembly lots with rework pending for this BOM")

    bom_no = str(bom["bom_no"] or "").strip()
    existing = fetch_one(
        """
        SELECT line_id FROM laser_welding_line
        WHERE lot_id IS NULL AND line_type = %s AND bom_id = %s
          AND operator_id = %s AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_WELDING_REWORK, bid, int(operator_id), wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open re-work welding row already exists for this BOM and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_id, machine_id
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s, %s)
        """,
        (bom_no, bid, LINE_WELDING_REWORK, SESSION_SOURCE_LOT, wd, int(operator_id), int(machine_id)),
    )
    if not line_id:
        raise ValueError("Failed to create pending re-work welding row — please try again")
    line = fetch_one(
        """
        SELECT ln.*, b.product_name, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.line_id = %s
        """,
        (line_id,),
    )
    if not line:
        raise ValueError("Pending re-work welding row could not be loaded — refresh and try again")
    row = _draft_session_row_from_line(
        line,
        "rework_welding",
        bom={"bom_id": bid, "product_name": bom.get("product_name")},
        customer_name=str(line.get("customer_name") or ""),
    )
    row["batchMode"] = "rework_welding"
    return row


def weld_rework_assembly(
    draft_line_id: int,
    work_date: str,
    target_lot_id: int,
    rework_qty: int,
    time_taken_minutes: int,
    consumptions: List[Dict[str, Any]],
    operator_id: Optional[int] = None,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if rework_qty <= 0:
        raise ValueError("Re-work QTY must be greater than 0")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    target_id = int(target_lot_id or 0)
    if not target_id:
        raise ValueError("Target assembly lot is required")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = %s
              AND source_lot_no = %s
            FOR UPDATE
            """,
            (draft_line_id, LINE_WELDING_REWORK, SESSION_SOURCE_LOT),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Pending re-work welding row not found — add BOM and operator first")

        pd = draft.get("production_date")
        draft_wd = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")[:10]
        if draft_wd != wd:
            raise ValueError("Work date does not match the pending row")

        bom_id = str(draft.get("bom_id") or "").strip()
        line_operator = int(operator_id or draft.get("operator_id") or 0)
        if not line_operator:
            raise ValueError("Operator is required")
        line_machine = int(draft.get("machine_id") or 0)
        if not line_machine:
            raise ValueError("Machine is required — add BOM, operator, and machine first")

        cursor.execute(
            """
            SELECT * FROM laser_welding_lot
            WHERE lot_id = %s AND bom_id IS NOT NULL AND new_lot_no IS NOT NULL
            FOR UPDATE
            """,
            (target_id,),
        )
        asm_lot = cursor.fetchone()
        if not asm_lot:
            raise ValueError("Target assembly lot not found")
        if bom_id and str(asm_lot.get("bom_id") or "") != bom_id:
            raise ValueError("Target lot does not belong to the selected BOM")

        if not _is_final_assembly_lot_row(asm_lot):
            raise ValueError("Target lot is not a final assembly lot")

        pending = int(asm_lot.get("rework_pending") or 0)
        if rework_qty > pending:
            raise ValueError(
                f"Re-work QTY ({rework_qty}) exceeds rework pending ({pending}) "
                f"for lot {asm_lot.get('new_lot_no')}"
            )

        effective_bom_id = bom_id or str(asm_lot.get("bom_id") or "")
        bom_children = get_laser_welding_bom_children(effective_bom_id)
        if not bom_children:
            raise ValueError("BOM has no weldable child parts")

        required: Dict[str, int] = {}
        for bc in bom_children:
            pn = str(bc.get("partNo") or "").strip()
            required[pn] = int(bc.get("qty") or 0) * rework_qty

        welded_by_part: Dict[str, int] = {}
        lots_by_part: Dict[str, set] = {}
        pending_consumptions: List[Dict[str, Any]] = []

        for c in consumptions or []:
            part_no = str(c.get("partNumber") or "").strip()
            child_lot_id = int(c.get("childLotId") or 0)
            consumed = int(c.get("consumedQty") or c.get("usedQty") or 0)
            qa = int(c.get("qaQty") or 0)
            scrap = int(c.get("scrapQty") or 0)
            if not part_no or not child_lot_id:
                continue
            if consumed <= 0:
                continue
            if qa + scrap > consumed:
                raise ValueError(f"QA + Scrap cannot exceed Consumed for part {part_no}")
            welded = consumed - qa - scrap
            if welded < 0:
                raise ValueError(f"Invalid quantities for part {part_no}")
            if part_no not in required:
                raise ValueError(f"Part {part_no} is not in this BOM")

            req = required[part_no]
            if welded > req:
                raise ValueError(
                    f"Welded ({welded}) cannot exceed required ({req}) for part {part_no}"
                )

            part_lots = lots_by_part.setdefault(part_no, set())
            if child_lot_id in part_lots:
                raise ValueError(f"Duplicate child lot for part {part_no}")
            part_lots.add(child_lot_id)

            cursor.execute(
                "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
                (child_lot_id,),
            )
            child = cursor.fetchone()
            _validate_lw_consumable_child_lot(child, part_no)

            okayed = int(child.get("total_okayed") or 0)
            if consumed > okayed:
                raise ValueError(
                    f"Consumed ({consumed}) exceeds available okayed ({okayed}) "
                    f"for {part_no} lot {child.get('new_lot_no')}"
                )

            welded_by_part[part_no] = welded_by_part.get(part_no, 0) + welded
            pending_consumptions.append({
                "part_no": part_no,
                "child_lot_id": child_lot_id,
                "child": child,
                "consumed": consumed,
                "qa": qa,
                "scrap": scrap,
            })

        for pn, req in required.items():
            got = welded_by_part.get(pn, 0)
            if got > req:
                raise ValueError(
                    f"Part {pn}: welded qty {got} exceeds required {req} (BOM × re-work qty)"
                )

        # Allocate scrap on original child lots before recording new rework consumption lines.
        _allocate_removed_scrap(cursor, target_id, welded_by_part, required)

        for c in pending_consumptions:
            part_no = c["part_no"]
            child_lot_id = c["child_lot_id"]
            child = c["child"]
            consumed = c["consumed"]
            qa = c["qa"]
            scrap = c["scrap"]

            cursor.execute(
                """
                UPDATE laser_welding_lot SET
                    total_okayed = total_okayed - %s,
                    total_qa = total_qa + %s,
                    scrap = scrap + %s
                WHERE lot_id = %s
                """,
                (consumed, qa, scrap, child_lot_id),
            )

            cursor.execute(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, child_lot_id, line_type, source_lot_no,
                 production_date, inspected_qty, qa_qty, scrap_qty, operator_id, machine_id, time_taken_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    part_no,
                    target_id,
                    child_lot_id,
                    LINE_WELDING_REWORK,
                    child.get("new_lot_no") or "",
                    wd,
                    consumed,
                    qa,
                    scrap,
                    line_operator,
                    line_machine,
                    time_taken_minutes,
                ),
            )

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                rework_pending = rework_pending - %s,
                inspection_pending = inspection_pending + %s,
                processed_by = %s
            WHERE lot_id = %s
            """,
            (rework_qty, rework_qty, processed_by, target_id),
        )

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

        saved_lot_no = str(asm_lot.get("new_lot_no") or "")
        removed_total = sum(
            int(welded_by_part.get(pn) or 0) or int(req or 0)
            for pn, req in required.items()
        )

    result = _fetch_lot(target_id)
    return {
        "lotId": target_id,
        "newLotNo": result.get("newLotNo") if result else saved_lot_no,
        "lot": result,
        "removedQty": removed_total,
    }


# --- Sub-Assembly ---


def _sub_assembly_bom_qualifier_sql(alias: str = "b") -> str:
    return f"""
        EXISTS (
          SELECT 1 FROM bom_lin_item bl_ch
          WHERE bl_ch.bom_id = {alias}.bom_id
            AND bl_ch.PARENT_ITEM_ID = bl.ITEM_ID
        )
    """


def get_all_sub_assembly_parts(
    cust_id: Optional[int] = None,
    bom_id: Optional[str] = None,
    rework_only: bool = False,
) -> List[Dict[str, Any]]:
    sql = f"""
        SELECT DISTINCT
            b.bom_id,
            b.bom_no,
            b.product_name,
            b.cust_id,
            COALESCE(c.CU_Name, '') AS customer_name,
            bl.PART_NO,
            bl.PART_NAME,
            bl.qty
        FROM bom b
        INNER JOIN bom_lin_item bl ON bl.bom_id = b.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE b.is_latest_version = 'Y'
          AND UPPER(TRIM(bl.CATEGORY_CODE)) = %s
          AND {_sub_assembly_bom_qualifier_sql("b")}
    """
    params: List[Any] = [SUB_ASSEMBLY_CATEGORY_CODE]
    if cust_id is not None:
        sql += " AND b.cust_id = %s"
        params.append(int(cust_id))
    if bom_id:
        sql += " AND b.bom_id = %s"
        params.append(str(bom_id).strip())
    if rework_only:
        sql += """
          AND EXISTS (
            SELECT 1 FROM laser_welding_lot l
            WHERE l.bom_id = b.bom_id
              AND l.new_lot_no IS NOT NULL
              AND l.rework_pending > 0
              AND TRIM(l.part_number) = TRIM(bl.PART_NO)
              AND TRIM(l.part_number) != TRIM(b.bom_no)
          )
        """
    sql += " ORDER BY bl.PART_NO, b.bom_no"
    rows = fetch_all(sql, tuple(params))
    result: List[Dict[str, Any]] = []
    seen: set = set()
    for r in rows:
        bid = str(r["bom_id"])
        pn = str(r.get("PART_NO") or "").strip()
        key = (bid, pn)
        if not pn or key in seen:
            continue
        seen.add(key)
        bom_no = str(r.get("bom_no") or "")
        part_name = str(r.get("PART_NAME") or "")
        result.append({
            "bomId": bid,
            "bomNo": bom_no,
            "productName": r.get("product_name") or "",
            "custId": int(r["cust_id"]) if r.get("cust_id") is not None else None,
            "customerName": r.get("customer_name") or "",
            "partNo": pn,
            "partName": part_name,
            "qty": int(r.get("qty") or 0),
            "label": f"{pn} — {part_name} ({bom_no})".strip(" —"),
        })
    return result


def _resolve_sub_assembly_bom_id(
    sub_assembly_part_no: str,
    bom_id: Optional[str] = None,
    rework_only: bool = False,
) -> str:
    bid = str(bom_id or "").strip()
    sa_part = str(sub_assembly_part_no or "").strip()
    if not sa_part:
        raise ValueError("Sub-assembly part is required")
    if bid:
        return bid
    matches = [
        p for p in get_all_sub_assembly_parts(rework_only=rework_only)
        if p["partNo"] == sa_part
    ]
    if not matches:
        raise ValueError("Sub-assembly part not found")
    if len(matches) > 1:
        raise ValueError(
            "Sub-assembly part exists on multiple BOMs — select the BOM-specific entry"
        )
    return matches[0]["bomId"]


def get_sub_assembly_boms(cust_id: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = """
        SELECT DISTINCT
            b.bom_id,
            b.bom_no,
            b.product_name,
            b.cust_id,
            COALESCE(c.CU_Name, '') AS customer_name
        FROM bom b
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE b.is_latest_version = 'Y'
    """
    params: List[Any] = []
    if cust_id is not None:
        sql += " AND b.cust_id = %s"
        params.append(int(cust_id))
    sql += " ORDER BY b.bom_no"
    rows = fetch_all(sql, tuple(params) if params else None)
    return [
        {
            "bomId": str(r["bom_id"]),
            "bomNo": r.get("bom_no") or "",
            "productName": r.get("product_name") or "",
            "custId": int(r["cust_id"]) if r.get("cust_id") is not None else None,
            "customerName": r.get("customer_name") or "",
            "label": f"{r.get('bom_no') or ''} — {r.get('product_name') or ''}".strip(" —"),
        }
        for r in rows
        if bom_has_sub_assembly(str(r["bom_id"]))
    ]


def _sub_assembly_row_from_lot(
    lot: Dict[str, Any],
    lines: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if lines is None:
        lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = %s
            ORDER BY line_id
            """,
            (lot["lot_id"], LINE_SUB_ASSEMBLY_CONSUME),
        )
    processed = _is_processed(lot)
    d = _lot_to_dict(lot, [_line_to_dict(ln) for ln in lines])
    d["rowKey"] = f"sa:{lot['lot_id']}"
    d["isDraft"] = not processed
    d["isPending"] = not processed
    d["isAssembly"] = True
    d["isSubAssembly"] = True
    d["batchMode"] = "sub_assembly"
    d["subAssemblyPartNo"] = str(lot.get("part_number") or "")
    d["weldQty"] = int(lot.get("inspection_pending") or 0) if processed else 0
    d["customerName"] = lot.get("customer_name") or ""
    return d


def get_sub_assembly_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")

    result: List[Dict[str, Any]] = []
    draft_lines = fetch_all(
        """
        SELECT ln.*, b.bom_no, b.product_name, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.lot_id IS NULL
          AND ln.line_type = %s
          AND ln.production_date = %s
          AND ln.source_lot_no = %s
          AND ln.inspected_qty = 0
        ORDER BY ln.line_id DESC
        """,
        (LINE_SUB_ASSEMBLY_CONSUME, wd, SESSION_SOURCE_LOT),
    )
    for line in draft_lines:
        bom = None
        if line.get("bom_id"):
            bom = {
                "bom_id": line["bom_id"],
                "product_name": line.get("product_name"),
                "bom_no": line.get("bom_no"),
            }
        row = _draft_session_row_from_line(
            line,
            "sub_assembly",
            bom=bom,
            customer_name=str(line.get("customer_name") or ""),
        )
        row["isSubAssembly"] = True
        row["subAssemblyPartNo"] = str(line.get("part_number") or "")
        row["partNumber"] = str(line.get("bom_no") or line.get("part_number") or "")
        result.append(row)

    lots = fetch_all(
        """
        SELECT l.*, b.bom_no, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_lot l
        LEFT JOIN bom b ON b.bom_id = l.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE l.work_date = %s AND l.bom_id IS NOT NULL AND l.new_lot_no IS NOT NULL
          AND TRIM(l.part_number) != TRIM(COALESCE(b.bom_no, ''))
        ORDER BY l.lot_id DESC
        """,
        (wd,),
    )
    for lot in lots:
        if not _is_sub_assembly_lot_row(lot, str(lot.get("bom_no") or "")):
            continue
        result.append(_sub_assembly_row_from_lot(lot))

    return result


def create_pending_sub_assembly(
    sub_assembly_part_no: str,
    operator_id: int,
    work_date: str,
    bom_id: Optional[str] = None,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    sa_part = str(sub_assembly_part_no or "").strip()
    if not sa_part:
        raise ValueError("Sub-assembly part is required")
    bid = _resolve_sub_assembly_bom_id(sa_part, bom_id)
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    op = _fetch_operator(operator_id)
    if not op:
        raise ValueError("Invalid operator — select an active laser-welding operator")

    bom = fetch_one(
        "SELECT bom_id, bom_no, product_name, cust_id FROM bom WHERE bom_id = %s AND is_latest_version = 'Y'",
        (bid,),
    )
    if not bom:
        raise ValueError("BOM not found")

    sa_parts = {p["partNo"]: p for p in get_sub_assembly_parts(bid)}
    if sa_part not in sa_parts:
        raise ValueError("Sub-assembly part is not valid for this BOM")

    children = get_sub_assembly_children(bid, sa_part)
    if not children:
        raise ValueError("BOM has no sub-assembly child parts")

    existing = fetch_one(
        """
        SELECT line_id FROM laser_welding_line
        WHERE lot_id IS NULL AND line_type = %s AND bom_id = %s
          AND part_number = %s AND operator_id = %s
          AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_SUB_ASSEMBLY_CONSUME, bid, sa_part, int(operator_id), wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError(
            "An open sub-assembly row already exists for this BOM, part, and operator today"
        )

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_id
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (sa_part, bid, LINE_SUB_ASSEMBLY_CONSUME, SESSION_SOURCE_LOT, wd, int(operator_id)),
    )
    if not line_id:
        raise ValueError("Failed to create pending sub-assembly row — please try again")
    line = fetch_one(
        """
        SELECT ln.*, b.bom_no, b.product_name, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.line_id = %s
        """,
        (line_id,),
    )
    if not line:
        raise ValueError("Pending sub-assembly row could not be loaded — refresh and try again")
    row = _draft_session_row_from_line(
        line,
        "sub_assembly",
        bom={"bom_id": bid, "product_name": bom.get("product_name"), "bom_no": bom.get("bom_no")},
        customer_name=str(line.get("customer_name") or ""),
    )
    row["isSubAssembly"] = True
    row["subAssemblyPartNo"] = sa_part
    row["partNumber"] = str(bom.get("bom_no") or "")
    row["partName"] = sa_parts[sa_part].get("partName") or sa_part
    return row


def get_sub_assembly_child_lots(part_number: str) -> List[Dict[str, Any]]:
    part = str(part_number or "").strip()
    if not part:
        return []
    rows = fetch_all(
        """
        SELECT lot_id, new_lot_no, total_okayed, total_qa
        FROM laser_welding_lot
        WHERE TRIM(part_number) = %s
          AND bom_id IS NULL
          AND new_lot_no IS NOT NULL
          AND total_okayed > 0
        ORDER BY lot_id DESC
        """,
        (part,),
    )
    return [
        {
            "lotId": int(r["lot_id"]),
            "newLotNo": r["new_lot_no"],
            "totalOkayed": int(r["total_okayed"] or 0),
        }
        for r in rows
    ]


def weld_sub_assembly(
    draft_line_id: int,
    work_date: str,
    weld_qty: int,
    time_taken_minutes: int,
    consumptions: List[Dict[str, Any]],
    operator_id: Optional[int] = None,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if weld_qty <= 0:
        raise ValueError("Weld QTY must be greater than 0")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = %s
              AND source_lot_no = %s
            FOR UPDATE
            """,
            (draft_line_id, LINE_SUB_ASSEMBLY_CONSUME, SESSION_SOURCE_LOT),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Pending sub-assembly row not found — add BOM, part, and operator first")

        pd = draft.get("production_date")
        draft_wd = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")[:10]
        if draft_wd != wd:
            raise ValueError("Work date does not match the pending row")

        bom_id = str(draft.get("bom_id") or "").strip()
        sa_part = str(draft.get("part_number") or "").strip()
        line_operator = int(operator_id or draft.get("operator_id") or 0)
        if not line_operator:
            raise ValueError("Operator is required")
        if not sa_part:
            raise ValueError("Sub-assembly part is required on the pending row")

        bom = fetch_one(
            "SELECT bom_id, bom_no, product_name FROM bom WHERE bom_id = %s AND is_latest_version = 'Y'",
            (bom_id,),
        )
        if not bom:
            raise ValueError("BOM not found")

        sa_meta = next(
            (p for p in get_sub_assembly_parts(bom_id) if p["partNo"] == sa_part),
            None,
        )
        if not sa_meta:
            raise ValueError("Sub-assembly part is not valid for this BOM")

        bom_children = get_sub_assembly_children(bom_id, sa_part)
        if not bom_children:
            raise ValueError("BOM has no sub-assembly child parts")

        bo_parts = {
            str(bc.get("partNo") or "").strip()
            for bc in bom_children
            if bc.get("isBoPart")
        }

        cursor.execute(
            """
            INSERT INTO laser_welding_lot (
                part_number, bom_id, product_name, new_lot_no, work_date,
                total_inwarded, total_qa, total_okayed, created_by
            ) VALUES (%s, %s, %s, NULL, %s, 0, 0, 0, %s)
            """,
            (
                sa_part,
                bom_id,
                sa_meta.get("partName") or sa_part,
                wd,
                processed_by,
            ),
        )
        lot_id = int(cursor.lastrowid or 0)
        if not lot_id:
            raise ValueError("Failed to create sub-assembly lot — please try again")

        required: Dict[str, int] = {}
        for bc in bom_children:
            pn = str(bc.get("partNo") or "").strip()
            required[pn] = int(bc.get("qty") or 0) * weld_qty

        welded_by_part: Dict[str, int] = {}
        lots_by_part: Dict[str, set] = {}

        for c in consumptions or []:
            part_no = str(c.get("partNumber") or "").strip()
            child_lot_id = int(c.get("childLotId") or 0)
            consumed = int(c.get("consumedQty") or c.get("usedQty") or 0)
            qa = int(c.get("qaQty") or 0)
            scrap = int(c.get("scrapQty") or 0)
            if not part_no or not child_lot_id or consumed <= 0:
                continue
            is_bo_child = part_no in bo_parts
            if is_bo_child:
                qa = 0
                if scrap > consumed:
                    raise ValueError(f"Scrap cannot exceed Consumed for part {part_no}")
            elif qa + scrap > consumed:
                raise ValueError(f"QA + Scrap cannot exceed Consumed for part {part_no}")
            welded = consumed - scrap if is_bo_child else consumed - qa - scrap
            if welded < 0:
                raise ValueError(f"Invalid quantities for part {part_no}")
            if part_no not in required:
                raise ValueError(f"Part {part_no} is not in this sub-assembly BOM")
            part_lots = lots_by_part.setdefault(part_no, set())
            if child_lot_id in part_lots:
                raise ValueError(f"Duplicate child lot for part {part_no}")
            part_lots.add(child_lot_id)

            cursor.execute(
                "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
                (child_lot_id,),
            )
            child = cursor.fetchone()
            _validate_sa_consumable_child_lot(child, part_no)

            okayed = int(child.get("total_okayed") or 0)
            if consumed > okayed:
                raise ValueError(
                    f"Consumed ({consumed}) exceeds available okayed ({okayed}) "
                    f"for {part_no} lot {child.get('new_lot_no')}"
                )

            if is_bo_child:
                cursor.execute(
                    """
                    UPDATE laser_welding_lot SET
                        total_okayed = total_okayed - %s,
                        scrap = scrap + %s
                    WHERE lot_id = %s
                    """,
                    (consumed, scrap, child_lot_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE laser_welding_lot SET
                        total_okayed = total_okayed - %s,
                        total_qa = total_qa + %s,
                        scrap = scrap + %s
                    WHERE lot_id = %s
                    """,
                    (consumed, qa, scrap, child_lot_id),
                )

            welded_by_part[part_no] = welded_by_part.get(part_no, 0) + welded

            cursor.execute(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, child_lot_id, line_type, source_lot_no,
                 production_date, inspected_qty, qa_qty, scrap_qty, operator_id, time_taken_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    part_no,
                    lot_id,
                    child_lot_id,
                    LINE_SUB_ASSEMBLY_CONSUME,
                    child.get("new_lot_no") or "",
                    wd,
                    consumed,
                    qa,
                    scrap,
                    line_operator,
                    time_taken_minutes,
                ),
            )

        for pn, req in required.items():
            got = welded_by_part.get(pn, 0)
            if got != req:
                raise ValueError(
                    f"Part {pn}: required welded qty {req} (BOM × weld qty), got {got}"
                )

        work_d = datetime.strptime(wd, "%Y-%m-%d").date()
        new_lot = _generate_next_sub_assembly_lot_no(work_d, cursor)

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                new_lot_no = %s,
                inspection_pending = %s,
                processed_at = NOW(),
                processed_by = %s
            WHERE lot_id = %s
            """,
            (new_lot, weld_qty, processed_by, lot_id),
        )

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

    result = _fetch_lot(lot_id)
    return {"newLotNo": new_lot, "lotId": lot_id, "lot": result}


def get_rework_sub_assembly_boms(cust_id: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = """
        SELECT DISTINCT
            b.bom_id,
            b.bom_no,
            b.product_name,
            b.cust_id,
            COALESCE(c.CU_Name, '') AS customer_name
        FROM bom b
        INNER JOIN laser_welding_lot l ON l.bom_id = b.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE b.is_latest_version = 'Y'
          AND l.new_lot_no IS NOT NULL
          AND l.rework_pending > 0
          AND TRIM(l.part_number) != TRIM(b.bom_no)
    """
    params: List[Any] = []
    if cust_id is not None:
        sql += " AND b.cust_id = %s"
        params.append(int(cust_id))
    sql += " ORDER BY b.bom_no"
    rows = fetch_all(sql, tuple(params) if params else None)
    return [
        {
            "bomId": str(r["bom_id"]),
            "bomNo": r.get("bom_no") or "",
            "productName": r.get("product_name") or "",
            "custId": int(r["cust_id"]) if r.get("cust_id") is not None else None,
            "customerName": r.get("customer_name") or "",
            "label": f"{r.get('bom_no') or ''} — {r.get('product_name') or ''}".strip(" —"),
        }
        for r in rows
    ]


def get_rework_sub_assembly_target_lots(
    bom_id: str,
    sub_assembly_part_no: Optional[str] = None,
) -> List[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    if not bid:
        return []
    sa_part = str(sub_assembly_part_no or "").strip()
    if sa_part:
        rows = fetch_all(
            """
            SELECT l.lot_id, l.new_lot_no, l.rework_pending, l.part_number
            FROM laser_welding_lot l
            INNER JOIN bom b ON b.bom_id = l.bom_id
            WHERE l.bom_id = %s AND l.new_lot_no IS NOT NULL AND l.rework_pending > 0
              AND TRIM(l.part_number) = %s
              AND TRIM(l.part_number) != TRIM(b.bom_no)
            ORDER BY l.lot_id DESC
            """,
            (bid, sa_part),
        )
    else:
        rows = fetch_all(
            """
            SELECT l.lot_id, l.new_lot_no, l.rework_pending, l.part_number
            FROM laser_welding_lot l
            INNER JOIN bom b ON b.bom_id = l.bom_id
            WHERE l.bom_id = %s AND l.new_lot_no IS NOT NULL AND l.rework_pending > 0
              AND TRIM(l.part_number) != TRIM(b.bom_no)
            ORDER BY l.lot_id DESC
            """,
            (bid,),
        )
    return [
        {
            "lotId": int(r["lot_id"]),
            "newLotNo": r["new_lot_no"],
            "reworkPending": int(r["rework_pending"] or 0),
            "subAssemblyPartNo": str(r.get("part_number") or ""),
        }
        for r in rows
    ]


def _rework_sub_assembly_row_from_lot(
    lot: Dict[str, Any],
    lines: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if lines is None:
        lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = %s
            ORDER BY line_id
            """,
            (lot["lot_id"], LINE_SUB_ASSEMBLY_REWORK),
        )
    line_dicts = [_line_to_dict(ln) for ln in lines]
    d = _lot_to_dict(lot, line_dicts)
    d["rowKey"] = f"sa-rw:lot:{lot['lot_id']}"
    d["isDraft"] = False
    d["isPending"] = False
    d["isProcessed"] = True
    d["isAssembly"] = True
    d["isSubAssembly"] = True
    d["batchMode"] = "rework_sub_assembly"
    d["subAssemblyPartNo"] = str(lot.get("part_number") or "")
    d["customerName"] = lot.get("customer_name") or ""
    if line_dicts and not d.get("operatorName"):
        d["operatorName"] = line_dicts[0].get("operatorName") or ""
        d["operatorId"] = line_dicts[0].get("operatorId")
    return d


def get_rework_sub_assembly_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")

    result: List[Dict[str, Any]] = []
    draft_lines = fetch_all(
        """
        SELECT ln.*, b.bom_no, b.product_name, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.lot_id IS NULL
          AND ln.line_type = %s
          AND ln.production_date = %s
          AND ln.source_lot_no = %s
          AND ln.inspected_qty = 0
        ORDER BY ln.line_id DESC
        """,
        (LINE_SUB_ASSEMBLY_REWORK, wd, SESSION_SOURCE_LOT),
    )
    for line in draft_lines:
        bom = None
        if line.get("bom_id"):
            bom = {
                "bom_id": line["bom_id"],
                "product_name": line.get("product_name"),
                "bom_no": line.get("bom_no"),
            }
        row = _draft_session_row_from_line(
            line,
            "rework_sub_assembly",
            bom=bom,
            customer_name=str(line.get("customer_name") or ""),
        )
        row["batchMode"] = "rework_sub_assembly"
        row["isSubAssembly"] = True
        row["subAssemblyPartNo"] = str(line.get("part_number") or "")
        row["partNumber"] = str(line.get("bom_no") or "")
        result.append(row)

    committed_lots = fetch_all(
        """
        SELECT DISTINCT l.*, b.bom_no, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        INNER JOIN laser_welding_lot l ON l.lot_id = ln.lot_id
        LEFT JOIN bom b ON b.bom_id = l.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.line_type = %s
          AND ln.production_date = %s
          AND ln.lot_id IS NOT NULL
          AND ln.inspected_qty > 0
          AND TRIM(l.part_number) != TRIM(COALESCE(b.bom_no, ''))
        ORDER BY l.lot_id DESC
        """,
        (LINE_SUB_ASSEMBLY_REWORK, wd),
    )
    seen: set = set()
    for lot in committed_lots:
        lid = int(lot["lot_id"])
        if lid in seen:
            continue
        seen.add(lid)
        rw_lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = %s AND production_date = %s
            ORDER BY line_id
            """,
            (lid, LINE_SUB_ASSEMBLY_REWORK, wd),
        )
        result.append(_rework_sub_assembly_row_from_lot(lot, rw_lines))

    return result


def create_pending_rework_sub_assembly(
    sub_assembly_part_no: str,
    operator_id: int,
    work_date: str,
    bom_id: Optional[str] = None,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    sa_part = str(sub_assembly_part_no or "").strip()
    if not sa_part:
        raise ValueError("Sub-assembly part is required")
    bid = _resolve_sub_assembly_bom_id(sa_part, bom_id, rework_only=True)
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    op = _fetch_operator(operator_id)
    if not op:
        raise ValueError("Invalid operator — select an active laser-welding operator")

    bom = fetch_one(
        "SELECT bom_id, bom_no, product_name, cust_id FROM bom WHERE bom_id = %s AND is_latest_version = 'Y'",
        (bid,),
    )
    if not bom:
        raise ValueError("BOM not found")

    if not get_rework_sub_assembly_target_lots(bid, sa_part):
        raise ValueError("No sub-assembly lots with rework pending for this part")

    existing = fetch_one(
        """
        SELECT line_id FROM laser_welding_line
        WHERE lot_id IS NULL AND line_type = %s AND bom_id = %s
          AND part_number = %s AND operator_id = %s
          AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_SUB_ASSEMBLY_REWORK, bid, sa_part, int(operator_id), wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError(
            "An open re-work sub-assembly row already exists for this BOM, part, and operator today"
        )

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_id
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (sa_part, bid, LINE_SUB_ASSEMBLY_REWORK, SESSION_SOURCE_LOT, wd, int(operator_id)),
    )
    if not line_id:
        raise ValueError("Failed to create pending re-work sub-assembly row — please try again")
    line = fetch_one(
        """
        SELECT ln.*, b.bom_no, b.product_name, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE ln.line_id = %s
        """,
        (line_id,),
    )
    if not line:
        raise ValueError("Pending re-work sub-assembly row could not be loaded — refresh and try again")
    row = _draft_session_row_from_line(
        line,
        "rework_sub_assembly",
        bom={"bom_id": bid, "product_name": bom.get("product_name"), "bom_no": bom.get("bom_no")},
        customer_name=str(line.get("customer_name") or ""),
    )
    row["batchMode"] = "rework_sub_assembly"
    row["isSubAssembly"] = True
    row["subAssemblyPartNo"] = sa_part
    row["partNumber"] = str(bom.get("bom_no") or "")
    return row


def _allocate_removed_scrap_for_sa_part(
    cursor: Any,
    lot_id: int,
    part_number: str,
    removed_qty: int,
) -> None:
    remaining = int(removed_qty or 0)
    if remaining <= 0:
        return
    pn = str(part_number or "").strip()
    cursor.execute(
        """
        SELECT line_id, child_lot_id, part_number, source_lot_no, line_type,
               inspected_qty, qa_qty, scrap_qty
        FROM laser_welding_line
        WHERE lot_id = %s
          AND TRIM(part_number) = %s
          AND line_type IN (%s, %s)
          AND (child_lot_id IS NOT NULL OR TRIM(source_lot_no) != '')
        ORDER BY updated_at ASC, line_id ASC
        """,
        (lot_id, pn, LINE_SUB_ASSEMBLY_CONSUME, LINE_SUB_ASSEMBLY_REWORK),
    )
    history = cursor.fetchall() or []
    for row in history:
        if remaining <= 0:
            break
        child_lot_id = _resolve_consume_child_lot_id(
            cursor,
            pn,
            row.get("child_lot_id"),
            str(row.get("source_lot_no") or ""),
        )
        if not child_lot_id:
            continue
        good = (
            int(row.get("inspected_qty") or 0)
            - int(row.get("qa_qty") or 0)
            - int(row.get("scrap_qty") or 0)
        )
        if good <= 0:
            continue
        take = min(remaining, good)
        line_id = int(row.get("line_id") or 0)
        cursor.execute(
            "SELECT lot_id FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
            (child_lot_id,),
        )
        if not cursor.fetchone():
            raise ValueError(
                f"Child lot {child_lot_id} not found for scrap allocation ({pn})"
            )
        cursor.execute(
            "UPDATE laser_welding_lot SET scrap = scrap + %s WHERE lot_id = %s",
            (take, child_lot_id),
        )
        if line_id:
            cursor.execute(
                "UPDATE laser_welding_line SET scrap_qty = scrap_qty + %s WHERE line_id = %s",
                (take, line_id),
            )
        cursor.execute(
            """
            INSERT INTO lw_re_work_scrap (part_number, lot_id, scrap_qty, line_id)
            VALUES (%s, %s, %s, %s)
            """,
            (pn, child_lot_id, take, line_id),
        )
        remaining -= take

    if remaining > 0:
        raise ValueError(
            f"Could not allocate all removed qty ({removed_qty}) for part {pn} — "
            f"{remaining} remaining on sub-assembly lot {lot_id}"
        )


def weld_rework_sub_assembly(
    draft_line_id: int,
    work_date: str,
    target_lot_id: int,
    rework_qty: int,
    time_taken_minutes: int,
    consumptions: List[Dict[str, Any]],
    operator_id: Optional[int] = None,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if rework_qty <= 0:
        raise ValueError("Re-work QTY must be greater than 0")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    target_id = int(target_lot_id or 0)
    if not target_id:
        raise ValueError("Target sub-assembly lot is required")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = %s
              AND source_lot_no = %s
            FOR UPDATE
            """,
            (draft_line_id, LINE_SUB_ASSEMBLY_REWORK, SESSION_SOURCE_LOT),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Pending re-work sub-assembly row not found")

        pd = draft.get("production_date")
        draft_wd = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")[:10]
        if draft_wd != wd:
            raise ValueError("Work date does not match the pending row")

        bom_id = str(draft.get("bom_id") or "").strip()
        sa_part = str(draft.get("part_number") or "").strip()
        line_operator = int(operator_id or draft.get("operator_id") or 0)
        if not line_operator:
            raise ValueError("Operator is required")

        cursor.execute(
            """
            SELECT * FROM laser_welding_lot
            WHERE lot_id = %s AND bom_id IS NOT NULL AND new_lot_no IS NOT NULL
            FOR UPDATE
            """,
            (target_id,),
        )
        sa_lot = cursor.fetchone()
        if not sa_lot:
            raise ValueError("Target sub-assembly lot not found")
        if not _is_sub_assembly_lot_row(sa_lot):
            raise ValueError("Target lot is not a sub-assembly lot")
        if bom_id and str(sa_lot.get("bom_id") or "") != bom_id:
            raise ValueError("Target lot does not belong to the selected BOM")
        if sa_part and str(sa_lot.get("part_number") or "").strip() != sa_part:
            raise ValueError("Target lot does not match the sub-assembly part")

        pending = int(sa_lot.get("rework_pending") or 0)
        if rework_qty > pending:
            raise ValueError(
                f"Re-work QTY ({rework_qty}) exceeds rework pending ({pending})"
            )

        effective_bom_id = bom_id or str(sa_lot.get("bom_id") or "")
        bom_children = get_sub_assembly_children(effective_bom_id, sa_part)
        if not bom_children:
            raise ValueError("BOM has no sub-assembly child parts")

        bo_parts = {
            str(bc.get("partNo") or "").strip()
            for bc in bom_children
            if bc.get("isBoPart")
        }

        required: Dict[str, int] = {}
        for bc in bom_children:
            pn = str(bc.get("partNo") or "").strip()
            required[pn] = int(bc.get("qty") or 0) * rework_qty

        welded_by_part: Dict[str, int] = {}
        lots_by_part: Dict[str, set] = {}
        pending_consumptions: List[Dict[str, Any]] = []

        for c in consumptions or []:
            part_no = str(c.get("partNumber") or "").strip()
            child_lot_id = int(c.get("childLotId") or 0)
            consumed = int(c.get("consumedQty") or c.get("usedQty") or 0)
            qa = int(c.get("qaQty") or 0)
            scrap = int(c.get("scrapQty") or 0)
            if not part_no or not child_lot_id or consumed <= 0:
                continue
            is_bo_child = part_no in bo_parts
            if is_bo_child:
                qa = 0
                if scrap > consumed:
                    raise ValueError(f"Scrap cannot exceed Consumed for part {part_no}")
            elif qa + scrap > consumed:
                raise ValueError(f"QA + Scrap cannot exceed Consumed for part {part_no}")
            welded = consumed - scrap if is_bo_child else consumed - qa - scrap
            if part_no not in required:
                raise ValueError(f"Part {part_no} is not in this sub-assembly BOM")
            if welded > required[part_no]:
                raise ValueError(
                    f"Welded ({welded}) cannot exceed required ({required[part_no]}) for {part_no}"
                )
            part_lots = lots_by_part.setdefault(part_no, set())
            if child_lot_id in part_lots:
                raise ValueError(f"Duplicate child lot for part {part_no}")
            part_lots.add(child_lot_id)

            cursor.execute(
                "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
                (child_lot_id,),
            )
            child = cursor.fetchone()
            _validate_sa_consumable_child_lot(child, part_no)

            okayed = int(child.get("total_okayed") or 0)
            if consumed > okayed:
                raise ValueError(
                    f"Consumed ({consumed}) exceeds available okayed ({okayed}) for {part_no}"
                )

            welded_by_part[part_no] = welded_by_part.get(part_no, 0) + welded
            pending_consumptions.append({
                "part_no": part_no,
                "child_lot_id": child_lot_id,
                "child": child,
                "consumed": consumed,
                "qa": qa,
                "scrap": scrap,
                "is_bo_child": is_bo_child,
            })

        for pn, req in required.items():
            got = welded_by_part.get(pn, 0)
            if got > req:
                raise ValueError(f"Part {pn}: welded qty {got} exceeds required {req}")

        for pn, req in required.items():
            removed = int(welded_by_part.get(pn) or 0)
            if removed <= 0:
                removed = int(req or 0)
            if removed > 0:
                _allocate_removed_scrap_for_sa_part(cursor, target_id, pn, removed)

        for c in pending_consumptions:
            if c.get("is_bo_child"):
                cursor.execute(
                    """
                    UPDATE laser_welding_lot SET
                        total_okayed = total_okayed - %s,
                        scrap = scrap + %s
                    WHERE lot_id = %s
                    """,
                    (c["consumed"], c["scrap"], c["child_lot_id"]),
                )
            else:
                cursor.execute(
                    """
                    UPDATE laser_welding_lot SET
                        total_okayed = total_okayed - %s,
                        total_qa = total_qa + %s,
                        scrap = scrap + %s
                    WHERE lot_id = %s
                    """,
                    (c["consumed"], c["qa"], c["scrap"], c["child_lot_id"]),
                )
            cursor.execute(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, child_lot_id, line_type, source_lot_no,
                 production_date, inspected_qty, qa_qty, scrap_qty, operator_id, time_taken_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    c["part_no"],
                    target_id,
                    c["child_lot_id"],
                    LINE_SUB_ASSEMBLY_REWORK,
                    c["child"].get("new_lot_no") or "",
                    wd,
                    c["consumed"],
                    c["qa"],
                    c["scrap"],
                    line_operator,
                    time_taken_minutes,
                ),
            )

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                rework_pending = rework_pending - %s,
                inspection_pending = inspection_pending + %s,
                processed_by = %s
            WHERE lot_id = %s
            """,
            (rework_qty, rework_qty, processed_by, target_id),
        )

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

        saved_lot_no = str(sa_lot.get("new_lot_no") or "")
        removed_total = sum(
            int(welded_by_part.get(pn) or 0) or int(req or 0)
            for pn, req in required.items()
        )

    result = _fetch_lot(target_id)
    return {
        "lotId": target_id,
        "newLotNo": result.get("newLotNo") if result else saved_lot_no,
        "lot": result,
        "removedQty": removed_total,
    }


# --- Cleaning (store inspection) ---


def _cleaning_sub_assembly_flags(
    part_number: Optional[str],
    bom_no: Optional[str],
) -> Dict[str, Any]:
    pn = str(part_number or "").strip()
    bn = str(bom_no or "").strip()
    is_sa = bool(pn and bn and pn != bn)
    out: Dict[str, Any] = {"isSubAssembly": is_sa}
    if is_sa:
        out["subAssemblyPartNo"] = pn
    return out


def _cleaning_row_from_lot(
    lot: Dict[str, Any],
    lines: List[Dict[str, Any]],
) -> Dict[str, Any]:
    line_dicts = [_line_to_dict(ln) for ln in lines]
    d = _lot_to_dict(lot, line_dicts)
    d["rowKey"] = f"clean:lot:{lot['lot_id']}"
    d["isDraft"] = False
    d["isPending"] = False
    d["isProcessed"] = True
    d["isAssembly"] = True
    d["batchMode"] = "cleaning"
    d["inspectedQty"] = sum(int(ln.get("inspectedQty") or 0) for ln in line_dicts)
    d["qaQty"] = sum(int(ln.get("qaQty") or 0) for ln in line_dicts)
    d["scrapQty"] = sum(int(ln.get("scrapQty") or 0) for ln in line_dicts)
    if line_dicts and not d.get("operatorName"):
        d["operatorName"] = line_dicts[0].get("operatorName") or ""
        d["operatorId"] = line_dicts[0].get("operatorId")
    if line_dicts:
        first_time = next((ln for ln in line_dicts if ln.get("timeTakenMinutes")), None)
        if first_time:
            d["timeTakenMinutes"] = first_time.get("timeTakenMinutes")
    d.update(_cleaning_sub_assembly_flags(lot.get("part_number"), lot.get("bom_no")))
    return d


def get_cleaning_source_lots(
    bom_id: str,
    sub_assembly_part_no: Optional[str] = None,
) -> List[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    if not bid:
        return []
    sa_part = str(sub_assembly_part_no or "").strip()
    if sa_part:
        rows = fetch_all(
            """
            SELECT lot_id, new_lot_no, inspection_pending
            FROM laser_welding_lot
            WHERE bom_id = %s AND TRIM(part_number) = %s
              AND new_lot_no IS NOT NULL AND inspection_pending > 0
            ORDER BY lot_id DESC
            """,
            (bid, sa_part),
        )
    else:
        rows = fetch_all(
            """
            SELECT l.lot_id, l.new_lot_no, l.inspection_pending
            FROM laser_welding_lot l
            INNER JOIN bom b ON b.bom_id = l.bom_id
            WHERE l.bom_id = %s AND l.new_lot_no IS NOT NULL AND l.inspection_pending > 0
              AND TRIM(l.part_number) = TRIM(b.bom_no)
            ORDER BY l.lot_id DESC
            """,
            (bid,),
        )
    return [
        {
            "lotId": int(r["lot_id"]),
            "newLotNo": r["new_lot_no"],
            "inspectionPending": int(r["inspection_pending"] or 0),
            "noOfComp": int(r["inspection_pending"] or 0),
        }
        for r in rows
    ]


def get_cleaning_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")

    result: List[Dict[str, Any]] = []
    draft_lines = fetch_all(
        """
        SELECT ln.*, b.product_name, b.bom_no
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        WHERE ln.lot_id IS NULL
          AND ln.line_type = %s
          AND ln.production_date = %s
          AND ln.source_lot_no = %s
          AND ln.inspected_qty = 0
        ORDER BY ln.line_id DESC
        """,
        (LINE_ASSEMBLY_INSPECTION, wd, SESSION_SOURCE_LOT),
    )
    for line in draft_lines:
        bom = None
        if line.get("bom_id"):
            bom = {"bom_id": line["bom_id"], "product_name": line.get("product_name")}
        row = _draft_session_row_from_line(line, "cleaning", bom=bom)
        row.update(_cleaning_sub_assembly_flags(line.get("part_number"), line.get("bom_no")))
        result.append(row)

    committed_lots = fetch_all(
        """
        SELECT DISTINCT l.*, b.product_name, b.bom_no
        FROM laser_welding_line ln
        INNER JOIN laser_welding_lot l ON l.lot_id = ln.lot_id
        LEFT JOIN bom b ON b.bom_id = l.bom_id
        WHERE ln.line_type = %s
          AND ln.production_date = %s
          AND ln.lot_id IS NOT NULL
          AND ln.inspected_qty > 0
        ORDER BY l.lot_id DESC
        """,
        (LINE_ASSEMBLY_INSPECTION, wd),
    )
    seen_lots: set = set()
    for lot in committed_lots:
        lid = int(lot["lot_id"])
        if lid in seen_lots:
            continue
        seen_lots.add(lid)
        insp_lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = %s AND production_date = %s
            ORDER BY line_id
            """,
            (lid, LINE_ASSEMBLY_INSPECTION, wd),
        )
        result.append(_cleaning_row_from_lot(lot, insp_lines))

    return result


def create_pending_cleaning(
    bom_id: str,
    operator_id: int,
    work_date: str,
    created_by: Optional[int] = None,
    sub_assembly_part_no: Optional[str] = None,
) -> Dict[str, Any]:
    bid = str(bom_id or "").strip()
    sa_part = str(sub_assembly_part_no or "").strip()
    wd = _parse_date(work_date)
    if not bid or not wd:
        raise ValueError("BOM and work date are required")

    op = _fetch_operator(operator_id)
    if not op:
        raise ValueError("Invalid operator — select an active laser-welding operator")

    bom = fetch_one(
        "SELECT bom_id, bom_no, product_name FROM bom WHERE bom_id = %s AND is_latest_version = 'Y'",
        (bid,),
    )
    if not bom:
        raise ValueError("BOM not found")

    if not get_cleaning_source_lots(bid, sa_part or None):
        raise ValueError("No welded lots with inspection pending for this selection")

    bom_no = str(bom["bom_no"] or "").strip()
    line_part_no = sa_part if sa_part else bom_no
    existing = fetch_one(
        """
        SELECT line_id FROM laser_welding_line
        WHERE lot_id IS NULL AND line_type = %s AND bom_id = %s
          AND part_number = %s AND operator_id = %s
          AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_ASSEMBLY_INSPECTION, bid, line_part_no, int(operator_id), wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open cleaning row already exists for this selection and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_id
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (line_part_no, bid, LINE_ASSEMBLY_INSPECTION, SESSION_SOURCE_LOT, wd, int(operator_id)),
    )
    if not line_id:
        raise ValueError("Failed to create pending cleaning row — please try again")
    line = fetch_one(
        """
        SELECT ln.*, b.product_name
        FROM laser_welding_line ln
        LEFT JOIN bom b ON b.bom_id = ln.bom_id
        WHERE ln.line_id = %s
        """,
        (line_id,),
    )
    if not line:
        raise ValueError("Pending cleaning row could not be loaded — refresh and try again")
    row = _draft_session_row_from_line(
        line,
        "cleaning",
        bom={"bom_id": bid, "product_name": bom.get("product_name")},
    )
    row.update(_cleaning_sub_assembly_flags(line_part_no, bom_no))
    return row


def inspect_assembly(
    draft_line_id: int,
    work_date: str,
    lines: List[Dict[str, Any]],
    time_taken_minutes: int,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")

    validated = [
        _validate_line(it, require_lot=False)
        for it in (lines or [])
        if int(it.get("targetLotId") or 0) or str(it.get("sourceLotNo") or "").strip()
    ]
    non_zero = [v for v in validated if v["inspectedQty"] > 0]
    if not non_zero:
        raise ValueError("Enter at least one line with Inspected QTY > 0")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = %s
              AND source_lot_no = %s
            FOR UPDATE
            """,
            (draft_line_id, LINE_ASSEMBLY_INSPECTION, SESSION_SOURCE_LOT),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Pending cleaning row not found — add BOM and operator first")

        operator_id = int(draft.get("operator_id") or 0)
        bom_id = str(draft.get("bom_id") or "").strip()
        pd = draft.get("production_date")
        draft_wd = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")[:10]
        if draft_wd != wd:
            raise ValueError("Work date does not match the pending row")

        by_target: Dict[int, List[Dict[str, Any]]] = {}
        for v in non_zero:
            tid = int(v.get("targetLotId") or 0)
            if not tid:
                raise ValueError("Each line must select a target LW lot")
            by_target.setdefault(tid, []).append(v)

        for target_lot_id, group in by_target.items():
            cursor.execute(
                """
                SELECT * FROM laser_welding_lot
                WHERE lot_id = %s AND bom_id IS NOT NULL AND new_lot_no IS NOT NULL
                FOR UPDATE
                """,
                (target_lot_id,),
            )
            target = cursor.fetchone()
            if not target:
                raise ValueError(f"Target assembly lot {target_lot_id} not found")
            if bom_id and str(target.get("bom_id") or "") != bom_id:
                raise ValueError("Target lot does not belong to the selected BOM")

            totals = _aggregate_lines(group)
            pending = int(target.get("inspection_pending") or 0)
            if totals["total_inspected"] > pending:
                raise ValueError(
                    f"Inspected QTY exceeds inspection pending ({pending}) "
                    f"for lot {target.get('new_lot_no')}"
                )

            cursor.execute(
                """
                UPDATE laser_welding_lot SET
                    inspection_pending = inspection_pending - %s,
                    total_inwarded = total_inwarded + %s,
                    total_qa = total_qa + %s,
                    scrap = scrap + %s,
                    total_okayed = total_okayed + %s,
                    processed_by = %s
                WHERE lot_id = %s
                """,
                (
                    totals["total_inspected"],
                    totals["total_inspected"],
                    totals["total_qa"],
                    totals["total_scrap"],
                    totals["total_okayed"],
                    processed_by,
                    target_lot_id,
                ),
            )

            for v in group:
                source_no = v["sourceLotNo"] or str(target.get("new_lot_no") or "")
                cursor.execute(
                    """
                    INSERT INTO laser_welding_line
                    (part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
                     inspected_qty, qa_qty, scrap_qty, operator_id, time_taken_minutes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        draft.get("part_number") or target.get("part_number"),
                        bom_id or target.get("bom_id"),
                        target_lot_id,
                        LINE_ASSEMBLY_INSPECTION,
                        source_no,
                        wd,
                        v["inspectedQty"],
                        v["qaQty"],
                        v["scrapQty"],
                        operator_id,
                        time_taken_minutes,
                    ),
                )

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

    return {"draftLineId": draft_line_id, "saved": len(non_zero)}
