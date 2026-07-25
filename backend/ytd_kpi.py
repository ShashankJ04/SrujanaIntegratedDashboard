"""Financial-year YTD overview KPIs (quantities, weights, distinct counts)."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Tuple

from .db import fetch_one

# Distinct report IDs (hub reports section)
DISTINCT_COMPONENT_REPORT_ID = "5749a7ed-e4be-4b41-a73b-78bd416f46b2"
DISTINCT_TOOLS_REPORT_ID = "ed95ec7b-1c11-4e58-8adb-524421ea224c"
DISTINCT_CUSTOMERS_REPORT_ID = "3b289936-891a-4770-b669-b8b724672431"
DISTINCT_RAW_MATERIALS_REPORT_ID = "51a29798-a36d-4933-bbfe-05e4097ba83d"
TOOL_BREAKDOWNS_REPORT_ID = "88a9ed8d-8131-44cb-8fef-fc2782449986"


def financial_year_start_year(for_date: date | None = None) -> int:
    d = for_date or date.today()
    return d.year if d.month >= 4 else d.year - 1


def financial_year_label(fy_start_year: int) -> str:
    end_yy = (fy_start_year + 1) % 100
    return f"FY {fy_start_year}-{end_yy:02d}"


def _fy_ytd_month_keys(for_date: date | None = None) -> Tuple[int, int, int, int]:
    """Return (fy_start_year, period_start_ym, period_end_ym, current_month)."""
    d = for_date or date.today()
    fy = financial_year_start_year(d)
    start_ym = fy * 12 + 4
    end_ym = d.year * 12 + d.month
    return fy, start_ym, end_ym, d.month


def _month_period_clause(alias: str) -> str:
    """SQL snippet: alias year/month columns fall within FY YTD month range."""
    return (
        f"(({alias}.SM_YEAR * 12 + {alias}.SM_MONTH) >= %s "
        f"AND ({alias}.SM_YEAR * 12 + {alias}.SM_MONTH) <= %s)"
    )


def _report_period_clause() -> str:
    return "(report_year * 12 + report_month) >= %s AND (report_year * 12 + report_month) <= %s"


def get_ytd_kpi(for_date: date | None = None) -> Dict[str, Any]:
    """Aggregate FY YTD metrics for the overview panel."""
    d = for_date or date.today()
    fy_start_year, start_ym, end_ym, _ = _fy_ytd_month_keys(d)
    fy_start = date(fy_start_year, 4, 1)
    fy_label = financial_year_label(fy_start_year)

    scheduled = 0.0
    planned = 0.0
    produced = 0.0
    dispatched = 0.0
    rm_inward_kg = 0.0
    tool_breakdown = 0
    distinct_components = 0
    distinct_tools = 0
    distinct_customers = 0
    distinct_raw_materials = 0

    try:
        row = fetch_one(
            f"""
            SELECT COALESCE(SUM(sc.CS_QTY), 0) AS total_scheduled
            FROM schedule_master sm
            INNER JOIN schedule_details sd ON sm.SM_ID = sd.SC_SMID
            INNER JOIN scheduled_customer sc ON sd.SC_ID = sc.CS_SCID
            WHERE sc.CS_SCHEDULESTATE IN (1, 2)
              AND {_month_period_clause("sm")}
            """,
            (start_ym, end_ym),
        )
        if row:
            scheduled = float(row.get("total_scheduled") or 0.0)
    except Exception:
        pass

    try:
        row = fetch_one(
            f"""
            SELECT COALESCE(SUM(GREATEST(production_pending, 0)), 0) AS total_planned
            FROM inventory_report_rows
            WHERE {_report_period_clause()}
            """,
            (start_ym, end_ym),
        )
        if row:
            planned = float(row.get("total_planned") or 0.0)
    except Exception:
        pass

    try:
        row = fetch_one(
            """
            SELECT COALESCE(SUM(pd.PD_PRODQTY), 0) AS total_produced
            FROM production_details pd
            WHERE pd.pd_ecsid = 8
              AND pd.PD_DATE >= %s
              AND pd.PD_DATE <= %s
            """,
            (fy_start.isoformat(), d.isoformat()),
        )
        if row:
            produced = float(row.get("total_produced") or 0.0)
    except Exception:
        pass

    try:
        row = fetch_one(
            """
            SELECT COALESCE(SUM(scd.SD_LOTSIZE), 0) AS total_dispatched
            FROM scheduled_customerdispatch scd
            INNER JOIN scheduled_customer sc ON scd.SD_CSID = sc.CS_Id
            WHERE scd.SD_Status = 7
              AND sc.CS_Date >= %s
              AND sc.CS_Date <= %s
            """,
            (fy_start.isoformat(), d.isoformat()),
        )
        if row:
            dispatched = float(row.get("total_dispatched") or 0.0)
    except Exception:
        pass

    try:
        row = fetch_one(
            """
            SELECT COALESCE(SUM(rd.RD_ACCEPTEDQTY), 0) AS total_inward_kg
            FROM rm_inwarddetails rd
            INNER JOIN rm_inwardmaster ri ON rd.rd_riid = ri.ri_id
            WHERE ri.RI_MOVEMENT = 'I'
              AND ri.RI_MOVEMENTTYPE = 1
              AND rd.RD_ACCEPTEDQTY > 0
              AND ri.RI_DATE >= %s
              AND ri.RI_DATE <= %s
            """,
            (fy_start.isoformat(), d.isoformat()),
        )
        if row:
            rm_inward_kg = float(row.get("total_inward_kg") or 0.0)
    except Exception:
        pass

    try:
        row = fetch_one(
            """
            SELECT COUNT(*) AS breakdown_count
            FROM tool_breakdowns
            WHERE DATE(created_at) >= %s
              AND DATE(created_at) <= %s
              AND COALESCE(tool_down, 'Breakdown') = 'Breakdown'
            """,
            (fy_start.isoformat(), d.isoformat()),
        )
        if row:
            tool_breakdown = int(row.get("breakdown_count") or 0)
    except Exception:
        pass

    try:
        row = fetch_one(
            """
            SELECT COUNT(*) AS cnt
            FROM components c
            WHERE c.CO_ID IN (
                SELECT DISTINCT CO_PARENTID
                FROM components
                WHERE CO_ACTIVEYN = 'Y'
            )
            """,
        )
        if row:
            distinct_components = int(row.get("cnt") or 0)
    except Exception:
        pass

    try:
        row = fetch_one(
            """
            SELECT COUNT(DISTINCT ct_toolno) AS cnt
            FROM components_tool
            WHERE ct_activeyn = 'Y'
            """,
        )
        if row:
            distinct_tools = int(row.get("cnt") or 0)
    except Exception:
        pass

    try:
        row = fetch_one(
            """
            SELECT COUNT(*) AS cnt
            FROM customer
            WHERE CU_Status = 'R'
            """,
        )
        if row:
            distinct_customers = int(row.get("cnt") or 0)
    except Exception:
        pass

    try:
        row = fetch_one(
            """
            SELECT COUNT(*) AS cnt
            FROM materialmaster
            WHERE mm_activeyn = 'Y'
            """,
        )
        if row:
            distinct_raw_materials = int(row.get("cnt") or 0)
    except Exception:
        pass

    return {
        "fyLabel": fy_label,
        "fyStartYear": fy_start_year,
        "periodStart": fy_start.isoformat(),
        "periodEnd": d.isoformat(),
        "scheduled": scheduled,
        "planned": planned,
        "produced": produced,
        "dispatched": dispatched,
        "rmInwardKg": rm_inward_kg,
        "toolBreakdown": tool_breakdown,
        "toolBreakdownReportId": TOOL_BREAKDOWNS_REPORT_ID,
        "distinct": {
            "components": distinct_components,
            "tools": distinct_tools,
            "customers": distinct_customers,
            "rawMaterials": distinct_raw_materials,
            "reports": {
                "components": DISTINCT_COMPONENT_REPORT_ID,
                "tools": DISTINCT_TOOLS_REPORT_ID,
                "customers": DISTINCT_CUSTOMERS_REPORT_ID,
                "rawMaterials": DISTINCT_RAW_MATERIALS_REPORT_ID,
            },
        },
    }
