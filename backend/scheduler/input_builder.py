"""Aggregate all data sources into a SchedulerInput bundle."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from ..db import fetch_all
from ..models import build_enriched_inventory_rows_for_period
from ..production_calendar import (
    PART_NO_COL,
    build_production_calendar_payload,
)

from .capacity import build_machine_day_grid, compute_run_minutes, get_working_days
from .models import (
    DEFAULT_WEIGHTS,
    Job,
    Scenario,
    SchedulerInput,
    ToolState,
)


_DAY_RE = re.compile(r"^\s*day\s+(\d+)\s*$", re.IGNORECASE)


def _normalize(v: Any) -> str:
    return str(v or "").strip().lower()


def _to_float(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ── Sub-queries ──────────────────────────────────────────────────────────

def _fetch_machines() -> List[Dict[str, Any]]:
    return fetch_all(
        "SELECT MCM_Id AS id, MCM_Name AS label, MCM_Capacity AS capacity, "
        "MCM_Make AS make FROM machinemaster WHERE MCM_ACTIVEYN = 'Y' ORDER BY MCM_Name"
    )


def _fetch_part_machine_mapping() -> Dict[str, Dict[str, Any]]:
    """Primary machine, SPM, cavity, is_supplier per component (one row per part)."""
    rows = fetch_all("""
        SELECT
            TRIM(c.CO_PARTNO)     AS part_no,
            m.machine_id,
            m.spm,
            m.cavity,
            m.is_supplier,
            m.mapping_id,
            m.component_id,
            (SELECT COUNT(*) FROM part_machine_alternate a WHERE a.mapping_id = m.mapping_id) AS alt_count
        FROM part_machine_mapping m
        INNER JOIN components c ON c.CO_Id = m.component_id
        WHERE c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_PARTNO
    """)
    by_part: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        pk = _normalize(r.get("part_no"))
        if pk:
            by_part.setdefault(pk, []).append(r)

    out: Dict[str, Dict[str, Any]] = {}
    for pk, group in by_part.items():
        # Prefer a real machine mapping with alternates; fall back to any non-supplier row.
        def row_rank(r: Dict[str, Any]) -> tuple:
            has_machine = 0 if r.get("machine_id") else 1
            is_supplier = 1 if r.get("is_supplier") else 0
            alt_count = -int(r.get("alt_count") or 0)
            mapping_id = int(r.get("mapping_id") or 0)
            return (has_machine, is_supplier, alt_count, mapping_id)

        out[pk] = sorted(group, key=row_rank)[0]
    return out


def _fetch_alternate_machines_by_part() -> Dict[str, List[Tuple[int, int]]]:
    """part_no (normalized) -> [(machine_id, alt_rank)] via mapping_id join."""
    rows = fetch_all("""
        SELECT
            TRIM(c.CO_PARTNO) AS part_no,
            a.machine_id,
            a.alt_rank
        FROM part_machine_alternate a
        INNER JOIN part_machine_mapping m ON m.mapping_id = a.mapping_id
        INNER JOIN components c ON c.CO_Id = m.component_id
        WHERE c.CO_ACTIVEYN = 'Y'
        ORDER BY a.alt_rank
    """)
    out: Dict[str, List[Tuple[int, int]]] = {}
    seen: Dict[str, set] = {}
    for r in rows:
        pk = _normalize(r.get("part_no"))
        if not pk:
            continue
        machine_id = int(r["machine_id"])
        alt_rank = int(r["alt_rank"])
        out.setdefault(pk, [])
        seen.setdefault(pk, set())
        if machine_id in seen[pk]:
            continue
        seen[pk].add(machine_id)
        out[pk].append((machine_id, alt_rank))
    return out


def _fetch_tool_states() -> Dict[str, ToolState]:
    """Tool life, PM state, and breakdown status keyed by normalized tool_no."""
    tools = fetch_all("SELECT * FROM tool_life")
    pm_rows = fetch_all("""
        SELECT pm1.*
        FROM preventive_maintenance pm1
        INNER JOIN (
            SELECT PM_tool_number, MAX(PM_id) AS maxId
            FROM preventive_maintenance
            GROUP BY PM_tool_number
        ) latest ON latest.PM_tool_number = pm1.PM_tool_number AND latest.maxId = pm1.PM_id
    """)
    pm_by_tool: Dict[str, Dict[str, Any]] = {}
    for pm in pm_rows:
        tn = _normalize(pm.get("PM_tool_number"))
        if tn:
            pm_by_tool[tn] = pm

    breakdown_tools: set = set()
    try:
        bd_rows = fetch_all(
            "SELECT DISTINCT tool_no FROM tool_breakdowns WHERE status = 'open'"
        )
        for r in bd_rows:
            tn = _normalize(r.get("tool_no"))
            if tn:
                breakdown_tools.add(tn)
    except Exception:
        pass

    stroke_rows = fetch_all("""
        SELECT
            ct.CT_TOOLNO AS toolNo,
            ct.CT_COMPID,
            SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
        FROM production_details pd
        INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
        GROUP BY ct.CT_TOOLNO, ct.CT_COMPID
    """)
    max_strokes_by_tool: Dict[str, int] = {}
    for sr in stroke_rows:
        tn = _normalize(sr.get("toolNo"))
        if tn:
            s = int(_to_float(sr.get("componentStrokes")))
            max_strokes_by_tool[tn] = max(max_strokes_by_tool.get(tn, 0), s)

    out: Dict[str, ToolState] = {}
    for t in tools:
        tn = _normalize(t.get("TL_tool_number"))
        if not tn:
            continue
        pm = pm_by_tool.get(tn, {})
        life_span = int(t.get("TL_life_span") or 0)
        spm = int(t.get("TL_spm") or 0)
        pm_interval = int(t.get("TL_preventive_maintenance_strokes") or 0)
        current_strokes = max_strokes_by_tool.get(tn, 0)
        next_pm = int(pm.get("PM_next_stroke") or (current_strokes + pm_interval))

        out[tn] = ToolState(
            tool_no=tn,
            current_strokes=current_strokes,
            next_pm_stroke=next_pm,
            total_life=life_span,
            pm_interval=pm_interval,
            is_in_breakdown=tn in breakdown_tools,
        )
    return out


def _fetch_spm_by_tool() -> Dict[str, float]:
    rows = fetch_all(
        "SELECT TL_tool_number AS toolNo, MAX(TL_spm) AS spm FROM tool_life GROUP BY TL_tool_number"
    )
    return {
        _normalize(r.get("toolNo")): _to_float(r.get("spm"))
        for r in rows
        if _normalize(r.get("toolNo"))
    }


def _fetch_cavity_by_part() -> Dict[str, int]:
    rows = fetch_all("""
        SELECT TRIM(c.CO_PARTNO) AS part_no,
               MAX(GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS cavity
        FROM components c
        INNER JOIN components_tool ct ON ct.CT_COMPID = c.CO_ID
        WHERE ct.CT_ACTIVEYN = 'Y'
        GROUP BY TRIM(c.CO_PARTNO)
    """)
    return {_normalize(r["part_no"]): int(_to_float(r["cavity"])) for r in rows}


def _fetch_parts_by_tool() -> Dict[str, List[str]]:
    """tool_no (normalized) -> display part numbers that share this physical tool."""
    rows = fetch_all("""
        SELECT TRIM(c.CO_PARTNO) AS part_no, ct.CT_TOOLNO AS tool_no
        FROM components c
        INNER JOIN components_tool ct ON ct.CT_COMPID = c.CO_ID
        WHERE ct.CT_ACTIVEYN = 'Y' AND c.CO_ACTIVEYN = 'Y'
        ORDER BY TRIM(c.CO_PARTNO)
    """)
    out: Dict[str, List[str]] = {}
    seen: Dict[str, set] = {}
    for r in rows:
        tn = _normalize(r.get("tool_no"))
        part_no = str(r.get("part_no") or "").strip()
        if not tn or not part_no:
            continue
        out.setdefault(tn, [])
        seen.setdefault(tn, set())
        key = part_no.lower()
        if key not in seen[tn]:
            seen[tn].add(key)
            out[tn].append(part_no)
    return out


def _fetch_tools_by_part() -> Dict[str, List[str]]:
    """All active tools per part (a part may have multiple tools for different machines)."""
    rows = fetch_all("""
        SELECT TRIM(c.CO_PARTNO) AS part_no, ct.CT_TOOLNO AS tool_no
        FROM components c
        INNER JOIN components_tool ct ON ct.CT_COMPID = c.CO_ID
        WHERE ct.CT_ACTIVEYN = 'Y'
        ORDER BY ct.CT_ID
    """)
    out: Dict[str, List[str]] = {}
    seen: Dict[str, set] = {}
    for r in rows:
        pk = _normalize(r.get("part_no"))
        tn = _normalize(r.get("tool_no"))
        if not pk or not tn:
            continue
        out.setdefault(pk, [])
        seen.setdefault(pk, set())
        if tn not in seen[pk]:
            seen[pk].add(tn)
            out[pk].append(tn)
    return out


def _fetch_tool_no_by_part() -> Dict[str, str]:
    """Primary/default tool per part (latest active components_tool row)."""
    by_part = _fetch_tools_by_part()
    return {pk: tools[-1] for pk, tools in by_part.items() if tools}


def _build_machine_tool_map(
    part_pk: str,
    primary_mid: Optional[int],
    alt_machines: List[Tuple[int, int]],
    tools_by_part: Dict[str, List[str]],
) -> Dict[int, str]:
    """Mark capable machines eligible — any part tool can run on any machine that can make the part."""
    tools = tools_by_part.get(part_pk, [])
    if not tools:
        return {}

    machines: List[int] = []
    if primary_mid is not None:
        machines.append(int(primary_mid))
    for mid, _rank in alt_machines:
        m = int(mid)
        if m not in machines:
            machines.append(m)

    default_tool = tools[0]
    return {m: default_tool for m in machines}


def _fetch_tool_day_usage_from_actuals(
    month: int, year: int,
) -> Tuple[Dict[Tuple[str, int], int], Dict[Tuple[str, int], str]]:
    """(tool_no, day) -> machine_id and part_no from recorded production this month."""
    rows = fetch_all("""
        SELECT
            LOWER(TRIM(ct.CT_TOOLNO)) AS tool_no,
            TRIM(c.CO_PARTNO) AS part_no,
            DAY(pd.PD_DATE) AS prod_day,
            pd.PD_MCID AS machine_id
        FROM production_details pd
        INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
        INNER JOIN components c ON ct.CT_COMPID = c.CO_ID
        WHERE MONTH(pd.PD_DATE) = %s AND YEAR(pd.PD_DATE) = %s
          AND pd.PD_MCID IS NOT NULL
        GROUP BY LOWER(TRIM(ct.CT_TOOLNO)), TRIM(c.CO_PARTNO), DAY(pd.PD_DATE), pd.PD_MCID
    """, (month, year))
    machine_out: Dict[Tuple[str, int], int] = {}
    part_out: Dict[Tuple[str, int], str] = {}
    for r in rows:
        tn = _normalize(r.get("tool_no"))
        day = int(r.get("prod_day") or 0)
        mid = int(r.get("machine_id") or 0)
        part_no = str(r.get("part_no") or "").strip()
        if tn and day and mid:
            key = (tn, day)
            machine_out[key] = mid
            if part_no:
                part_out[key] = part_no
    return machine_out, part_out


def _fetch_working_calendar_rows(month: int, year: int) -> List[Dict[str, Any]]:
    try:
        return fetch_all(
            "SELECT cal_date, is_working, shift_hours FROM scheduler_working_calendar "
            "WHERE cal_date BETWEEN %s AND %s",
            (f"{year}-{month:02d}-01", f"{year}-{month:02d}-31"),
        )
    except Exception:
        return []


# ── Actual production (machine-level) for past-day overlay ───────────────

def _fetch_machine_level_actuals(month: int, year: int) -> List[Dict[str, Any]]:
    """Part + day + machine + qty from production_details for display and capacity pre-fill."""
    try:
        rows = fetch_all("""
            SELECT
                TRIM(c.CO_PARTNO) AS part_no,
                c.CO_PARTNAME AS part_name,
                DAY(pd.PD_DATE) AS prod_day,
                pd.PD_MCID AS machine_id,
                mm.MCM_Name AS machine_name,
                SUM(pd.PD_PRODQTY) AS produced_qty
            FROM production_details pd
            INNER JOIN scheduled_production sp ON pd.PD_PSID = sp.PS_ID
            INNER JOIN components c ON sp.PS_PARENTCOMPID = c.CO_ID
            LEFT JOIN machinemaster mm ON mm.MCM_Id = pd.PD_MCID
            WHERE MONTH(pd.PD_DATE) = %s AND YEAR(pd.PD_DATE) = %s
            GROUP BY TRIM(c.CO_PARTNO), c.CO_PARTNAME, DAY(pd.PD_DATE), pd.PD_MCID, mm.MCM_Name
        """, (month, year))
        return rows or []
    except Exception:
        return []


# ── Production calendar day extraction ───────────────────────────────────

def _extract_dispatch_days(payload: Dict[str, Any]) -> Dict[str, Dict[int, float]]:
    """part_no -> {day: qty} from production calendar pending columns."""
    columns = payload.get("columns") or []
    day_cols = []
    for col in columns:
        m = _DAY_RE.match(str(col or ""))
        if m:
            day_cols.append((col, int(m.group(1))))

    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []
    out: Dict[str, Dict[int, float]] = {}

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if meta.get("isGrandTotal"):
            continue
        pk = _normalize(row.get(PART_NO_COL))
        if not pk:
            continue
        days: Dict[int, float] = {}
        for col_name, day_num in day_cols:
            qty = _to_float(row.get(col_name))
            if qty > 0:
                days[day_num] = qty
        if days:
            out[pk] = days
    return out


# ── Main builder ─────────────────────────────────────────────────────────

def build_scheduler_input(
    month: int,
    year: int,
    scenario: Optional[Scenario] = None,
) -> SchedulerInput:
    """Assemble all data into a SchedulerInput ready for the engine."""
    if scenario is None:
        scenario = Scenario()

    work_hours = int(current_app.config.get("WORK_HOURS_PER_DAY", 6))
    overflow_minutes = int(current_app.config.get("CAPACITY_OVERFLOW_MINUTES", 30))

    # Compute schedule_from_day: today for current month, else 1
    today = date.today()
    if month == today.month and year == today.year:
        schedule_from_day = today.day
    else:
        schedule_from_day = 1

    prod_payload = build_production_calendar_payload(month, year)
    dispatch_days_by_part = _extract_dispatch_days(prod_payload)

    inv_rows = build_enriched_inventory_rows_for_period(month, year)
    inv_by_part: Dict[str, Dict[str, Any]] = {}
    for r in inv_rows:
        pk = _normalize(r.get("part_no"))
        if pk:
            inv_by_part[pk] = r

    machines = _fetch_machines()
    pmm = _fetch_part_machine_mapping()
    alt_machines_by_part = _fetch_alternate_machines_by_part()
    tool_states = _fetch_tool_states()
    spm_by_tool = _fetch_spm_by_tool()
    cavity_by_part = _fetch_cavity_by_part()
    tools_by_part = _fetch_tools_by_part()
    tool_by_part = {pk: tools[-1] for pk, tools in tools_by_part.items() if tools}
    parts_by_tool = _fetch_parts_by_tool()
    tool_day_machine, tool_day_part = _fetch_tool_day_usage_from_actuals(month, year)

    cal_rows = _fetch_working_calendar_rows(month, year)
    working_days = get_working_days(month, year, cal_rows)
    grid = build_machine_day_grid(machines, working_days, work_hours)

    # Set overflow limit on all machine-days
    for md in grid.values():
        md.overflow_limit = float(overflow_minutes)

    # Fetch actuals and pre-consume past-day capacity
    raw_actuals = _fetch_machine_level_actuals(month, year)
    actuals_payload: List[Dict[str, Any]] = []
    for row in raw_actuals:
        prod_day = int(row.get("prod_day") or 0)
        mid = int(row.get("machine_id") or 0)
        qty = _to_float(row.get("produced_qty"))
        part_no = str(row.get("part_no") or "").strip()
        part_name = str(row.get("part_name") or "")
        machine_name = str(row.get("machine_name") or "")

        # Derive run minutes from qty using spm/cavity for that part
        pk = _normalize(part_no)
        tool_no = tool_by_part.get(pk, "")
        spm = spm_by_tool.get(tool_no, 0.0)
        cavity = cavity_by_part.get(pk, 1)
        run_min = compute_run_minutes(qty, spm, cavity) if spm > 0 else 0.0

        actuals_payload.append({
            "part_no": part_no,
            "part_name": part_name,
            "machine_id": mid,
            "machine_name": machine_name,
            "day": prod_day,
            "qty": round(qty, 2),
            "run_minutes": round(run_min, 2),
            "tool_no": tool_no,
        })

        # Pre-consume capacity on past days so forward scheduling doesn't overbook
        if prod_day < schedule_from_day:
            md_key = (mid, prod_day)
            if md_key in grid:
                grid[md_key].used_minutes += run_min
                grid[md_key].parts_scheduled.append(part_no)

    overrides = scenario.overrides or {}
    pins = overrides.get("pins", {})
    boosts = overrides.get("boosts", {})
    blocked_machines = set(overrides.get("blocked_machines", []))

    jobs: List[Job] = []
    seen: set = set()

    all_part_keys = set(inv_by_part.keys()) | set(dispatch_days_by_part.keys())
    for pk in all_part_keys:
        if pk in seen:
            continue
        seen.add(pk)

        inv = inv_by_part.get(pk, {})
        balance_prod = max(0.0, _to_float(inv.get("balance_production_qty")))
        if balance_prod <= 0:
            continue

        rm_alloc_kgs = _to_float(inv.get("balance_allocated_rm_qty"))
        rm_conval = _to_float(inv.get("rm_conval"))
        rm_cap_qty = ((rm_alloc_kgs * 1000) / rm_conval) if rm_conval > 0 else balance_prod

        mapping = pmm.get(pk, {})
        primary_mid = mapping.get("machine_id")
        if primary_mid is not None:
            primary_mid = int(primary_mid)
        is_supplier = bool(mapping.get("is_supplier"))
        raw_alts = [
            (int(mid), int(rank))
            for mid, rank in alt_machines_by_part.get(pk, [])
            if int(mid) not in blocked_machines and int(mid) != primary_mid
        ]
        part_tools = tools_by_part.get(pk, [])
        machine_tools = _build_machine_tool_map(pk, primary_mid, raw_alts, tools_by_part)
        # Alternate eligible when part has tools and machine is capable of making the part
        alts = [
            (mid, rank) for mid, rank in raw_alts
            if mid in machine_tools
        ]

        tool_no = part_tools[-1] if part_tools else tool_by_part.get(pk, "")
        if primary_mid is not None and primary_mid in machine_tools:
            tool_no = machine_tools[primary_mid]
        spm = spm_by_tool.get(tool_no, 0.0)
        cavity = cavity_by_part.get(pk, 1)
        part_name = str(inv.get("part_name") or "")
        part_no_display = str(inv.get("part_no") or pk)

        dispatch = dispatch_days_by_part.get(pk, {})

        pin = pins.get(pk, {})
        boost = int(boosts.get(pk, 0))

        jobs.append(Job(
            part_no=part_no_display,
            part_name=part_name,
            total_qty=balance_prod,
            rm_cap_qty=rm_cap_qty,
            dispatch_days=dispatch,
            primary_machine_id=primary_mid,
            alt_machines=alts,
            is_supplier=is_supplier,
            tool_no=tool_no,
            part_tools=part_tools,
            machine_tools=machine_tools,
            spm=spm,
            cavity=cavity,
            user_priority=boost,
            pinned_machine=pin.get("machine_id"),
            pinned_day=pin.get("day"),
        ))

    return SchedulerInput(
        month=month,
        year=year,
        jobs=jobs,
        machine_days=grid,
        tool_states=tool_states,
        scenario=scenario,
        work_hours_per_day=work_hours,
        overflow_minutes=overflow_minutes,
        schedule_from_day=schedule_from_day,
        actuals=actuals_payload,
        tool_day_machine=tool_day_machine,
        tool_day_part=tool_day_part,
        parts_by_tool=parts_by_tool,
    )
