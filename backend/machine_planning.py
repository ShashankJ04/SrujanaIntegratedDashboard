"""Machine Planning — business logic for monthly machine-wise production plans.

Replaces the Excel-based "MC WISE PLAN" workflow.  Users enter part number,
additional qty, priority and remarks.  Part name, RM code, SPM, production
pending, produced qty, max-parts-per-day and days-required are auto-populated
from ERP tables at query time.  SPM is resolved from the tool_life table via
the part's tool number.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .db import execute, fetch_all, fetch_one
from .models import build_enriched_inventory_rows_for_period

WORK_HOURS_PER_DAY = 7


# ── Machine helpers ──────────────────────────────────────────────────────

def get_machines() -> List[Dict[str, Any]]:
    """Active machines from machinemaster, sorted by name."""
    return fetch_all(
        "SELECT MCM_Id AS id, MCM_Name AS label, MCM_Capacity AS capacity, "
        "MCM_Make AS make FROM machinemaster "
        "WHERE MCM_ACTIVEYN = 'Y' ORDER BY MCM_Name"
    )


def get_machine_meta(machine_id: int) -> Optional[Dict[str, Any]]:
    """Single machine metadata."""
    return fetch_one(
        "SELECT MCM_Id AS id, MCM_Name AS label, MCM_Capacity AS capacity, "
        "MCM_Make AS make FROM machinemaster WHERE MCM_Id = %s",
        (machine_id,),
    )


# ── Part search ──────────────────────────────────────────────────────────

def search_parts(query: str, limit: int = 20) -> List[Dict[str, str]]:
    """Autocomplete search for part numbers from components table."""
    q = str(query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    rows = fetch_all(
        "SELECT DISTINCT TRIM(CO_PARTNO) AS part_no, TRIM(CO_PARTNAME) AS part_name "
        "FROM components WHERE CO_ACTIVEYN = 'Y' "
        "AND (CO_PARTNO LIKE %s OR CO_PARTNAME LIKE %s) "
        "ORDER BY CO_PARTNO LIMIT %s",
        (like, like, limit),
    )
    return [{"part_no": r["part_no"], "part_name": r["part_name"]} for r in rows]


# ── Auto-populated data lookup ───────────────────────────────────────────

def _lookup_part_details(part_numbers: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Batch-fetch part name, RM code, stock, production data and SPM for parts.

    SPM is resolved from tool_life via the part's first tool number
    (same logic as production_calendar._fetch_part_info).
    """
    cleaned = [str(p or "").strip() for p in part_numbers if str(p or "").strip()]
    if not cleaned:
        return {}

    placeholders = ", ".join(["%s"] * len(cleaned))

    sql = f"""
        SELECT
            TRIM(c.CO_PARTNO) AS part_no,
            MAX(TRIM(c.CO_PARTNAME)) AS part_name,
            MAX(mm.MM_RAWMTPARTNO) AS rm_code,
            MAX(ct.CT_TOOLNO) AS tool_no,
            MAX(COALESCE(stk_wip.csQty, 0)) AS wip,
            MAX(COALESCE(stk_fg.csQty, 0)) AS fg,
            MAX(COALESCE(stk_wip.csQty, 0) + COALESCE(stk_fg.csQty, 0)) AS total_stock,
            MAX(COALESCE(prod.produced_qty, 0)) AS produced_qty
        FROM components c
        LEFT JOIN (
            SELECT CT_COMPID, CT_RMID, CT_TOOLNO
            FROM components_tool
            WHERE CT_ACTIVEYN = 'Y'
              AND ct_id IN (
                  SELECT MAX(ct_id) FROM components_tool
                  WHERE CT_ACTIVEYN = 'Y' GROUP BY CT_COMPID
              )
        ) ct ON ct.CT_COMPID = c.CO_ID
        LEFT JOIN materialmaster mm ON mm.MM_ID = ct.CT_RMID
        LEFT JOIN (
            SELECT CS_COMPID, SUM(CS_QTY) AS csQty
            FROM comp_stock WHERE CS_STAGEID != 6
            GROUP BY CS_COMPID
        ) stk_wip ON stk_wip.CS_COMPID = c.CO_ID
        LEFT JOIN (
            SELECT CS_COMPID, SUM(CS_QTY) AS csQty
            FROM comp_stock WHERE CS_STAGEID = 6
            GROUP BY CS_COMPID
        ) stk_fg ON stk_fg.CS_COMPID = c.CO_ID
        LEFT JOIN (
            SELECT
                ct2.CT_COMPID,
                SUM(pd.PD_PRODQTY) AS produced_qty
            FROM production_details pd
            INNER JOIN scheduled_production ps ON pd.PD_PSID = ps.PS_ID
            INNER JOIN components_tool ct2 ON pd.PD_TOOLID = ct2.CT_ID
            WHERE ps.PS_DATE BETWEEN
                  DATE_SUB(CURRENT_DATE, INTERVAL DAYOFMONTH(CURRENT_DATE)-1 DAY)
                  AND LAST_DAY(CURRENT_DATE)
            GROUP BY ct2.CT_COMPID
        ) prod ON prod.CT_COMPID = c.CO_ID
        WHERE c.CO_ACTIVEYN = 'Y'
          AND c.CO_ID = c.CO_PARENTID
          AND TRIM(c.CO_PARTNO) IN ({placeholders})
        GROUP BY TRIM(c.CO_PARTNO)
    """
    rows = fetch_all(sql, tuple(cleaned))

    tool_numbers = set()
    for r in rows:
        tn = str(r.get("tool_no") or "").strip()
        if tn:
            tool_numbers.add(tn)

    spm_by_tool = _fetch_spm_by_tool(tool_numbers)

    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = str(r["part_no"] or "").strip()
        tn = str(r.get("tool_no") or "").strip().lower()
        r["spm"] = int(spm_by_tool.get(tn, 0))
        out[key] = r
    return out


def _fetch_spm_by_tool(tool_numbers: set) -> Dict[str, float]:
    """SPM (strokes per minute) from tool_life, keyed by lowercase tool number."""
    if not tool_numbers:
        return {}
    spm_rows = fetch_all(
        "SELECT TL_tool_number AS toolNo, MAX(TL_spm) AS spm "
        "FROM tool_life GROUP BY TL_tool_number"
    )
    return {
        str(r.get("toolNo") or "").strip().lower(): float(r.get("spm") or 0)
        for r in spm_rows
        if str(r.get("toolNo") or "").strip()
    }



# ── Plan CRUD ────────────────────────────────────────────────────────────

def get_plan(machine_id: int, month_year: str) -> Dict[str, Any]:
    """Full plan for a machine + month, with auto-populated fields.

    `month_year` is ISO format 'YYYY-MM' (day is ignored, stored as first-of-month).
    """
    first_of_month = f"{month_year}-01"

    rows = fetch_all(
        "SELECT mp_id, machine_id, month_year, part_number, "
        "additional_qty, priority, remarks, created_by, created_at, updated_at "
        "FROM machine_planning "
        "WHERE machine_id = %s AND month_year = %s "
        "ORDER BY mp_id",
        (machine_id, first_of_month),
    )

    part_numbers = [r["part_number"] for r in rows]
    details = _lookup_part_details(part_numbers) if part_numbers else {}

    # Pull production_pending & produced_qty from the same source as Inventory Report
    ym_parts = month_year.split("-")
    inv_month, inv_year = int(ym_parts[1]), int(ym_parts[0])
    inv_rows = build_enriched_inventory_rows_for_period(inv_month, inv_year)
    inv_by_part: Dict[str, Dict[str, Any]] = {}
    for ir in inv_rows:
        pk = str(ir.get("part_no") or "").strip()
        if pk:
            inv_by_part[pk] = ir

    enriched = []
    total_days = 0.0
    for idx, r in enumerate(rows, start=1):
        pn = str(r["part_number"]).strip()
        info = details.get(pn, {})
        inv = inv_by_part.get(pn, {})

        spm = int(info.get("spm") or 0)
        max_parts_per_day = spm * 60 * WORK_HOURS_PER_DAY if spm > 0 else 0

        production_pending = max(0, float(inv.get("production_pending") or 0))
        produced_qty = int(inv.get("produced_qty") or info.get("produced_qty") or 0)

        days_required = round(production_pending / max_parts_per_day, 1) if max_parts_per_day > 0 and production_pending > 0 else 0
        total_days += days_required

        enriched.append({
            "mp_id": r["mp_id"],
            "sl_no": idx,
            "part_number": pn,
            "part_name": inv.get("part_name") or info.get("part_name", ""),
            "production_pending": production_pending,
            "produced_qty": produced_qty,
            "additional_qty": int(r.get("additional_qty") or 0),
            "priority": int(r.get("priority") or 0),
            "spm": spm,
            "max_parts_per_day": max_parts_per_day,
            "days_required": days_required,
            "rm_code": info.get("rm_code", ""),
            "remarks": r.get("remarks") or "",
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
        })

    machine = get_machine_meta(machine_id) or {}
    return {
        "machine": machine,
        "month_year": month_year,
        "total_days_required": round(total_days, 1),
        "rows": enriched,
    }


def add_plan_row(
    machine_id: int,
    month_year: str,
    part_number: str,
    additional_qty: int = 0,
    priority: int = 0,
    remarks: str = "",
    created_by: Optional[int] = None,
) -> int:
    """Insert a new part row.  Returns the new mp_id."""
    first_of_month = f"{month_year}-01"
    execute(
        "INSERT INTO machine_planning "
        "(machine_id, month_year, part_number, additional_qty, priority, remarks, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (machine_id, first_of_month, part_number.strip(), additional_qty, priority, remarks, created_by),
    )
    row = fetch_one("SELECT LAST_INSERT_ID() AS id")
    return int(row["id"]) if row else 0


def update_plan_row(mp_id: int, **fields: Any) -> int:
    """Partial update of a plan row.  Only allowed fields are patched."""
    allowed = {"additional_qty", "priority", "remarks"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return 0
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    params = list(updates.values()) + [mp_id]
    return execute(f"UPDATE machine_planning SET {set_clause} WHERE mp_id = %s", params)


def delete_plan_row(mp_id: int) -> int:
    """Delete a single plan row."""
    return execute("DELETE FROM machine_planning WHERE mp_id = %s", (mp_id,))


def get_machines_with_plans(month_year: str) -> List[int]:
    """Return machine IDs that have at least one plan row for the given month."""
    first_of_month = f"{month_year}-01"
    rows = fetch_all(
        "SELECT DISTINCT machine_id FROM machine_planning "
        "WHERE month_year = %s ORDER BY machine_id",
        (first_of_month,),
    )
    return [int(r["machine_id"]) for r in rows]
