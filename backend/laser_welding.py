"""Laser Welding — lot-centric workflow (Child Parts, QA Disposition, Rework)."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .config import Config
from .db import execute, execute_insert, fetch_all, fetch_one, get_cursor
from . import bo_inventory
from . import erp_component_stock as erp_stock
from . import packing_inventory as pack_inv
from . import lw_packing_materials as pack_mat

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


def _normalize_ot_flag(value: Any) -> str:
    if value is True:
        return "Y"
    if value is False:
        return "N"
    raw = str(value or "").strip().upper()
    return "Y" if raw in ("Y", "YES", "1", "TRUE") else "N"


def _line_ot_flag(line: Dict[str, Any], session_ot: str) -> str:
    """Per-line OT when set; otherwise fall back to session-level OT from the modal."""
    if line.get("otFlag") is not None or line.get("ot_flag") is not None:
        return _normalize_ot_flag(line.get("otFlag") or line.get("ot_flag"))
    return _normalize_ot_flag(session_ot)


def _remark_or_none(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text if text else None


def _line_extras_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    scrap = int(item.get("scrapQty") or item.get("scrap_qty") or 0)
    rework = int(item.get("reworkQty") or item.get("rework_qty") or 0)
    return {
        "scrap_remark": _remark_or_none(
            item.get("scrapRemark") or item.get("scrap_remark")
        ) if scrap > 0 else None,
        "rework_remark": _remark_or_none(
            item.get("reworkRemark") or item.get("rework_remark")
        ) if rework > 0 else None,
        "rework_qty": rework,
        "ot_flag": (
            _normalize_ot_flag(item.get("otFlag") or item.get("ot_flag"))
            if ("otFlag" in item or "ot_flag" in item)
            else None
        ),
    }


def _row_total_qty_from_lines(
    lines: Optional[List[Dict[str, Any]]],
    *,
    qty_mode: str = "inspected",
) -> int:
    if not lines:
        return 0
    if qty_mode == "qa":
        total = 0
        for ln in lines:
            total += int(ln.get("qaQty") or ln.get("qa_qty") or 0)
            total += int(ln.get("scrapQty") or ln.get("scrap_qty") or 0)
            total += int(ln.get("reworkQty") or ln.get("rework_qty") or 0)
        return total
    if qty_mode == "weld":
        return sum(int(ln.get("weldQty") or ln.get("weld_qty") or 0) for ln in lines)
    return sum(int(ln.get("inspectedQty") or ln.get("inspected_qty") or 0) for ln in lines)


def _welded_child_qty(line: Dict[str, Any], *, is_bo_part: bool = False) -> int:
    consumed = int(line.get("inspectedQty") or line.get("inspected_qty") or 0)
    qa = int(line.get("qaQty") or line.get("qa_qty") or 0)
    scrap = int(line.get("scrapQty") or line.get("scrap_qty") or 0)
    if is_bo_part:
        return max(0, consumed - scrap)
    return max(0, consumed - qa - scrap)


def _produced_qty_from_consume_lines(
    lines: Optional[List[Dict[str, Any]]],
    bom_children: List[Dict[str, Any]],
) -> int:
    """Assemblies/welds produced from consume lines (BOM qty), not sum of consumed child parts."""
    if not lines or not bom_children:
        return 0
    bo_parts = {
        str(bc.get("partNo") or bc.get("part_no") or "").strip()
        for bc in bom_children
        if bc.get("isBoPart")
    }
    bom_qty: Dict[str, int] = {}
    for bc in bom_children:
        pn = str(bc.get("partNo") or bc.get("part_no") or "").strip()
        per_unit = int(bc.get("qty") or 0)
        if pn and per_unit > 0:
            bom_qty[pn] = per_unit

    welded_by_part: Dict[str, int] = {}
    for ln in lines:
        pn = str(ln.get("partNumber") or ln.get("part_number") or "").strip()
        if not pn:
            continue
        welded_by_part[pn] = welded_by_part.get(pn, 0) + _welded_child_qty(
            ln, is_bo_part=pn in bo_parts
        )

    produced: List[int] = []
    for pn, per_unit in bom_qty.items():
        welded = welded_by_part.get(pn, 0)
        if welded > 0:
            produced.append(welded // per_unit)
    return min(produced) if produced else 0


def _all_packing_material_codes() -> Set[str]:
    return pack_mat.all_packing_material_codes()


def _resolve_packing_material_code(
    item_code: Optional[str],
    kind: str,
    part_number: str,
) -> str:
    return pack_mat.resolve_packing_material_for_part(item_code, kind, part_number)


# Part Inspection ERP writes (strict):
# SS (plant 1): reduce_stock (txn 18, insp-qa / stock insp) + fg_segregate (QA, stage 6).
# Whitelist (plant 2): whitelist_reduce_stock (txn 1, op 1→19, full insp) + fg_segregate (QA, stage 6, no lotstock).
# Whitelist pack: inward txn 19→6 + comp_stock stage 6↑ only.


def _part_inspection_part_no(part_number: str) -> str:
    return str(part_number or "").strip()


_part_inspection_parent_ids_cache: Optional[Tuple[int, ...]] = None


def _clear_part_inspection_parent_ids_cache() -> None:
    global _part_inspection_parent_ids_cache
    _part_inspection_parent_ids_cache = None


def _part_inspection_parent_ids() -> Tuple[int, ...]:
    global _part_inspection_parent_ids_cache
    if _part_inspection_parent_ids_cache is not None:
        return _part_inspection_parent_ids_cache
    rows = fetch_all(
        """
        SELECT parent_id
        FROM lw_non_lw_part
        WHERE is_active = 1
        ORDER BY parent_id
        """
    )
    _part_inspection_parent_ids_cache = tuple(
        int(r["parent_id"]) for r in rows if r.get("parent_id") is not None
    )
    return _part_inspection_parent_ids_cache


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


def _month_range_from_work_date(work_date: str) -> Tuple[str, str]:
    """First and last calendar day (yyyy-mm-dd) for the work date's month."""
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    d = datetime.strptime(wd, "%Y-%m-%d").date()
    month_start = d.replace(day=1)
    if d.month == 12:
        month_end = date(d.year, 12, 31)
    else:
        month_end = date(d.year, d.month + 1, 1) - timedelta(days=1)
    return month_start.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d")


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


def _pck_fy_lot_prefix(for_date: Optional[date] = None) -> str:
    d = for_date or date.today()
    start_year = d.year if d.month >= 4 else d.year - 1
    yy = start_year % 100
    return f"PCK/{yy:02d}-{(yy + 1) % 100:02d}/"


def _generate_next_packing_lot_no(for_date: date, cursor: Any) -> str:
    prefix = _pck_fy_lot_prefix(for_date)
    cursor.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(new_lot_no, '/', -1) AS UNSIGNED)), 0) AS mx "
        "FROM laser_welding_lot WHERE new_lot_no LIKE %s",
        (prefix + "%",),
    )
    row = cursor.fetchone()
    mx = int((row or {}).get("mx") or 0)
    return f"{prefix}{mx + 1}"


def _insert_line_row(
    cursor: Any,
    *,
    part_number: str,
    line_type: str,
    lot_id: Optional[int] = None,
    child_lot_id: Optional[int] = None,
    bom_id: Optional[str] = None,
    source_lot_no: str = "",
    production_date: Optional[str] = None,
    inspected_qty: int = 0,
    qa_qty: int = 0,
    scrap_qty: int = 0,
    rework_qty: int = 0,
    scrap_remark: Optional[str] = None,
    rework_remark: Optional[str] = None,
    operator_ids: Optional[str] = None,
    machine_id: Optional[int] = None,
    time_taken_minutes: Optional[int] = None,
    ot_flag: str = "N",
    cd_line_id: Optional[int] = None,
    operator_id: Optional[int] = None,  # ignored, kept for legacy call-site compat
) -> int:
    cursor.execute(
        """
        INSERT INTO laser_welding_line (
            part_number, lot_id, child_lot_id, bom_id, line_type, source_lot_no,
            production_date, inspected_qty, qa_qty, scrap_qty, rework_qty,
            scrap_remark, rework_remark, operator_ids, machine_id,
            time_taken_minutes, ot_flag, cd_line_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            part_number,
            lot_id,
            child_lot_id,
            bom_id,
            line_type,
            source_lot_no or "",
            production_date,
            int(inspected_qty or 0),
            int(qa_qty or 0),
            int(scrap_qty or 0),
            int(rework_qty or 0),
            scrap_remark,
            rework_remark,
            operator_ids or "",
            machine_id,
            time_taken_minutes,
            _normalize_ot_flag(ot_flag),
            cd_line_id,
        ),
    )
    line_id = int(cursor.lastrowid or 0)
    if not line_id:
        raise ValueError("Failed to insert laser welding line")
    return line_id


def _insert_line_batch(cursor: Any, specs: List[Dict[str, Any]]) -> int:
    """Insert rows sharing one cd_line_id (= first inserted line_id)."""
    if not specs:
        raise ValueError("No lines to insert")
    cd_line_id: Optional[int] = None
    for spec in specs:
        row = dict(spec)
        if cd_line_id is not None:
            row["cd_line_id"] = cd_line_id
        lid = _insert_line_row(cursor, **row)
        if cd_line_id is None:
            cd_line_id = lid
            cursor.execute(
                "UPDATE laser_welding_line SET cd_line_id = %s WHERE line_id = %s",
                (cd_line_id, cd_line_id),
            )
    return int(cd_line_id or 0)


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


def _is_packing_output_lot_row(lot: Dict[str, Any]) -> bool:
    return str(lot.get("new_lot_no") or "").strip().startswith("PCK/")


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


def _operator_ids_csv(value: Any) -> str:
    """Normalize operator id list to a sorted, deduplicated CSV string."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
    elif isinstance(value, (list, tuple, set)):
        parts = [str(x).strip() for x in value if x is not None and str(x).strip()]
    else:
        parts = [str(value).strip()]
    seen: Set[int] = set()
    for part in parts:
        try:
            seen.add(int(part))
        except (TypeError, ValueError):
            continue
    return ",".join(str(x) for x in sorted(seen))


def _resolve_operator_ids(operator_ids: Any) -> str:
    """Normalize any operator input to a sorted CSV string."""
    csv = _operator_ids_csv(operator_ids)
    if not csv:
        raise ValueError("Operator is required")
    return csv


def _validate_operator_ids_csv(ids_csv: str) -> None:
    csv = _operator_ids_csv(ids_csv)
    if not csv:
        raise ValueError("Operator is required")
    for part in csv.split(","):
        if not _fetch_operator(int(part)):
            raise ValueError("Invalid operator — select active laser-welding operators")


def _fetch_operators_detail(ids_csv: Any) -> List[Dict[str, Any]]:
    csv = _operator_ids_csv(ids_csv)
    if not csv:
        return []
    ids = [int(x) for x in csv.split(",") if x.strip()]
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    rows = fetch_all(
        f"""
        SELECT
            OP_ID AS id,
            COALESCE(OP_ECNO, '') AS ecno,
            COALESCE(OP_NAME, '') AS name
        FROM operators
        WHERE OP_ACTIVEYN = 'Y' AND OP_OTID = 3 AND OP_ID IN ({placeholders})
        """,
        tuple(ids),
    )
    by_id = {int(r["id"]): r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def _fetch_operators_csv(ids_csv: Any) -> str:
    detail = _fetch_operators_detail(ids_csv)
    return ", ".join(_operator_label(r) for r in detail)


def _line_operator_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    csv = str(row.get("operator_ids") or "").strip()
    ids_list = [int(x) for x in csv.split(",") if x.strip()] if csv else []
    detail = _fetch_operators_detail(csv) if csv else []
    names = ", ".join(_operator_label(r) for r in detail)
    ecnos = ", ".join(str(r.get("ecno") or "") for r in detail)
    return {
        "operatorId": ids_list[0] if ids_list else None,
        "operatorIds": ids_list,
        "operatorName": names.split(", ")[0] if names else "",
        "operatorNames": names,
        "operatorEcno": ecnos.split(", ")[0] if ecnos else "",
        "operatorEcnos": ecnos,
    }


def _default_lw_machine_type() -> int:
    return int(getattr(Config, "LW_WELDING_MACHINE_TYPE", 3))


def _default_sa_machine_type() -> int:
    return int(getattr(Config, "LW_SUB_ASSEMBLY_MACHINE_TYPE", 4))


def _fetch_lw_machine(
    machine_id: Any,
    cursor: Any = None,
    *,
    machine_type: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    try:
        mid = int(machine_id)
    except (TypeError, ValueError):
        return None
    if machine_type is not None:
        sql = """
            SELECT MCM_Id AS id, COALESCE(MCM_Name, '') AS name
            FROM machinemaster
            WHERE MCM_Id = %s AND MCM_Type = %s AND MCM_ACTIVEYN = 'Y'
        """
        params: Tuple[Any, ...] = (mid, int(machine_type))
    else:
        sql = """
            SELECT MCM_Id AS id, COALESCE(MCM_Name, '') AS name
            FROM machinemaster
            WHERE MCM_Id = %s AND MCM_ACTIVEYN = 'Y'
        """
        params = (mid,)
    if cursor is not None:
        cursor.execute(sql, params)
        return cursor.fetchone()
    return fetch_one(sql, params)


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
    op_fields = _line_operator_fields(row)
    machine_id = row.get("machine_id")
    machine_row = _fetch_lw_machine(machine_id) if machine_id is not None else None
    return {
        "lineId": int(row["line_id"]),
        "cdLineId": int(row["cd_line_id"]) if row.get("cd_line_id") is not None else None,
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
        "reworkQty": int(row.get("rework_qty") or 0),
        "scrapRemark": str(row.get("scrap_remark") or "").strip(),
        "reworkRemark": str(row.get("rework_remark") or "").strip(),
        "operatorId": op_fields["operatorId"],
        "operatorIds": op_fields["operatorIds"],
        "operatorName": op_fields["operatorName"],
        "operatorNames": op_fields["operatorNames"],
        "machineId": int(machine_id) if machine_id is not None else None,
        "machineName": _machine_label(machine_row) if machine_row else "",
        "timeTakenMinutes": int(row["time_taken_minutes"]) if row.get("time_taken_minutes") is not None else None,
        "otFlag": _normalize_ot_flag(row.get("ot_flag")),
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
    first_op = next((ln for ln in line_list if ln.get("operatorId") or ln.get("operatorNames")), None)
    return {
        "lotId": int(row["lot_id"]),
        "partNumber": part_no,
        "partName": part_name,
        "bomId": str(bom_id) if bom_id is not None else None,
        "productName": row.get("product_name") or "",
        "operatorId": first_op.get("operatorId") if first_op else None,
        "operatorIds": first_op.get("operatorIds") if first_op else [],
        "operatorName": first_op.get("operatorName") if first_op else "",
        "operatorNames": first_op.get("operatorNames") if first_op else "",
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
    operator_ids: str,
) -> Optional[Dict[str, Any]]:
    """Existing LBO lot for same part, operator(s), and work date."""
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
          AND ln.operator_ids = %s
        ORDER BY l.lot_id DESC
        LIMIT 1
        FOR UPDATE
        """,
        (part, "LBO/%", LINE_PART_INSPECTION, production_date, operator_ids),
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
        operator_ids=str(operator_id),
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


def _insert_part_inspection_line(
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
    scrap_remark: Optional[str] = None,
    rework_remark: Optional[str] = None,
    rework_qty: int = 0,
    ot_flag: str = "N",
    cd_line_id: Optional[int] = None,
) -> int:
    """Insert Part_Inspection line (never merge/update existing rows)."""
    return _insert_line_row(
        cursor,
        part_number=part,
        lot_id=lot_id,
        line_type=LINE_PART_INSPECTION,
        source_lot_no=source_lot_no,
        production_date=production_date,
        inspected_qty=inspected,
        qa_qty=qa,
        scrap_qty=scrap,
        rework_qty=rework_qty,
        scrap_remark=scrap_remark,
        rework_remark=rework_remark,
        operator_ids=str(operator_id),
        time_taken_minutes=time_taken_minutes,
        ot_flag=ot_flag,
        cd_line_id=cd_line_id,
    )


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
    extras = _line_extras_from_item(item)
    out = {
        "sourceLotNo": lot_no,
        "productionDate": prod_date,
        "inspectedQty": inspected,
        "qaQty": qa,
        "scrapQty": scrap,
        "targetLotId": int(item["targetLotId"]) if item.get("targetLotId") else None,
        "scrapRemark": extras["scrap_remark"],
        "reworkRemark": extras["rework_remark"],
        "reworkQty": extras["rework_qty"],
    }
    if extras["ot_flag"] is not None:
        out["otFlag"] = extras["ot_flag"]
    pack_qty = int(item.get("packQty") or item.get("pack_qty") or 0)
    if pack_qty:
        out["packQty"] = pack_qty
    qa_passed = int(item.get("qaPassed") or item.get("qa_passed") or 0)
    if qa_passed or item.get("qaPassed") is not None or item.get("qa_passed") is not None:
        out["qaPassed"] = qa_passed
    rework = int(item.get("rework") or item.get("reworkQty") or extras["rework_qty"] or 0)
    if rework:
        out["rework"] = rework
    return out


def _draft_session_row_from_line(
    line: Dict[str, Any],
    batch_mode: str,
    *,
    bom: Optional[Dict[str, Any]] = None,
    customer_name: str = "",
) -> Dict[str, Any]:
    part_no = line.get("part_number") or ""
    op_fields = _line_operator_fields(line)
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
        "operatorId": op_fields["operatorId"],
        "operatorIds": op_fields["operatorIds"],
        "operatorName": op_fields["operatorName"],
        "operatorNames": op_fields["operatorNames"],
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
    if m == "inspection":
        m = "production"
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
    if m == "qa":
        return [
            {
                "part_no": r["partNumber"],
                "part_name": r.get("partName") or "",
                "partNo": r["partNumber"],
                "partName": r.get("partName") or "",
            }
            for r in get_qa_eligible_parts()
        ]
    if m in ("cleaning", "sa_cleaning", "lw_cleaning"):
        sa_only = m == "sa_cleaning"
        lw_only = m == "lw_cleaning"
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
        result: List[Dict[str, str]] = []
        for r in rows:
            is_sa = bool(int(r.get("is_sub_assembly") or 0))
            if sa_only and not is_sa:
                continue
            if lw_only and is_sa:
                continue
            result.append(
                {
                    "part_no": r["part_no"],
                    "part_name": r["part_name"] or r["part_no"],
                    "partNo": r["part_no"],
                    "partName": r["part_name"] or r["part_no"],
                    "bomId": str(r["bom_id"]),
                    "isSubAssembly": is_sa,
                    "subAssemblyPartNo": (
                        str(r["part_no"]) if is_sa else None
                    ),
                }
            )
        return result

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
        "totalQty": _row_total_qty_from_lines([_line_to_dict(r)]),
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


def get_lw_machines(machine_type: Optional[int] = None) -> List[Dict[str, Any]]:
    mtype = int(machine_type) if machine_type is not None else _default_lw_machine_type()
    rows = fetch_all(
        """
        SELECT MCM_Id AS id, COALESCE(MCM_Name, '') AS name
        FROM machinemaster
        WHERE MCM_Type = %s AND MCM_ACTIVEYN = 'Y'
        ORDER BY MCM_Name
        """,
        (mtype,),
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


def _session_row_from_cd_group(
    cd_line_id: int,
    lines: List[Dict[str, Any]],
    batch_mode: str,
    wd: str,
    *,
    pack_lot_no: Optional[str] = None,
    pack_lot_id: Optional[int] = None,
) -> Dict[str, Any]:
    if not lines:
        raise ValueError("Session lines required")
    ordered = sorted(lines, key=lambda ln: int(ln.get("line_id") or 0))
    first = ordered[0]
    part_no = str(first.get("part_number") or "").strip()
    op_fields = _line_operator_fields(first)
    machine_id = first.get("machine_id")
    machine_row = _fetch_lw_machine(machine_id) if machine_id is not None else None
    line_dicts = [_line_to_dict(ln) for ln in ordered]
    times = [
        int(ln.get("time_taken_minutes") or 0)
        for ln in ordered
        if int(ln.get("time_taken_minutes") or 0) > 0
    ]
    max_time = max(times) if times else None
    ot_vals = [_normalize_ot_flag(ln.get("ot_flag")) for ln in ordered]
    session_ot = "Y" if any(f == "Y" for f in ot_vals) else "N"
    row: Dict[str, Any] = {
        "rowKey": f"session:{batch_mode}:{cd_line_id}",
        "cdLineId": int(cd_line_id),
        "partNumber": part_no,
        "partName": _part_name(part_no) if batch_mode not in ("cleaning", "assembly") else part_no,
        "operatorId": op_fields["operatorId"],
        "operatorIds": op_fields["operatorIds"],
        "operatorName": op_fields["operatorName"],
        "operatorNames": op_fields["operatorNames"],
        "machineId": int(machine_id) if machine_id is not None else None,
        "machineName": _machine_label(machine_row) if machine_row else "",
        "workDate": wd,
        "totalQty": _row_total_qty_from_lines(
            line_dicts,
            qty_mode="qa" if batch_mode == "qa" else "production",
        ),
        "isDraft": False,
        "isPending": False,
        "isProcessed": True,
        "batchMode": batch_mode,
        "lines": line_dicts,
        "timeTakenMinutes": max_time,
        "otFlag": session_ot,
    }
    bom_id = first.get("bom_id")
    if bom_id:
        row["bomId"] = str(bom_id)
        bom = fetch_one(
            "SELECT product_name, bom_no FROM bom WHERE bom_id = %s",
            (str(bom_id),),
        )
        if bom:
            row["productName"] = bom.get("product_name") or ""
            if batch_mode == "cleaning":
                row["partNumber"] = str(bom.get("bom_no") or part_no)
    if batch_mode == "cleaning":
        row.update(_cleaning_sub_assembly_flags(first.get("part_number"), row.get("partNumber")))
        row["isAssembly"] = True
        row["lines"] = _enrich_packing_product_lines(line_dicts)
    if batch_mode == "qa":
        row["lines"] = _enrich_packing_product_lines(line_dicts)
    if batch_mode == "packing":
        material_codes = _all_packing_material_codes()
        product_lines = [
            ln for ln in line_dicts
            if str(ln.get("partNumber") or "").strip() not in material_codes
        ]
        material_lines = [
            ln for ln in line_dicts
            if str(ln.get("partNumber") or "").strip() in material_codes
        ]
        row["lines"] = _enrich_packing_product_lines(product_lines)
        row["packMaterials"] = material_lines
        row["totalQty"] = sum(int(ln.get("inspectedQty") or 0) for ln in product_lines)
        if pack_lot_no:
            row["packLotNo"] = pack_lot_no
        if pack_lot_id:
            row["packLotId"] = int(pack_lot_id)
    return row


def _committed_lines_by_cd(
    lines: List[Dict[str, Any]],
    *,
    exclude_material_codes: bool = False,
) -> Dict[int, List[Dict[str, Any]]]:
    material_codes = _all_packing_material_codes() if exclude_material_codes else set()
    sessions: Dict[int, List[Dict[str, Any]]] = {}
    for ln in lines:
        if exclude_material_codes:
            pn = str(ln.get("part_number") or "").strip()
            if pn in material_codes:
                continue
        cd = ln.get("cd_line_id")
        if cd is None:
            cd = ln.get("line_id")
        if cd is None:
            continue
        sessions.setdefault(int(cd), []).append(ln)
    return sessions


def _find_pack_lot_for_session(
    cd_line_id: int,
    part_no: str,
    wd: str,
) -> Tuple[Optional[int], Optional[str]]:
    bounds = fetch_one(
        """
        SELECT MIN(created_at) AS min_at, MAX(created_at) AS max_at
        FROM laser_welding_line
        WHERE cd_line_id = %s
        """,
        (int(cd_line_id),),
    )
    if not bounds or not bounds.get("min_at"):
        return None, None
    min_at = bounds["min_at"]
    max_at = bounds["max_at"]
    row = fetch_one(
        """
        SELECT lot_id, new_lot_no
        FROM laser_welding_lot
        WHERE work_date = %s
          AND TRIM(part_number) = %s
          AND new_lot_no LIKE %s
          AND created_at >= %s
          AND created_at <= DATE_ADD(%s, INTERVAL 2 SECOND)
        ORDER BY lot_id DESC
        LIMIT 1
        """,
        (wd, part_no, "PCK/%", min_at, max_at),
    )
    if not row:
        return None, None
    return int(row["lot_id"]), str(row.get("new_lot_no") or "")


def _production_row_from_operator_session(
    part: str,
    operator_ids: str,
    lines: List[Dict[str, Any]],
    wd: str,
) -> Dict[str, Any]:
    part_no = str(part or "").strip()
    op_fields = _line_operator_fields(lines[0]) if lines else _line_operator_fields({"operator_ids": operator_ids})
    line_dicts = [_line_to_dict(ln) for ln in lines]
    times = [
        int(ln.get("time_taken_minutes") or 0)
        for ln in lines
        if int(ln.get("time_taken_minutes") or 0) > 0
    ]
    max_time = max(times) if times else None
    return {
        "rowKey": f"prod:{part_no}:{operator_ids}:{wd}",
        "partNumber": part_no,
        "partName": _part_name(part_no),
        "operatorId": op_fields["operatorId"],
        "operatorIds": op_fields["operatorIds"],
        "operatorName": op_fields["operatorName"],
        "operatorNames": op_fields["operatorNames"],
        "workDate": wd,
        "inspectedQty": 0,
        "qaQty": 0,
        "scrapQty": 0,
        "totalQty": _row_total_qty_from_lines(line_dicts),
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
    d["totalQty"] = _row_total_qty_from_lines(line_dicts)
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
        ORDER BY ln.cd_line_id, ln.line_id
        """,
        (LINE_PART_INSPECTION, wd),
    )
    for cd_id, lines in _committed_lines_by_cd(committed_lines).items():
        result.append(_session_row_from_cd_group(cd_id, lines, "production", wd))

    return result


def create_pending_lot(
    part_number: str,
    operator_ids: str,
    work_date: str,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Insert draft session line (no laser_welding_lot row)."""
    part = _part_inspection_part_no(part_number)
    wd = _parse_date(work_date)
    if not part or not wd:
        raise ValueError("Part number and work date are required")

    ids_csv = _resolve_operator_ids(operator_ids)
    _validate_operator_ids_csv(ids_csv)

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
          AND operator_ids = %s AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_PART_INSPECTION, part, ids_csv, wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open inspection row already exists for this part and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_ids
        ) VALUES (%s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (part, LINE_PART_INSPECTION, SESSION_SOURCE_LOT, wd, ids_csv),
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
    if mode == "inspection":
        mode = "production"
    if mode == "rework":
        return get_rework_inspect_rows(wd)
    if mode == "sa_cleaning":
        return get_cleaning_rows(wd, scope="sa")
    if mode == "lw_cleaning":
        return get_cleaning_rows(wd, scope="lw")
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
    operator_ids: Optional[str] = None,
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

    ids_csv = _operator_ids_csv(operator_ids or operator_id or "")
    non_zero = [v for v in validated if v["inspectedQty"] > 0 or v["qaQty"] > 0]
    if not non_zero:
        if ids_csv:
            execute(
                """
                DELETE FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND production_date = %s AND operator_ids = %s
                """,
                (part, wd, ids_csv),
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
        if ids_csv:
            existing = fetch_one(
                """
                SELECT * FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND source_lot_no = %s AND production_date = %s
                  AND operator_ids = %s
                """,
                (part, v["sourceLotNo"], wd, ids_csv),
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
            if ids_csv:
                execute(
                    """
                    INSERT INTO laser_welding_line
                    (part_number, lot_id, line_type, source_lot_no, production_date,
                     inspected_qty, qa_qty, operator_ids)
                    VALUES (%s, NULL, 'Part_Inspection', %s, %s, %s, %s, %s)
                    """,
                    (part, v["sourceLotNo"], wd, v["inspectedQty"], v["qaQty"], ids_csv),
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
        if ids_csv:
            execute(
                f"""
                DELETE FROM laser_welding_line
                WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
                  AND production_date = %s AND operator_ids = %s
                  AND source_lot_no NOT IN ({placeholders})
                """,
                (part, wd, ids_csv, *kept_source),
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

    if ids_csv:
        saved_lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'Part_Inspection'
              AND production_date = %s AND operator_ids = %s
            ORDER BY line_id
            """,
            (part, wd, ids_csv),
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
    ot_flag: Optional[str] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    session_ot = _normalize_ot_flag(ot_flag)

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
        draft_operator_ids = str(draft.get("operator_ids") or "").strip()
        if not draft_operator_ids:
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
            draft_op_int = int(draft_operator_ids.split(",")[0]) if draft_operator_ids else 0
            lot_id, lbo_lot_no = _get_or_add_bo_part_inspection_lot(
                cursor,
                part=part,
                wd=wd,
                inspected=total_insp,
                scrap=total_scrap,
                operator_id=draft_op_int,
                work_d=work_d,
                processed_by=processed_by,
            )
            _insert_line_batch(
                cursor,
                [{
                    "part_number": part,
                    "lot_id": lot_id,
                    "line_type": LINE_PART_INSPECTION,
                    "source_lot_no": lbo_lot_no,
                    "production_date": wd,
                    "inspected_qty": total_insp,
                    "qa_qty": 0,
                    "scrap_qty": total_scrap,
                    "scrap_remark": _remark_or_none(
                        next((v.get("scrapRemark") for v in non_zero if v.get("scrapRemark")), None)
                    ) if total_scrap > 0 else None,
                    "operator_ids": draft_operator_ids,
                    "time_taken_minutes": time_taken_minutes,
                    "ot_flag": session_ot,
                }],
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
        line_specs: List[Dict[str, Any]] = []
        for v in non_zero:
            source_lot_no = v["sourceLotNo"]
            insp = int(v["inspectedQty"])
            qa = int(v["qaQty"])
            scrap = int(v["scrapQty"])
            line_ot = _line_ot_flag(v, session_ot)
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
            line_specs.append({
                "part_number": part,
                "lot_id": lot_id,
                "line_type": LINE_PART_INSPECTION,
                "source_lot_no": source_lot_no,
                "production_date": wd,
                "inspected_qty": insp,
                "qa_qty": qa,
                "scrap_qty": scrap,
                "rework_qty": int(v.get("reworkQty") or 0),
                "scrap_remark": v.get("scrapRemark") if scrap > 0 else None,
                "rework_remark": v.get("reworkRemark"),
                "operator_ids": draft_operator_ids,
                "time_taken_minutes": time_taken_minutes,
                "ot_flag": line_ot,
            })
            created_lots.append(
                {
                    "lotId": lot_id,
                    "newLotNo": source_lot_no,
                    "lot": _fetch_lot(lot_id),
                }
            )
        if line_specs:
            _insert_line_batch(cursor, line_specs)

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


def _lot_consume_trace_lines(lot_id: int) -> List[Dict[str, Any]]:
    lot = fetch_one(
        """
        SELECT l.*, b.bom_no
        FROM laser_welding_lot l
        LEFT JOIN bom b ON b.bom_id = l.bom_id AND b.is_latest_version = 'Y'
        WHERE l.lot_id = %s
        """,
        (int(lot_id),),
    )
    if not lot or _is_packing_output_lot_row(lot):
        return []
    bom_no = str(lot.get("bom_no") or "").strip()
    if _is_final_assembly_lot_row(lot, bom_no):
        line_type = LINE_WELDING_CONSUME
    elif _is_sub_assembly_lot_row(lot, bom_no):
        line_type = LINE_SUB_ASSEMBLY_CONSUME
    else:
        return []
    lines = fetch_all(
        """
        SELECT * FROM laser_welding_line
        WHERE lot_id = %s AND line_type = %s
        ORDER BY line_id
        """,
        (int(lot_id), line_type),
    )
    return _enrich_consume_lines_with_nested_sa([_line_to_dict(ln) for ln in lines])


def _enrich_packing_product_lines(
    line_dicts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for ln in line_dicts:
        out = dict(ln)
        lot_id = out.get("lotId")
        if lot_id:
            out["sourceTrace"] = _lot_consume_trace_lines(int(lot_id))
            lot = fetch_one(
                "SELECT part_number, product_name, bom_id FROM laser_welding_lot WHERE lot_id = %s",
                (int(lot_id),),
            )
            if lot:
                out["sourcePartNumber"] = str(lot.get("part_number") or "").strip()
                out["sourceProductName"] = str(lot.get("product_name") or "").strip()
                if lot.get("bom_id"):
                    out["sourceBomId"] = str(lot.get("bom_id"))
        enriched.append(out)
    return enriched


def _enrich_consume_lines_with_nested_sa(
    line_dicts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for ln in line_dicts:
        out = dict(ln)
        child_lot_id = out.get("childLotId")
        if child_lot_id:
            child_lot = fetch_one(
                "SELECT * FROM laser_welding_lot WHERE lot_id = %s",
                (int(child_lot_id),),
            )
            if child_lot and _is_sub_assembly_lot_row(child_lot):
                nested = fetch_all(
                    """
                    SELECT * FROM laser_welding_line
                    WHERE lot_id = %s AND line_type = %s
                    ORDER BY line_id
                    """,
                    (int(child_lot_id), LINE_SUB_ASSEMBLY_CONSUME),
                )
                out["nestedLines"] = [_line_to_dict(n) for n in nested]
        enriched.append(out)
    return enriched


def _qa_row_from_operator_session(
    part: str,
    operator_ids: str,
    lines: List[Dict[str, Any]],
    wd: str,
) -> Dict[str, Any]:
    part_no = str(part or "").strip()
    op_fields = _line_operator_fields(lines[0]) if lines else _line_operator_fields({"operator_ids": operator_ids})
    line_dicts = [_line_to_dict(ln) for ln in lines]
    times = [
        int(ln.get("time_taken_minutes") or 0)
        for ln in lines
        if int(ln.get("time_taken_minutes") or 0) > 0
    ]
    max_time = max(times) if times else None
    return {
        "rowKey": f"qa:{part_no}:{operator_ids}:{wd}",
        "partNumber": part_no,
        "partName": _part_name(part_no),
        "operatorId": op_fields["operatorId"],
        "operatorIds": op_fields["operatorIds"],
        "operatorName": op_fields["operatorName"],
        "operatorNames": op_fields["operatorNames"],
        "workDate": wd,
        "totalQty": _row_total_qty_from_lines(line_dicts, qty_mode="qa"),
        "isDraft": False,
        "isPending": False,
        "isProcessed": True,
        "batchMode": "qa",
        "lines": line_dicts,
        "timeTakenMinutes": max_time,
    }


def get_qa_source_lots(part_number: str) -> List[Dict[str, Any]]:
    part = str(part_number or "").strip()
    if not part:
        return []
    rows = fetch_all(
        """
        SELECT lot_id, new_lot_no, total_qa, part_number
        FROM laser_welding_lot
        WHERE TRIM(part_number) = %s AND total_qa > 0 AND new_lot_no IS NOT NULL
          AND new_lot_no NOT LIKE %s
        ORDER BY lot_id DESC
        """,
        (part, "PCK/%"),
    )
    return [
        {
            "lotId": int(r["lot_id"]),
            "newLotNo": r["new_lot_no"],
            "totalQa": int(r["total_qa"] or 0),
            "noOfComp": int(r["total_qa"] or 0),
        }
        for r in rows
        if not str(r.get("new_lot_no") or "").startswith("PCK/")
    ]


def get_qa_eligible_parts(work_date: Optional[str] = None) -> List[Dict[str, Any]]:
    month_sql = ""
    params: Tuple[Any, ...] = ("PCK/%",)
    if work_date:
        month_start, month_end = _month_range_from_work_date(work_date)
        month_sql = " AND l.work_date BETWEEN %s AND %s"
        params = ("PCK/%", month_start, month_end)
    rows = fetch_all(
        f"""
        SELECT
            MAX(TRIM(l.part_number)) AS part_no,
            COALESCE(MAX(l.product_name), MAX(c.CO_PARTNAME), MAX(TRIM(l.part_number))) AS part_name,
            SUM(l.total_qa) AS pending_qty
        FROM laser_welding_lot l
        LEFT JOIN components c
            ON TRIM(c.CO_PARTNO) = TRIM(l.part_number) AND c.CO_ACTIVEYN = 'Y'
        WHERE l.new_lot_no IS NOT NULL
          AND l.total_qa > 0
          AND l.new_lot_no NOT LIKE %s
          {month_sql}
        GROUP BY TRIM(l.part_number)
        HAVING SUM(l.total_qa) > 0
        ORDER BY part_no
        """,
        params,
    )
    result: List[Dict[str, Any]] = []
    for r in rows:
        part_no = str(r.get("part_no") or "").strip()
        if not part_no:
            continue
        part_name = str(r.get("part_name") or part_no).strip()
        result.append({
            "eligibleKey": f"qa:eligible:{part_no}",
            "partNumber": part_no,
            "partNo": part_no,
            "partName": part_name,
            "pendingQty": int(r.get("pending_qty") or 0),
            "isEligible": True,
        })
    return result


def create_pending_qa(
    part_number: str,
    operator_ids: str,
    work_date: str,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    part = _part_inspection_part_no(part_number)
    wd = _parse_date(work_date)
    if not part or not wd:
        raise ValueError("Part number and work date are required")

    ids_csv = _resolve_operator_ids(operator_ids)
    _validate_operator_ids_csv(ids_csv)

    if not get_qa_source_lots(part):
        raise ValueError(
            f"No lots with QTY for QA for part {part} — cannot add to QA list"
        )

    existing = fetch_one(
        """
        SELECT line_id FROM laser_welding_line
        WHERE lot_id IS NULL AND line_type = %s AND part_number = %s
          AND operator_ids = %s AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_QA_DISPOSITION, part, ids_csv, wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open QA row already exists for this part and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_ids
        ) VALUES (%s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (part, LINE_QA_DISPOSITION, SESSION_SOURCE_LOT, wd, ids_csv),
    )
    if not line_id:
        raise ValueError("Failed to create pending QA row — please try again")
    line = fetch_one("SELECT * FROM laser_welding_line WHERE line_id = %s", (line_id,))
    if not line:
        raise ValueError("Pending QA row could not be loaded — refresh and try again")
    return _draft_session_row_from_line(line, "qa")


def get_qa_inspect_rows(work_date: str) -> List[Dict[str, Any]]:
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
          AND qa_qty = 0
        ORDER BY line_id DESC
        """,
        (LINE_QA_DISPOSITION, wd, SESSION_SOURCE_LOT),
    )
    for line in draft_lines:
        result.append(_draft_session_row_from_line(line, "qa"))

    committed_lines = fetch_all(
        """
        SELECT ln.*
        FROM laser_welding_line ln
        WHERE ln.line_type = %s
          AND ln.lot_id IS NOT NULL
          AND ln.production_date = %s
        ORDER BY ln.cd_line_id, ln.line_id
        """,
        (LINE_QA_DISPOSITION, wd),
    )
    for cd_id, lines in _committed_lines_by_cd(committed_lines).items():
        result.append(_session_row_from_cd_group(cd_id, lines, "qa", wd))

    return result


def get_qa_rows(work_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Legacy alias — dated grid uses get_qa_inspect_rows."""
    if work_date:
        return get_qa_inspect_rows(work_date)
    rows = fetch_all(
        """
        SELECT l.*
        FROM laser_welding_lot l
        WHERE l.total_qa > 0
        ORDER BY l.processed_at DESC, l.lot_id DESC
        """
    )
    return [_lot_to_dict(r, []) for r in rows]


def _apply_qa_disposition_for_lot(
    cursor: Any,
    *,
    lot: Dict[str, Any],
    qa_passed: int,
    scrap: int,
    rework: int,
    operator_ids: str,
    work_date: str,
    time_taken_minutes: int,
    scrap_remark: Optional[str] = None,
    rework_remark: Optional[str] = None,
    ot_flag: str = "N",
    processed_by: Optional[int] = None,
    cd_line_id: Optional[int] = None,
) -> int:
    lot_id = int(lot["lot_id"])
    qp = max(0, int(qa_passed or 0))
    sc = max(0, int(scrap or 0))
    rw = max(0, int(rework or 0))
    total_qa = int(lot.get("total_qa") or 0)
    if qp + sc + rw != total_qa:
        raise ValueError(
            f"QA Passed + Scrap + Rework must equal QTY for QA ({total_qa}) "
            f"for lot {lot.get('new_lot_no')}; got {qp + sc + rw}"
        )

    cursor.execute(
        """
        UPDATE laser_welding_lot SET
            total_okayed = total_okayed + %s,
            total_qa = 0,
            scrap = scrap + %s,
            rework_pending = rework_pending + %s,
            qa_approved_at = NOW(),
            qa_approved_by = %s,
            processed_by = %s
        WHERE lot_id = %s
        """,
        (qp, sc, rw, processed_by, processed_by, lot_id),
    )
    return _insert_line_row(
        cursor,
        part_number=str(lot.get("part_number") or ""),
        bom_id=str(lot.get("bom_id")) if lot.get("bom_id") else None,
        lot_id=lot_id,
        line_type=LINE_QA_DISPOSITION,
        source_lot_no=str(lot.get("new_lot_no") or ""),
        production_date=work_date,
        inspected_qty=total_qa,
        qa_qty=qp,
        scrap_qty=sc,
        rework_qty=rw,
        scrap_remark=scrap_remark if sc > 0 else None,
        rework_remark=rework_remark if rw > 0 else None,
        operator_ids=operator_ids,
        time_taken_minutes=time_taken_minutes,
        ot_flag=ot_flag,
        cd_line_id=cd_line_id,
    )


def inspect_qa(
    draft_line_id: int,
    work_date: str,
    lines: List[Dict[str, Any]],
    time_taken_minutes: int,
    ot_flag: Optional[str] = None,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    session_ot = _normalize_ot_flag(ot_flag)

    validated = [
        _validate_line(it, require_lot=False)
        for it in (lines or [])
        if int(it.get("targetLotId") or 0)
    ]
    non_zero = [v for v in validated if (v.get("qaPassed") or 0) + v["scrapQty"] + (v.get("rework") or 0) > 0]
    if not non_zero:
        raise ValueError("Enter at least one lot with QA disposition quantities")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = %s
              AND source_lot_no = %s
            FOR UPDATE
            """,
            (draft_line_id, LINE_QA_DISPOSITION, SESSION_SOURCE_LOT),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Pending QA row not found — add part and operator first")

        part = _part_inspection_part_no(draft.get("part_number") or "")
        qa_operator_ids = str(draft.get("operator_ids") or "").strip()
        if not qa_operator_ids:
            raise ValueError("Operator is required on the pending QA row")
        pd = draft.get("production_date")
        draft_wd = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")[:10]
        if draft_wd != wd:
            raise ValueError("Work date does not match the pending row")

        updated_lots: List[Dict[str, Any]] = []
        session_cd_line_id: Optional[int] = None
        for v in non_zero:
            target_lot_id = int(v["targetLotId"] or 0)
            cursor.execute(
                "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
                (target_lot_id,),
            )
            lot = cursor.fetchone()
            if not lot:
                raise ValueError(f"Target lot {target_lot_id} not found")
            if str(lot.get("part_number") or "").strip() != part:
                raise ValueError("Target lot does not match the selected part")

            line_ot = _line_ot_flag(v, session_ot)
            line_id = _apply_qa_disposition_for_lot(
                cursor,
                lot=lot,
                qa_passed=int(v.get("qaPassed") or 0),
                scrap=int(v.get("scrapQty") or 0),
                rework=int(v.get("rework") or v.get("reworkQty") or 0),
                operator_ids=qa_operator_ids,
                work_date=wd,
                time_taken_minutes=time_taken_minutes,
                scrap_remark=v.get("scrapRemark"),
                rework_remark=v.get("reworkRemark"),
                ot_flag=line_ot,
                processed_by=processed_by,
                cd_line_id=session_cd_line_id,
            )
            if session_cd_line_id is None:
                session_cd_line_id = line_id
                cursor.execute(
                    "UPDATE laser_welding_line SET cd_line_id = %s WHERE line_id = %s",
                    (session_cd_line_id, session_cd_line_id),
                )
            updated_lots.append(_fetch_lot(target_lot_id, include_lines=False) or {})

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

    first = updated_lots[0] if updated_lots else {}
    return {
        "lots": updated_lots,
        "lotId": first.get("lotId"),
        "lot": first,
    }


def approve_qa(
    lot_id: int,
    qa_passed: int,
    scrap: int,
    rework: int,
    approved_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Legacy single-lot QA approve — prefer inspect_qa for the modal flow."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM laser_welding_lot WHERE lot_id = %s FOR UPDATE",
            (lot_id,),
        )
        lot = cursor.fetchone()
        if not lot:
            raise ValueError("Lot not found")
        _apply_qa_disposition_for_lot(
            cursor,
            lot=lot,
            qa_passed=qa_passed,
            scrap=scrap,
            rework=rework,
            operator_ids=str(approved_by or ""),
            work_date=date.today().strftime("%Y-%m-%d"),
            time_taken_minutes=0,
            processed_by=approved_by,
        )
    return {"lot": _fetch_lot(lot_id, include_lines=False)}


def _packing_rows_query_rows() -> List[Dict[str, Any]]:
    return fetch_all(
        """
        SELECT l.*, b.bom_no, b.product_name
        FROM laser_welding_lot l
        LEFT JOIN bom b ON b.bom_id = l.bom_id AND b.is_latest_version = 'Y'
        WHERE l.total_okayed > 0
          AND l.new_lot_no IS NOT NULL
          AND TRIM(l.new_lot_no) != ''
          AND l.new_lot_no NOT LIKE %s
          AND l.new_lot_no NOT LIKE %s
          AND l.new_lot_no NOT LIKE %s
        ORDER BY l.processed_at DESC, l.lot_id DESC
        """,
        ("SA/%", "LBO/%", "PCK/%"),
    )


def _packing_entry_from_lot_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _is_packing_output_lot_row(row):
        return None
    part_no = str(row.get("part_number") or "").strip()
    bom_no = str(row.get("bom_no") or "").strip()
    if _is_final_assembly_lot_row(row, bom_no):
        return {
            "lotId": int(row["lot_id"]),
            "packType": "bom",
            "partNo": bom_no or part_no,
            "partName": str(row.get("product_name") or "").strip(),
            "bomId": str(row["bom_id"]) if row.get("bom_id") else None,
            "newLotNo": row.get("new_lot_no") or "",
            "totalOkayed": int(row.get("total_okayed") or 0),
        }
    if row.get("bom_id") is None and _is_part_inspection_part(part_no):
        return {
            "lotId": int(row["lot_id"]),
            "packType": "whitelist",
            "partNo": part_no,
            "partName": _part_inspection_display_name(part_no) or str(row.get("product_name") or "").strip(),
            "bomId": None,
            "newLotNo": row.get("new_lot_no") or "",
            "totalOkayed": int(row.get("total_okayed") or 0),
        }
    return None


def get_packing_rows() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in _packing_rows_query_rows():
        entry = _packing_entry_from_lot_row(row)
        if entry:
            out.append(entry)
    return out


def get_packing_parts_catalog() -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for entry in get_packing_rows():
        part_no = str(entry.get("partNo") or "").strip()
        if not part_no or part_no in seen:
            continue
        seen[part_no] = {
            "partNo": part_no,
            "partName": entry.get("partName") or part_no,
            "packType": entry.get("packType"),
            "bomId": entry.get("bomId"),
        }
    return sorted(seen.values(), key=lambda x: x["partNo"])


def _catalog_key(part_no: str, cust_id: Optional[int]) -> str:
    pn = str(part_no or "").strip().upper()
    cid = int(cust_id) if cust_id is not None and str(cust_id).strip() != "" else 0
    return f"{pn}|{cid}"


def get_trays_carton_parts_catalog(cust_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """All latest BOMs + whitelist parts (customer from parent CO_CUSTID).

    Same BOM number may exist for multiple customers — keep one row per (part, cust).
    """
    seen: Dict[str, Dict[str, Any]] = {}

    for bom in get_boms(None):
        part_no = str(bom.get("bomNo") or "").strip()
        if not part_no:
            continue
        bom_cust = bom.get("custId")
        bom_id = bom.get("bomId")
        resolved = pack_mat.resolve_part_for_mapping(
            part_no,
            cust_id=bom_cust,
            bom_id=bom_id,
        )
        seen[_catalog_key(part_no, bom_cust)] = {
            "partNo": part_no,
            "partName": bom.get("productName") or part_no,
            "custId": bom_cust,
            "bomId": (resolved or {}).get("bomId") or bom_id,
            "customerName": bom.get("customerName") or "",
            "coId": (resolved or {}).get("coId"),
            "partSource": "bom",
        }

    parent_ids = _part_inspection_parent_ids()
    if parent_ids:
        placeholders = _part_inspection_parent_id_placeholders()
        rows = fetch_all(
            f"""
            SELECT c.CO_ID AS co_id,
                   TRIM(c.CO_PARTNO) AS part_no,
                   TRIM(c.CO_PARTNAME) AS part_name,
                   p.CO_CUSTID AS cust_id,
                   COALESCE(cu.CU_Name, '') AS customer_name
            FROM components c
            INNER JOIN components p
                ON p.CO_ID = c.CO_PARENTID AND p.CO_ACTIVEYN = 'Y'
            LEFT JOIN customer cu ON cu.CU_Id = p.CO_CUSTID
            WHERE c.CO_ACTIVEYN = 'Y'
              AND c.CO_PARENTID IN ({placeholders})
            ORDER BY c.CO_PARTNO
            """,
            parent_ids,
        )
        for r in rows:
            part_no = str(r.get("part_no") or "").strip()
            if not part_no:
                continue
            wl_cust = int(r["cust_id"]) if r.get("cust_id") is not None else None
            key = _catalog_key(part_no, wl_cust)
            if key in seen:
                continue
            seen[key] = {
                "partNo": part_no,
                "partName": r.get("part_name") or part_no,
                "custId": wl_cust,
                "customerName": r.get("customer_name") or "",
                "coId": int(r["co_id"]) if r.get("co_id") is not None else None,
                "bomId": None,
                "partSource": "whitelist",
            }

    out = list(seen.values())
    if cust_id is not None:
        cid = int(cust_id)
        out = [p for p in out if int(p.get("custId") or 0) == cid]
    return sorted(out, key=lambda x: (str(x.get("partNo") or ""), int(x.get("custId") or 0)))


def get_packing_source_lots(part_number: str) -> List[Dict[str, Any]]:
    part = str(part_number or "").strip()
    if not part:
        return []
    return [
        {
            "lotId": r["lotId"],
            "newLotNo": r["newLotNo"],
            "totalOkayed": r["totalOkayed"],
            "noOfComp": r["totalOkayed"],
            "packType": r.get("packType"),
        }
        for r in get_packing_rows()
        if str(r.get("partNo") or "").strip() == part
    ]


def _pack_material_available_qty(item_code: str) -> int:
    code = str(item_code or "").strip()
    if not code:
        return 0
    row = fetch_one(
        """
        SELECT COALESCE(QTY, 0) AS qty
        FROM inventory
        WHERE TRIM(ITEM_CODE) = %s
        ORDER BY INVENTORY_ID
        LIMIT 1
        """,
        (code,),
    )
    return int(float((row or {}).get("qty") or 0))


def get_packing_pack_materials(part_number: Optional[str] = None) -> Dict[str, Any]:
    part = str(part_number or "").strip()
    if not part:
        return {"trays": [], "cartons": [], "materials": [], "hasMapping": False}
    return pack_mat.get_pack_materials_for_part(part)


def _reduce_pack_material_qty(cursor: Any, item_code: str, qty: int) -> None:
    code = str(item_code or "").strip()
    if not code:
        raise ValueError("Pack material item code is not configured")
    if qty <= 0:
        return
    cursor.execute(
        """
        SELECT INVENTORY_ID, QTY
        FROM inventory
        WHERE TRIM(ITEM_CODE) = %s
        ORDER BY INVENTORY_ID
        LIMIT 1
        FOR UPDATE
        """,
        (code,),
    )
    row = cursor.fetchone()
    available = int(float((row or {}).get("QTY") or 0)) if row else 0
    if not row or available < qty:
        raise ValueError(f"Insufficient inventory for {code} (need {qty}, have {available})")
    cursor.execute(
        "UPDATE inventory SET QTY = QTY - %s WHERE INVENTORY_ID = %s",
        (qty, row["INVENTORY_ID"]),
    )


def create_pending_packing(
    part_no: str,
    operator_ids: str,
    work_date: str,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    part = str(part_no or "").strip()
    wd = _parse_date(work_date)
    if not part or not wd:
        raise ValueError("Part number and work date are required")

    ids_csv = _resolve_operator_ids(operator_ids)
    _validate_operator_ids_csv(ids_csv)

    if not get_packing_source_lots(part):
        raise ValueError(
            f"No lots with quantity available for packing for part {part}"
        )

    existing = fetch_one(
        """
        SELECT line_id FROM laser_welding_line
        WHERE lot_id IS NULL AND line_type = %s AND part_number = %s
          AND operator_ids = %s AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_PACKING, part, ids_csv, wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open packing row already exists for this part and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_ids
        ) VALUES (%s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (part, LINE_PACKING, SESSION_SOURCE_LOT, wd, ids_csv),
    )
    if not line_id:
        raise ValueError("Failed to create pending packing row — please try again")
    line = fetch_one("SELECT * FROM laser_welding_line WHERE line_id = %s", (line_id,))
    if not line:
        raise ValueError("Pending packing row could not be loaded — refresh and try again")
    return _draft_session_row_from_line(line, "packing")


def _packing_row_from_operator_session(
    part: str,
    operator_ids: str,
    lines: List[Dict[str, Any]],
    wd: str,
) -> Dict[str, Any]:
    part_no = str(part or "").strip()
    op_fields = _line_operator_fields(lines[0]) if lines else _line_operator_fields({"operator_ids": operator_ids})
    material_codes = _all_packing_material_codes()
    product_lines = [
        ln for ln in lines
        if str(ln.get("part_number") or "").strip() not in material_codes
    ]
    line_dicts = [_line_to_dict(ln) for ln in product_lines]
    times = [
        int(ln.get("time_taken_minutes") or 0)
        for ln in lines
        if int(ln.get("time_taken_minutes") or 0) > 0
    ]
    max_time = max(times) if times else None
    return {
        "rowKey": f"pack:{part_no}:{operator_ids}:{wd}",
        "partNumber": part_no,
        "partName": _part_name(part_no) or part_no,
        "operatorId": op_fields["operatorId"],
        "operatorIds": op_fields["operatorIds"],
        "operatorName": op_fields["operatorName"],
        "operatorNames": op_fields["operatorNames"],
        "workDate": wd,
        "totalQty": sum(int(ln.get("inspected_qty") or 0) for ln in product_lines),
        "isDraft": False,
        "isPending": False,
        "isProcessed": True,
        "batchMode": "packing",
        "lines": line_dicts,
        "timeTakenMinutes": max_time,
    }


def get_packing_inspect_rows(work_date: str) -> List[Dict[str, Any]]:
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
        (LINE_PACKING, wd, SESSION_SOURCE_LOT),
    )
    for line in draft_lines:
        result.append(_draft_session_row_from_line(line, "packing"))

    committed_lines = fetch_all(
        """
        SELECT ln.*
        FROM laser_welding_line ln
        WHERE ln.line_type = %s
          AND ln.lot_id IS NOT NULL
          AND ln.production_date = %s
        ORDER BY ln.cd_line_id, ln.line_id
        """,
        (LINE_PACKING, wd),
    )
    material_codes = _all_packing_material_codes()
    sessions_by_cd = _committed_lines_by_cd(committed_lines, exclude_material_codes=True)
    for cd_id in sessions_by_cd:
        all_lines = [
            ln for ln in committed_lines
            if int(ln.get("cd_line_id") or ln.get("line_id") or 0) == int(cd_id)
        ]
        if not all_lines:
            continue
        part_no = str(all_lines[0].get("part_number") or "").strip()
        if part_no in material_codes:
            part_line = next(
                (ln for ln in all_lines if str(ln.get("part_number") or "").strip() not in material_codes),
                None,
            )
            part_no = str((part_line or {}).get("part_number") or "").strip()
        pack_lot_id, pack_lot_no = _find_pack_lot_for_session(cd_id, part_no, wd)
        result.append(
            _session_row_from_cd_group(
                cd_id,
                all_lines,
                "packing",
                wd,
                pack_lot_no=pack_lot_no,
                pack_lot_id=pack_lot_id,
            )
        )

    return result


def _pack_inventory_inward(
    cursor: Any,
    lot: Dict[str, Any],
    net_qty: int,
    packed_by: Optional[int] = None,
) -> str:
    """Add net packed qty to BOM or whitelist inventory; return pack type."""
    pack_qty = int(net_qty or 0)
    new_lot_no = str(lot.get("new_lot_no") or "").strip()
    if not new_lot_no:
        raise ValueError("Lot has no LW lot number")
    if (
        new_lot_no.startswith("SA/")
        or new_lot_no.startswith("LBO/")
        or new_lot_no.startswith("PCK/")
    ):
        raise ValueError("This lot is not eligible for packing")

    part_no = str(lot.get("part_number") or "").strip()
    bom_no = str(lot.get("bom_no") or "").strip()
    if not bom_no and lot.get("bom_id"):
        bom_no = _bom_no_for_id(lot.get("bom_id"))

    if _is_final_assembly_lot_row(lot, bom_no):
        pack_type = "bom"
        if pack_qty > 0:
            item_code = bom_no or part_no
            if not item_code:
                raise ValueError("BOM number not found for this lot")
            meta = pack_inv.resolve_bom_inventory_meta(lot.get("bom_id"), cursor)
            pack_inv.add_inventory_qty(
                cursor,
                item_code,
                pack_qty,
                item_name=meta.get("item_name") or lot.get("product_name") or "",
                cust_id=meta.get("cust_id"),
                plant_id=1,
                revision=meta.get("revision"),
            )
    elif lot.get("bom_id") is None and _is_part_inspection_part(part_no):
        pack_type = "whitelist"
        if pack_qty > 0:
            comp_id = erp_stock.resolve_comp_id(part_no, cursor)
            erp_stock.whitelist_pack_inward(
                cursor,
                comp_id,
                erp_stock.LW_WHITELIST_ERP_PLANT_ID,
                new_lot_no,
                pack_qty,
                user_id=packed_by,
            )
    else:
        raise ValueError("This lot is not eligible for packing")
    return pack_type


def _apply_packing_source_lot(
    cursor: Any,
    lot: Dict[str, Any],
    consumed: int,
    qa: int,
    scrap: int,
    packed_by: Optional[int] = None,
) -> None:
    cursor.execute(
        """
        UPDATE laser_welding_lot SET
            total_okayed = total_okayed - %s,
            total_qa = total_qa + %s,
            scrap = scrap + %s,
            processed_at = NOW(),
            processed_by = %s
        WHERE lot_id = %s
        """,
        (int(consumed), int(qa), int(scrap), packed_by, lot["lot_id"]),
    )
def _execute_pack_qty(
    cursor: Any,
    lot: Dict[str, Any],
    qty: int,
    packed_by: Optional[int] = None,
) -> str:
    """Legacy single-lot pack: full qty off total_okayed, same qty to inventory."""
    pack_qty = int(qty or 0)
    if pack_qty <= 0:
        raise ValueError("Pack quantity must be greater than 0")

    available = int(lot.get("total_okayed") or 0)
    if available <= 0:
        raise ValueError("This lot has no quantity available for packing")
    if pack_qty > available:
        raise ValueError(f"Pack quantity must be between 1 and {available}")

    pack_type = _pack_inventory_inward(cursor, lot, pack_qty, packed_by)
    cursor.execute(
        """
        UPDATE laser_welding_lot SET
            total_okayed = total_okayed - %s,
            processed_at = NOW(),
            processed_by = %s
        WHERE lot_id = %s
        """,
        (pack_qty, packed_by, lot["lot_id"]),
    )
    return pack_type


def inspect_packing(
    draft_line_id: int,
    work_date: str,
    lines: List[Dict[str, Any]],
    tray_qty: int,
    carton_qty: int,
    time_taken_minutes: int,
    ot_flag: Optional[str] = None,
    processed_by: Optional[int] = None,
    tray_item_code: Optional[str] = None,
    carton_item_code: Optional[str] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    session_ot = _normalize_ot_flag(ot_flag)
    tray_code = ""
    carton_code = ""

    validated = [
        _validate_line(it, require_lot=False)
        for it in (lines or [])
        if int(it.get("targetLotId") or 0)
    ]
    non_zero = [
        v for v in validated
        if int(v.get("inspectedQty") or v.get("packQty") or 0) > 0
    ]
    if not non_zero:
        raise ValueError("Enter at least one lot with consumed quantity > 0")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE line_id = %s AND lot_id IS NULL AND line_type = %s
              AND source_lot_no = %s
            FOR UPDATE
            """,
            (draft_line_id, LINE_PACKING, SESSION_SOURCE_LOT),
        )
        draft = cursor.fetchone()
        if not draft:
            raise ValueError("Pending packing row not found — add part and operator first")

        part = str(draft.get("part_number") or "").strip()
        pack_operator_ids = str(draft.get("operator_ids") or "").strip()
        if not pack_operator_ids:
            raise ValueError("Operator is required on the pending packing row")
        pd = draft.get("production_date")
        draft_wd = pd.strftime("%Y-%m-%d") if hasattr(pd, "strftime") else str(pd or "")[:10]
        if draft_wd != wd:
            raise ValueError("Work date does not match the pending row")

        if int(tray_qty or 0) > 0:
            tray_code = _resolve_packing_material_code(tray_item_code, "tray", part)
        if int(carton_qty or 0) > 0:
            carton_code = _resolve_packing_material_code(carton_item_code, "carton", part)

        updated_lots: List[Dict[str, Any]] = []
        line_specs: List[Dict[str, Any]] = []
        line_ot = session_ot
        total_net = 0
        pack_bom_id: Optional[str] = None
        pack_product_name = ""
        first_pack_type: Optional[str] = None

        for v in non_zero:
            target_lot_id = int(v["targetLotId"] or 0)
            consumed = int(v.get("inspectedQty") or v.get("packQty") or 0)
            qa = int(v.get("qaQty") or 0)
            scrap = int(v.get("scrapQty") or 0)
            if qa + scrap > consumed:
                raise ValueError("QA + Scrap cannot exceed Consumed")
            net = consumed - qa - scrap
            cursor.execute(
                """
                SELECT l.*, b.bom_no, b.product_name
                FROM laser_welding_lot l
                LEFT JOIN bom b ON b.bom_id = l.bom_id AND b.is_latest_version = 'Y'
                WHERE l.lot_id = %s
                FOR UPDATE
                """,
                (target_lot_id,),
            )
            lot = cursor.fetchone()
            if not lot:
                raise ValueError(f"Target lot {target_lot_id} not found")
            entry = _packing_entry_from_lot_row(lot)
            if not entry or str(entry.get("partNo") or "").strip() != part:
                raise ValueError("Target lot does not match the selected part")

            available = int(lot.get("total_okayed") or 0)
            if consumed > available:
                raise ValueError(
                    f"Consumed ({consumed}) exceeds available ({available}) "
                    f"for lot {lot.get('new_lot_no')}"
                )

            line_ot = _line_ot_flag(v, session_ot)
            pack_type = _pack_inventory_inward(cursor, lot, net, processed_by)
            if first_pack_type is None:
                first_pack_type = pack_type
            _apply_packing_source_lot(cursor, lot, consumed, qa, scrap, processed_by)

            if pack_bom_id is None and lot.get("bom_id"):
                pack_bom_id = str(lot.get("bom_id"))
                pack_product_name = str(lot.get("product_name") or "").strip()

            total_net += net
            line_specs.append({
                "part_number": part,
                "bom_id": lot.get("bom_id"),
                "lot_id": target_lot_id,
                "line_type": LINE_PACKING,
                "source_lot_no": lot.get("new_lot_no") or "",
                "production_date": wd,
                "inspected_qty": consumed,
                "qa_qty": qa,
                "scrap_qty": scrap,
                "scrap_remark": v.get("scrapRemark") if scrap > 0 else None,
                "operator_ids": pack_operator_ids,
                "time_taken_minutes": time_taken_minutes,
                "ot_flag": line_ot,
            })
            updated_lots.append({
                "lotId": target_lot_id,
                "packType": pack_type,
                "packQty": consumed,
                "netQty": net,
                "lot": _fetch_lot(target_lot_id, include_lines=False),
            })

        pack_lot_id: Optional[int] = None
        pack_lot_no: Optional[str] = None
        if total_net > 0:
            work_d = datetime.strptime(wd, "%Y-%m-%d").date()
            pack_lot_no = _generate_next_packing_lot_no(work_d, cursor)
            cursor.execute(
                """
                INSERT INTO laser_welding_lot (
                    part_number, bom_id, product_name, new_lot_no, work_date,
                    total_inwarded, total_qa, total_okayed, created_by
                ) VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s)
                """,
                (
                    part,
                    pack_bom_id,
                    pack_product_name or part,
                    pack_lot_no,
                    wd,
                    total_net,
                    processed_by,
                ),
            )
            pack_lot_id = int(cursor.lastrowid or 0)

        if tray_qty > 0:
            _reduce_pack_material_qty(cursor, tray_code, int(tray_qty))
            line_specs.append({
                "part_number": tray_code,
                "lot_id": None,
                "line_type": LINE_PACKING,
                "source_lot_no": SESSION_SOURCE_LOT,
                "production_date": wd,
                "inspected_qty": int(tray_qty),
                "operator_ids": pack_operator_ids,
                "time_taken_minutes": time_taken_minutes,
                "ot_flag": line_ot,
            })
        if carton_qty > 0:
            _reduce_pack_material_qty(cursor, carton_code, int(carton_qty))
            line_specs.append({
                "part_number": carton_code,
                "lot_id": None,
                "line_type": LINE_PACKING,
                "source_lot_no": SESSION_SOURCE_LOT,
                "production_date": wd,
                "inspected_qty": int(carton_qty),
                "operator_ids": pack_operator_ids,
                "time_taken_minutes": time_taken_minutes,
                "ot_flag": line_ot,
            })

        if line_specs:
            _insert_line_batch(cursor, line_specs)

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

    first = updated_lots[0] if updated_lots else {}
    return {
        "lots": updated_lots,
        "lotId": first.get("lotId"),
        "packType": first.get("packType") or first_pack_type,
        "packQty": first.get("packQty"),
        "lot": first.get("lot"),
        "packLotId": pack_lot_id,
        "packLotNo": pack_lot_no,
        "netQty": total_net,
    }


def pack_lot(
    lot_id: int,
    pack_qty: int,
    work_date: Optional[str] = None,
    packed_by: Optional[int] = None,
) -> Dict[str, Any]:
    qty = int(pack_qty or 0)
    wd = _parse_date(work_date) or date.today().strftime("%Y-%m-%d")

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

        pack_type = _execute_pack_qty(cursor, lot, qty, packed_by)
        cursor.execute(
            """
            INSERT INTO laser_welding_line (
                part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
                inspected_qty, qa_qty, scrap_qty, operator_ids
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, %s)
            """,
            (
                lot.get("part_number"),
                lot.get("bom_id"),
                lot_id,
                LINE_PACKING,
                lot.get("new_lot_no") or "",
                wd,
                qty,
                str(packed_by or ""),
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
    line_dicts = _enrich_consume_lines_with_nested_sa([_line_to_dict(ln) for ln in lines])
    d = _lot_to_dict(lot, line_dicts)
    d.update(_row_machine_from_lines(line_dicts))
    d["rowKey"] = f"asm:{lot['lot_id']}"
    d["isDraft"] = not processed
    d["isPending"] = not processed
    d["isAssembly"] = True
    d["batchMode"] = "assembly"
    bom_id = str(lot.get("bom_id") or "")
    bom_children = get_laser_welding_bom_children(bom_id) if bom_id else []
    produced = _produced_qty_from_consume_lines(line_dicts, bom_children)
    d["weldQty"] = produced
    d["totalQty"] = produced
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
          AND l.new_lot_no NOT LIKE %s
        ORDER BY l.lot_id DESC
        """,
        (wd, "PCK/%"),
    )
    for lot in lots:
        if _is_packing_output_lot_row(lot):
            continue
        result.append(_assembly_row_from_lot(lot))

    return result


def create_pending_assembly(
    bom_id: str,
    operator_ids: str,
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
    ids_csv = _resolve_operator_ids(operator_ids)
    _validate_operator_ids_csv(ids_csv)
    machine = _fetch_lw_machine(machine_id, machine_type=_default_lw_machine_type())
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
          AND operator_ids = %s AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_WELDING_CONSUME, bid, ids_csv, wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open assembly row already exists for this BOM and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_ids, machine_id
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s, %s)
        """,
        (bom_no, bid, LINE_WELDING_CONSUME, SESSION_SOURCE_LOT, wd, ids_csv, int(machine_id)),
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
    operator_ids: Optional[str] = None,
    processed_by: Optional[int] = None,
    ot_flag: Optional[str] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if weld_qty <= 0:
        raise ValueError("Weld QTY must be greater than 0")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    session_ot = _normalize_ot_flag(ot_flag)

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
        line_operator_ids = _operator_ids_csv(operator_ids or draft.get("operator_ids") or "")
        if not line_operator_ids:
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
        consume_specs: List[Dict[str, Any]] = []

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
            extras = _line_extras_from_item({**c, "otFlag": c.get("otFlag") or session_ot})

            consume_specs.append({
                "part_number": part_no,
                "lot_id": lot_id,
                "child_lot_id": child_lot_id,
                "line_type": LINE_WELDING_CONSUME,
                "source_lot_no": child.get("new_lot_no") or "",
                "production_date": wd,
                "inspected_qty": consumed,
                "qa_qty": qa,
                "scrap_qty": scrap,
                "rework_qty": extras["rework_qty"],
                "scrap_remark": extras["scrap_remark"],
                "rework_remark": extras["rework_remark"],
                "operator_ids": line_operator_ids,
                "machine_id": line_machine,
                "time_taken_minutes": time_taken_minutes,
                "ot_flag": extras["ot_flag"],
            })

        for pn, req in required.items():
            got = welded_by_part.get(pn, 0)
            if got != req:
                raise ValueError(
                    f"Part {pn}: required welded qty {req} (BOM × weld qty), got {got}"
                )

        if consume_specs:
            _insert_line_batch(cursor, consume_specs)

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
          AND TRIM(l.part_number) = TRIM(b.bom_no)
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


def get_rework_weld_eligible_items(work_date: str) -> List[Dict[str, Any]]:
    month_start, month_end = _month_range_from_work_date(work_date)
    rows = fetch_all(
        """
        SELECT
            b.bom_id,
            b.bom_no,
            b.product_name,
            b.cust_id,
            COALESCE(c.CU_Name, '') AS customer_name,
            SUM(l.rework_pending) AS pending_qty
        FROM bom b
        INNER JOIN laser_welding_lot l ON l.bom_id = b.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE b.is_latest_version = 'Y'
          AND l.new_lot_no IS NOT NULL
          AND l.rework_pending > 0
          AND TRIM(l.part_number) = TRIM(b.bom_no)
          AND l.work_date BETWEEN %s AND %s
        GROUP BY b.bom_id, b.bom_no, b.product_name, b.cust_id, COALESCE(c.CU_Name, '')
        HAVING SUM(l.rework_pending) > 0
        ORDER BY b.bom_no
        """,
        (month_start, month_end),
    )
    result: List[Dict[str, Any]] = []
    for r in rows:
        bid = str(r["bom_id"])
        bom_no = str(r.get("bom_no") or "").strip()
        result.append({
            "eligibleKey": f"rweld:eligible:{bid}",
            "bomId": bid,
            "bomNo": bom_no,
            "partNumber": bom_no,
            "productName": r.get("product_name") or "",
            "custId": int(r["cust_id"]) if r.get("cust_id") is not None else None,
            "customerName": r.get("customer_name") or "",
            "pendingQty": int(r.get("pending_qty") or 0),
            "isEligible": True,
        })
    return result


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
    bom_id = str(lot.get("bom_id") or "")
    bom_children = get_laser_welding_bom_children(bom_id) if bom_id else []
    produced = _produced_qty_from_consume_lines(line_dicts, bom_children)
    d["totalQty"] = produced
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
    operator_ids: str,
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
    ids_csv = _resolve_operator_ids(operator_ids)
    _validate_operator_ids_csv(ids_csv)
    machine = _fetch_lw_machine(machine_id, machine_type=_default_lw_machine_type())
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
          AND operator_ids = %s AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_WELDING_REWORK, bid, ids_csv, wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open re-work welding row already exists for this BOM and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_ids, machine_id
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s, %s)
        """,
        (bom_no, bid, LINE_WELDING_REWORK, SESSION_SOURCE_LOT, wd, ids_csv, int(machine_id)),
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
    operator_ids: Optional[str] = None,
    processed_by: Optional[int] = None,
    ot_flag: Optional[str] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if rework_qty <= 0:
        raise ValueError("Re-work QTY must be greater than 0")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    session_ot = _normalize_ot_flag(ot_flag)
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
        line_operator_ids = _operator_ids_csv(operator_ids or draft.get("operator_ids") or "")
        if not line_operator_ids:
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
                "extras": _line_extras_from_item({**c, "otFlag": c.get("otFlag") or session_ot}),
            })

        for pn, req in required.items():
            got = welded_by_part.get(pn, 0)
            if got > req:
                raise ValueError(
                    f"Part {pn}: welded qty {got} exceeds required {req} (BOM × re-work qty)"
                )

        # Allocate scrap on original child lots before recording new rework consumption lines.
        _allocate_removed_scrap(cursor, target_id, welded_by_part, required)

        consume_specs: List[Dict[str, Any]] = []
        for c in pending_consumptions:
            part_no = c["part_no"]
            child_lot_id = c["child_lot_id"]
            child = c["child"]
            consumed = c["consumed"]
            qa = c["qa"]
            scrap = c["scrap"]
            extras = c.get("extras") or _line_extras_from_item({"otFlag": session_ot})

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

            consume_specs.append({
                "part_number": part_no,
                "lot_id": target_id,
                "child_lot_id": child_lot_id,
                "line_type": LINE_WELDING_REWORK,
                "source_lot_no": child.get("new_lot_no") or "",
                "production_date": wd,
                "inspected_qty": consumed,
                "qa_qty": qa,
                "scrap_qty": scrap,
                "rework_qty": extras["rework_qty"],
                "scrap_remark": extras["scrap_remark"],
                "rework_remark": extras["rework_remark"],
                "operator_ids": line_operator_ids,
                "machine_id": line_machine,
                "time_taken_minutes": time_taken_minutes,
                "ot_flag": extras["ot_flag"],
            })

        if consume_specs:
            _insert_line_batch(cursor, consume_specs)

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
    line_dicts = _enrich_consume_lines_with_nested_sa([_line_to_dict(ln) for ln in lines])
    d = _lot_to_dict(lot, line_dicts)
    d["rowKey"] = f"sa:{lot['lot_id']}"
    d["isDraft"] = not processed
    d["isPending"] = not processed
    d["isAssembly"] = True
    d["isSubAssembly"] = True
    d["batchMode"] = "sub_assembly"
    d["subAssemblyPartNo"] = str(lot.get("part_number") or "")
    bom_id = str(lot.get("bom_id") or "")
    sa_part = str(lot.get("part_number") or "")
    bom_children = get_sub_assembly_children(bom_id, sa_part) if bom_id and sa_part else []
    produced = _produced_qty_from_consume_lines(line_dicts, bom_children)
    d["weldQty"] = produced
    d["totalQty"] = produced
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
          AND l.new_lot_no NOT LIKE %s
        ORDER BY l.lot_id DESC
        """,
        (wd, "PCK/%"),
    )
    for lot in lots:
        if _is_packing_output_lot_row(lot):
            continue
        if not _is_sub_assembly_lot_row(lot, str(lot.get("bom_no") or "")):
            continue
        result.append(_sub_assembly_row_from_lot(lot))

    return result


def create_pending_sub_assembly(
    sub_assembly_part_no: str,
    operator_ids: str,
    work_date: str,
    machine_id: int,
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
    ids_csv = _resolve_operator_ids(operator_ids)
    _validate_operator_ids_csv(ids_csv)
    machine = _fetch_lw_machine(machine_id, machine_type=_default_sa_machine_type())
    if not machine:
        raise ValueError("Invalid machine — select an active sub-assembly machine")

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
          AND part_number = %s AND operator_ids = %s
          AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_SUB_ASSEMBLY_CONSUME, bid, sa_part, ids_csv, wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError(
            "An open sub-assembly row already exists for this BOM, part, and operator today"
        )

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_ids, machine_id
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s, %s)
        """,
        (sa_part, bid, LINE_SUB_ASSEMBLY_CONSUME, SESSION_SOURCE_LOT, wd, ids_csv, int(machine_id)),
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
    operator_ids: Optional[str] = None,
    processed_by: Optional[int] = None,
    ot_flag: Optional[str] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if weld_qty <= 0:
        raise ValueError("Weld QTY must be greater than 0")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    session_ot = _normalize_ot_flag(ot_flag)

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
        line_operator_ids = _operator_ids_csv(operator_ids or draft.get("operator_ids") or "")
        if not line_operator_ids:
            raise ValueError("Operator is required")
        line_machine = int(draft.get("machine_id") or 0)
        if not line_machine:
            raise ValueError("Machine is required — add BOM, part, operator, and machine first")
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
        consume_specs: List[Dict[str, Any]] = []

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
            extras = _line_extras_from_item({**c, "otFlag": c.get("otFlag") or session_ot})

            consume_specs.append({
                "part_number": part_no,
                "lot_id": lot_id,
                "child_lot_id": child_lot_id,
                "line_type": LINE_SUB_ASSEMBLY_CONSUME,
                "source_lot_no": child.get("new_lot_no") or "",
                "production_date": wd,
                "inspected_qty": consumed,
                "qa_qty": qa,
                "scrap_qty": scrap,
                "rework_qty": extras["rework_qty"],
                "scrap_remark": extras["scrap_remark"],
                "rework_remark": extras["rework_remark"],
                "operator_ids": line_operator_ids,
                "machine_id": line_machine,
                "time_taken_minutes": time_taken_minutes,
                "ot_flag": extras["ot_flag"],
            })

        for pn, req in required.items():
            got = welded_by_part.get(pn, 0)
            if got != req:
                raise ValueError(
                    f"Part {pn}: required welded qty {req} (BOM × weld qty), got {got}"
                )

        if consume_specs:
            _insert_line_batch(cursor, consume_specs)

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


def get_rework_sub_assembly_eligible_items(work_date: str) -> List[Dict[str, Any]]:
    month_start, month_end = _month_range_from_work_date(work_date)
    rows = fetch_all(
        """
        SELECT
            b.bom_id,
            b.bom_no,
            b.product_name,
            b.cust_id,
            COALESCE(c.CU_Name, '') AS customer_name,
            MAX(TRIM(l.part_number)) AS part_no,
            COALESCE(
                MAX(l.product_name),
                MAX(bl.PART_NAME),
                MAX(TRIM(l.part_number))
            ) AS part_name,
            SUM(l.rework_pending) AS pending_qty
        FROM bom b
        INNER JOIN laser_welding_lot l ON l.bom_id = b.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        LEFT JOIN bom_lin_item bl
            ON bl.bom_id = b.bom_id AND TRIM(bl.PART_NO) = TRIM(l.part_number)
        WHERE b.is_latest_version = 'Y'
          AND l.new_lot_no IS NOT NULL
          AND l.rework_pending > 0
          AND TRIM(l.part_number) != TRIM(b.bom_no)
          AND l.work_date BETWEEN %s AND %s
        GROUP BY
            b.bom_id, b.bom_no, b.product_name, b.cust_id, COALESCE(c.CU_Name, ''),
            TRIM(l.part_number)
        HAVING SUM(l.rework_pending) > 0
        ORDER BY part_no, b.bom_no
        """,
        (month_start, month_end),
    )
    result: List[Dict[str, Any]] = []
    for r in rows:
        bid = str(r["bom_id"])
        part_no = str(r.get("part_no") or "").strip()
        if not part_no:
            continue
        result.append({
            "eligibleKey": f"sa-rw:eligible:{bid}:{part_no}",
            "bomId": bid,
            "bomNo": str(r.get("bom_no") or "").strip(),
            "partNumber": str(r.get("bom_no") or "").strip(),
            "productName": r.get("product_name") or "",
            "subAssemblyPartNo": part_no,
            "partName": str(r.get("part_name") or part_no).strip(),
            "custId": int(r["cust_id"]) if r.get("cust_id") is not None else None,
            "customerName": r.get("customer_name") or "",
            "pendingQty": int(r.get("pending_qty") or 0),
            "isEligible": True,
            "isSubAssembly": True,
        })
    return result


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
    bom_id = str(lot.get("bom_id") or "")
    sa_part = str(lot.get("part_number") or "")
    bom_children = get_sub_assembly_children(bom_id, sa_part) if bom_id and sa_part else []
    d["totalQty"] = _produced_qty_from_consume_lines(line_dicts, bom_children)
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
    operator_ids: str,
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
    ids_csv = _resolve_operator_ids(operator_ids)
    _validate_operator_ids_csv(ids_csv)

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
          AND part_number = %s AND operator_ids = %s
          AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_SUB_ASSEMBLY_REWORK, bid, sa_part, ids_csv, wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError(
            "An open re-work sub-assembly row already exists for this BOM, part, and operator today"
        )

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_ids
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (sa_part, bid, LINE_SUB_ASSEMBLY_REWORK, SESSION_SOURCE_LOT, wd, ids_csv),
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
    operator_ids: Optional[str] = None,
    processed_by: Optional[int] = None,
    ot_flag: Optional[str] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if rework_qty <= 0:
        raise ValueError("Re-work QTY must be greater than 0")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    session_ot = _normalize_ot_flag(ot_flag)
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
        line_operator_ids = _operator_ids_csv(operator_ids or draft.get("operator_ids") or "")
        if not line_operator_ids:
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
                "extras": _line_extras_from_item({**c, "otFlag": c.get("otFlag") or session_ot}),
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

        consume_specs: List[Dict[str, Any]] = []
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
            extras = c.get("extras") or _line_extras_from_item({"otFlag": session_ot})
            consume_specs.append({
                "part_number": c["part_no"],
                "lot_id": target_id,
                "child_lot_id": c["child_lot_id"],
                "line_type": LINE_SUB_ASSEMBLY_REWORK,
                "source_lot_no": c["child"].get("new_lot_no") or "",
                "production_date": wd,
                "inspected_qty": c["consumed"],
                "qa_qty": c["qa"],
                "scrap_qty": c["scrap"],
                "rework_qty": extras["rework_qty"],
                "scrap_remark": extras["scrap_remark"],
                "rework_remark": extras["rework_remark"],
                "operator_ids": line_operator_ids,
                "machine_id": int(draft.get("machine_id") or 0) or None,
                "time_taken_minutes": time_taken_minutes,
                "ot_flag": extras["ot_flag"],
            })

        if consume_specs:
            _insert_line_batch(cursor, consume_specs)

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
    line_dicts = _enrich_packing_product_lines([_line_to_dict(ln) for ln in lines])
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
    d["totalQty"] = _row_total_qty_from_lines(line_dicts)
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
              AND new_lot_no NOT LIKE %s
            ORDER BY lot_id DESC
            """,
            (bid, sa_part, "PCK/%"),
        )
    else:
        rows = fetch_all(
            """
            SELECT l.lot_id, l.new_lot_no, l.inspection_pending
            FROM laser_welding_lot l
            INNER JOIN bom b ON b.bom_id = l.bom_id
            WHERE l.bom_id = %s AND l.new_lot_no IS NOT NULL AND l.inspection_pending > 0
              AND TRIM(l.part_number) = TRIM(b.bom_no)
              AND l.new_lot_no NOT LIKE %s
            ORDER BY l.lot_id DESC
            """,
            (bid, "PCK/%"),
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


def get_cleaning_rows(work_date: str, scope: Optional[str] = None) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    scope_key = str(scope or "").strip().lower()
    sa_only = scope_key in ("sa", "sa_cleaning")
    lw_only = scope_key in ("lw", "lw_cleaning")

    def _matches_scope(lot: Dict[str, Any]) -> bool:
        flags = _cleaning_sub_assembly_flags(lot.get("part_number"), lot.get("bom_no"))
        is_sa = bool(flags.get("isSubAssembly"))
        if sa_only and not is_sa:
            return False
        if lw_only and is_sa:
            return False
        return True

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
        if not _matches_scope({"part_number": line.get("part_number"), "bom_no": line.get("bom_no")}):
            continue
        row = _draft_session_row_from_line(line, "cleaning", bom=bom)
        row.update(_cleaning_sub_assembly_flags(line.get("part_number"), line.get("bom_no")))
        result.append(row)

    committed_lines = fetch_all(
        """
        SELECT ln.*, l.part_number AS lot_part_number, l.bom_id AS lot_bom_id,
               b.product_name, b.bom_no
        FROM laser_welding_line ln
        INNER JOIN laser_welding_lot l ON l.lot_id = ln.lot_id
        LEFT JOIN bom b ON b.bom_id = l.bom_id
        WHERE ln.line_type = %s
          AND ln.production_date = %s
          AND ln.lot_id IS NOT NULL
          AND ln.inspected_qty > 0
        ORDER BY ln.cd_line_id, ln.line_id
        """,
        (LINE_ASSEMBLY_INSPECTION, wd),
    )
    for cd_id, lines in _committed_lines_by_cd(committed_lines).items():
        first = lines[0]
        lot_stub = {
            "part_number": first.get("lot_part_number") or first.get("part_number"),
            "bom_no": first.get("bom_no"),
        }
        if not _matches_scope(lot_stub):
            continue
        result.append(_session_row_from_cd_group(cd_id, lines, "cleaning", wd))

    return result


def create_pending_cleaning(
    bom_id: str,
    operator_ids: str,
    work_date: str,
    created_by: Optional[int] = None,
    sub_assembly_part_no: Optional[str] = None,
) -> Dict[str, Any]:
    bid = str(bom_id or "").strip()
    sa_part = str(sub_assembly_part_no or "").strip()
    wd = _parse_date(work_date)
    if not bid or not wd:
        raise ValueError("BOM and work date are required")

    ids_csv = _resolve_operator_ids(operator_ids)
    _validate_operator_ids_csv(ids_csv)

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
          AND part_number = %s AND operator_ids = %s
          AND production_date = %s AND source_lot_no = %s
        """,
        (LINE_ASSEMBLY_INSPECTION, bid, line_part_no, ids_csv, wd, SESSION_SOURCE_LOT),
    )
    if existing:
        raise ValueError("An open cleaning row already exists for this selection and operator today")

    line_id = execute_insert(
        """
        INSERT INTO laser_welding_line (
            part_number, bom_id, lot_id, line_type, source_lot_no, production_date,
            inspected_qty, qa_qty, scrap_qty, operator_ids
        ) VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 0, %s)
        """,
        (line_part_no, bid, LINE_ASSEMBLY_INSPECTION, SESSION_SOURCE_LOT, wd, ids_csv),
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


def _apply_inspection_to_lot(
    cursor: Any,
    target: Dict[str, Any],
    *,
    inspected_qty: int,
    qa_qty: int,
    scrap_qty: int,
    scrap_remark: Optional[str],
    operator_ids: str,
    part_number: str,
    bom_id: Optional[str],
    production_date: str,
    time_taken_minutes: int,
    ot_flag: str,
    processed_by: Optional[int],
    source_lot_no: Optional[str] = None,
) -> Dict[str, Any]:
    target_lot_id = int(target["lot_id"])
    pending = int(target.get("inspection_pending") or 0)
    if inspected_qty > pending:
        raise ValueError(
            f"Inspected QTY exceeds inspection pending ({pending}) "
            f"for lot {target.get('new_lot_no')}"
        )
    totals = _aggregate_lines([{
        "inspectedQty": inspected_qty,
        "qaQty": qa_qty,
        "scrapQty": scrap_qty,
    }])
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
    source_no = source_lot_no or str(target.get("new_lot_no") or "")
    scrap = int(scrap_qty or 0)
    return {
        "part_number": part_number or target.get("part_number"),
        "bom_id": bom_id or target.get("bom_id"),
        "lot_id": target_lot_id,
        "line_type": LINE_ASSEMBLY_INSPECTION,
        "source_lot_no": source_no,
        "production_date": production_date,
        "inspected_qty": inspected_qty,
        "qa_qty": qa_qty,
        "scrap_qty": scrap,
        "rework_qty": 0,
        "scrap_remark": scrap_remark if scrap > 0 else None,
        "rework_remark": None,
        "operator_ids": operator_ids,
        "time_taken_minutes": time_taken_minutes,
        "ot_flag": ot_flag,
    }


def apply_weld_inspection(
    lot_id: int,
    work_date: str,
    qa_qty: int,
    scrap_qty: int,
    operator_ids: str,
    time_taken_minutes: int,
    scrap_remark: Optional[str] = None,
    processed_by: Optional[int] = None,
    ot_flag: Optional[str] = None,
) -> None:
    """Apply parent-level QA/scrap to a freshly welded lot (Assembly_Inspection line)."""
    inspected = int(qa_qty or 0) + int(scrap_qty or 0)
    if inspected <= 0:
        return
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    ids_csv = _operator_ids_csv(operator_ids)
    if not ids_csv:
        raise ValueError("Operator is required")
    session_ot = _normalize_ot_flag(ot_flag)

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_lot
            WHERE lot_id = %s AND bom_id IS NOT NULL AND new_lot_no IS NOT NULL
            FOR UPDATE
            """,
            (int(lot_id),),
        )
        target = cursor.fetchone()
        if not target:
            raise ValueError(f"Target assembly lot {lot_id} not found")

        line_spec = _apply_inspection_to_lot(
            cursor,
            target,
            inspected_qty=inspected,
            qa_qty=int(qa_qty or 0),
            scrap_qty=int(scrap_qty or 0),
            scrap_remark=scrap_remark,
            operator_ids=ids_csv,
            part_number=str(target.get("part_number") or ""),
            bom_id=str(target.get("bom_id") or "") or None,
            production_date=wd,
            time_taken_minutes=int(time_taken_minutes or 0),
            ot_flag=session_ot,
            processed_by=processed_by,
        )
        _insert_line_batch(cursor, [line_spec])


def inspect_assembly(
    draft_line_id: int,
    work_date: str,
    lines: List[Dict[str, Any]],
    time_taken_minutes: int,
    processed_by: Optional[int] = None,
    ot_flag: Optional[str] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")
    session_ot = _normalize_ot_flag(ot_flag)

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

        draft_operator_ids = str(draft.get("operator_ids") or "").strip()
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

        line_specs: List[Dict[str, Any]] = []
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
                scrap = int(v["scrapQty"])
                line_ot = _line_ot_flag(v, session_ot)
                line_specs.append({
                    "part_number": draft.get("part_number") or target.get("part_number"),
                    "bom_id": bom_id or target.get("bom_id"),
                    "lot_id": target_lot_id,
                    "line_type": LINE_ASSEMBLY_INSPECTION,
                    "source_lot_no": source_no,
                    "production_date": wd,
                    "inspected_qty": v["inspectedQty"],
                    "qa_qty": v["qaQty"],
                    "scrap_qty": scrap,
                    "rework_qty": int(v.get("reworkQty") or 0),
                    "scrap_remark": v.get("scrapRemark") if scrap > 0 else None,
                    "rework_remark": v.get("reworkRemark"),
                    "operator_ids": draft_operator_ids,
                    "time_taken_minutes": time_taken_minutes,
                    "ot_flag": line_ot,
                })

        if line_specs:
            _insert_line_batch(cursor, line_specs)

        cursor.execute("DELETE FROM laser_welding_line WHERE line_id = %s", (draft_line_id,))

    return {"draftLineId": draft_line_id, "saved": len(non_zero)}


# --- Tracking snapshot (from ProductionScheduling) ---

_PHASE_PRIORITY = {
    "rework_pending": 0,
    "qa_pending": 1,
    "awaiting_clean": 2,
    "ready_for_weld": 3,
    "ready_to_pack": 3,
    "inspected_ready": 3,
    "erp_stock": 4,
    "consumed": 5,
}


def _tracking_erp_available(part_no: str, cache: Dict[str, int]) -> int:
    part = str(part_no or "").strip()
    if not part:
        return 0
    if part in cache:
        return cache[part]
    qty = 0
    try:
        if bo_inventory.is_bo_sub_assembly_part(part):
            qty = int(bo_inventory.fetch_bo_available_qty(part) or 0)
        else:
            comp_id = erp_stock.resolve_comp_id(part)
            if comp_id:
                _, next_stages = _erp_stages_for_part(part)
                plant_id = _erp_plant_for_part(part)
                rows = erp_stock.fetch_lot_inventory(comp_id, plant_id, next_stages=next_stages)
                qty = sum(int(r.get("availableQty") or 0) for r in rows if int(r.get("availableQty") or 0) > 0)
    except (ValueError, TypeError):
        qty = 0
    cache[part] = max(0, qty)
    return cache[part]


def _classify_child_part_phase(
    total_okayed: int,
    total_qa: int,
    erp_available: int,
    has_lots: bool,
    has_consumed: bool,
) -> str:
    if total_qa > 0:
        return "qa_pending"
    if total_okayed > 0:
        return "inspected_ready"
    if erp_available > 0:
        return "erp_stock"
    if has_consumed or has_lots:
        return "consumed"
    return "erp_stock"


def _classify_assembly_lot_phase(row: Dict[str, Any], is_sa: bool) -> Optional[str]:
    rework = int(row.get("rework_pending") or 0)
    qa = int(row.get("total_qa") or 0)
    insp = int(row.get("inspection_pending") or 0)
    okayed = int(row.get("total_okayed") or 0)
    if rework > 0:
        return "rework_pending"
    if qa > 0:
        return "qa_pending"
    if insp > 0:
        return "awaiting_clean"
    if okayed > 0:
        return "ready_for_weld" if is_sa else "ready_to_pack"
    if _is_processed(row):
        return "consumed"
    return None


def _tracking_lot_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "lotId": int(row["lot_id"]),
        "lotNo": row.get("new_lot_no") or "",
        "totalInwarded": int(row.get("total_inwarded") or 0),
        "totalOkayed": int(row.get("total_okayed") or 0),
        "totalQa": int(row.get("total_qa") or 0),
        "inspectionPending": int(row.get("inspection_pending") or 0),
        "reworkPending": int(row.get("rework_pending") or 0),
        "scrap": int(row.get("scrap") or 0),
    }


def _tracking_matches_query(item: Dict[str, Any], q: str) -> bool:
    if not q:
        return True
    hay = " ".join(
        str(item.get(k) or "")
        for k in (
            "partNo",
            "partName",
            "bomNo",
            "productName",
            "lotNo",
            "customerName",
            "saPartNo",
        )
    ).lower()
    return q in hay


def _tracking_matches_phase(item: Dict[str, Any], phase: str) -> bool:
    if not phase:
        return True
    return str(item.get("phase") or "") == phase


def _compute_capacity_children(
    children: List[Dict[str, Any]],
    lw_okayed_by_part: Dict[str, int],
    erp_cache: Dict[str, int],
) -> Tuple[List[Dict[str, Any]], int, Optional[Dict[str, Any]]]:
    child_rows: List[Dict[str, Any]] = []
    max_build = None
    bottleneck: Optional[Dict[str, Any]] = None
    for ch in children:
        part_no = str(ch.get("partNo") or "").strip()
        bom_qty = max(1, int(ch.get("qty") or 0))
        lw_okayed = int(lw_okayed_by_part.get(part_no) or 0)
        erp_avail = _tracking_erp_available(part_no, erp_cache)
        total_avail = lw_okayed + erp_avail
        max_from = total_avail // bom_qty if bom_qty else 0
        if lw_okayed > 0 and erp_avail > 0:
            source = "both"
        elif lw_okayed > 0:
            source = "lw"
        elif erp_avail > 0:
            source = "erp"
        else:
            source = "lw"
        row = {
            "partNo": part_no,
            "partName": ch.get("partName") or _part_name(part_no),
            "bomQty": bom_qty,
            "lwOkayed": lw_okayed,
            "erpAvailable": erp_avail,
            "maxFromChild": max_from,
            "source": source,
            "isBottleneck": False,
        }
        child_rows.append(row)
        if max_build is None or max_from < max_build:
            max_build = max_from
            bottleneck = row
    if bottleneck:
        for r in child_rows:
            r["isBottleneck"] = r["partNo"] == bottleneck["partNo"]
    return child_rows, int(max_build or 0), bottleneck


def get_tracking_snapshot(
    cust_id: Optional[int] = None,
    q: str = "",
    phase: str = "",
) -> Dict[str, Any]:
    search_q = str(q or "").strip().lower()
    phase_filter = str(phase or "").strip()

    child_lot_rows = fetch_all(
        """
        SELECT l.*
        FROM laser_welding_lot l
        WHERE l.bom_id IS NULL
        ORDER BY l.part_number, l.lot_id DESC
        """
    )

    lw_agg_rows = fetch_all(
        """
        SELECT TRIM(part_number) AS part_no,
               SUM(total_okayed) AS lw_okayed,
               SUM(total_qa) AS qa_pending
        FROM laser_welding_lot
        GROUP BY TRIM(part_number)
        """
    )
    lw_okayed_by_part = {
        str(r.get("part_no") or "").strip(): int(r.get("lw_okayed") or 0)
        for r in lw_agg_rows
        if str(r.get("part_no") or "").strip()
    }

    erp_cache: Dict[str, int] = {}
    parts_catalog = get_parts("production")
    child_by_part: Dict[str, Dict[str, Any]] = {}

    for lot in child_lot_rows:
        part_no = str(lot.get("part_number") or "").strip()
        if not part_no:
            continue
        entry = child_by_part.setdefault(
            part_no,
            {
                "partNo": part_no,
                "partName": _part_name(part_no),
                "lwOkayed": 0,
                "qaPending": 0,
                "erpAvailable": 0,
                "lotCount": 0,
                "lots": [],
                "hasConsumed": False,
            },
        )
        entry["lwOkayed"] += int(lot.get("total_okayed") or 0)
        entry["qaPending"] += int(lot.get("total_qa") or 0)
        entry["lotCount"] += 1
        lot_phase = _classify_child_part_phase(
            int(lot.get("total_okayed") or 0),
            int(lot.get("total_qa") or 0),
            0,
            True,
            _is_processed(lot) and int(lot.get("total_okayed") or 0) == 0,
        )
        if lot_phase == "consumed":
            entry["hasConsumed"] = True
        if _is_processed(lot) or int(lot.get("total_okayed") or 0) > 0 or int(lot.get("total_qa") or 0) > 0:
            entry["lots"].append({**_tracking_lot_summary(lot), "phase": lot_phase})

    for p in parts_catalog:
        part_no = str(p.get("partNo") or p.get("part_no") or "").strip()
        if not part_no:
            continue
        entry = child_by_part.setdefault(
            part_no,
            {
                "partNo": part_no,
                "partName": p.get("partName") or p.get("part_name") or _part_name(part_no),
                "lwOkayed": 0,
                "qaPending": 0,
                "erpAvailable": 0,
                "lotCount": 0,
                "lots": [],
                "hasConsumed": False,
            },
        )
        if p.get("partName") or p.get("part_name"):
            entry["partName"] = p.get("partName") or p.get("part_name")

    child_parts: List[Dict[str, Any]] = []
    for part_no, entry in child_by_part.items():
        erp_avail = _tracking_erp_available(part_no, erp_cache)
        entry["erpAvailable"] = erp_avail
        entry["lwOkayed"] = int(lw_okayed_by_part.get(part_no) or entry["lwOkayed"])
        for r in lw_agg_rows:
            if str(r.get("part_no") or "").strip() == part_no:
                entry["qaPending"] = int(r.get("qa_pending") or 0)
                break
        entry["phase"] = _classify_child_part_phase(
            entry["lwOkayed"],
            entry["qaPending"],
            erp_avail,
            entry["lotCount"] > 0,
            entry["hasConsumed"],
        )
        if entry["phase"] == "consumed" and entry["lwOkayed"] == 0 and entry["qaPending"] == 0 and erp_avail == 0:
            if entry["lotCount"] == 0:
                continue
        if not _tracking_matches_query(entry, search_q):
            continue
        if not _tracking_matches_phase(entry, phase_filter):
            continue
        child_parts.append(
            {
                "partNo": entry["partNo"],
                "partName": entry["partName"],
                "phase": entry["phase"],
                "erpAvailable": entry["erpAvailable"],
                "lwOkayed": entry["lwOkayed"],
                "qaPending": entry["qaPending"],
                "lotCount": entry["lotCount"],
                "lots": entry["lots"],
            }
        )
    child_parts.sort(key=lambda x: (x["phase"], x["partNo"]))

    asm_rows = fetch_all(
        """
        SELECT l.*, b.bom_no, b.product_name, b.cust_id,
               COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_lot l
        LEFT JOIN bom b ON b.bom_id = l.bom_id AND b.is_latest_version = 'Y'
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE l.bom_id IS NOT NULL
          AND l.new_lot_no IS NOT NULL
          AND TRIM(l.new_lot_no) != ''
          AND l.new_lot_no NOT LIKE %s
        ORDER BY l.processed_at DESC, l.lot_id DESC
        """,
        ("LBO/%",),
    )

    sub_assemblies: List[Dict[str, Any]] = []
    final_assemblies: List[Dict[str, Any]] = []

    for row in asm_rows:
        if cust_id is not None and int(row.get("cust_id") or 0) != int(cust_id):
            continue
        bom_no = str(row.get("bom_no") or "").strip()
        is_sa = _is_sub_assembly_lot_row(row, bom_no)
        is_fg = _is_final_assembly_lot_row(row, bom_no)
        if not is_sa and not is_fg:
            lot_no = str(row.get("new_lot_no") or "")
            if lot_no.startswith("SA/"):
                is_sa = True
            elif lot_no.startswith("LW/"):
                is_fg = True
            else:
                continue
        lot_phase = _classify_assembly_lot_phase(row, is_sa)
        if not lot_phase:
            continue
        part_no = str(row.get("part_number") or "").strip()
        item = {
            "bomId": str(row.get("bom_id") or ""),
            "bomNo": bom_no,
            "productName": row.get("product_name") or "",
            "customerName": row.get("customer_name") or "",
            "lotNo": row.get("new_lot_no") or "",
            "lotId": int(row["lot_id"]),
            "partNo": part_no,
            "phase": lot_phase,
            "totalInwarded": int(row.get("total_inwarded") or 0),
            "totalOkayed": int(row.get("total_okayed") or 0),
            "totalQa": int(row.get("total_qa") or 0),
            "inspectionPending": int(row.get("inspection_pending") or 0),
            "reworkPending": int(row.get("rework_pending") or 0),
            "scrap": int(row.get("scrap") or 0),
        }
        if is_sa:
            item["saPartNo"] = part_no
            if not _tracking_matches_query(item, search_q):
                continue
            if not _tracking_matches_phase(item, phase_filter):
                continue
            sub_assemblies.append(item)
        else:
            if not _tracking_matches_query(item, search_q):
                continue
            if not _tracking_matches_phase(item, phase_filter):
                continue
            final_assemblies.append(item)

    bom_capacity: List[Dict[str, Any]] = []
    sa_capacity: List[Dict[str, Any]] = []
    boms = get_boms(cust_id)
    sa_seen: set = set()

    for bom in boms:
        bid = str(bom.get("bomId") or "")
        children = get_laser_welding_bom_children(bid)
        if not children:
            continue
        child_rows, max_build, bottleneck = _compute_capacity_children(
            children, lw_okayed_by_part, erp_cache
        )
        cap_item = {
            "bomId": bid,
            "bomNo": bom.get("bomNo") or "",
            "productName": bom.get("productName") or "",
            "customerName": bom.get("customerName") or "",
            "maxBuildQty": max_build,
            "bottleneckPartNo": bottleneck["partNo"] if bottleneck else "",
            "bottleneckAvailable": (
                bottleneck["lwOkayed"] + bottleneck["erpAvailable"] if bottleneck else 0
            ),
            "bottleneckBomQty": bottleneck["bomQty"] if bottleneck else 0,
            "children": child_rows,
        }
        if search_q:
            hay = f"{cap_item['bomNo']} {cap_item['productName']} {cap_item['customerName']}".lower()
            child_hay = " ".join(c["partNo"] for c in child_rows).lower()
            if search_q not in hay and search_q not in child_hay:
                continue
        bom_capacity.append(cap_item)

        if bom_has_sub_assembly(bid):
            for sa in get_sub_assembly_parts(bid):
                sa_part = str(sa.get("partNo") or "").strip()
                key = (bid, sa_part)
                if not sa_part or key in sa_seen:
                    continue
                sa_seen.add(key)
                sa_children = get_sub_assembly_children(bid, sa_part)
                if not sa_children:
                    continue
                sa_child_rows, sa_max, sa_bn = _compute_capacity_children(
                    sa_children, lw_okayed_by_part, erp_cache
                )
                sa_cap = {
                    "bomId": bid,
                    "bomNo": bom.get("bomNo") or "",
                    "saPartNo": sa_part,
                    "saPartName": sa.get("partName") or _part_name(sa_part),
                    "maxBuildQty": sa_max,
                    "bottleneckPartNo": sa_bn["partNo"] if sa_bn else "",
                    "bottleneckAvailable": (
                        sa_bn["lwOkayed"] + sa_bn["erpAvailable"] if sa_bn else 0
                    ),
                    "bottleneckBomQty": sa_bn["bomQty"] if sa_bn else 0,
                    "children": sa_child_rows,
                }
                if search_q:
                    hay = f"{sa_cap['bomNo']} {sa_part} {sa_cap['saPartName']}".lower()
                    if search_q not in hay:
                        continue
                sa_capacity.append(sa_cap)

    summary = {
        "childPartsReady": sum(1 for p in child_parts if p["phase"] == "inspected_ready"),
        "childErpStock": sum(1 for p in child_parts if p["phase"] == "erp_stock"),
        "childQaPending": sum(1 for p in child_parts if p["phase"] == "qa_pending"),
        "saAwaitingClean": sum(1 for s in sub_assemblies if s["phase"] == "awaiting_clean"),
        "saReadyForWeld": sum(1 for s in sub_assemblies if s["phase"] == "ready_for_weld"),
        "fgAwaitingClean": sum(1 for f in final_assemblies if f["phase"] == "awaiting_clean"),
        "fgReadyToPack": sum(1 for f in final_assemblies if f["phase"] == "ready_to_pack"),
        "qaQueueTotal": (
            sum(p["qaPending"] for p in child_parts)
            + sum(s["totalQa"] for s in sub_assemblies)
            + sum(f["totalQa"] for f in final_assemblies)
        ),
        "reworkPendingTotal": (
            sum(s["reworkPending"] for s in sub_assemblies)
            + sum(f["reworkPending"] for f in final_assemblies)
        ),
    }

    return {
        "summary": summary,
        "childParts": child_parts,
        "subAssemblies": sub_assemblies,
        "finalAssemblies": final_assemblies,
        "bomCapacity": sorted(bom_capacity, key=lambda x: x["maxBuildQty"]),
        "saCapacity": sa_capacity,
    }


# --- Reports: action history ---

HISTORY_STEP_LABELS: Dict[str, str] = {
    "inspection": "Inspection",
    "sub_assembly": "Sub-Assembly",
    "sa_cleaning": "SA Inspection",
    "sa_rework": "SA Re-Work",
    "laser_welding": "Laser Welding",
    "lw_cleaning": "LW Cleaning/Inspection",
    "lw_rework": "LW Re-Work",
    "packing": "Packing",
    "qa": "QA",
}

HISTORY_STEP_ORDER = list(HISTORY_STEP_LABELS.keys())


def _history_step_for_line(
    line_type: str,
    part_number: Optional[str],
    bom_no: Optional[str],
) -> Optional[str]:
    lt = str(line_type or "").strip()
    pn = str(part_number or "").strip()
    bn = str(bom_no or "").strip()
    if lt == LINE_PART_INSPECTION:
        return "inspection"
    if lt == LINE_SUB_ASSEMBLY_CONSUME:
        return "sub_assembly"
    if lt == LINE_ASSEMBLY_INSPECTION:
        if pn and bn and pn != bn:
            return "sa_cleaning"
        return "lw_cleaning"
    if lt == LINE_SUB_ASSEMBLY_REWORK:
        return "sa_rework"
    if lt in (LINE_WELDING_CONSUME, *LINE_WELDING_CONSUME_LEGACY):
        return "laser_welding"
    if lt == LINE_WELDING_REWORK:
        return "lw_rework"
    if lt == LINE_QA_DISPOSITION:
        return "qa"
    if lt == LINE_PACKING:
        return "packing"
    if lt == LINE_REWORK:
        if bn and pn and pn != bn:
            return "sa_rework"
        if bn and pn == bn:
            return "lw_rework"
        return "inspection"
    return None


def _history_row_class(
    wf_step: str,
    part_number: Optional[str] = None,
    bom_no: Optional[str] = None,
) -> str:
    if wf_step == "inspection":
        return "Part"
    if wf_step in ("sub_assembly", "sa_cleaning", "sa_rework"):
        return "SA"
    if wf_step in ("laser_welding", "lw_cleaning", "lw_rework", "packing"):
        return "BOM"
    if wf_step == "qa":
        pn = str(part_number or "").strip()
        bn = str(bom_no or "").strip()
        if bn and pn == bn:
            return "BOM"
        if bn and pn and pn != bn:
            return "SA"
        return "Part"
    return "Part"


HISTORY_CONSUME_TYPES = frozenset({
    LINE_SUB_ASSEMBLY_CONSUME,
    LINE_WELDING_CONSUME,
    *LINE_WELDING_CONSUME_LEGACY,
})


def _history_consume_from_row(r: Dict[str, Any]) -> Dict[str, Any]:
    child_lot_id = r.get("child_lot_id")
    row_class = "Part"
    if child_lot_id:
        child_lot = fetch_one(
            "SELECT * FROM laser_welding_lot WHERE lot_id = %s",
            (int(child_lot_id),),
        )
        if child_lot and _is_sub_assembly_lot_row(child_lot):
            row_class = "SA"
    lot_no = str(r.get("child_lot_no") or r.get("source_lot_no") or "").strip()
    return {
        "partNo": str(r.get("part_number") or "").strip(),
        "lotNo": lot_no,
        "rowClass": row_class,
        "childLotId": int(child_lot_id) if child_lot_id is not None else None,
        "consumedQty": int(r.get("inspected_qty") or 0),
        "qaQty": int(r.get("qa_qty") or 0),
        "scrapQty": int(r.get("scrap_qty") or 0),
        "reworkQty": int(r.get("rework_qty") or 0),
    }


def _enrich_history_consumptions(
    consumptions: List[Dict[str, Any]],
    group_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for cons, r in zip(consumptions, group_rows):
        out = dict(cons)
        child_lot_id = r.get("child_lot_id")
        if child_lot_id and out.get("rowClass") == "SA":
            nested = fetch_all(
                """
                SELECT ln.part_number, ln.inspected_qty, ln.qa_qty, ln.scrap_qty,
                       ln.rework_qty, cl.new_lot_no AS child_lot_no, ln.source_lot_no
                FROM laser_welding_line ln
                LEFT JOIN laser_welding_lot cl ON cl.lot_id = ln.child_lot_id
                WHERE ln.lot_id = %s
                  AND ln.line_type = %s
                  AND ln.child_lot_id IS NOT NULL
                ORDER BY ln.line_id
                """,
                (int(child_lot_id), LINE_SUB_ASSEMBLY_CONSUME),
            )
            out["nestedConsumptions"] = [
                {
                    "partNo": str(n.get("part_number") or "").strip(),
                    "lotNo": str(n.get("child_lot_no") or n.get("source_lot_no") or "").strip(),
                    "rowClass": "Part",
                    "consumedQty": int(n.get("inspected_qty") or 0),
                    "qaQty": int(n.get("qa_qty") or 0),
                    "scrapQty": int(n.get("scrap_qty") or 0),
                    "reworkQty": int(n.get("rework_qty") or 0),
                }
                for n in nested
            ]
        enriched.append(out)
    return enriched


def _history_produced_qty_from_group(
    r: Dict[str, Any],
    agg_rows: List[Dict[str, Any]],
    wf_step: str,
) -> Optional[int]:
    """Weld/SA output qty for a consume session — not sum of child consumed qty."""
    effective_bom_id = str(r.get("effective_bom_id") or r.get("bom_id") or "").strip()
    if not effective_bom_id or not agg_rows:
        return None
    if wf_step == "laser_welding":
        bom_children = get_laser_welding_bom_children(effective_bom_id)
    elif wf_step == "sub_assembly":
        sa_part = str(r.get("lot_part_number") or r.get("part_number") or "").strip()
        if not sa_part:
            return None
        bom_children = get_sub_assembly_children(effective_bom_id, sa_part)
    else:
        return None
    if not bom_children:
        return None
    line_dicts = [
        {
            "partNumber": str(x.get("part_number") or "").strip(),
            "inspectedQty": int(x.get("inspected_qty") or 0),
            "qaQty": int(x.get("qa_qty") or 0),
            "scrapQty": int(x.get("scrap_qty") or 0),
        }
        for x in agg_rows
    ]
    return _produced_qty_from_consume_lines(line_dicts, bom_children)


def _history_item_from_row(
    r: Dict[str, Any],
    *,
    consumptions: Optional[List[Dict[str, Any]]] = None,
    aggregate_rows: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    bom_no = str(r.get("bom_no") or "").strip()
    part_no = str(r.get("part_number") or "").strip()
    if consumptions:
        lot_part = str(r.get("lot_part_number") or "").strip()
        if lot_part:
            part_no = lot_part
    wf_step = _history_step_for_line(r.get("line_type"), part_no, bom_no)
    if not wf_step:
        return None

    lot_no = str(r.get("lot_no") or "").strip()
    if not lot_no:
        src = str(r.get("source_lot_no") or "").strip()
        if src and src != SESSION_SOURCE_LOT:
            lot_no = src

    label = part_no
    if wf_step in ("laser_welding", "lw_cleaning", "lw_rework", "packing") and bom_no:
        label = bom_no
    elif wf_step in ("sub_assembly", "sa_cleaning", "sa_rework") and part_no:
        label = part_no

    pd = r.get("production_date")
    if hasattr(pd, "strftime"):
        work_date_iso = pd.strftime("%Y-%m-%d")
    else:
        work_date_iso = _parse_date(pd) or ""

    agg = aggregate_rows or [r]
    inspected = sum(int(x.get("inspected_qty") or 0) for x in agg)
    qa = sum(int(x.get("qa_qty") or 0) for x in agg)
    scrap = sum(int(x.get("scrap_qty") or 0) for x in agg)
    rework = sum(int(x.get("rework_qty") or 0) for x in agg)
    if consumptions:
        produced = _history_produced_qty_from_group(r, agg, wf_step)
        if produced is not None:
            inspected = produced

    row_class = _history_row_class(wf_step, part_no, bom_no)
    detail_steps = ("sub_assembly", "laser_welding")
    has_detail = bool(consumptions) and wf_step in detail_steps
    op_fields = _line_operator_fields(r)

    return {
        "lineId": int(r["line_id"]),
        "cdLineId": int(r["cd_line_id"]) if r.get("cd_line_id") is not None else None,
        "workDate": work_date_iso,
        "workflowStep": wf_step,
        "workflowLabel": HISTORY_STEP_LABELS.get(wf_step, wf_step),
        "rowClass": row_class,
        "rowType": row_class,
        "partNo": part_no,
        "bomNo": bom_no,
        "label": label,
        "partName": _part_name(part_no) if part_no else "",
        "productName": str(r.get("product_name") or "").strip(),
        "customerName": str(r.get("customer_name") or "").strip(),
        "lotNo": lot_no,
        "lotId": int(r["lot_id"]) if r.get("lot_id") is not None else None,
        "lineType": str(r.get("line_type") or ""),
        "inspectedQty": inspected,
        "qaQty": qa,
        "scrapQty": scrap,
        "reworkQty": rework,
        "scrapRemark": str(r.get("scrap_remark") or "").strip(),
        "reworkRemark": str(r.get("rework_remark") or "").strip(),
        "operatorId": op_fields["operatorId"],
        "operatorIds": op_fields["operatorIds"],
        "operatorName": op_fields["operatorName"],
        "operatorNames": op_fields["operatorNames"],
        "operatorEcno": op_fields["operatorEcno"],
        "machineId": int(r["machine_id"]) if r.get("machine_id") is not None else None,
        "machineName": str(r.get("machine_name") or "").strip(),
        "timeTakenMinutes": int(r["time_taken_minutes"]) if r.get("time_taken_minutes") is not None else None,
        "otFlag": _normalize_ot_flag(r.get("ot_flag")),
        "hasDetail": has_detail,
        "consumptions": consumptions or [],
    }


def _trace_lines_for_history(trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map sourceTrace nodes for activity detail tree (same layout as weld/SA)."""
    out: List[Dict[str, Any]] = []
    for ln in trace or []:
        item: Dict[str, Any] = {
            "partNumber": str(ln.get("partNumber") or "").strip(),
            "sourceLotNo": str(ln.get("sourceLotNo") or "").strip(),
            "inspectedQty": int(ln.get("inspectedQty") or 0),
            "qaQty": int(ln.get("qaQty") or 0),
            "scrapQty": int(ln.get("scrapQty") or 0),
        }
        nested = ln.get("nestedLines")
        if nested:
            item["nestedLines"] = _trace_lines_for_history(nested)
        out.append(item)
    return out


def _pack_material_history_row_class(item_code: str) -> str:
    code = str(item_code or "").strip().upper()
    if code.startswith("SE-C-") or code.startswith("SE-B-"):
        return "Carton"
    if code.startswith("SE-"):
        return "Tray"
    return "Part"


def _history_consumptions_from_packing_lines(
    enriched_lines: List[Dict[str, Any]],
    material_lines: List[Dict[str, Any]],
    bom_no: str,
    product_row_class: str,
) -> List[Dict[str, Any]]:
    """Packing session lines as consumption rows (unified activity detail layout)."""
    consumptions: List[Dict[str, Any]] = []
    for ln in enriched_lines:
        lot_no = str(ln.get("sourceLotNo") or "").strip()
        part_label = bom_no or str(
            ln.get("sourcePartNumber") or ln.get("partNumber") or ""
        ).strip()
        trace = _trace_lines_for_history(ln.get("sourceTrace") or [])
        cons: Dict[str, Any] = {
            "partNo": part_label,
            "lotNo": lot_no,
            "rowClass": product_row_class,
            "consumedQty": int(ln.get("inspectedQty") or 0),
            "qaQty": int(ln.get("qaQty") or 0),
            "scrapQty": int(ln.get("scrapQty") or 0),
        }
        if trace:
            cons["traceLines"] = trace
        consumptions.append(cons)

    for ln in material_lines:
        code = str(ln.get("partNumber") or "").strip()
        if not code:
            continue
        consumptions.append(
            {
                "partNo": code,
                "lotNo": "",
                "rowClass": _pack_material_history_row_class(code),
                "consumedQty": int(ln.get("inspectedQty") or 0),
                "qaQty": int(ln.get("qaQty") or 0),
                "scrapQty": int(ln.get("scrapQty") or 0),
            }
        )
    return consumptions


def _history_item_from_packing_group(
    group_rows: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """One activity row per packing session (PCK lot + source-lot tree in detail)."""
    material_codes = _all_packing_material_codes()
    ordered = sorted(group_rows, key=lambda x: int(x.get("line_id") or 0))
    product_rows = [
        r for r in ordered
        if str(r.get("part_number") or "").strip() not in material_codes
    ]
    if not product_rows:
        return None

    primary = product_rows[0]
    bom_no = str(primary.get("bom_no") or "").strip()
    part_no = str(primary.get("part_number") or "").strip()
    wf_step = "packing"

    pd = primary.get("production_date")
    if hasattr(pd, "strftime"):
        work_date_iso = pd.strftime("%Y-%m-%d")
    else:
        work_date_iso = _parse_date(pd) or ""

    cd_id = int(primary["cd_line_id"])
    pack_lot_id, pack_lot_no = _find_pack_lot_for_session(cd_id, part_no, work_date_iso)

    enriched_lines = _enrich_packing_product_lines([_line_to_dict(r) for r in product_rows])
    material_lines = [
        _line_to_dict(r) for r in ordered
        if str(r.get("part_number") or "").strip() in material_codes
    ]
    row_class = "BOM" if bom_no else "Part"
    consumptions = _history_consumptions_from_packing_lines(
        enriched_lines, material_lines, bom_no, row_class
    )

    inspected = sum(int(ln.get("inspectedQty") or 0) for ln in enriched_lines)
    qa = sum(int(r.get("qa_qty") or 0) for r in product_rows)
    scrap = sum(int(r.get("scrap_qty") or 0) for r in product_rows)
    rework = sum(int(r.get("rework_qty") or 0) for r in product_rows)
    times = [
        int(r.get("time_taken_minutes") or 0)
        for r in ordered
        if int(r.get("time_taken_minutes") or 0) > 0
    ]
    max_time = max(times) if times else None
    ot_vals = [_normalize_ot_flag(r.get("ot_flag")) for r in ordered]
    session_ot = "Y" if any(f == "Y" for f in ot_vals) else "N"

    label = bom_no or part_no
    op_fields = _line_operator_fields(primary)

    return {
        "lineId": int(primary["line_id"]),
        "cdLineId": cd_id,
        "workDate": work_date_iso,
        "workflowStep": wf_step,
        "workflowLabel": HISTORY_STEP_LABELS.get(wf_step, wf_step),
        "rowClass": row_class,
        "rowType": row_class,
        "partNo": part_no,
        "bomNo": bom_no,
        "label": label,
        "partName": _part_name(part_no) if part_no else "",
        "productName": str(primary.get("product_name") or "").strip(),
        "customerName": str(primary.get("customer_name") or "").strip(),
        "lotNo": pack_lot_no or "",
        "packLotNo": pack_lot_no or "",
        "lotId": int(pack_lot_id) if pack_lot_id is not None else None,
        "lineType": LINE_PACKING,
        "inspectedQty": inspected,
        "qaQty": qa,
        "scrapQty": scrap,
        "reworkQty": rework,
        "scrapRemark": str(primary.get("scrap_remark") or "").strip(),
        "reworkRemark": str(primary.get("rework_remark") or "").strip(),
        "operatorId": op_fields["operatorId"],
        "operatorIds": op_fields["operatorIds"],
        "operatorName": op_fields["operatorName"],
        "operatorNames": op_fields["operatorNames"],
        "operatorEcno": op_fields["operatorEcno"],
        "machineId": int(primary["machine_id"]) if primary.get("machine_id") is not None else None,
        "machineName": str(primary.get("machine_name") or "").strip(),
        "timeTakenMinutes": max_time,
        "otFlag": session_ot,
        "hasDetail": bool(consumptions),
        "consumptions": consumptions,
    }


def _history_matches_search(item: Dict[str, Any], search_q: str) -> bool:
    if not search_q:
        return True
    parts = [
        str(item.get(k) or "")
        for k in (
            "workflowLabel", "rowClass", "rowType", "label", "partNo", "bomNo",
            "partName", "productName", "customerName", "lotNo", "packLotNo",
            "operatorName", "operatorEcno", "machineName", "lineType",
        )
    ]
    for cons in item.get("consumptions") or []:
        parts.extend(str(cons.get(k) or "") for k in ("partNo", "lotNo", "rowClass"))
        for nested in cons.get("nestedConsumptions") or []:
            parts.extend(str(nested.get(k) or "") for k in ("partNo", "lotNo", "rowClass"))
        for trace_ln in cons.get("traceLines") or []:
            parts.extend(
                str(trace_ln.get(k) or "")
                for k in ("partNumber", "sourceLotNo")
            )
            for nested in trace_ln.get("nestedLines") or []:
                parts.extend(
                    str(nested.get(k) or "")
                    for k in ("partNumber", "sourceLotNo")
                )
    return search_q in " ".join(parts).lower()


def get_action_history(
    date_from: str,
    date_to: str,
    q: str = "",
    step: str = "",
    limit: int = 2500,
) -> Dict[str, Any]:
    d_from_str = _parse_date(date_from)
    d_to_str = _parse_date(date_to)
    if not d_from_str or not d_to_str:
        raise ValueError("from and to dates are required (YYYY-MM-DD)")
    d_from = datetime.strptime(d_from_str, "%Y-%m-%d").date()
    d_to = datetime.strptime(d_to_str, "%Y-%m-%d").date()
    if d_from > d_to:
        raise ValueError("from date must be on or before to date")
    if (d_to - d_from).days > 366:
        raise ValueError("Date range cannot exceed 366 days")

    search_q = str(q or "").strip().lower()
    step_filter = str(step or "").strip()
    if step_filter and step_filter not in HISTORY_STEP_LABELS:
        raise ValueError("Invalid workflow step filter")

    cap = max(1, min(int(limit or 2500), 5000))

    rows = fetch_all(
        """
        SELECT
            ln.line_id,
            ln.production_date,
            ln.line_type,
            ln.part_number,
            ln.source_lot_no,
            ln.inspected_qty,
            ln.qa_qty,
            ln.scrap_qty,
            ln.rework_qty,
            ln.scrap_remark,
            ln.rework_remark,
            ln.time_taken_minutes,
            ln.ot_flag,
            ln.operator_ids,
            ln.machine_id,
            ln.bom_id,
            ln.child_lot_id,
            ln.cd_line_id,
            l.new_lot_no AS lot_no,
            l.lot_id,
            l.part_number AS lot_part_number,
            COALESCE(l.bom_id, ln.bom_id) AS effective_bom_id,
            b.bom_no,
            b.product_name,
            COALESCE(c.CU_Name, '') AS customer_name,
            COALESCE(m.MCM_Name, '') AS machine_name,
            cl.new_lot_no AS child_lot_no
        FROM laser_welding_line ln
        LEFT JOIN laser_welding_lot l ON l.lot_id = ln.lot_id
        LEFT JOIN laser_welding_lot cl ON cl.lot_id = ln.child_lot_id
        LEFT JOIN bom b ON b.bom_id = COALESCE(l.bom_id, ln.bom_id) AND b.is_latest_version = 'Y'
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        LEFT JOIN machinemaster m ON m.MCM_Id = ln.machine_id
        WHERE ln.production_date >= %s
          AND ln.production_date <= %s
          AND (
            ln.lot_id IS NOT NULL
            OR ln.inspected_qty > 0
            OR ln.qa_qty > 0
            OR ln.scrap_qty > 0
            OR ln.rework_qty > 0
          )
          AND NOT (
            ln.lot_id IS NULL
            AND ln.source_lot_no = %s
            AND ln.inspected_qty = 0
            AND ln.qa_qty = 0
            AND ln.scrap_qty = 0
            AND ln.rework_qty = 0
          )
        ORDER BY ln.production_date DESC, ln.line_id DESC
        LIMIT %s
        """,
        (d_from, d_to, SESSION_SOURCE_LOT, cap),
    )

    consume_groups: Dict[Any, List[Dict[str, Any]]] = {}
    packing_groups: Dict[int, List[Dict[str, Any]]] = {}
    grouped_line_ids: set = set()
    for r in rows:
        lt = str(r.get("line_type") or "").strip()
        cd = r.get("cd_line_id")
        child = r.get("child_lot_id")
        if cd is not None and child is not None and lt in HISTORY_CONSUME_TYPES:
            key = (int(cd), lt)
            consume_groups.setdefault(key, []).append(r)
            grouped_line_ids.add(int(r["line_id"]))
        elif cd is not None and lt == LINE_PACKING:
            packing_groups.setdefault(int(cd), []).append(r)
            grouped_line_ids.add(int(r["line_id"]))

    out: List[Dict[str, Any]] = []

    for group_rows in consume_groups.values():
        group_rows.sort(key=lambda x: int(x["line_id"]))
        primary = group_rows[0]
        wf_step = _history_step_for_line(
            primary.get("line_type"),
            str(primary.get("part_number") or "").strip(),
            str(primary.get("bom_no") or "").strip(),
        )
        if not wf_step:
            continue
        if step_filter and wf_step != step_filter:
            continue
        consumptions = [_history_consume_from_row(r) for r in group_rows]
        if wf_step == "laser_welding":
            consumptions = _enrich_history_consumptions(consumptions, group_rows)
        item = _history_item_from_row(
            primary,
            consumptions=consumptions,
            aggregate_rows=group_rows,
        )
        if not item:
            continue
        if not _history_matches_search(item, search_q):
            continue
        out.append(item)

    for group_rows in packing_groups.values():
        if step_filter and step_filter != "packing":
            continue
        item = _history_item_from_packing_group(group_rows)
        if not item:
            continue
        if not _history_matches_search(item, search_q):
            continue
        out.append(item)

    for r in rows:
        if int(r["line_id"]) in grouped_line_ids:
            continue
        bom_no = str(r.get("bom_no") or "").strip()
        part_no = str(r.get("part_number") or "").strip()
        wf_step = _history_step_for_line(r.get("line_type"), part_no, bom_no)
        if not wf_step:
            continue
        if step_filter and wf_step != step_filter:
            continue
        item = _history_item_from_row(r)
        if not item:
            continue
        if not _history_matches_search(item, search_q):
            continue
        out.append(item)

    out.sort(
        key=lambda x: HISTORY_STEP_ORDER.index(x["workflowStep"])
        if x.get("workflowStep") in HISTORY_STEP_ORDER
        else 99,
    )
    out.sort(key=lambda x: x.get("workDate") or "", reverse=True)
    return {
        "from": _format_date(d_from),
        "to": _format_date(d_to),
        "count": len(out),
        "rows": out,
    }


# --- Reports: stock, QA history, scrap history ---

STOCK_STATE_KEYS: Tuple[str, ...] = (
    "inspection_pending",
    "fg",
    "qa",
    "scrap",
    "rework_pending",
    "packed",
)

STOCK_STATE_LABELS: Dict[str, str] = {
    "inspection_pending": "Inspection Pending",
    "fg": "FG",
    "qa": "QA",
    "scrap": "Scrap",
    "rework_pending": "Rework Pending",
    "packed": "Packed",
}


def _empty_stock_states() -> Dict[str, int]:
    return {k: 0 for k in STOCK_STATE_KEYS}


def _stock_states_total(states: Dict[str, int]) -> int:
    return sum(int(states.get(k) or 0) for k in STOCK_STATE_KEYS)


def _stock_matches_query(
    row_type: str,
    part_no: str,
    bom_no: str,
    name: str,
    q: str,
) -> bool:
    if not q:
        return True
    hay = " ".join(
        str(x or "")
        for x in (row_type, part_no, bom_no, name)
    ).lower()
    return q in hay


def _inventory_qty_by_item_codes(item_codes: Optional[Iterable[str]] = None) -> Dict[str, int]:
    """On-hand qty from ERP inventory (first row per ITEM_CODE)."""
    codes = sorted({str(c).strip() for c in (item_codes or []) if str(c).strip()})
    if not codes:
        return {}
    out: Dict[str, int] = {}
    chunk = 200
    for i in range(0, len(codes), chunk):
        batch = codes[i : i + chunk]
        placeholders = ", ".join(["%s"] * len(batch))
        rows = fetch_all(
            f"""
            SELECT TRIM(i.ITEM_CODE) AS item_code, i.QTY AS qty
            FROM inventory i
            INNER JOIN (
                SELECT TRIM(ITEM_CODE) AS code, MIN(INVENTORY_ID) AS min_id
                FROM inventory
                WHERE TRIM(ITEM_CODE) IN ({placeholders})
                GROUP BY TRIM(ITEM_CODE)
            ) pick ON TRIM(i.ITEM_CODE) = pick.code AND i.INVENTORY_ID = pick.min_id
            """,
            tuple(batch),
        )
        for r in rows:
            code = str(r.get("item_code") or "").strip()
            if code:
                out[code] = int(float(r.get("qty") or 0))
    return out


def _packed_qty_by_bom(bom_nos: Optional[Iterable[str]] = None) -> Dict[str, int]:
    """Packed FG qty from ERP inventory (first row per ITEM_CODE, LW BOMs only)."""
    codes = sorted({str(b).strip() for b in (bom_nos or []) if str(b).strip()})
    return _inventory_qty_by_item_codes(codes)


def _packed_qty_from_packing_lines(
    material_codes: Optional[Iterable[str]] = None,
) -> Dict[str, int]:
    """Tray/carton qty consumed on packing lines."""
    codes = sorted({str(c).strip() for c in (material_codes or []) if str(c).strip()})
    if not codes:
        return {}
    out: Dict[str, int] = {}
    chunk = 200
    for i in range(0, len(codes), chunk):
        batch = codes[i : i + chunk]
        placeholders = ", ".join(["%s"] * len(batch))
        rows = fetch_all(
            f"""
            SELECT TRIM(ln.part_number) AS item_code,
                   SUM(ln.inspected_qty) AS packed_qty
            FROM laser_welding_line ln
            WHERE ln.line_type = %s
              AND ln.lot_id IS NOT NULL
              AND TRIM(ln.part_number) IN ({placeholders})
            GROUP BY TRIM(ln.part_number)
            """,
            (LINE_PACKING, *batch),
        )
        for r in rows:
            code = str(r.get("item_code") or "").strip()
            if code:
                out[code] = int(float(r.get("packed_qty") or 0))
    return out


def _pack_material_stock_catalog(
    cust_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Tray and carton item codes from lw_packing_tray / lw_packing_carton."""
    tray_sql = """
        SELECT TRIM(t.tray_item_code) AS item_code,
               'Tray' AS row_type,
               COALESCE(im.ITEM_NAME, 'Tray') AS item_name,
               t.cust_id
        FROM lw_packing_tray t
        LEFT JOIN ITEM_MASTER im ON TRIM(im.ITEM_CODE) = TRIM(t.tray_item_code)
    """
    tray_params: List[Any] = []
    if cust_id is not None:
        tray_sql += " WHERE t.cust_id = %s"
        tray_params.append(int(cust_id))
    tray_sql += " ORDER BY t.tray_item_code"

    carton_sql = """
        SELECT TRIM(c.carton_item_code) AS item_code,
               'Carton' AS row_type,
               COALESCE(im.ITEM_NAME, 'Carton') AS item_name,
               NULL AS cust_id
        FROM lw_packing_carton c
        LEFT JOIN ITEM_MASTER im ON TRIM(im.ITEM_CODE) = TRIM(c.carton_item_code)
        ORDER BY c.carton_item_code
    """
    catalog: List[Dict[str, Any]] = []
    for r in fetch_all(tray_sql, tuple(tray_params) if tray_params else None):
        code = str(r.get("item_code") or "").strip()
        if code:
            catalog.append(dict(r))
    for r in fetch_all(carton_sql):
        code = str(r.get("item_code") or "").strip()
        if code:
            catalog.append(dict(r))
    return catalog


def get_stock_report(
    cust_id: Optional[int] = None,
    q: str = "",
) -> Dict[str, Any]:
    search_q = str(q or "").strip().lower()
    erp_cache: Dict[str, int] = {}
    lw_boms = get_boms(cust_id)
    bom_catalog: Dict[str, Dict[str, Any]] = {
        str(b.get("bomNo") or "").strip(): b
        for b in lw_boms
        if str(b.get("bomNo") or "").strip()
    }
    packed_by_bom = _packed_qty_by_bom(bom_catalog.keys())

    child_lot_rows = fetch_all(
        """
        SELECT l.*
        FROM laser_welding_lot l
        WHERE l.bom_id IS NULL
        ORDER BY l.part_number, l.lot_id DESC
        """
    )
    part_states: Dict[str, Dict[str, Any]] = {}

    for lot in child_lot_rows:
        part_no = str(lot.get("part_number") or "").strip()
        if not part_no:
            continue
        entry = part_states.setdefault(
            part_no,
            {
                "rowType": "Part",
                "partNo": part_no,
                "bomNo": "",
                "label": part_no,
                "partName": _part_name(part_no),
                "states": _empty_stock_states(),
            },
        )
        entry["states"]["fg"] += int(lot.get("total_okayed") or 0)
        entry["states"]["qa"] += int(lot.get("total_qa") or 0)
        entry["states"]["scrap"] += int(lot.get("scrap") or 0)
        entry["states"]["rework_pending"] += int(lot.get("rework_pending") or 0)

    for p in get_parts("production"):
        part_no = str(p.get("partNo") or p.get("part_no") or "").strip()
        if not part_no:
            continue
        entry = part_states.setdefault(
            part_no,
            {
                "rowType": "Part",
                "partNo": part_no,
                "bomNo": "",
                "label": part_no,
                "partName": p.get("partName") or p.get("part_name") or _part_name(part_no),
                "states": _empty_stock_states(),
            },
        )
        if p.get("partName") or p.get("part_name"):
            entry["partName"] = p.get("partName") or p.get("part_name")

    for part_no, entry in part_states.items():
        entry["states"]["inspection_pending"] = _tracking_erp_available(part_no, erp_cache)

    sa_states: Dict[str, Dict[str, Any]] = {}
    bom_states: Dict[str, Dict[str, Any]] = {}

    asm_rows = fetch_all(
        """
        SELECT l.*, b.bom_no, b.product_name, b.cust_id,
               COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_lot l
        LEFT JOIN bom b ON b.bom_id = l.bom_id AND b.is_latest_version = 'Y'
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE l.bom_id IS NOT NULL
          AND l.new_lot_no IS NOT NULL
          AND TRIM(l.new_lot_no) != ''
          AND l.new_lot_no NOT LIKE %s
        """,
        ("LBO/%",),
    )

    for row in asm_rows:
        if cust_id is not None and int(row.get("cust_id") or 0) != int(cust_id):
            continue
        bom_no = str(row.get("bom_no") or "").strip()
        part_no = str(row.get("part_number") or "").strip()
        is_sa = _is_sub_assembly_lot_row(row, bom_no)
        is_fg = _is_final_assembly_lot_row(row, bom_no)
        if not is_sa and not is_fg:
            lot_no = str(row.get("new_lot_no") or "")
            if lot_no.startswith("SA/"):
                is_sa = True
            elif lot_no.startswith("LW/"):
                is_fg = True
            else:
                continue

        awaiting = int(row.get("inspection_pending") or 0)
        qa = int(row.get("total_qa") or 0)
        ready = int(row.get("total_okayed") or 0)
        rework = int(row.get("rework_pending") or 0)
        scrap = int(row.get("scrap") or 0)
        packed_avail = int(packed_by_bom.get(bom_no) or 0) if is_fg and bom_no else 0
        if awaiting + qa + ready + rework + scrap <= 0 and packed_avail <= 0:
            continue

        if is_sa:
            key = part_no
            entry = sa_states.setdefault(
                key,
                {
                    "rowType": "SA",
                    "partNo": part_no,
                    "bomNo": bom_no,
                    "label": part_no,
                    "partName": row.get("product_name") or _part_name(part_no),
                    "states": _empty_stock_states(),
                },
            )
            entry["states"]["inspection_pending"] += awaiting
            entry["states"]["qa"] += qa
            entry["states"]["fg"] += ready
            entry["states"]["rework_pending"] += rework
            entry["states"]["scrap"] += scrap
        else:
            key = bom_no or part_no
            entry = bom_states.setdefault(
                key,
                {
                    "rowType": "BOM",
                    "partNo": part_no,
                    "bomNo": bom_no,
                    "label": bom_no or part_no,
                    "partName": row.get("product_name") or "",
                    "states": _empty_stock_states(),
                },
            )
            entry["states"]["inspection_pending"] += awaiting
            entry["states"]["qa"] += qa
            entry["states"]["fg"] += ready
            entry["states"]["rework_pending"] += rework
            entry["states"]["scrap"] += scrap

    for entry in bom_states.values():
        bn = str(entry.get("bomNo") or "").strip()
        if bn:
            entry["states"]["packed"] = int(packed_by_bom.get(bn) or 0)

    for bom_no, bom in bom_catalog.items():
        if bom_no in bom_states:
            continue
        packed_qty = int(packed_by_bom.get(bom_no) or 0)
        if packed_qty <= 0:
            continue
        bom_states[bom_no] = {
            "rowType": "BOM",
            "partNo": bom_no,
            "bomNo": bom_no,
            "label": bom_no,
            "partName": bom.get("productName") or "",
            "states": _empty_stock_states(),
        }
        bom_states[bom_no]["states"]["packed"] = packed_qty

    out: List[Dict[str, Any]] = []
    for bucket in (part_states, sa_states, bom_states):
        for entry in bucket.values():
            total = _stock_states_total(entry["states"])
            if total <= 0:
                continue
            if not _stock_matches_query(
                entry["rowType"],
                entry["partNo"],
                entry["bomNo"],
                entry["partName"],
                search_q,
            ):
                continue
            row = {
                "rowType": entry["rowType"],
                "partNo": entry["partNo"],
                "bomNo": entry["bomNo"],
                "label": entry["label"],
                "partName": entry["partName"],
                "totalQty": total,
            }
            for sk in STOCK_STATE_KEYS:
                row[sk] = int(entry["states"].get(sk) or 0)
            out.append(row)

    material_catalog = _pack_material_stock_catalog(cust_id)
    material_codes = [str(m.get("item_code") or "").strip() for m in material_catalog]
    material_codes = [c for c in material_codes if c]
    fg_by_material = _inventory_qty_by_item_codes(material_codes)
    packed_by_material = _packed_qty_from_packing_lines(material_codes)
    seen_materials: set = set()
    for mat in material_catalog:
        item_code = str(mat.get("item_code") or "").strip()
        if not item_code or item_code in seen_materials:
            continue
        seen_materials.add(item_code)
        row_type = str(mat.get("row_type") or "Material")
        item_name = str(mat.get("item_name") or item_code)
        fg_qty = int(fg_by_material.get(item_code) or 0)
        packed_qty = int(packed_by_material.get(item_code) or 0)
        if fg_qty <= 0 and packed_qty <= 0:
            continue
        if not _stock_matches_query(row_type, item_code, "", item_name, search_q):
            continue
        states = _empty_stock_states()
        states["fg"] = fg_qty
        states["packed"] = packed_qty
        out.append(
            {
                "rowType": row_type,
                "partNo": item_code,
                "bomNo": "",
                "label": item_code,
                "partName": item_name,
                "totalQty": _stock_states_total(states),
                **{sk: int(states.get(sk) or 0) for sk in STOCK_STATE_KEYS},
            }
        )

    type_order = {"Part": 0, "SA": 1, "BOM": 2, "Tray": 3, "Carton": 4}
    out.sort(key=lambda x: (type_order.get(x.get("rowType"), 9), x.get("label") or ""))
    return {
        "count": len(out),
        "rows": out,
        "stateColumns": [
            {"key": k, "label": STOCK_STATE_LABELS[k]}
            for k in STOCK_STATE_KEYS
        ],
    }


def _report_lines_base_sql() -> str:
    return """
        SELECT
            ln.line_id,
            ln.production_date,
            ln.line_type,
            ln.part_number,
            ln.source_lot_no,
            ln.inspected_qty,
            ln.qa_qty,
            ln.scrap_qty,
            ln.rework_qty,
            ln.scrap_remark,
            ln.rework_remark,
            ln.time_taken_minutes,
            ln.ot_flag,
            ln.operator_ids,
            ln.machine_id,
            ln.bom_id,
            l.new_lot_no AS lot_no,
            l.lot_id,
            l.part_number AS lot_part_number,
            COALESCE(l.bom_id, ln.bom_id) AS effective_bom_id,
            b.bom_no,
            b.product_name,
            COALESCE(c.CU_Name, '') AS customer_name,
            COALESCE(m.MCM_Name, '') AS machine_name
        FROM laser_welding_line ln
        LEFT JOIN laser_welding_lot l ON l.lot_id = ln.lot_id
        LEFT JOIN bom b ON b.bom_id = COALESCE(l.bom_id, ln.bom_id) AND b.is_latest_version = 'Y'
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        LEFT JOIN machinemaster m ON m.MCM_Id = ln.machine_id
    """


def _report_entry_from_line(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bom_no = str(r.get("bom_no") or "").strip()
    part_no = str(r.get("part_number") or "").strip()
    lot_part = str(r.get("lot_part_number") or "").strip()
    if lot_part:
        part_no = lot_part
    wf_step = _history_step_for_line(r.get("line_type"), part_no, bom_no)
    if not wf_step:
        return None

    lot_no = str(r.get("lot_no") or "").strip()
    if not lot_no:
        src = str(r.get("source_lot_no") or "").strip()
        if src and src != SESSION_SOURCE_LOT:
            lot_no = src

    label = part_no
    if wf_step in ("laser_welding", "lw_cleaning", "lw_rework", "packing") and bom_no:
        label = bom_no
    elif wf_step in ("sub_assembly", "sa_cleaning", "sa_rework") and part_no:
        label = part_no

    pd = r.get("production_date")
    if hasattr(pd, "strftime"):
        work_date_iso = pd.strftime("%Y-%m-%d")
    else:
        work_date_iso = _parse_date(pd) or ""

    row_class = _history_row_class(wf_step, part_no, bom_no)
    return {
        "lineId": int(r["line_id"]),
        "workDate": work_date_iso,
        "workflowStep": wf_step,
        "workflowLabel": HISTORY_STEP_LABELS.get(wf_step, wf_step),
        "rowClass": row_class,
        "rowType": row_class,
        "partNo": part_no,
        "bomNo": bom_no,
        "label": label,
        "partName": _part_name(part_no) if part_no else "",
        "productName": str(r.get("product_name") or "").strip(),
        "customerName": str(r.get("customer_name") or "").strip(),
        "lotNo": lot_no,
        "lotId": int(r["lot_id"]) if r.get("lot_id") is not None else None,
        "lineType": str(r.get("line_type") or ""),
        "inspectedQty": int(r.get("inspected_qty") or 0),
        "qaQty": int(r.get("qa_qty") or 0),
        "scrapQty": int(r.get("scrap_qty") or 0),
        "reworkQty": int(r.get("rework_qty") or 0),
        "scrapRemark": str(r.get("scrap_remark") or "").strip(),
        "reworkRemark": str(r.get("rework_remark") or "").strip(),
        "operatorId": _line_operator_fields(r)["operatorId"],
        "operatorIds": _line_operator_fields(r)["operatorIds"],
        "operatorName": _line_operator_fields(r)["operatorName"],
        "operatorNames": _line_operator_fields(r)["operatorNames"],
        "machineName": str(r.get("machine_name") or "").strip(),
        "timeTakenMinutes": int(r["time_taken_minutes"]) if r.get("time_taken_minutes") is not None else None,
        "otFlag": _normalize_ot_flag(r.get("ot_flag")),
    }


def _report_entry_matches_search(item: Dict[str, Any], search_q: str) -> bool:
    if not search_q:
        return True
    hay = " ".join(
        str(item.get(k) or "")
        for k in (
            "workflowLabel", "rowClass", "label", "partNo", "bomNo",
            "partName", "productName", "customerName", "lotNo",
            "operatorName", "operatorEcno", "machineName", "lineType",
            "scrapRemark", "reworkRemark",
        )
    ).lower()
    return search_q in hay


def get_qa_history(
    date_from: str,
    date_to: str,
    q: str = "",
    step: str = "",
    limit: int = 2500,
) -> Dict[str, Any]:
    d_from_str = _parse_date(date_from)
    d_to_str = _parse_date(date_to)
    if not d_from_str or not d_to_str:
        raise ValueError("from and to dates are required (YYYY-MM-DD)")
    d_from = datetime.strptime(d_from_str, "%Y-%m-%d").date()
    d_to = datetime.strptime(d_to_str, "%Y-%m-%d").date()
    if d_from > d_to:
        raise ValueError("from date must be on or before to date")
    if (d_to - d_from).days > 366:
        raise ValueError("Date range cannot exceed 366 days")

    search_q = str(q or "").strip().lower()
    step_filter = str(step or "").strip()
    if step_filter and step_filter not in HISTORY_STEP_LABELS:
        raise ValueError("Invalid workflow step filter")
    cap = max(1, min(int(limit or 2500), 5000))

    rows = fetch_all(
        _report_lines_base_sql()
        + """
        WHERE ln.production_date >= %s
          AND ln.production_date <= %s
          AND ln.qa_qty > 0
          AND ln.line_type <> %s
          AND NOT (
            ln.lot_id IS NULL
            AND ln.source_lot_no = %s
            AND ln.inspected_qty = 0
            AND ln.qa_qty = 0
            AND ln.scrap_qty = 0
            AND ln.rework_qty = 0
          )
        ORDER BY ln.production_date DESC, ln.line_id DESC
        LIMIT %s
        """,
        (d_from, d_to, LINE_QA_DISPOSITION, SESSION_SOURCE_LOT, cap),
    )

    out: List[Dict[str, Any]] = []
    for r in rows:
        item = _report_entry_from_line(r)
        if not item:
            continue
        if item.get("workflowStep") == "qa":
            continue
        if step_filter and item.get("workflowStep") != step_filter:
            continue
        if not _report_entry_matches_search(item, search_q):
            continue
        out.append(item)

    out.sort(key=lambda x: x.get("workDate") or "", reverse=True)
    return {
        "from": _format_date(d_from),
        "to": _format_date(d_to),
        "count": len(out),
        "rows": out,
    }


def get_scrap_history(
    date_from: str,
    date_to: str,
    q: str = "",
    step: str = "",
    limit: int = 2500,
) -> Dict[str, Any]:
    d_from_str = _parse_date(date_from)
    d_to_str = _parse_date(date_to)
    if not d_from_str or not d_to_str:
        raise ValueError("from and to dates are required (YYYY-MM-DD)")
    d_from = datetime.strptime(d_from_str, "%Y-%m-%d").date()
    d_to = datetime.strptime(d_to_str, "%Y-%m-%d").date()
    if d_from > d_to:
        raise ValueError("from date must be on or before to date")
    if (d_to - d_from).days > 366:
        raise ValueError("Date range cannot exceed 366 days")

    search_q = str(q or "").strip().lower()
    step_filter = str(step or "").strip()
    if step_filter and step_filter not in HISTORY_STEP_LABELS:
        raise ValueError("Invalid workflow step filter")
    cap = max(1, min(int(limit or 2500), 5000))

    rows = fetch_all(
        _report_lines_base_sql()
        + """
        WHERE ln.production_date >= %s
          AND ln.production_date <= %s
          AND ln.scrap_qty > 0
          AND NOT (
            ln.lot_id IS NULL
            AND ln.source_lot_no = %s
            AND ln.inspected_qty = 0
            AND ln.qa_qty = 0
            AND ln.scrap_qty = 0
            AND ln.rework_qty = 0
          )
        ORDER BY ln.production_date DESC, ln.line_id DESC
        LIMIT %s
        """,
        (d_from, d_to, SESSION_SOURCE_LOT, cap),
    )

    out: List[Dict[str, Any]] = []
    for r in rows:
        item = _report_entry_from_line(r)
        if not item:
            continue
        if step_filter and item.get("workflowStep") != step_filter:
            continue
        if not _report_entry_matches_search(item, search_q):
            continue
        out.append(item)

    out.sort(key=lambda x: x.get("workDate") or "", reverse=True)
    return {
        "from": _format_date(d_from),
        "to": _format_date(d_to),
        "count": len(out),
        "rows": out,
    }
