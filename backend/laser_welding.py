"""Laser Welding — lot-centric workflow (Child Parts, QA Disposition, Rework)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .db import execute, execute_insert, fetch_all, fetch_one, get_cursor
from . import erp_component_stock as erp_stock


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
    return {
        "lineId": int(row["line_id"]),
        "partNumber": row.get("part_number") or "",
        "lotId": int(lot_id) if lot_id is not None else None,
        "childLotId": int(child_lot_id) if child_lot_id is not None else None,
        "lineType": row.get("line_type") or "production",
        "sourceLotNo": row.get("source_lot_no") or "",
        "productionDate": _format_date(row.get("production_date")),
        "inspectedQty": int(row.get("inspected_qty") or 0),
        "qaQty": int(row.get("qa_qty") or 0),
        "isDraft": lot_id is None,
    }


def _lot_to_dict(row: Dict[str, Any], lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    wd = row.get("work_date")
    work_date_str = wd.strftime("%Y-%m-%d") if hasattr(wd, "strftime") else str(wd or "")
    processed = _is_processed(row)
    qa_approved = _is_qa_approved(row)
    op_id = row.get("operator_id")
    op_row = None
    if op_id is not None:
        op_row = _fetch_operator(op_id)
    operator_name = row.get("operator_name") or (op_row and _operator_label(op_row)) or ""
    bom_id = row.get("bom_id")
    part_no = row["part_number"] or ""
    part_name = row.get("part_name") or row.get("product_name") or ""
    if not part_name and not bom_id:
        part_name = _part_name(part_no)
    return {
        "lotId": int(row["lot_id"]),
        "partNumber": part_no,
        "partName": part_name,
        "bomId": str(bom_id) if bom_id is not None else None,
        "productName": row.get("product_name") or "",
        "operatorId": int(op_id) if op_id is not None else None,
        "operatorName": operator_name,
        "newLotNo": row.get("new_lot_no"),
        "workDate": work_date_str,
        "totalInspected": int(row.get("total_inspected") or 0),
        "totalQa": int(row.get("total_qa") or 0),
        "totalOkayed": int(row.get("total_okayed") or 0),
        "scrap": int(row.get("scrap") or 0),
        "reworkPending": int(row.get("rework_pending") or 0),
        "reworkPool": int(row.get("rework_pool") or 0),
        "uncleanedQty": int(row.get("uncleaned_qty") or 0),
        "inspectionPending": int(row.get("inspection_pending") or 0),
        "timeTakenMinutes": int(row["time_taken_minutes"]) if row.get("time_taken_minutes") is not None else None,
        "isAssembly": bom_id is not None,
        "isStorePart": bom_id is not None and processed and int(row.get("inspection_pending") or 0) > 0,
        "isProcessed": processed,
        "isPending": not processed,
        "isQaApproved": qa_approved,
        "processedAt": (
            row["processed_at"].isoformat()
            if row.get("processed_at") and hasattr(row["processed_at"], "isoformat")
            else (str(row["processed_at"]) if row.get("processed_at") else None)
        ),
        "lines": lines if lines is not None else [],
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
    return {
        "total_inspected": inspected,
        "total_qa": qa,
        "total_okayed": inspected - qa,
    }


def _validate_line(item: Dict[str, Any]) -> Dict[str, Any]:
    lot_no = str(item.get("sourceLotNo") or "").strip()
    if not lot_no:
        raise ValueError("Source lot number is required")
    inspected = int(item.get("inspectedQty") or 0)
    qa = int(item.get("qaQty") or 0)
    no_of_comp = int(item.get("noOfComp") or 0)
    if qa > inspected:
        raise ValueError(f"QA cannot exceed Inspected QTY for lot {lot_no}")
    if no_of_comp > 0 and inspected > no_of_comp:
        raise ValueError(f"Inspected QTY cannot exceed No of Comp for lot {lot_no}")
    prod_date = _parse_date(item.get("productionDate"))
    return {
        "sourceLotNo": lot_no,
        "productionDate": prod_date,
        "inspectedQty": inspected,
        "qaQty": qa,
    }


def get_meta(work_date: str) -> Dict[str, Any]:
    wd = _parse_date(work_date) or date.today().strftime("%Y-%m-%d")
    child_count = fetch_one(
        "SELECT COUNT(*) AS cnt FROM laser_welding_lot WHERE work_date = %s",
        (wd,),
    )
    qa_count = fetch_one(
        "SELECT COUNT(*) AS cnt FROM laser_welding_lot "
        "WHERE new_lot_no IS NOT NULL AND total_qa > 0 AND qa_approved_at IS NULL",
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
            ORDER BY c.CO_PARTNO
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
    else:
        plant_id = erp_stock.LW_ERP_PLANT_ID
        sql = """
            SELECT TRIM(im.ITEM_CODE) AS part_no, TRIM(c.CO_PARTNAME) AS part_name
            FROM ITEM_MASTER im
            INNER JOIN components c
                ON TRIM(c.CO_PARTNO) = TRIM(im.ITEM_CODE) AND c.CO_ACTIVEYN = 'Y'
            WHERE im.CATEGORY_CODE = 'SS'
              AND EXISTS (
                SELECT 1
                FROM comp_transaction ct
                WHERE ct.CT_COMPID = c.CO_ID
                  AND ct.CT_PLANTID = %s
                  AND ct.CT_NEXTSTAGE IN (6, 106, 206, 306)
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
        rows = fetch_all(sql, (plant_id,))
        parts_map: Dict[str, Dict[str, str]] = {}
        for r in rows:
            pn = r["part_no"]
            parts_map[pn] = {
                "part_no": pn,
                "part_name": r["part_name"] or "",
                "partNo": pn,
                "partName": r["part_name"] or "",
                "isStorePart": False,
            }
        store_rows = fetch_all(
            """
            SELECT DISTINCT l.part_number AS part_no,
                   COALESCE(l.product_name, l.part_number) AS part_name,
                   l.bom_id
            FROM laser_welding_lot l
            WHERE l.bom_id IS NOT NULL AND l.inspection_pending > 0
            ORDER BY l.part_number
            """
        )
        for r in store_rows:
            pn = r["part_no"]
            parts_map[pn] = {
                "part_no": pn,
                "part_name": r["part_name"] or "",
                "partNo": pn,
                "partName": r["part_name"] or "",
                "isStorePart": True,
                "bomId": str(r["bom_id"]) if r.get("bom_id") else None,
            }
        return sorted(parts_map.values(), key=lambda x: x["partNo"])


def get_source_lots(part_number: str) -> List[Dict[str, Any]]:
    part = str(part_number or "").strip()
    if not part:
        return []
    comp_id = erp_stock.resolve_comp_id(part)
    rows = erp_stock.fetch_lot_inventory(comp_id)
    return [
        {
            "lotNo": r["lotNo"],
            "availableQty": r["availableQty"],
            "noOfComp": r["availableQty"],
            "productionDate": "",
        }
        for r in rows
    ]


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
        WHERE ln.line_type = 'rework' AND ln.production_date = %s
        ORDER BY ln.source_lot_no, ln.lot_id IS NULL, ln.line_id
        """,
        (wd,),
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


def _production_row_from_lot(lot: Dict[str, Any], lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if lines is None:
        lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = 'production'
            ORDER BY line_id
            """,
            (lot["lot_id"],),
        )
    processed = _is_processed(lot)
    d = _lot_to_dict(lot, [_line_to_dict(ln) for ln in lines])
    d["rowKey"] = f"lot:{lot['lot_id']}"
    d["isDraft"] = not processed
    d["isPending"] = not processed
    d["inspectedQty"] = int(lot.get("total_inspected") or 0)
    d["qaQty"] = int(lot.get("total_qa") or 0)
    d["batchMode"] = "production"
    return d


def _store_inspection_row_from_lot(lot: Dict[str, Any]) -> Dict[str, Any]:
    d = _lot_to_dict(lot, [])
    d["rowKey"] = f"store:{lot['lot_id']}"
    d["isStorePart"] = True
    d["isDraft"] = False
    d["isPending"] = False
    d["isProcessed"] = True
    d["batchMode"] = "production"
    d["inspectedQty"] = int(lot.get("inspection_pending") or 0)
    d["qaQty"] = 0
    return d


def get_production_inspect_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")

    result: List[Dict[str, Any]] = []
    seen_lot_ids: set = set()

    child_lots = fetch_all(
        """
        SELECT l.*
        FROM laser_welding_lot l
        WHERE l.work_date = %s AND l.bom_id IS NULL
        ORDER BY l.new_lot_no IS NULL DESC, l.lot_id DESC
        """,
        (wd,),
    )
    for lot in child_lots:
        lot_id = int(lot["lot_id"])
        if lot_id in seen_lot_ids:
            continue
        seen_lot_ids.add(lot_id)
        result.append(_production_row_from_lot(lot))

    store_lots = fetch_all(
        """
        SELECT l.*
        FROM laser_welding_lot l
        WHERE l.bom_id IS NOT NULL AND l.inspection_pending > 0
        ORDER BY l.lot_id DESC
        """
    )
    for lot in store_lots:
        lot_id = int(lot["lot_id"])
        if lot_id in seen_lot_ids:
            continue
        seen_lot_ids.add(lot_id)
        result.append(_store_inspection_row_from_lot(lot))

    return result


def create_pending_lot(
    part_number: str,
    operator_id: int,
    work_date: str,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    part = str(part_number or "").strip()
    wd = _parse_date(work_date)
    if not part or not wd:
        raise ValueError("Part number and work date are required")

    op = _fetch_operator(operator_id)
    if not op:
        raise ValueError("Invalid operator — select an active laser-welding operator")

    if not get_source_lots(part):
        raise ValueError(
            f"No FG lots with available stock for part {part} — "
            "cannot add to inspection list"
        )

    lot_id = execute_insert(
        """
        INSERT INTO laser_welding_lot (
            part_number, operator_id, new_lot_no, work_date,
            total_inspected, total_qa, total_okayed,
            created_by
        ) VALUES (%s, %s, NULL, %s, 0, 0, 0, %s)
        """,
        (part, int(operator_id), wd, created_by),
    )
    if not lot_id:
        raise ValueError("Failed to create pending inspection row — please try again")
    lot = fetch_one("SELECT * FROM laser_welding_lot WHERE lot_id = %s", (lot_id,))
    if not lot:
        raise ValueError(
            f"Pending inspection row was created but could not be loaded (id {lot_id}) — "
            "refresh the page and try again"
        )
    return _production_row_from_lot(lot, [])


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

        existing = fetch_one(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'rework'
              AND source_lot_no = %s AND production_date = %s
            """,
            (part, new_lot_no, wd),
        )
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
                VALUES (%s, NULL, 'rework', %s, %s, %s, %s)
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
        execute(
            """
            DELETE FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'production'
              AND production_date = %s
            """,
            (part, wd),
        )
        return {"lotId": None, "saved": 0, "lines": []}

    erp_stock.validate_lot_lines(part, non_zero)

    kept_source = set()
    saved = 0
    for v in non_zero:
        kept_source.add(v["sourceLotNo"])
        existing = fetch_one(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'production'
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
            execute(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, line_type, source_lot_no, production_date, inspected_qty, qa_qty)
                VALUES (%s, NULL, 'production', %s, %s, %s, %s)
                """,
                (part, v["sourceLotNo"], wd, v["inspectedQty"], v["qaQty"]),
            )
        saved += 1

    if kept_source:
        placeholders = ",".join(["%s"] * len(kept_source))
        execute(
            f"""
            DELETE FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'production'
              AND production_date = %s AND source_lot_no NOT IN ({placeholders})
            """,
            (part, wd, *kept_source),
        )

    saved_lines = fetch_all(
        """
        SELECT * FROM laser_welding_line
        WHERE lot_id IS NULL AND part_number = %s AND line_type = 'production'
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
    lot_id: int,
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

    validated = [_validate_line(it) for it in (lines or []) if str(it.get("sourceLotNo") or "").strip()]
    non_zero = [v for v in validated if v["inspectedQty"] > 0]
    if not non_zero:
        raise ValueError("Enter at least one line with Inspected QTY > 0")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_lot
            WHERE lot_id = %s AND new_lot_no IS NULL
            FOR UPDATE
            """,
            (lot_id,),
        )
        lot = cursor.fetchone()
        if not lot:
            raise ValueError("Pending lot not found or already inspected")
        if lot.get("bom_id") is not None:
            raise ValueError("Use assembly weld for BOM lots — not child part inspect")

        part = str(lot.get("part_number") or "").strip()
        lot_wd_val = lot.get("work_date")
        lot_wd_str = (
            lot_wd_val.strftime("%Y-%m-%d")
            if hasattr(lot_wd_val, "strftime")
            else str(lot_wd_val or "")[:10]
        )
        if lot_wd_str != wd:
            raise ValueError("Work date does not match the pending lot")

        totals = _aggregate_lines(non_zero)
        comp_id = erp_stock.resolve_comp_id(part, cursor)
        erp_stock.validate_lot_lines(part, non_zero, cursor=cursor)

        lot_lines = [
            {"lotNo": v["sourceLotNo"], "qty": v["inspectedQty"]}
            for v in non_zero
        ]
        erp_stock.reduce_stock(
            cursor,
            comp_id,
            erp_stock.LW_ERP_PLANT_ID,
            erp_stock.LW_FG_STAGE_ID,
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
                erp_stock.LW_ERP_PLANT_ID,
                v["sourceLotNo"],
                qa_qty,
                processed_by,
            )

        work_d = datetime.strptime(wd, "%Y-%m-%d").date()
        new_lot = _generate_next_lot_no(work_d, cursor)
        auto_approve = totals["total_qa"] == 0

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                new_lot_no = %s,
                total_inspected = %s,
                total_qa = %s,
                total_okayed = %s,
                time_taken_minutes = %s,
                processed_at = NOW(),
                processed_by = %s,
                qa_approved_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                qa_approved_by = CASE WHEN %s THEN %s ELSE NULL END
            WHERE lot_id = %s
            """,
            (
                new_lot,
                totals["total_inspected"],
                totals["total_qa"],
                totals["total_okayed"],
                time_taken_minutes,
                processed_by,
                auto_approve,
                auto_approve,
                processed_by,
                lot_id,
            ),
        )

        for v in non_zero:
            prod_date = v.get("productionDate") or wd
            cursor.execute(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, line_type, source_lot_no, production_date, inspected_qty, qa_qty)
                VALUES (%s, %s, 'production', %s, %s, %s, %s)
                """,
                (
                    part,
                    lot_id,
                    v["sourceLotNo"],
                    prod_date,
                    v["inspectedQty"],
                    v["qaQty"],
                ),
            )

    result = _fetch_lot(lot_id)
    return {"newLotNo": new_lot, "lotId": lot_id, "lot": result}


def process_production(
    part_number: str,
    work_date: str,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Legacy entry point — draft-line flow; UI uses inspect_production instead."""
    part = str(part_number or "").strip()
    wd = _parse_date(work_date)
    if not part or not wd:
        raise ValueError("Part number and work date are required")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'production'
              AND production_date = %s
            FOR UPDATE
            """,
            (part, wd),
        )
        draft_lines = cursor.fetchall() or []
        if not draft_lines:
            raise ValueError("Save at least one line with Inspected QTY > 0 before processing")

        totals = _aggregate_lines(draft_lines)
        if totals["total_inspected"] <= 0:
            raise ValueError("Save at least one line with Inspected QTY > 0 before processing")

        comp_id = erp_stock.resolve_comp_id(part, cursor)
        erp_stock.validate_lot_lines(part, draft_lines, cursor=cursor)

        lot_lines = [
            {
                "lotNo": str(ln.get("source_lot_no") or "").strip(),
                "qty": int(ln.get("inspected_qty") or 0),
            }
            for ln in draft_lines
            if int(ln.get("inspected_qty") or 0) > 0
        ]
        erp_stock.reduce_stock(
            cursor,
            comp_id,
            erp_stock.LW_ERP_PLANT_ID,
            erp_stock.LW_FG_STAGE_ID,
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
                erp_stock.LW_ERP_PLANT_ID,
                str(ln.get("source_lot_no") or "").strip(),
                qa_qty,
                processed_by,
            )

        work_d = datetime.strptime(wd, "%Y-%m-%d").date()
        new_lot = _generate_next_lot_no(work_d, cursor)
        auto_approve = totals["total_qa"] == 0

        cursor.execute(
            """
            INSERT INTO laser_welding_lot (
                part_number, new_lot_no, work_date,
                total_inspected, total_qa, total_okayed,
                processed_at, processed_by,
                qa_approved_at, qa_approved_by, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s,
                CASE WHEN %s THEN NOW() ELSE NULL END,
                CASE WHEN %s THEN %s ELSE NULL END,
                %s)
            """,
            (
                part,
                new_lot,
                wd,
                totals["total_inspected"],
                totals["total_qa"],
                totals["total_okayed"],
                processed_by,
                auto_approve,
                auto_approve,
                processed_by,
                processed_by,
            ),
        )
        new_lot_id = int(cursor.lastrowid or 0)
        if not new_lot_id:
            raise ValueError("Failed to create processed lot — please try again")

        cursor.execute(
            """
            UPDATE laser_welding_line SET lot_id = %s
            WHERE lot_id IS NULL AND part_number = %s AND line_type = 'production'
              AND production_date = %s
            """,
            (new_lot_id, part, wd),
        )

    result = _fetch_lot(new_lot_id)
    return {"newLotNo": new_lot, "lotId": new_lot_id, "lot": result}


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
            WHERE line_id = %s AND lot_id IS NULL AND line_type = 'rework'
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
            WHERE lot_id = %s AND line_type = 'rework' AND production_date = %s
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
                VALUES (%s, %s, 'rework', %s, %s, %s, %s)
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
        WHERE l.new_lot_no IS NOT NULL
          AND l.total_qa > 0
          AND l.qa_approved_at IS NULL
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
    lot = fetch_one("SELECT * FROM laser_welding_lot WHERE lot_id = %s", (lot_id,))
    if not lot:
        raise ValueError("Lot not found")
    if _is_qa_approved(lot):
        raise ValueError("QA already approved for this lot")
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

    execute(
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
    return {"lot": _fetch_lot(lot_id, include_lines=False)}


def get_rework_rows() -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT l.*
        FROM laser_welding_lot l
        WHERE l.rework_pending > 0
        ORDER BY l.lot_id DESC
        """
    )
    return [_lot_to_dict(r, []) for r in rows]


def inward_rework(lot_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
    lot = fetch_one("SELECT * FROM laser_welding_lot WHERE lot_id = %s", (lot_id,))
    if not lot:
        raise ValueError("Lot not found")
    pending = int(lot.get("rework_pending") or 0)
    if pending <= 0:
        raise ValueError("No rework pending to inward")

    execute(
        """
        UPDATE laser_welding_lot SET
            rework_pending = 0,
            rework_pool = rework_pool + %s
        WHERE lot_id = %s
        """,
        (pending, lot_id),
    )
    return {"lot": _fetch_lot(lot_id, include_lines=False), "inwardedQty": pending}


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


def get_bom_children(bom_id: str) -> List[Dict[str, Any]]:
    bid = str(bom_id or "").strip()
    if not bid:
        return []
    rows = fetch_all(
        """
        SELECT PART_NO, PART_NAME, qty
        FROM bom_lin_item
        WHERE CATEGORY_CODE = 'SS' AND PARENT_ITEM_ID != 0 AND bom_id = %s
        ORDER BY PART_NO
        """,
        (bid,),
    )
    return [
        {
            "partNo": r.get("PART_NO") or "",
            "partName": r.get("PART_NAME") or "",
            "qty": int(r.get("qty") or 0),
        }
        for r in rows
    ]


def _assembly_row_from_lot(lot: Dict[str, Any], lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if lines is None:
        lines = fetch_all(
            """
            SELECT * FROM laser_welding_line
            WHERE lot_id = %s AND line_type = 'assembly_consume'
            ORDER BY line_id
            """,
            (lot["lot_id"],),
        )
    processed = _is_processed(lot)
    d = _lot_to_dict(lot, [_line_to_dict(ln) for ln in lines])
    d["rowKey"] = f"asm:{lot['lot_id']}"
    d["isDraft"] = not processed
    d["isPending"] = not processed
    d["isAssembly"] = True
    d["batchMode"] = "assembly"
    d["weldQty"] = int(lot.get("uncleaned_qty") or 0) if processed else 0
    d["customerName"] = lot.get("customer_name") or ""
    return d


def get_assembly_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    lots = fetch_all(
        """
        SELECT l.*, COALESCE(c.CU_Name, '') AS customer_name
        FROM laser_welding_lot l
        LEFT JOIN bom b ON b.bom_id = l.bom_id
        LEFT JOIN customer c ON c.CU_Id = b.cust_id
        WHERE l.work_date = %s AND l.bom_id IS NOT NULL
        ORDER BY l.new_lot_no IS NULL DESC, l.lot_id DESC
        """,
        (wd,),
    )
    result: List[Dict[str, Any]] = []
    seen: set = set()
    for lot in lots:
        lid = int(lot["lot_id"])
        if lid in seen:
            continue
        seen.add(lid)
        result.append(_assembly_row_from_lot(lot))
    return result


def create_pending_assembly(
    bom_id: str,
    operator_id: int,
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

    bom = fetch_one(
        "SELECT bom_id, bom_no, product_name FROM bom WHERE bom_id = %s AND is_latest_version = 'Y'",
        (bid,),
    )
    if not bom:
        raise ValueError("BOM not found")

    children = get_bom_children(bid)
    if not children:
        raise ValueError("BOM has no SS child parts for welding")

    lot_id = execute_insert(
        """
        INSERT INTO laser_welding_lot (
            part_number, bom_id, product_name, operator_id, new_lot_no, work_date,
            total_inspected, total_qa, total_okayed, created_by
        ) VALUES (%s, %s, %s, %s, NULL, %s, 0, 0, 0, %s)
        """,
        (
            bom["bom_no"],
            bid,
            bom.get("product_name") or "",
            int(operator_id),
            wd,
            created_by,
        ),
    )
    if not lot_id:
        raise ValueError("Failed to create pending assembly row — please try again")
    lot = fetch_one("SELECT * FROM laser_welding_lot WHERE lot_id = %s", (lot_id,))
    if not lot:
        raise ValueError("Pending assembly row could not be loaded — refresh and try again")
    return _assembly_row_from_lot(lot, [])


def get_assembly_child_lots(part_number: str) -> List[Dict[str, Any]]:
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


def weld_assembly(
    lot_id: int,
    work_date: str,
    weld_qty: int,
    time_taken_minutes: int,
    consumptions: List[Dict[str, Any]],
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
            SELECT * FROM laser_welding_lot
            WHERE lot_id = %s AND bom_id IS NOT NULL AND new_lot_no IS NULL
            FOR UPDATE
            """,
            (lot_id,),
        )
        asm_lot = cursor.fetchone()
        if not asm_lot:
            raise ValueError("Pending assembly lot not found or already welded")

        bom_id = str(asm_lot["bom_id"] or "").strip()
        cursor.execute(
            """
            SELECT PART_NO, PART_NAME, qty
            FROM bom_lin_item
            WHERE CATEGORY_CODE = 'SS' AND PARENT_ITEM_ID != 0 AND bom_id = %s
            """,
            (bom_id,),
        )
        bom_lines = cursor.fetchall() or []
        if not bom_lines:
            raise ValueError("BOM has no SS child parts")

        required: Dict[str, int] = {}
        for bl in bom_lines:
            pn = str(bl.get("PART_NO") or "").strip()
            required[pn] = int(bl.get("qty") or 0) * weld_qty

        used_by_part: Dict[str, int] = {}
        qa_by_part: Dict[str, int] = {}
        lots_by_part: Dict[str, set] = {}

        for c in consumptions or []:
            part_no = str(c.get("partNumber") or "").strip()
            child_lot_id = int(c.get("childLotId") or 0)
            used = int(c.get("usedQty") or 0)
            qa = int(c.get("qaQty") or 0)
            if not part_no or not child_lot_id:
                continue
            if used <= 0 and qa <= 0:
                continue
            if qa > used:
                raise ValueError(f"QA cannot exceed Used QTY for part {part_no}")
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
            if not child:
                raise ValueError(f"Child lot not found for part {part_no}")
            if child.get("bom_id") is not None:
                raise ValueError(f"Lot {child_lot_id} is not a child inspection lot")
            if str(child.get("part_number") or "").strip() != part_no:
                raise ValueError(f"Child lot does not match part {part_no}")

            okayed = int(child.get("total_okayed") or 0)
            deduct = used + qa
            if deduct > okayed:
                raise ValueError(
                    f"Used+QA ({deduct}) exceeds available okayed ({okayed}) "
                    f"for {part_no} lot {child.get('new_lot_no')}"
                )

            cursor.execute(
                """
                UPDATE laser_welding_lot SET
                    total_okayed = total_okayed - %s,
                    total_qa = total_qa + %s
                WHERE lot_id = %s
                """,
                (deduct, qa, child_lot_id),
            )

            used_by_part[part_no] = used_by_part.get(part_no, 0) + used
            qa_by_part[part_no] = qa_by_part.get(part_no, 0) + qa

            cursor.execute(
                """
                INSERT INTO laser_welding_line
                (part_number, lot_id, child_lot_id, line_type, source_lot_no,
                 production_date, inspected_qty, qa_qty)
                VALUES (%s, %s, %s, 'assembly_consume', %s, %s, %s, %s)
                """,
                (
                    part_no,
                    lot_id,
                    child_lot_id,
                    child.get("new_lot_no") or "",
                    wd,
                    used,
                    qa,
                ),
            )

        for pn, req in required.items():
            got = used_by_part.get(pn, 0)
            if got != req:
                raise ValueError(
                    f"Part {pn}: required used qty {req} (BOM × weld qty), got {got}"
                )

        work_d = datetime.strptime(wd, "%Y-%m-%d").date()
        new_lot = _generate_next_lot_no(work_d, cursor)

        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                new_lot_no = %s,
                uncleaned_qty = %s,
                time_taken_minutes = %s,
                processed_at = NOW(),
                processed_by = %s
            WHERE lot_id = %s
            """,
            (new_lot, weld_qty, time_taken_minutes, processed_by, lot_id),
        )

    result = _fetch_lot(lot_id)
    return {"newLotNo": new_lot, "lotId": lot_id, "lot": result}


# --- Cleaning ---


def _cleaning_row_from_lot(lot: Dict[str, Any]) -> Dict[str, Any]:
    d = _lot_to_dict(lot, [])
    d["rowKey"] = f"clean:{lot['lot_id']}"
    d["isAssembly"] = True
    d["isDraft"] = False
    d["isProcessed"] = True
    d["batchMode"] = "cleaning"
    return d


def get_cleaning_rows(work_date: str) -> List[Dict[str, Any]]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    lots = fetch_all(
        """
        SELECT l.*
        FROM laser_welding_lot l
        WHERE l.bom_id IS NOT NULL AND l.uncleaned_qty > 0
        ORDER BY l.lot_id DESC
        """,
    )
    return [_cleaning_row_from_lot(lot) for lot in lots]


def clean_assembly(
    lot_id: int,
    lot_no: str,
    qty: int,
    operator_id: int,
    work_date: str,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    wd = _parse_date(work_date)
    if not wd:
        raise ValueError("Invalid work date")
    if qty <= 0:
        raise ValueError("QTY must be greater than 0")

    op = _fetch_operator(operator_id)
    if not op:
        raise ValueError("Invalid operator")

    lot = fetch_one("SELECT * FROM laser_welding_lot WHERE lot_id = %s", (lot_id,))
    if not lot or not lot.get("bom_id"):
        raise ValueError("Assembly lot not found")
    expected = str(lot.get("new_lot_no") or "").strip()
    if str(lot_no or "").strip() != expected:
        raise ValueError(f"Lot number must be {expected}")
    uncleaned = int(lot.get("uncleaned_qty") or 0)
    if qty > uncleaned:
        raise ValueError(f"QTY cannot exceed uncleaned quantity ({uncleaned})")

    execute(
        """
        UPDATE laser_welding_lot SET
            uncleaned_qty = uncleaned_qty - %s,
            inspection_pending = inspection_pending + %s,
            operator_id = %s,
            processed_by = %s
        WHERE lot_id = %s
        """,
        (qty, qty, int(operator_id), processed_by, lot_id),
    )
    return {"lot": _fetch_lot(lot_id, include_lines=False), "cleanedQty": qty}


# --- Store Part Inspection (assembly lots, no ERP) ---


def inspect_store_assembly(
    lot_id: int,
    qty: int,
    qa_qty: int,
    time_taken_minutes: int,
    processed_by: Optional[int] = None,
) -> Dict[str, Any]:
    if qty <= 0:
        raise ValueError("QTY must be greater than 0")
    if qa_qty > qty:
        raise ValueError("QA cannot exceed QTY")
    if time_taken_minutes <= 0:
        raise ValueError("Time taken is required and must be greater than 0")

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM laser_welding_lot
            WHERE lot_id = %s AND bom_id IS NOT NULL
            FOR UPDATE
            """,
            (lot_id,),
        )
        lot = cursor.fetchone()
        if not lot:
            raise ValueError("Assembly store lot not found")
        pending = int(lot.get("inspection_pending") or 0)
        if pending <= 0:
            raise ValueError("No inspection pending on this lot")
        if qty > pending:
            raise ValueError(f"QTY cannot exceed inspection pending ({pending})")

        okayed_add = qty - qa_qty
        cursor.execute(
            """
            UPDATE laser_welding_lot SET
                inspection_pending = inspection_pending - %s,
                total_inspected = total_inspected + %s,
                total_okayed = total_okayed + %s,
                total_qa = total_qa + %s,
                time_taken_minutes = %s,
                processed_by = %s
            WHERE lot_id = %s
            """,
            (qty, qty, okayed_add, qa_qty, time_taken_minutes, processed_by, lot_id),
        )

    return {"lot": _fetch_lot(lot_id, include_lines=False)}
