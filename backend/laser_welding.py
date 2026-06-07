"""Laser Welding — business logic for child-parts processing workflow."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .db import execute, fetch_all, fetch_one, get_cursor

VALID_TABS = frozenset({"child_parts", "sub_assembly", "final_assembly"})


def get_stages() -> List[Dict[str, Any]]:
    """All operation stages from comp_opstages."""
    rows = fetch_all(
        "SELECT OS_ID AS id, OS_NAME AS name FROM comp_opstages ORDER BY OS_ID"
    )
    return [{"id": int(r["id"]), "name": r["name"] or ""} for r in rows]


def _parse_production_date(value: Any) -> Optional[str]:
    """Parse dd-mm-yyyy or yyyy-mm-dd to yyyy-mm-dd for MySQL DATE."""
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _lot_prefix(for_date: Optional[date] = None) -> str:
    d = for_date or date.today()
    yy = d.year % 100
    yy1 = (d.year + 1) % 100
    return f"LN/LW/{yy:02d}-{yy1:02d}/"


def _generate_next_lot_no(cursor: Any) -> str:
    prefix = _lot_prefix()
    cursor.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(new_lot_no, '/', -1) AS UNSIGNED)), 0) AS mx "
        "FROM laser_welding_processing WHERE new_lot_no LIKE %s",
        (prefix + "%",),
    )
    row = cursor.fetchone()
    mx = int((row or {}).get("mx") or 0)
    return f"{prefix}{mx + 1}"


def get_production_details(part_number: str) -> List[Dict[str, Any]]:
    """All production_details lots for a part (no date filter)."""
    part = str(part_number or "").strip()
    if not part:
        return []

    sql = """
        SELECT
            DATE_FORMAT(pd_date, '%%d-%%m-%%Y') AS productionDate,
            PD_LotNo AS lotNo,
            pd_prodqty AS noOfComp
        FROM production_details
        LEFT JOIN scheduled_production ON pd_psid = ps_id
        LEFT JOIN components ON PS_PARENTCOMPID = CO_ID
        WHERE TRIM(CO_PARTNO) = %s
          AND PD_LotNo IS NOT NULL
          AND TRIM(PD_LotNo) != ''
        ORDER BY pd_date DESC
    """
    rows = fetch_all(sql, (part,))
    entries: List[Dict[str, Any]] = []
    for r in rows:
        entries.append(
            {
                "productionDate": r["productionDate"] or "",
                "lotNo": r["lotNo"] or "",
                "noOfComp": int(r["noOfComp"] or 0),
            }
        )
    return entries


def _part_name(part_number: str) -> str:
    row = fetch_one(
        "SELECT TRIM(CO_PARTNAME) AS part_name FROM components "
        "WHERE TRIM(CO_PARTNO) = %s AND CO_ACTIVEYN = 'Y' LIMIT 1",
        (part_number.strip(),),
    )
    return (row or {}).get("part_name") or ""


def get_rows(tab_type: str) -> List[Dict[str, Any]]:
    """Grouped part rows for a tab (unprocessed + processed batches)."""
    tab = str(tab_type or "child_parts").strip()
    if tab not in VALID_TABS:
        tab = "child_parts"

    sql = """
        SELECT
            lwp.lwp_id,
            lwp.tab_type,
            lwp.part_number,
            lwp.stage_id,
            lwp.source_lot_no,
            lwp.production_date,
            lwp.no_of_comp,
            lwp.qty_processed,
            lwp.new_lot_no,
            lwp.processed_at,
            os.OS_NAME AS stage_name,
            c.CO_PARTNAME AS part_name
        FROM laser_welding_processing lwp
        LEFT JOIN comp_opstages os ON os.OS_ID = lwp.stage_id
        LEFT JOIN components c ON TRIM(c.CO_PARTNO) = TRIM(lwp.part_number) AND c.CO_ACTIVEYN = 'Y'
        WHERE lwp.tab_type = %s
        ORDER BY
            CASE WHEN lwp.new_lot_no IS NULL THEN 0 ELSE 1 END,
            lwp.processed_at DESC,
            lwp.updated_at DESC
    """
    raw = fetch_all(sql, (tab,))

    groups: Dict[str, Dict[str, Any]] = {}
    for r in raw:
        if r.get("new_lot_no"):
            key = f"processed:{r['new_lot_no']}"
        else:
            key = f"unprocessed:{r['part_number']}:{r['stage_id']}"

        if key not in groups:
            groups[key] = {
                "rowKey": key,
                "tabType": tab,
                "partNumber": r["part_number"] or "",
                "partName": r["part_name"] or _part_name(r["part_number"] or ""),
                "stageId": int(r["stage_id"]),
                "stageName": r["stage_name"] or "",
                "newLotNo": r["new_lot_no"],
                "isProcessed": bool(r["new_lot_no"]),
                "processedAt": (
                    r["processed_at"].isoformat()
                    if r.get("processed_at") and hasattr(r["processed_at"], "isoformat")
                    else (str(r["processed_at"]) if r.get("processed_at") else None)
                ),
                "items": [],
            }

        if int(r.get("qty_processed") or 0) > 0 or r.get("new_lot_no"):
            prod_date = r.get("production_date")
            if prod_date and hasattr(prod_date, "strftime"):
                prod_date_str = prod_date.strftime("%d-%m-%Y")
            else:
                prod_date_str = str(prod_date) if prod_date else ""

            groups[key]["items"].append(
                {
                    "sourceLotNo": r["source_lot_no"] or "",
                    "productionDate": prod_date_str,
                    "noOfComp": int(r["no_of_comp"] or 0),
                    "qtyProcessed": int(r["qty_processed"] or 0),
                }
            )

        if not groups[key]["partName"] and r.get("part_name"):
            groups[key]["partName"] = r["part_name"]

    result = list(groups.values())
    result = [g for g in result if g["isProcessed"] or g["items"]]
    result.sort(
        key=lambda x: (
            0 if not x["isProcessed"] else 1,
            x.get("processedAt") or "",
            x["partNumber"],
        )
    )
    return result


def has_open_row(tab_type: str, part_number: str, stage_id: int) -> bool:
    """True if an unprocessed batch already exists for part+stage."""
    row = fetch_one(
        "SELECT lwp_id FROM laser_welding_processing "
        "WHERE tab_type = %s AND part_number = %s AND stage_id = %s AND new_lot_no IS NULL "
        "LIMIT 1",
        (tab_type, part_number.strip(), stage_id),
    )
    return row is not None


def save_rows(
    tab_type: str,
    part_number: str,
    stage_id: int,
    items: List[Dict[str, Any]],
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Upsert qty rows; delete entries where qty is 0."""
    tab = str(tab_type or "child_parts").strip()
    if tab not in VALID_TABS:
        raise ValueError("Invalid tab type")

    part = str(part_number or "").strip()
    if not part:
        raise ValueError("Part number is required")
    if not stage_id:
        raise ValueError("Stage is required")

    saved = 0
    deleted = 0

    for item in items or []:
        lot = str(item.get("sourceLotNo") or "").strip()
        if not lot:
            continue

        qty = int(item.get("qtyProcessed") or 0)
        no_of_comp = int(item.get("noOfComp") or 0)
        prod_date = _parse_production_date(item.get("productionDate"))

        if qty <= 0:
            deleted += execute(
                "DELETE FROM laser_welding_processing "
                "WHERE tab_type = %s AND part_number = %s AND stage_id = %s "
                "AND source_lot_no = %s AND new_lot_no IS NULL",
                (tab, part, stage_id, lot),
            )
            continue

        if qty > no_of_comp:
            raise ValueError(
                f"Qty processed ({qty}) cannot exceed No of Comp ({no_of_comp}) for lot {lot}"
            )

        existing = fetch_one(
            "SELECT lwp_id FROM laser_welding_processing "
            "WHERE tab_type = %s AND part_number = %s AND stage_id = %s "
            "AND source_lot_no = %s AND new_lot_no IS NULL",
            (tab, part, stage_id, lot),
        )
        if existing:
            execute(
                "UPDATE laser_welding_processing "
                "SET qty_processed = %s, no_of_comp = %s, production_date = %s, updated_at = NOW() "
                "WHERE lwp_id = %s",
                (qty, no_of_comp, prod_date, existing["lwp_id"]),
            )
        else:
            execute(
                "INSERT INTO laser_welding_processing "
                "(tab_type, part_number, stage_id, source_lot_no, production_date, "
                "no_of_comp, qty_processed, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (tab, part, stage_id, lot, prod_date, no_of_comp, qty, created_by),
            )
        saved += 1

    return {"saved": saved, "deleted": deleted}


def process_batch(
    tab_type: str,
    part_number: str,
    stage_id: int,
    processed_by: Optional[int] = None,
) -> str:
    """Generate new lot number and mark unprocessed rows as processed."""
    tab = str(tab_type or "child_parts").strip()
    if tab not in VALID_TABS:
        raise ValueError("Invalid tab type")

    part = str(part_number or "").strip()
    if not part:
        raise ValueError("Part number is required")
    if not stage_id:
        raise ValueError("Stage is required")

    rows = fetch_all(
        "SELECT lwp_id, qty_processed, no_of_comp, source_lot_no "
        "FROM laser_welding_processing "
        "WHERE tab_type = %s AND part_number = %s AND stage_id = %s AND new_lot_no IS NULL",
        (tab, part, stage_id),
    )
    if not rows:
        raise ValueError("No saved data found for this part and stage")

    positive = [r for r in rows if int(r.get("qty_processed") or 0) > 0]
    if not positive:
        raise ValueError("Save at least one lot with Qty Processed > 0 before processing")

    for r in positive:
        qty = int(r["qty_processed"])
        cap = int(r["no_of_comp"] or 0)
        if qty > cap:
            raise ValueError(
                f"Qty processed ({qty}) exceeds No of Comp ({cap}) for lot {r['source_lot_no']}"
            )

    with get_cursor() as cursor:
        new_lot = _generate_next_lot_no(cursor)
        cursor.execute(
            "UPDATE laser_welding_processing "
            "SET new_lot_no = %s, processed_at = NOW(), processed_by = %s "
            "WHERE tab_type = %s AND part_number = %s AND stage_id = %s AND new_lot_no IS NULL",
            (new_lot, processed_by, tab, part, stage_id),
        )

    return new_lot
