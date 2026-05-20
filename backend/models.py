from __future__ import annotations

import os
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from flask import current_app

from .db import execute, fetch_all, fetch_one


@dataclass
class ColumnMeta:
    name: str
    label: str
    data_type: str
    is_numeric: bool
    is_sortable: bool


_CACHED_COLUMNS: Optional[List[ColumnMeta]] = None
_DASHBOARD_BASE_CACHE: Dict[str, Any] = {"rows": [], "last_refreshed": None}
_PULSE_CACHE_LOCK = threading.Lock()
_PULSE_CACHE: Dict[str, Any] = {"ts": 0.0, "items": []}
_PULSE_SCHEMA_CACHE: Dict[str, Tuple[float, set]] = {}
_REPORT_SUMMARY_CACHE_LOCK = threading.Lock()
_REPORT_SUMMARY_CACHE: Dict[str, Any] = {"ts": 0.0, "summary": None}


def _clear_reports_summary_cache() -> None:
    with _REPORT_SUMMARY_CACHE_LOCK:
        _REPORT_SUMMARY_CACHE["ts"] = 0.0
        _REPORT_SUMMARY_CACHE["summary"] = None


def _get_table_name() -> str:
    table = current_app.config.get("TARGET_TABLE_NAME")
    if not table:
        raise RuntimeError("TARGET_TABLE_NAME is not configured.")
    return table


def get_dashboard_columns() -> List[ColumnMeta]:
    """Column metadata for the dashboard base/derived metrics.

    These are defined explicitly rather than inferred from INFORMATION_SCHEMA
    so that we can compose data from multiple sources (base metrics + buffer config)
    while still reusing the generic table rendering on the frontend.
    """
    return [
        ColumnMeta(
            name="part_no",
            label="Part Number",
            data_type="varchar",
            is_numeric=False,
            is_sortable=True,
        ),
        ColumnMeta(
            name="part_name",
            label="Part Name",
            data_type="varchar",
            is_numeric=False,
            is_sortable=True,
        ),
        ColumnMeta(
            name="feb",
            label="Total Requirement",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="buffer_qty",
            label="Buffer Qty",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="wip",
            label="WIP--Closing Stock",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="fg",
            label="FG-Closing Stock",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="total_stock",
            label="Total Stock",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="production_pending",
            label="Production Pending",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="produced_qty",
            label="Produced Qty",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="balance_production_qty",
            label="Balance Production Quantity",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="qty_can_be_produced_nos",
            label="RM Coverage (Nos)",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="rm_rawmt_part_no",
            label="RM Code",
            data_type="varchar",
            is_numeric=False,
            is_sortable=True,
        ),
        ColumnMeta(
            name="rm_conval",
            label="Input RM (Grams)",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="rm_inward_accepted_qty",
            label="RM Closing Stock",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="rm_utilized",
            label="RM Utilized",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="total_rm_utilized",
            label="Total RM Utilized",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="current_acceptedqty",
            label="Current Stock Available Actual",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="current_stock_available",
            label="Theoretical Stock AV",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="rm_requirement",
            label="RM Production Requirement",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="rm_balance_kgs",
            label="RM Balance (Kgs)",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="total_rm_production_requirement",
            label="Total RM Production Requirement",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="rm_allocated",
            label="RM Allocated",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
        ColumnMeta(
            name="balance_allocated_rm_qty",
            label="Balance Allocated RM Qty",
            data_type="decimal",
            is_numeric=True,
            is_sortable=True,
        ),
    ]


def get_table_columns(force_refresh: bool = False) -> List[ColumnMeta]:
    """Return metadata for all columns of the target table.

    Results are cached in-process for performance; use force_refresh=True
    if the schema changes while the app is running.
    """
    global _CACHED_COLUMNS
    if _CACHED_COLUMNS is not None and not force_refresh:
        return _CACHED_COLUMNS

    table = _get_table_name()
    sql = """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """
    rows = fetch_all(sql, (table,))

    cols: List[ColumnMeta] = []
    numeric_types = {
        "int",
        "integer",
        "smallint",
        "mediumint",
        "bigint",
        "decimal",
        "numeric",
        "float",
        "double",
    }
    for row in rows:
        name = row["COLUMN_NAME"]
        data_type = row["DATA_TYPE"].lower()
        is_numeric = data_type in numeric_types
        label = name.replace("_", " ").title()
        cols.append(
            ColumnMeta(
                name=name,
                label=label,
                data_type=data_type,
                is_numeric=bool(is_numeric),
                is_sortable=True,
            )
        )

    _CACHED_COLUMNS = cols
    return cols


def _build_where_clause(
    columns: List[ColumnMeta],
    global_search: Optional[str],
) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []

    if global_search:
        like_pattern = f"%{global_search}%"
        text_cols = [c for c in columns if not c.is_numeric]
        if text_cols:
            or_parts = []
            for col in text_cols:
                or_parts.append(f"`{col.name}` LIKE %s")
                params.append(like_pattern)
            clauses.append("(" + " OR ".join(or_parts) + ")")

    if not clauses:
        return "", []

    where_sql = " WHERE " + " AND ".join(clauses)
    return where_sql, params


def _validate_sort(
    columns: List[ColumnMeta],
    sort_by: Optional[str],
    sort_dir: Optional[str],
) -> str:
    if not sort_by:
        return ""
    col_names = {c.name for c in columns if c.is_sortable}
    if sort_by not in col_names:
        return ""
    direction = "ASC" if (sort_dir or "").lower() != "desc" else "DESC"
    return f" ORDER BY `{sort_by}` {direction} "


def _matches_global_search(
    row: Dict[str, Any],
    columns: List[ColumnMeta],
    term: str,
) -> bool:
    for col in columns:
        val = row.get(col.name)
        if val is None:
            continue
        if term in str(val).lower():
            return True
    return False


def get_rows(
    page: int,
    page_size: int,
    global_search: Optional[str],
    sort_by: Optional[str],
    sort_dir: Optional[str],
) -> Dict[str, Any]:
    columns = get_table_columns()
    table = _get_table_name()

    where_sql, params = _build_where_clause(columns, global_search)
    order_sql = _validate_sort(columns, sort_by, sort_dir)

    count_sql = f"SELECT COUNT(*) AS cnt FROM `{table}`{where_sql}"
    count_row = fetch_one(count_sql, params)
    total_count = int(count_row["cnt"]) if count_row else 0

    max_page_size = int(current_app.config.get("MAX_PAGE_SIZE", 200))

    # Special case: page_size == -1 means "all rows"
    if page_size == -1:
        page = 1
        sql = f"SELECT * FROM `{table}`{where_sql}{order_sql}"
        rows = fetch_all(sql, params)
        effective_page_size = total_count
    else:
        if page_size <= 0:
            page_size = int(current_app.config.get("DEFAULT_PAGE_SIZE", 25))
        page_size = min(page_size, max_page_size)
        page = max(page, 1)
        offset = (page - 1) * page_size
        sql = f"SELECT * FROM `{table}`{where_sql}{order_sql} LIMIT %s OFFSET %s"
        params_with_pagination: List[Any] = list(params) + [page_size, offset]
        rows = fetch_all(sql, params_with_pagination)
        effective_page_size = page_size

    return {
        "columns": [c.__dict__ for c in columns],
        "rows": rows,
        "totalCount": total_count,
        "page": page,
        "pageSize": effective_page_size,
    }


def _get_dashboard_base_sql() -> str:
    """Base SQL for dashboard metrics (without buffer calculations).

    This mirrors vw_bharat_dashboard and returns:
    part_no, part_name, feb (monthly demand), wip, fg, total_stock, produced_qty,
    plus raw-material fields: rm_rawmt_part_no, rm_conval, rm_inward_accepted_qty,
    current_acceptedqty (actual RM stock from inward).
    """
    # Note: date logic and joins are kept aligned with static/sql/vw_bharat_dashboard.sql
    return """
        SELECT
            x.PART_NO AS part_no,
            x.PART_NAME AS part_name,
            x.QTY AS feb,
            IFNULL(y_wip.csQty, 0) AS wip,
            IFNULL(y_fg.csQty, 0) AS fg,
            (IFNULL(y_wip.csQty, 0) + IFNULL(y_fg.csQty, 0)) AS total_stock,
            IFNULL(z.pdProdQty, 0) AS produced_qty,
            rm.rm_rawmt_part_no,
            IFNULL(rm.rm_conval, 0) AS rm_conval,
            IFNULL(rm.rm_inward_accepted_qty, 0) AS rm_inward_accepted_qty,
            IFNULL(rm.current_acceptedqty, 0) AS current_acceptedqty
        FROM (
            SELECT trim(PART_NAME) as PART_NAME, trim(PART_NO) as PART_NO, SUM(QTY) AS QTY
            FROM (
                SELECT trim(PART_NAME) as PART_NAME, trim(PART_NO) as PART_NO, SUM(QTY) AS qty
                FROM sales_order
                WHERE DLV_DATE between DATE_SUB(current_date,INTERVAL DAYOFMONTH(current_date)-1 day) and last_day(current_date)
                  AND CATEGORY_ID = 1
                  AND SO_TYPE_ID IN (1, 2)
                  AND STATUS_ID IN (1, 7)
                GROUP BY trim(PART_NAME), trim(PART_NO)
                UNION ALL
                SELECT trim(b.PART_NAME) as PART_NAME, trim(b.PART_NO) as PART_NO, SUM(a.QTY * b.QTY) AS qty
                FROM sales_order a
                JOIN bom_lin_item b
                  ON b.bom_id IN (
                      SELECT c.bom_id
                      FROM bom c
                      WHERE c.bom_no = a.bom_no
                        AND c.is_latest_version = 'Y'
                  )
                WHERE a.DLV_DATE between DATE_SUB(current_date,INTERVAL DAYOFMONTH(current_date)-1 day) and last_day(current_date)
                  AND a.CATEGORY_ID = 2
                  AND a.SO_TYPE_ID IN (1, 2)
                  AND a.STATUS_ID IN (1, 7)
                  AND category_code = 'SS'
                GROUP BY trim(b.PART_NAME), trim(b.PART_NO)
            ) a
            GROUP BY trim(PART_NAME), trim(PART_NO)
        ) x
        LEFT JOIN (
            SELECT trim(c.CO_PARTNO) as PART_NO, SUM(a.csQty) AS csQty
            FROM (
                SELECT CH_CompId AS csCompId, CH_Qty AS csQty
                FROM comp_stockhistory
                WHERE CH_Month = EXTRACT(MONTH FROM CURRENT_DATE) - 1
                  AND CH_Year = EXTRACT(YEAR FROM DATE_ADD(CURRENT_DATE, INTERVAL -1 MONTH))
                  AND CH_StageId = 6
                  AND CH_WEEK = 0
            ) a
            JOIN components c ON a.csCompId = c.CO_id
            WHERE c.CO_ACTIVEYN = 'Y'
            GROUP BY trim(c.CO_PARTNO)
        ) y_fg ON x.PART_NO = y_fg.PART_NO
        LEFT JOIN (
            SELECT trim(c.CO_PARTNO) as PART_NO, SUM(a.csQty) AS csQty
            FROM (
                SELECT CH_CompId AS csCompId, CH_Qty AS csQty
                FROM comp_stockhistory
                WHERE CH_Month = EXTRACT(MONTH FROM CURRENT_DATE) - 1
                  AND CH_Year = EXTRACT(YEAR FROM DATE_ADD(CURRENT_DATE, INTERVAL -1 MONTH))
                  AND CH_StageId != 6
                  AND CH_WEEK = 0
            ) a
            JOIN components c ON a.csCompId = c.CO_id
            WHERE c.CO_ACTIVEYN = 'Y'
            GROUP BY trim(c.CO_PARTNO)
        ) y_wip ON x.PART_NO = y_wip.PART_NO 
        LEFT JOIN (
            SELECT trim(CO_partNo) as PART_NO, SUM(PD_PRODQTY) AS pdProdQty
            FROM scheduled_production
            INNER JOIN production_details ON PS_ID = PD_PSID
            INNER JOIN schedule_master ON SM_Id = PS_SMID
            INNER JOIN components ON CO_Id = PS_ParentCompId
            WHERE PD_DATE between DATE_SUB(current_date,INTERVAL DAYOFMONTH(current_date)-1 day) and last_day(current_date)
              AND SM_Status = 'S'
              AND PS_plantId = 2
            GROUP BY trim(CO_partNo)
        ) z ON x.PART_NO = z.PART_NO
        LEFT JOIN (
            SELECT
                TRIM(mq.co_partNo) AS PART_NO,
                mq.mm_rawmtpartNo AS rm_rawmt_part_no,
                mq.conVal AS rm_conval,
                IFNULL(iq.total_acceptedqty, 0) AS rm_inward_accepted_qty,
                IFNULL(inq.current_acceptedqty, 0) AS current_acceptedqty
            FROM (
                SELECT rmx.*, rmy.conVal
                FROM (
                    SELECT c.co_id, c.co_partNo, c.CO_PARTNAME, mm_rawmtpartNo, mm_id
                    FROM (
                        SELECT MIN(co_id) AS co_id,
                               TRIM(co_partNo) AS co_partNo,
                               MIN(CO_PARTNAME) AS CO_PARTNAME
                        FROM components
                        WHERE co_activeyn = 'Y'
                          AND TRIM(co_partNo) IN (
                              SELECT TRIM(PART_NO)
                              FROM (
                                  SELECT PART_NAME, PART_NO
                                  FROM sales_order
                                  WHERE DLV_DATE BETWEEN DATE_SUB(current_date, INTERVAL DAYOFMONTH(current_date)-1 DAY)
                                        AND last_day(current_date)
                                    AND CATEGORY_ID = 1
                                    AND SO_TYPE_ID IN (1, 2)
                                    AND STATUS_ID IN (1, 7)
                                  GROUP BY PART_NAME, PART_NO
                                  UNION ALL
                                  SELECT b.PART_NAME, b.PART_NO
                                  FROM sales_order a
                                  JOIN bom_lin_item b
                                    ON b.bom_id IN (
                                        SELECT bm.bom_id FROM bom bm
                                        WHERE bm.bom_no = a.bom_no AND bm.is_latest_version = 'Y'
                                    )
                                  WHERE a.DLV_DATE BETWEEN DATE_SUB(current_date, INTERVAL DAYOFMONTH(current_date)-1 DAY)
                                        AND last_day(current_date)
                                    AND a.CATEGORY_ID = 2
                                    AND a.SO_TYPE_ID IN (1, 2)
                                    AND a.STATUS_ID IN (1, 7)
                                    AND category_code = 'SS'
                                  GROUP BY b.PART_NAME, b.PART_NO
                              ) rm_so
                              GROUP BY TRIM(PART_NO)
                          )
                        GROUP BY TRIM(co_partNo)
                    ) c
                    JOIN (
                        SELECT ct_compid AS compId, MAX(ct_rmid) AS rmId
                        FROM components_tool where CT_ACTIVEYN ='Y' GROUP BY ct_compid
                    ) ct ON c.co_id = ct.compId
                    JOIN materialmaster ON ct.rmId = mm_id
                ) rmx
                LEFT JOIN (
                    SELECT co_Id, co_partNo, co_partname, ct.rmId, ct_compid, MM_RawMtPartNo,
                        ROUND(1000 / ((1 / ((MT_Density * MM_Thickness) * MM_StripWidth))
                            * ((1000 * ct.ctNoOfCavity) / ct.ctPitch)), 1) AS conVal
                    FROM components
                    INNER JOIN (
                        SELECT CT_RMID AS rmId, ct_compid,
                               CT_NO_OF_CAVITY AS ctNoOfCavity, CT_Pitch AS ctPitch
                        FROM components_tool
                        WHERE ct_id IN (
                            SELECT MAX(ct_id) FROM components_tool
                            WHERE CT_ActiveYN='Y' AND CT_PPC='Y'
                              AND CT_PITCH > 0 AND CT_NO_OF_CAVITY > 0
                            GROUP BY ct_compid
                        )
                        AND CT_ActiveYN='Y' AND CT_PPC='Y'
                        AND CT_PITCH > 0 AND CT_NO_OF_CAVITY > 0
                    ) ct ON co_id = ct.ct_compid
                    INNER JOIN materialmaster ON ct.rmId = mm_id
                    INNER JOIN materialtypemaster ON MM_MTID = MT_Id
                    WHERE co_activeyn = 'Y' AND co_id = CO_PARENTID
                ) rmy ON rmx.co_Id = rmy.co_Id
                     AND rmx.co_partNo = rmy.co_partNo
                     AND rmx.CO_PARTNAME = rmy.CO_PARTNAME
            ) mq
            LEFT JOIN (
                SELECT RD_RMID,
round(SUM(CASE WHEN ri_movement = 'I' THEN RD_acceptedqty ELSE 0 END)
- SUM(CASE WHEN ri_movement = 'O' THEN RD_acceptedqty ELSE 0 END) ,2)AS total_acceptedqty
FROM rm_inwarddetails , rm_inwardmaster, materialmaster, materialtypemaster
    where rd_riid=ri_id and RD_RMID = MM_Id and MM_mtId = MT_Id AND RI_date <= last_day(DATE_ADD(current_date, INTERVAL -1 MONTH))     
    group by RD_RMID
            ) iq ON mq.mm_id = iq.RD_rmid
            LEFT JOIN (
                SELECT RD_RMID,
      round(SUM(CASE WHEN ri_movement = 'I' THEN RD_acceptedqty ELSE 0 END)
      - SUM(CASE WHEN ri_movement = 'O' THEN RD_acceptedqty ELSE 0 END) ,2)AS current_acceptedqty
      FROM rm_inwarddetails , rm_inwardmaster, materialmaster, materialtypemaster
    where rd_riid=ri_id and RD_RMID = MM_Id and MM_mtId = MT_Id   
    group by RD_RMID
            ) inq ON mq.mm_id = inq.RD_rmid
        ) rm ON x.PART_NO = rm.PART_NO
    """


def refresh_dashboard_base_cache() -> Dict[str, Any]:
    """Run the heavy base SQL once and cache results in memory.

    This is intended to be called only on explicit hard refresh.
    """
    global _DASHBOARD_BASE_CACHE

    base_sql = _get_dashboard_base_sql()
    rows = fetch_all(base_sql)
    _DASHBOARD_BASE_CACHE = {
        "rows": rows,
        "last_refreshed": datetime.utcnow(),
    }
    # Keep summary KPI consistent after explicit base cache refresh.
    _clear_reports_summary_cache()
    return _DASHBOARD_BASE_CACHE


def _get_cached_base_rows() -> List[Dict[str, Any]]:
    """Return cached base rows (or empty list if cache is empty)."""
    return list(_DASHBOARD_BASE_CACHE.get("rows", []))


def get_dashboard_base_rows(
    page: int,
    page_size: int,
    global_search: Optional[str],
    sort_by: Optional[str],
    sort_dir: Optional[str],
) -> Dict[str, Any]:
    """Return paginated base metrics using the in-memory cache only.

    This function does NOT execute the heavy SQL; it works over the
    cache populated by refresh_dashboard_base_cache().
    """
    columns = get_dashboard_columns()
    base_rows = _get_cached_base_rows()
    if not base_rows:
        # Cache is empty – populate it once from the database.
        refresh_dashboard_base_cache()
        base_rows = _get_cached_base_rows()

    # Apply global search across all configured columns (string match)
    if global_search:
        term = str(global_search).lower()
        filtered: List[Dict[str, Any]] = []
        for row in base_rows:
            if _matches_global_search(row, columns, term):
                filtered.append(row)
        working_rows = filtered
    else:
        working_rows = list(base_rows)

    # Apply sorting
    if sort_by:
        col_names = {c.name for c in columns if c.is_sortable}
        if sort_by in col_names:
            direction = -1 if (sort_dir or "").lower() == "desc" else 1

            def sort_key(row: Dict[str, Any]) -> Any:
                val = row.get(sort_by)
                if val is None:
                    return (1, None)
                try:
                    num = float(val)
                    return (0, num)
                except (TypeError, ValueError):
                    return (0, str(val).lower())

            working_rows.sort(key=sort_key, reverse=direction < 0)

    total_count = len(working_rows)

    max_page_size = int(current_app.config.get("MAX_PAGE_SIZE", 200))

    if page_size == -1:
        page = 1
        effective_page_size = total_count
        page_rows = working_rows
    else:
        if page_size <= 0:
            page_size = int(current_app.config.get("DEFAULT_PAGE_SIZE", 25))
        page_size = min(page_size, max_page_size)
        page = max(page, 1)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        page_rows = working_rows[offset : offset + page_size]
        effective_page_size = page_size

    return {
        "columns": [c.__dict__ for c in columns],
        "rows": page_rows,
        "totalCount": total_count,
        "page": page,
        "pageSize": effective_page_size,
    }


def _rm_material_group_key(row: Dict[str, Any]) -> str:
    """Aggregate RM metrics by raw material part number; isolated rows without RM code."""
    rm = row.get("rm_rawmt_part_no")
    if rm is not None and str(rm).strip():
        return str(rm).strip()
    return f"__nopart__{row.get('part_no', '')}"


def _normalize_rm_allocation_inputs(rows: List[Dict[str, Any]]) -> None:
    """Round base RM fields and compute per-row rm_utilized from produced × conval."""
    for row in rows:
        row["rm_inward_accepted_qty"] = round(
            float(row.get("rm_inward_accepted_qty") or 0), 2
        )
        row["current_acceptedqty"] = round(
            float(row.get("current_acceptedqty") or 0), 2
        )
        pq = float(row.get("produced_qty") or 0)
        cv = float(row.get("rm_conval") or 0)
        row["rm_utilized"] = round((pq * cv) / 1000, 2) if cv else 0.0
        rq = float(row.get("rm_requirement") or 0)
        row["rm_requirement"] = round(rq, 2)


def _rm_material_group_aggregates(
    rows: List[Dict[str, Any]],
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float]]:
    """Sum utilization/requirement by RM; keep max inward and max current actual stock."""
    sum_util: Dict[str, float] = defaultdict(float)
    sum_req: Dict[str, float] = defaultdict(float)
    inward_by_key: Dict[str, float] = {}
    actual_by_key: Dict[str, float] = {}

    for row in rows:
        key = _rm_material_group_key(row)
        sum_util[key] += float(row.get("rm_utilized") or 0)
        sum_req[key] += float(row.get("rm_requirement") or 0)
        inv = float(row.get("rm_inward_accepted_qty") or 0)
        if key not in inward_by_key:
            inward_by_key[key] = inv
        else:
            inward_by_key[key] = max(inward_by_key[key], inv)
        act = float(row.get("current_acceptedqty") or 0)
        if key not in actual_by_key:
            actual_by_key[key] = act
        else:
            actual_by_key[key] = max(actual_by_key[key], act)

    return sum_util, sum_req, inward_by_key, actual_by_key


def _apply_rm_allocation_assignments(
    rows: List[Dict[str, Any]],
    sum_util: Dict[str, float],
    sum_req: Dict[str, float],
    inward_by_key: Dict[str, float],
    actual_by_key: Dict[str, float],
) -> None:
    """Fill RM totals/allocations; allocation uses current actual stock, theoretical remains standalone."""
    for row in rows:
        key = _rm_material_group_key(row)
        total_u = sum_util[key]
        total_prod_req = sum_req[key]
        inward = inward_by_key[key]
        actual_stock = max(float(actual_by_key.get(key, 0.0)), 0.0)

        raw_available = inward - total_u
        current_stock = float(raw_available) if raw_available > 0 else 0.0

        rm_req = float(row.get("rm_requirement") or 0)

        if total_prod_req > 0:
            rm_allocated = rm_req * (actual_stock / total_prod_req)
        else:
            rm_allocated = 0.0

        balance_allocated = min(rm_allocated, rm_req)

        cv = float(row.get("rm_conval") or 0)
        qty_nos = ((balance_allocated * 1000) / cv) if cv else 0.0
        rm_bal_kgs = balance_allocated - rm_req

        row["total_rm_utilized"] = round(total_u, 2)
        row["current_stock_available"] = round(current_stock, 2)
        row["total_rm_production_requirement"] = round(total_prod_req, 2)
        row["rm_allocated"] = round(rm_allocated, 2)
        row["balance_allocated_rm_qty"] = round(balance_allocated, 2)
        row["qty_can_be_produced_nos"] = round(qty_nos, 2)
        row["rm_balance_kgs"] = round(rm_bal_kgs, 2)


def _apply_rm_allocation_metrics(rows: List[Dict[str, Any]]) -> None:
    """Per-row RM utilization and allocation; totals are summed by rm_rawmt_part_no."""
    _normalize_rm_allocation_inputs(rows)
    su, sr, inv, act = _rm_material_group_aggregates(rows)
    _apply_rm_allocation_assignments(rows, su, sr, inv, act)


def _enrich_dashboard_buffer_rows(
    base_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Buffer + balance production + rm_requirement for each base row (dashboard rules)."""
    buffer_map = get_buffer_config_for_all_parts()
    enriched_rows: List[Dict[str, Any]] = []
    for row in base_rows:
        part_no = str(row.get("part_no", ""))
        qty = float(row.get("feb") or 0)
        total_stock = float(row.get("total_stock") or 0)
        produced_qty = float(row.get("produced_qty") or 0)

        buffer_qty = float(buffer_map.get(part_no, 0.0))
        production_pending = round(qty + buffer_qty) - total_stock
        balance_production_qty = production_pending - produced_qty

        rm_conval = float(row.get("rm_conval") or 0)
        if balance_production_qty > 0 and rm_conval:
            rm_requirement = round((balance_production_qty * rm_conval) / 1000, 2)
        else:
            rm_requirement = 0.0

        enriched = dict(row)
        enriched.update(
            {
                "buffer_qty": buffer_qty,
                "production_pending": production_pending,
                "balance_production_qty": balance_production_qty,
                "rm_requirement": rm_requirement,
            }
        )
        enriched_rows.append(enriched)
    return enriched_rows


def get_dashboard_rows_with_buffer(
    page: int,
    page_size: int,
    global_search: Optional[str],
    sort_by: Optional[str],
    sort_dir: Optional[str],
    row_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Return dashboard rows enriched with buffer and RM derived columns.

    Default buffer_qty is 0 when not configured for a part_no.
    All filtering, sorting, and pagination are applied on the enriched rows so
    that derived column sorting works correctly.
    """
    columns = get_dashboard_columns()
    base_rows = _get_cached_base_rows()
    if not base_rows:
        # Cache is empty – populate it once from the database.
        refresh_dashboard_base_cache()
        base_rows = _get_cached_base_rows()

    # Enrich full cache first so RM group totals (total_rm_*, current_stock_available, etc.)
    # reflect all parts sharing an RM code — not only rows matching global search.
    enriched_all = _enrich_dashboard_buffer_rows(base_rows)
    _normalize_rm_allocation_inputs(enriched_all)
    sum_util, sum_req, inward_by_key, actual_by_key = _rm_material_group_aggregates(
        enriched_all
    )
    _apply_rm_allocation_assignments(
        enriched_all, sum_util, sum_req, inward_by_key, actual_by_key
    )

    if global_search:
        term = str(global_search).lower()
        enriched_rows = [
            r
            for r in enriched_all
            if _matches_global_search(r, columns, term)
        ]
    else:
        enriched_rows = list(enriched_all)

    if (row_filter or "").strip().lower() == "pending":
        enriched_rows = [
            r
            for r in enriched_rows
            if float(r.get("balance_production_qty") or 0) > 0
        ]

    # Apply sorting on enriched rows
    if sort_by:
        col_names = {c.name for c in columns if c.is_sortable}
        if sort_by in col_names:
            direction = -1 if (sort_dir or "").lower() == "desc" else 1

            def sort_key(row: Dict[str, Any]) -> Any:
                val = row.get(sort_by)
                if val is None:
                    return (1, None)
                try:
                    num = float(val)
                    return (0, num)
                except (TypeError, ValueError):
                    return (0, str(val).lower())

            enriched_rows.sort(key=sort_key, reverse=direction < 0)

    total_count = len(enriched_rows)

    max_page_size = int(current_app.config.get("MAX_PAGE_SIZE", 200))

    if page_size == -1:
        page = 1
        effective_page_size = total_count
        page_rows = enriched_rows
    else:
        if page_size <= 0:
            page_size = int(current_app.config.get("DEFAULT_PAGE_SIZE", 25))
        page_size = min(page_size, max_page_size)
        page = max(page, 1)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        page_rows = enriched_rows[offset : offset + page_size]
        effective_page_size = page_size

    return {
        "columns": [c.__dict__ for c in columns],
        "rows": page_rows,
        "totalCount": total_count,
        "page": page,
        "pageSize": effective_page_size,
    }


def get_buffer_config_for_all_parts() -> Dict[str, float]:
    """Return buffer_qty per part_no as a simple dictionary."""
    sql = "SELECT part_no, buffer_qty FROM buffer_stock_config"
    rows = fetch_all(sql)
    return {str(r["part_no"]): float(r["buffer_qty"]) for r in rows}


def get_buffer_config_for_part(part_no: str) -> Optional[float]:
    """Return buffer_qty for a specific part_no, or None if not configured."""
    sql = "SELECT buffer_qty FROM buffer_stock_config WHERE part_no = %s"
    row = fetch_one(sql, (part_no,))
    if not row:
        return None
    return float(row["buffer_qty"])


def upsert_buffer_config(part_no: str, buffer_qty: float, updated_by: Optional[str] = None) -> None:
    """Insert or update buffer_qty for a part_no (may be negative)."""

    sql = """
        INSERT INTO buffer_stock_config (part_no, buffer_qty, updated_by)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            buffer_qty = VALUES(buffer_qty),
            updated_by = VALUES(updated_by)
    """
    execute(sql, (part_no, buffer_qty, updated_by))
    _clear_reports_summary_cache()


def _get_enriched_rows_for_reports() -> List[Dict[str, Any]]:
    """Return dashboard rows enriched with balance production values."""
    base_rows = _get_cached_base_rows()
    if not base_rows:
        refresh_dashboard_base_cache()
        base_rows = _get_cached_base_rows()

    buffer_map = get_buffer_config_for_all_parts()
    enriched_rows: List[Dict[str, Any]] = []
    for row in base_rows:
        part_no = str(row.get("part_no", ""))
        req = float(row.get("feb") or 0)
        total_stock = float(row.get("total_stock") or 0)
        produced = float(row.get("produced_qty") or 0)
        buffer_qty = float(buffer_map.get(part_no, 0.0))
        production_pending = round(req + buffer_qty) - total_stock
        balance = production_pending - produced

        rm_conval = float(row.get("rm_conval") or 0)
        if balance > 0 and rm_conval:
            rm_requirement = round((balance * rm_conval) / 1000, 2)
        else:
            rm_requirement = 0.0

        enriched = dict(row)
        enriched.update(
            {
                "buffer_qty": buffer_qty,
                "production_pending": float(production_pending),
                "balance_production_qty": float(balance),
                "rm_requirement": rm_requirement,
            }
        )
        enriched_rows.append(enriched)
    return enriched_rows


def get_report_summary() -> Dict[str, Any]:
    """High-level KPI metrics for the reports page using balance production qty."""
    cache_seconds = int(
        current_app.config.get("REPORTS_SUMMARY_CACHE_SECONDS", 30) or 30
    )
    now = time.monotonic()
    if cache_seconds > 0:
        with _REPORT_SUMMARY_CACHE_LOCK:
            cached_ts = float(_REPORT_SUMMARY_CACHE.get("ts") or 0.0)
            cached_summary = _REPORT_SUMMARY_CACHE.get("summary")
            if cached_summary is not None and (now - cached_ts) < cache_seconds:
                return dict(cached_summary)

    rows = _get_enriched_rows_for_reports()

    total_so = 0.0
    total_produced_qty = 0.0
    total_production_requirement = 0.0
    total_pending = 0.0
    total_excess = 0.0
    total_parts = 0
    parts_completed = 0
    parts_pending = 0

    for row in rows:
        req = float(row.get("feb") or 0)
        produced = float(row.get("produced_qty") or 0)
        buffer_qty = float(row.get("buffer_qty") or 0)
        balance = float(row.get("balance_production_qty") or 0)
        
        total_so += req
        total_produced_qty += max(0.0, produced)
        total_production_requirement += max(0.0, req + buffer_qty)
        
        if balance > 0:
            total_pending += balance
            parts_pending += 1
        else:
            total_excess += abs(balance)
            parts_completed += 1
        total_parts += 1

    dispatch_qty_mtd = 0.0
    dispatch_invoice_count_mtd = 0
    try:
        today = date.today()
        month_start = today.replace(day=1)
        if month_start.month == 12:
            next_month_start = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=month_start.month + 1)
        month_end = next_month_start - timedelta(days=1)
        dispatch_row = fetch_one(
            """
            SELECT
                COALESCE(SUM(SD_LOTSIZE), 0) AS dispatched_qty_mtd,
                COUNT(DISTINCT COALESCE(NULLIF(TRIM(SD_INVOICE), ''), SD_ID)) AS dispatch_invoice_count_mtd
            FROM scheduled_customerdispatch
            INNER JOIN scheduled_customer ON SD_CSID = CS_Id
            INNER JOIN customer ON CU_Id = CS_CUSTID
            INNER JOIN schedule_details ON SC_Id = CS_SCID
            INNER JOIN components ON CO_Id = SC_COMPID
            INNER JOIN dispatch_status ON DS_Id = SD_Status
            WHERE SD_Status = 7
              AND CS_Date BETWEEN %s AND %s
            """,
            (month_start.isoformat(), month_end.isoformat()),
        )
        if dispatch_row:
            dispatch_qty_mtd = float(dispatch_row.get("dispatched_qty_mtd") or 0.0)
            dispatch_invoice_count_mtd = int(
                dispatch_row.get("dispatch_invoice_count_mtd") or 0
            )
    except Exception:
        pass

    summary = {
        "total_so_qty": total_so,
        "total_produced_qty": total_produced_qty,
        "total_production_requirement": total_production_requirement,
        "total_pending_qty": total_pending,
        "total_excess_qty": total_excess,
        "parts_total": total_parts,
        "parts_completed": parts_completed,
        "parts_pending": parts_pending,
        "dispatch_qty_mtd": dispatch_qty_mtd,
        "dispatch_invoice_count_mtd": dispatch_invoice_count_mtd,
    }
    if cache_seconds > 0:
        with _REPORT_SUMMARY_CACHE_LOCK:
            _REPORT_SUMMARY_CACHE["ts"] = now
            _REPORT_SUMMARY_CACHE["summary"] = dict(summary)
    return summary


def get_production_vs_requirement(limit: int = 15) -> Dict[str, Any]:
    """Top components by pending production (based on balance production qty)."""
    rows = _get_enriched_rows_for_reports()

    ranked: List[Dict[str, Any]] = []
    for row in rows:
        req = float(row.get("feb") or 0)
        balance = float(row.get("balance_production_qty") or 0)
        pending = max(balance, 0.0)
        excess = abs(min(balance, 0.0))
        ranked.append(
            {
                "part_no": row.get("part_no"),
                "part_name": row.get("part_name"),
                "required_qty": req,
                "pending_qty": pending,
                "excess_qty": excess,
                "balance_qty": balance,
            }
        )

    ranked.sort(key=lambda r: r["pending_qty"], reverse=True)
    top = ranked[: max(1, limit)]

    return {
        "items": top,
        "labels": [f'{r["part_no"]}' for r in top],
        "required": [r["required_qty"] for r in top],
        "pending": [r["pending_qty"] for r in top],
        "excess": [r["excess_qty"] for r in top],
        "meta": top,
    }


def get_completion_buckets() -> Dict[str, Any]:
    """Bucket components by fulfillment based on balance production qty."""
    rows = _get_enriched_rows_for_reports()

    buckets = {
        "NotStarted": 0,
        "Low(0-50%)": 0,
        "Medium(50-90%)": 0,
        "NearDone(90-100%)": 0,
        "DoneOrExcess(>=100%)": 0,
    }

    for row in rows:
        req = float(row.get("feb") or 0)
        balance = float(row.get("balance_production_qty") or 0)
        if req <= 0:
            continue
        pending = max(balance, 0.0)
        pct = max(0.0, min(1.0, (req - pending) / req))
        if pct <= 0.0:
            buckets["NotStarted"] += 1
        elif pct < 0.5:
            buckets["Low(0-50%)"] += 1
        elif pct < 0.9:
            buckets["Medium(50-90%)"] += 1
        elif pct < 1.0:
            buckets["NearDone(90-100%)"] += 1
        else:
            buckets["DoneOrExcess(>=100%)"] += 1

    labels = list(buckets.keys())
    counts = [buckets[label] for label in labels]
    return {
        "buckets": [{"label": l, "count": c} for l, c in zip(labels, counts)],
        "labels": labels,
        "counts": counts
    }


def get_top_shortfalls(limit: int = 20) -> List[Dict[str, Any]]:
    """Return parts with the highest pending balance production quantity."""
    rows = _get_enriched_rows_for_reports()
    items: List[Dict[str, Any]] = []
    for row in rows:
        req = float(row.get("feb") or 0)
        balance = float(row.get("balance_production_qty") or 0)
        pending = max(balance, 0.0)
        excess = abs(min(balance, 0.0))
        if pending <= 0 and excess <= 0:
            continue
        items.append(
            {
                "part_no": row.get("part_no"),
                "part_name": row.get("part_name"),
                "required_qty": req,
                "pending_qty": pending,
                "excess_qty": excess,
                "balance_qty": balance,
            }
        )

    items.sort(key=lambda r: r["pending_qty"], reverse=True)
    return items[: max(1, limit)]


def get_pending_treemap(limit: int = 40) -> List[Dict[str, Any]]:
    """Treemap payload for pending component production."""
    rows = _get_enriched_rows_for_reports()
    items: List[Dict[str, Any]] = []
    for row in rows:
        balance = float(row.get("balance_production_qty") or 0)
        pending = max(balance, 0.0)
        if pending <= 0:
            continue
        items.append(
            {
                "part_no": row.get("part_no"),
                "part_name": row.get("part_name"),
                "pending_qty": pending,
            }
        )
    items.sort(key=lambda r: r["pending_qty"], reverse=True)
    return {"items": items[: max(1, limit)]}


def get_rm_chart_data(limit: int = 20) -> Dict[str, Any]:
    """Return aggregated raw-material chart series from enriched dashboard rows."""
    rows = _get_enriched_rows_for_reports()
    _apply_rm_allocation_metrics(rows)

    top_rm: List[Dict[str, Any]] = []
    material_agg: Dict[str, float] = {}

    for row in rows:
        rm_req = float(row.get("rm_requirement") or 0)
        rm_inward = float(row.get("rm_inward_accepted_qty") or 0)
        rm_part = row.get("rm_rawmt_part_no") or ""

        top_rm.append(
            {
                "part_no": row.get("part_no"),
                "part_name": row.get("part_name"),
                "rm_requirement": rm_req,
                "rm_inward_accepted_qty": rm_inward,
                "rm_rawmt_part_no": rm_part,
                "rm_balance_kgs": float(row.get("rm_balance_kgs") or 0),
                "current_stock_available": float(row.get("current_stock_available") or 0),
            }
        )

        if rm_part and rm_req != 0:
            material_agg[rm_part] = material_agg.get(rm_part, 0) + rm_req

    top_rm.sort(key=lambda r: abs(r["rm_requirement"]), reverse=True)
    top_rm = top_rm[: max(1, limit)]

    mat_labels = sorted(material_agg.keys(), key=lambda k: material_agg[k], reverse=True)
    mat_values = [material_agg[k] for k in mat_labels]

    seen_mat: set = set()
    material_stock_vs_req: List[Dict[str, Any]] = []
    for row in rows:
        key = _rm_material_group_key(row)
        if key.startswith("__nopart__") or key in seen_mat:
            continue
        seen_mat.add(key)
        material_stock_vs_req.append(
            {
                "rm_code": str(row.get("rm_rawmt_part_no") or key).strip() or key,
                "current_stock": float(row.get("current_acceptedqty") or 0),
                "total_production_req": float(row.get("total_rm_production_requirement") or 0),
                "total_rm_utilized": float(row.get("total_rm_utilized") or 0),
            }
        )
    material_stock_vs_req.sort(
        key=lambda x: x["total_production_req"], reverse=True
    )
    material_stock_vs_req = material_stock_vs_req[: max(1, min(limit, 15))]

    top_rm_balance = sorted(
        rows,
        key=lambda r: abs(float(r.get("rm_balance_kgs") or 0)),
        reverse=True,
    )[: max(1, limit)]
    top_rm_balance_parts = [
        {
            "part_no": r.get("part_no"),
            "rm_balance_kgs": float(r.get("rm_balance_kgs") or 0),
            "rm_requirement": float(r.get("rm_requirement") or 0),
            "rm_rawmt_part_no": r.get("rm_rawmt_part_no") or "",
        }
        for r in top_rm_balance
    ]

    util_pairs: List[Tuple[str, float]] = []
    seen_u: set = set()
    for row in rows:
        key = _rm_material_group_key(row)
        if key.startswith("__nopart__") or key in seen_u:
            continue
        seen_u.add(key)
        util_pairs.append(
            (
                str(row.get("rm_rawmt_part_no") or key).strip() or key,
                float(row.get("total_rm_utilized") or 0),
            )
        )
    util_pairs.sort(key=lambda p: p[1], reverse=True)
    util_pairs = util_pairs[:15]

    rm_shortage_rows: List[Dict[str, Any]] = []
    for row in rows:
        ca = float(row.get("current_acceptedqty") or 0)
        # Use total plant-level requirement for the RM instead of just this single part's req
        tpr = float(row.get("total_rm_production_requirement") or 0)
        shortage = round(ca - tpr, 2)
        rm_shortage_rows.append(
            {
                "part_no": row.get("part_no"),
                "part_name": row.get("part_name"),
                "rm_rawmt_part_no": row.get("rm_rawmt_part_no") or "",
                "current_acceptedqty": ca,
                "rm_requirement": tpr,
                "rm_shortage_actual": shortage,
            }
        )
    rm_shortage_rows.sort(
        key=lambda r: abs(float(r["rm_shortage_actual"])), reverse=True
    )
    rm_shortage_by_part = rm_shortage_rows[: max(1, min(limit, 15))]

    seen_shortage_mat: set = set()
    rm_shortage_by_material: List[Dict[str, Any]] = []
    for row in rows:
        key = _rm_material_group_key(row)
        if key.startswith("__nopart__") or key in seen_shortage_mat:
            continue
        seen_shortage_mat.add(key)
        ca = float(row.get("current_acceptedqty") or 0)
        tpr = float(row.get("total_rm_production_requirement") or 0)
        shortage = round(ca - tpr, 2)
        rm_code = str(row.get("rm_rawmt_part_no") or key).strip() or key
        rm_shortage_by_material.append(
            {
                "rm_rawmt_part_no": rm_code,
                "current_acceptedqty": ca,
                "total_rm_production_requirement": tpr,
                "rm_shortage_actual": shortage,
            }
        )
    rm_shortage_by_material.sort(
        key=lambda r: abs(float(r["rm_shortage_actual"])), reverse=True
    )
    # Provide all items so the frontend can toggle between Top 15 and All Items

    return {
        "top_rm_parts": top_rm,
        "material_mix": {"labels": mat_labels, "values": mat_values},
        "material_stock_vs_req": material_stock_vs_req,
        "top_rm_balance_parts": top_rm_balance_parts,
        "material_utilized": {
            "labels": [p[0] for p in util_pairs],
            "values": [p[1] for p in util_pairs],
        },
        "rm_shortage_by_part": rm_shortage_by_part,
        "rm_shortage_by_material": rm_shortage_by_material,
    }


# ══════════════════════════════════════════════════════════════════════════
# DPR — Daily Production Review
# ══════════════════════════════════════════════════════════════════════════

def get_dpr_machine_options() -> List[Dict[str, Any]]:
    """Machine dropdown options. Uses Config.DPR_MACHINE_LIST_SQL."""
    sql = str(current_app.config.get("DPR_MACHINE_LIST_SQL") or "").strip()
    if not sql:
        return []
    rows = fetch_all(sql)
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        keys = {str(k).lower(): k for k in row.keys()}
        id_key = (
            keys.get("id")
            or keys.get("machine_id")
            or keys.get("mc_id")
            or keys.get("mcm_id")
        )
        label_key = (
            keys.get("label")
            or keys.get("name")
            or keys.get("machine_name")
            or keys.get("mcm_name")
            or id_key
        )
        if id_key is None:
            continue
        mid = row.get(id_key)
        label = row.get(label_key) if label_key else mid
        out.append(
            {
                "id": str(mid).strip() if mid is not None else "",
                "label": str(label).strip() if label is not None else "",
            }
        )
    return [x for x in out if x["id"]]


def get_hub_pulse_feed() -> List[Dict[str, Any]]:
    """Short ops ticker for the Hub top bar across core transactional tables."""

    cache_seconds = int(current_app.config.get("HUB_PULSE_CACHE_SECONDS", 20) or 20)
    now = time.monotonic()
    if cache_seconds > 0:
        with _PULSE_CACHE_LOCK:
            cached_ts = float(_PULSE_CACHE.get("ts") or 0.0)
            if (now - cached_ts) < cache_seconds:
                return list(_PULSE_CACHE.get("items") or [])

    def _table_columns(table: str) -> set:
        schema_cache_seconds = int(
            current_app.config.get("HUB_SCHEMA_CACHE_SECONDS", 600) or 600
        )
        if schema_cache_seconds > 0:
            cached = _PULSE_SCHEMA_CACHE.get(table)
            if cached and (now - cached[0]) < schema_cache_seconds:
                return set(cached[1])
        rows = fetch_all(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table,),
        )
        cols = {str(r.get("COLUMN_NAME") or "").strip() for r in rows}
        if schema_cache_seconds > 0:
            _PULSE_SCHEMA_CACHE[table] = (now, cols)
        return cols

    def _pick(cols: set, candidates: List[str]) -> Optional[str]:
        low_map = {str(c).lower(): c for c in cols}
        for c in candidates:
            hit = low_map.get(str(c).lower())
            if hit:
                return hit
        return None

    def _qid(col: str) -> str:
        return f"`{col}`"

    pulse: List[Dict[str, Any]] = []
    enriched_done: set = set()

    # 1) Production details (explicit, rich event)
    try:
        prods = fetch_all(
            """
            SELECT TRIM(co.CO_PARTNO) AS part_no, pd.PD_PRODQTY AS qty, pd.PD_DATE AS date
            FROM production_details pd
            INNER JOIN components_tool ct ON pd.PD_TOOLID = ct.CT_ID
            INNER JOIN components co ON ct.CT_COMPID = co.CO_ID
            ORDER BY pd.PD_DATE DESC
            LIMIT 5
            """
        )
        for p in prods:
            qraw = p.get("qty")
            try:
                qn = int(float(qraw)) if qraw is not None and str(qraw).strip() != "" else 0
            except (TypeError, ValueError):
                qn = 0
            pn = str(p.get("part_no") or "").strip() or "—"
            pulse.append(
                {
                    "id": f"prod-{pn}-{p.get('date')}",
                    "text": f"Production: {qn} nos of {pn}",
                    "time": p.get("date"),
                }
            )
    except Exception:
        pass

    # 2) Enriched table-specific feeds (as available)
    try:
        rows = fetch_all(
            """
            SELECT
                ct.CT_DATE AS event_time,
                ct.CT_ID AS event_ref,
                ct.CT_QTY AS event_qty,
                COALESCE(c.CO_PARTNO, '') AS part_no,
                COALESCE(c.CO_PARTNAME, '') AS part_name,
                COALESCE(os.OS_NAME, '') AS stage_name
            FROM comp_transaction ct
            LEFT JOIN components c ON c.CO_ID = ct.CT_COMPID
            LEFT JOIN comp_opstages os ON os.OS_ID = ct.CT_OPSTAGE
            ORDER BY ct.CT_DATE DESC, ct.CT_ID DESC
            LIMIT 2
            """
        )
        for idx, r in enumerate(rows):
            stage = str(r.get("stage_name") or "").strip() or "Stage N/A"
            part = str(r.get("part_no") or "").strip()
            part_name = str(r.get("part_name") or "").strip()
            part_txt = part if part else (part_name if part_name else "Unknown part")
            pulse.append(
                {
                    "id": f"comp_transaction-{r.get('event_ref')}-{idx}",
                    "text": f"Component movement | {stage} | {part_txt} | Qty {r.get('event_qty')}",
                    "time": r.get("event_time"),
                }
            )
        if rows:
            enriched_done.add("comp_transaction")
    except Exception:
        pass

    try:
        rows = fetch_all(
            """
            SELECT
                do.SO_NO AS event_ref,
                do.STATUS_ID AS status_id,
                COALESCE(ds.DS_NAME, '') AS status_name,
                do.DISPATCHED_QTY AS event_qty,
                do.DISPATCHED_DATE AS event_time
            FROM dispatch_order do
            LEFT JOIN dispatch_status ds ON ds.DS_ID = do.STATUS_ID
            ORDER BY do.DISPATCHED_DATE DESC, do.DISPATCH_ORDER_ID DESC
            LIMIT 2
            """
        )
        for idx, r in enumerate(rows):
            status = str(r.get("status_name") or "").strip()
            if not status:
                status = f"Status {r.get('status_id')}"
            pulse.append(
                {
                    "id": f"dispatch_order-{r.get('event_ref')}-{idx}",
                    "text": f"Dispatch order | {r.get('event_ref')} | {status} | Qty {r.get('event_qty')}",
                    "time": r.get("event_time"),
                }
            )
        if rows:
            enriched_done.add("dispatch_order")
    except Exception:
        pass

    try:
        rows = fetch_all(
            """
            SELECT
                it.TRANSACTION_DATE AS event_time,
                it.QTY AS event_qty,
                it.TRANSACTION_TYPE_ID AS ttype_id
            FROM inventory_transaction it
            ORDER BY it.TRANSACTION_DATE DESC
            LIMIT 2
            """
        )
        for idx, r in enumerate(rows):
            ttype = str(r.get("ttype_id") or "").strip() or "N/A"
            pulse.append(
                {
                    "id": f"inventory_transaction-{ttype}-{r.get('event_time')}-{idx}",
                    "text": f"Inventory movement | Type {ttype} | Qty {r.get('event_qty')}",
                    "time": r.get("event_time"),
                }
            )
        if rows:
            enriched_done.add("inventory_transaction")
    except Exception:
        pass

    try:
        rows = fetch_all(
            """
            SELECT
                rt.RT_DATE AS event_time,
                rt.RT_ID AS event_ref,
                rt.RT_QTY AS event_qty,
                rt.RT_MOVEMENT AS movement_code,
                rt.RT_MOVEMENTTYPE AS movement_type_id,
                COALESCE(rm.ML_DESCRIPTION, '') AS movement_type_name
            FROM rm_transaction rt
            LEFT JOIN rm_movements rm ON rm.ML_ID = rt.RT_MOVEMENTTYPE
            ORDER BY rt.RT_DATE DESC, rt.RT_ID DESC
            LIMIT 2
            """
        )
        for idx, r in enumerate(rows):
            mv = str(r.get("movement_code") or "").strip().upper()
            mv_txt = "Inward" if mv == "I" else ("Outward" if mv == "O" else (mv or "N/A"))
            mv_type = str(r.get("movement_type_name") or "").strip()
            if not mv_type:
                mv_type = f"Type {r.get('movement_type_id')}"
            pulse.append(
                {
                    "id": f"rm_transaction-{r.get('event_ref')}-{idx}",
                    "text": f"RM movement | {mv_txt} | {mv_type} | Qty {r.get('event_qty')}",
                    "time": r.get("event_time"),
                }
            )
        if rows:
            enriched_done.add("rm_transaction")
    except Exception:
        pass

    # 3) Generic feed builders for remaining tables
    generic_specs = [
        ("comp_transaction", "Component movement", ["CT_Date", "ct_date", "created_at"], ["CT_QTy", "ct_qty", "qty"], ["CT_ID", "ct_id", "CT_CompId", "ct_compid"]),
        ("dispatch_order", "Dispatch order", ["DO_Date", "dispatch_date", "created_at", "updated_at"], ["DO_QTY", "qty", "order_qty"], ["DO_NO", "dispatch_no", "order_no", "SO_NO", "so_no"]),
        ("inventory_transaction", "Inventory movement", ["IT_Date", "trans_date", "transaction_date", "created_at", "updated_at"], ["IT_Qty", "qty", "quantity"], ["IT_ID", "it_id", "tag_id", "TAG_ID"]),
        ("rm_transaction", "RM movement", ["RT_Date", "trans_date", "created_at", "updated_at"], ["RT_Qty", "qty", "quantity"], ["RT_ID", "rt_id", "RT_BatchNo", "rt_batchno"]),
        ("sales_order", "Sales order", ["SO_DATE", "DLV_DATE", "created_at", "updated_at"], ["QTY", "SO_QTY", "order_qty"], ["SO_NO", "PART_NO"]),
        ("tool_life", "Tool update", ["updated_at", "TL_updated_at", "created_at"], ["TL_tool_life", "TL_preventive_maintenance_strokes"], ["TL_tool_number", "TL_tool_id"]),
    ]

    for table, title, date_candidates, qty_candidates, id_candidates in generic_specs:
        try:
            if table in enriched_done:
                continue
            cols = _table_columns(table)
            if not cols:
                continue
            dcol = _pick(cols, date_candidates)
            qcol = _pick(cols, qty_candidates)
            icol = _pick(cols, id_candidates)
            if not dcol and not icol:
                continue

            select_bits = [f"{_qid(dcol)} AS event_time"]
            if dcol:
                select_bits = [f"{_qid(dcol)} AS event_time"]
            else:
                select_bits = ["NULL AS event_time"]
            if qcol:
                select_bits.append(f"{_qid(qcol)} AS event_qty")
            if icol:
                select_bits.append(f"{_qid(icol)} AS event_ref")
            order_col = dcol or icol
            sql = f"SELECT {', '.join(select_bits)} FROM {_qid(table)} ORDER BY {_qid(order_col)} DESC LIMIT 2"
            rows = fetch_all(sql)
            for idx, r in enumerate(rows):
                qty = r.get("event_qty")
                ref = str(r.get("event_ref") or "").strip()
                qty_txt = ""
                if qty is not None and str(qty).strip() != "":
                    qty_txt = f" | Qty {qty}"
                ref_txt = f" | {ref}" if ref else ""
                pulse.append(
                    {
                        "id": f"{table}-{ref or 'x'}-{r.get('event_time')}-{idx}",
                        "text": f"{title}{ref_txt}{qty_txt}",
                        "time": r.get("event_time"),
                    }
                )
        except Exception:
            # Keep pulse resilient even when one source schema differs.
            continue

    # 4) DPR daily snapshot for context
    try:
        today = datetime.now().date().isoformat()
        row = fetch_one(
            "SELECT COUNT(*) AS c FROM dpr_daily_review WHERE review_date = %s",
            (today,),
        )
        c = int(row.get("c") or 0) if row else 0
        pulse.append(
            {
                "id": "dpr-today",
                "text": f"DPR today: {c} line(s) updated",
                "time": today,
            }
        )
    except Exception:
        pass

    pulse.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    items = pulse[:18]
    if cache_seconds > 0:
        with _PULSE_CACHE_LOCK:
            _PULSE_CACHE["ts"] = now
            _PULSE_CACHE["items"] = list(items)
    return items


def get_dpr_qr_storage_dir() -> Path:
    """Directory for DPR machine QR PNGs (`qr-codes/` at project root by default)."""
    configured = str(current_app.config.get("DPR_QR_STORAGE_DIR") or "").strip()
    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured))
        p = Path(expanded)
        if p.is_absolute():
            return p
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(current_app.root_path).parent
        return (base_dir / p).resolve()
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(current_app.root_path).parent
    return (base_dir / "qr-codes").resolve()


def write_dpr_machine_qr_png(path: Union[str, Path], scan_url: str, machine_label: str) -> None:
    """Render QR for scan_url and stamp machine name above (shop-floor print)."""
    try:
        import qrcode
    except ImportError as e:
        raise RuntimeError("Install the qrcode package (see requirements.txt)") from e
    from PIL import Image, ImageDraw, ImageFont

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    qr_img = qrcode.make(scan_url).convert("RGB")
    label = str(machine_label or "").strip() or "Machine"
    pad = 14
    label_h = 46
    canvas = Image.new(
        "RGB",
        (qr_img.width + pad * 2, qr_img.height + label_h + pad * 2),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = max(0, bbox[2] - bbox[0])
    text_x = max(pad, (canvas.width - text_w) // 2)
    draw.text((text_x, pad), label, fill="black", font=font)
    canvas.paste(qr_img, (pad, label_h + pad))
    canvas.save(str(out))


def fetch_dpr_machine_qr_row(machine_id: str) -> Optional[Dict[str, Any]]:
    """Lookup `dpr_machine_qr` (machine_id, qr_token, png_filename). Returns None if missing or table absent."""
    mid = str(machine_id or "").strip()
    if not mid:
        return None
    try:
        row = fetch_one(
            """
            SELECT machine_id, qr_token, png_filename
            FROM dpr_machine_qr
            WHERE machine_id = %s
            """,
            (mid,),
        )
        return row
    except Exception:
        return None


def fetch_dpr_machine_by_qr_token(token: str) -> Optional[Dict[str, Any]]:
    """Resolve stable shop-floor QR token to a machine row."""
    tok = str(token or "").strip()
    if not tok:
        return None
    try:
        row = fetch_one(
            """
            SELECT machine_id, qr_token, png_filename
            FROM dpr_machine_qr
            WHERE qr_token = %s
            """,
            (tok,),
        )
        return row
    except Exception:
        return None


# Synthetic DPR part numbers (not in components) for new-product lines.
_DPR_NPD_PARTS: Tuple[Tuple[str, str], ...] = (
    ("NPD-001", "New Product Development"),
    ("NPD-002", "New Product Development"),
    ("NPD-003", "New Product Development"),
    ("NPD-004", "New Product Development"),
)
# Former NPD-XXX picklist slot (now NPD-004); keep name resolution for existing DPR rows.
_DPR_NPD_LEGACY_PART_NAMES: Dict[str, str] = {
    "NPD-XXX": "New Product Development",
}


def get_dpr_part_options(limit: int = 8000) -> List[Dict[str, str]]:
    """Distinct active components for Part No picklist."""
    sql = """
        SELECT TRIM(co_partNo) AS part_no, MIN(CO_PARTNAME) AS part_name
        FROM components
        WHERE co_activeyn = 'Y'
        GROUP BY TRIM(co_partNo)
        ORDER BY part_no
        LIMIT %s
    """
    rows = fetch_all(sql, (max(1, min(limit, 20000)),))
    out = [
        {
            "part_no": str(r["part_no"] or "").strip(),
            "part_name": str(r["part_name"] or "").strip(),
        }
        for r in rows
        if r.get("part_no")
    ]
    existing = {str(x.get("part_no") or "").strip().lower() for x in out}
    for part_no, part_name in _DPR_NPD_PARTS:
        if part_no.lower() not in existing:
            out.append({"part_no": part_no, "part_name": part_name})
            existing.add(part_no.lower())
    out.sort(key=lambda x: str(x.get("part_no") or "").strip().lower())
    return out


def _dpr_tool_row_for_part(part_no: str) -> Optional[Dict[str, Any]]:
    """Latest active components_tool row for a part."""
    p = str(part_no or "").strip()
    if not p:
        return None
    sql = """
        SELECT
            ct.ct_toolno AS tool_no,
            ct.CT_NO_OF_CAVITY AS cavity,
            ct.ct_rmid AS rm_id,
            mm.MM_RAWMTPARTNO AS rm_code,
            c.CO_PARENTID AS comp_id
        FROM components_tool ct
        INNER JOIN components c ON ct.CT_COMPID = c.CO_ID
        LEFT JOIN materialmaster mm ON mm.MM_ID = ct.ct_rmid
        WHERE ct.ct_activeyn = 'Y'
          AND c.co_activeyn = 'Y'
          AND TRIM(c.co_partNo) = %s
        ORDER BY ct.ct_id DESC
        LIMIT 1
    """
    row = fetch_one(sql, (p,))
    return dict(row) if row else None


def _dpr_rm_available_for_rmid(rm_id: Any) -> Optional[float]:
    """Current accepted RM qty for an RD_RMID."""
    if rm_id is None:
        return None
    try:
        rid = int(rm_id)
    except (TypeError, ValueError):
        return None
    sql = """
        SELECT ROUND(
            COALESCE(SUM(CASE WHEN ri_movement = 'I' THEN RD_acceptedqty ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN ri_movement = 'O' THEN RD_acceptedqty ELSE 0 END), 0),
            2
        ) AS current_acceptedqty
        FROM rm_inwarddetails
        INNER JOIN rm_inwardmaster ON rd_riid = ri_id
        INNER JOIN materialmaster ON RD_RMID = MM_Id
        INNER JOIN materialtypemaster ON MM_mtId = MT_Id
        WHERE RD_RMID = %s
    """
    row = fetch_one(sql, (rid,))
    if not row or row.get("current_acceptedqty") is None:
        return None
    return float(row["current_acceptedqty"])


def _dpr_rm_issued_map(review_date: str) -> Dict[Tuple[int, int], float]:
    """RM issued grouped by (rm_id, comp_id) from rm_inward tables."""
    sql = """
        SELECT
            ROUND(
                COALESCE(SUM(CASE WHEN ri_movement = 'O' THEN RD_acceptedqty ELSE 0 END), 0)
                - COALESCE(SUM(CASE WHEN ri_movement = 'I' THEN RD_acceptedqty ELSE 0 END), 0),
                2
            ) AS issued_qty,
            RD_RMID AS rm_id,
            RD_COMPID AS CO_PARENTID
        FROM rm_inwarddetails
        INNER JOIN rm_inwardmaster ON rd_riid = ri_id
        INNER JOIN materialmaster ON RD_RMID = MM_Id
        INNER JOIN materialtypemaster ON MM_mtId = MT_Id
        WHERE RI_MOVEMENTTYPE = 3
          AND rd_smid = 1
        GROUP BY RD_RMID, RD_COMPID
    """
    rows = fetch_all(sql)
    out: Dict[Tuple[int, int], float] = {}
    for r in rows:
        try:
            rid = int(r.get("rm_id"))
            comp_id = int(r.get("CO_PARENTID"))
            qty = float(r.get("issued_qty") or 0)
        except (TypeError, ValueError):
            continue
        out[(rid, comp_id)] = qty
    return out


def _dpr_strokes_consumed_by_tool() -> Dict[str, float]:
    """Total strokes per tool from production vs cavity."""
    sql = """
        SELECT
            comp.toolNo AS tool_no,
            MAX(comp.componentStrokes) AS total_strokes
        FROM (
            SELECT
                ct.CT_TOOLNO AS toolNo,
                SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
            FROM production_details pd
            INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
            GROUP BY ct.CT_TOOLNO, ct.CT_COMPID
        ) comp
        GROUP BY comp.toolNo
    """
    rows = fetch_all(sql)
    out: Dict[str, float] = {}
    for r in rows:
        key = str(r.get("tool_no") or "").strip()
        if not key:
            continue
        try:
            out[key] = float(r.get("total_strokes") or 0)
        except (TypeError, ValueError):
            continue
    return out


def _dpr_pm_due_by_tool() -> Dict[str, float]:
    """PM Due = PM_next_stroke from latest preventive_maintenance row per tool."""
    sql = """
        SELECT
            pm.PM_tool_number AS tool_no,
            pm.PM_next_stroke AS pm_due
        FROM (
            SELECT pm1.PM_tool_number, pm1.PM_next_stroke
            FROM preventive_maintenance pm1
            INNER JOIN (
                SELECT PM_tool_number, MAX(PM_id) AS maxId
                FROM preventive_maintenance
                GROUP BY PM_tool_number
            ) latest_pm ON latest_pm.maxId = pm1.PM_id
        ) pm
        ORDER BY pm.PM_tool_number
    """
    rows = fetch_all(sql)
    out: Dict[str, float] = {}
    for r in rows:
        key = str(r.get("tool_no") or "").strip()
        if not key:
            continue
        try:
            if r.get("pm_due") is not None:
                out[key] = float(r.get("pm_due"))
        except (TypeError, ValueError):
            continue
    return out


def _dpr_rm_coverage_by_part_map() -> Dict[str, float]:
    """RM coverage nos by part from reports allocation output."""
    rows = _get_enriched_rows_for_reports()
    _apply_rm_allocation_metrics(rows)
    out: Dict[str, float] = {}
    for row in rows:
        key = str(row.get("part_no") or "").strip().lower()
        if not key:
            continue
        try:
            out[key] = float(row.get("qty_can_be_produced_nos") or 0)
        except (TypeError, ValueError):
            continue
    return out


def _dpr_rm_allocated_by_part_map() -> Dict[str, float]:
    """balance_allocated_rm_qty (kg) by part from reports allocation output."""
    rows = _get_enriched_rows_for_reports()
    _apply_rm_allocation_metrics(rows)
    out: Dict[str, float] = {}
    for row in rows:
        key = str(row.get("part_no") or "").strip().lower()
        if not key:
            continue
        try:
            out[key] = float(row.get("balance_allocated_rm_qty") or 0)
        except (TypeError, ValueError):
            continue
    return out


def _dpr_derived_fields(
    part_no: str,
    planned_qty: float,
    review_date: Optional[str] = None,
    rm_issued_by_rmid: Optional[Dict[Tuple[int, int], float]] = None,
    strokes_by_tool: Optional[Dict[str, float]] = None,
    pm_due_by_tool: Optional[Dict[str, float]] = None,
    rm_coverage_by_part: Optional[Dict[str, float]] = None,
    rm_allocated_by_part: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Tool no, RM values, strokes consumed and PM due for a part + date."""
    tool = _dpr_tool_row_for_part(part_no)
    tool_no = None
    strokes = None
    pm_due = None
    rm_avail = None
    rm_issued = None
    rm_coverage_nos = None
    rm_allocated = None
    rm_code = None
    coverage_map = rm_coverage_by_part if rm_coverage_by_part is not None else _dpr_rm_coverage_by_part_map()
    alloc_map = rm_allocated_by_part if rm_allocated_by_part is not None else _dpr_rm_allocated_by_part_map()
    part_key = str(part_no or "").strip().lower()
    if part_key:
        rm_coverage_nos = coverage_map.get(part_key)
        rm_allocated = alloc_map.get(part_key)
    if tool:
        tool_no = tool.get("tool_no")
        if tool_no is not None:
            tool_no = str(tool_no).strip() or None
        rm_code = str(tool.get("rm_code") or "").strip() or None
        rm_id_raw = tool.get("rm_id")
        comp_id_raw = tool.get("comp_id")
        rm_avail = _dpr_rm_available_for_rmid(rm_id_raw)
        try:
            rm_id = int(rm_id_raw) if rm_id_raw is not None else None
        except (TypeError, ValueError):
            rm_id = None
        try:
            comp_id = int(comp_id_raw) if comp_id_raw is not None else None
        except (TypeError, ValueError):
            comp_id = None
        if rm_id is not None:
            rm_map = rm_issued_by_rmid if rm_issued_by_rmid is not None else (
                _dpr_rm_issued_map(review_date or "") if review_date else {}
            )
            if comp_id is not None:
                rm_issued = rm_map.get((rm_id, comp_id))
            if rm_issued is None:
                vals = [v for (rid, _cid), v in rm_map.items() if rid == rm_id]
                rm_issued = sum(vals) if vals else None

        if tool_no:
            s_map = strokes_by_tool if strokes_by_tool is not None else _dpr_strokes_consumed_by_tool()
            p_map = pm_due_by_tool if pm_due_by_tool is not None else _dpr_pm_due_by_tool()
            if tool_no in s_map:
                strokes = s_map[tool_no]
            else:
                for k, v in s_map.items():
                    if k.strip().lower() == tool_no.lower():
                        strokes = v
                        break
            if tool_no in p_map:
                pm_due = p_map[tool_no]
            else:
                for k, v in p_map.items():
                    if k.strip().lower() == tool_no.lower():
                        pm_due = v
                        break

    return {
        "toolNo": tool_no,
        "rmCode": rm_code,
        "strokesConsumed": strokes,
        "rmIssued": rm_issued,
        "rmAvailable": rm_avail,
        "rmCoverageNos": rm_coverage_nos,
        "rmAllocated": rm_allocated,
        "pmDue": pm_due,
    }


def get_dpr_derived_preview(
    part_no: str,
    planned_qty: Optional[float] = None,
    review_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Tool, RM, strokes and PM due preview for part/date."""
    p = str(part_no or "").strip()
    pq = float(planned_qty or 0)
    d = str(review_date or "").strip() or None
    return _dpr_derived_fields(p, pq, d)


def _dpr_part_name_map(part_nos: Sequence[str]) -> Dict[str, str]:
    if not part_nos:
        return {}
    uniq = sorted({str(p).strip() for p in part_nos if str(p).strip()})
    if not uniq:
        return {}
    placeholders = ",".join(["%s"] * len(uniq))
    sql = f"""
        SELECT TRIM(co_partNo) AS part_no, MIN(CO_PARTNAME) AS part_name
        FROM components
        WHERE co_activeyn = 'Y' AND TRIM(co_partNo) IN ({placeholders})
        GROUP BY TRIM(co_partNo)
    """
    rows = fetch_all(sql, tuple(uniq))
    out = {str(r["part_no"]).strip(): str(r["part_name"] or "").strip() for r in rows}
    for part_no, part_name in _DPR_NPD_PARTS:
        out.setdefault(part_no, part_name)
    for part_no, part_name in _DPR_NPD_LEGACY_PART_NAMES.items():
        out.setdefault(part_no, part_name)
    return out


def _dpr_produced_percent(planned: float, produced: Optional[float]) -> Optional[float]:
    """100 * produced / planned when planned > 0."""
    try:
        p = float(planned or 0)
    except (TypeError, ValueError):
        p = 0.0
    if p <= 0:
        return None
    if produced is None:
        return None
    try:
        q = float(produced)
    except (TypeError, ValueError):
        return None
    return round(100.0 * q / p, 2)


def _dpr_iso_datetime(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).strip()


def _dpr_row_created_sort_key(created_at: Any, row_id: Any) -> Tuple[int, int]:
    """Sort key for DPR lines: earliest created first; stable tie-break by id."""
    ts = 0
    if created_at is not None:
        if isinstance(created_at, datetime):
            ts = int(created_at.timestamp())
        elif hasattr(created_at, "timestamp"):
            ts = int(created_at.timestamp())
        else:
            raw = str(created_at).strip().replace("Z", "+00:00")
            if raw:
                try:
                    ts = int(datetime.fromisoformat(raw[:26]).timestamp())
                except (TypeError, ValueError):
                    ts = 0
    try:
        rid = int(row_id or 0)
    except (TypeError, ValueError):
        rid = 0
    if ts <= 0 and rid <= 0:
        return (2_147_483_647, 0)
    if ts <= 0:
        return (rid, rid)
    return (ts, rid)


def list_dpr_rows(review_date: str) -> List[Dict[str, Any]]:
    """Load DPR rows for a date; tool/strokes/RM derived from part + planned qty."""
    sql = """
        SELECT id, review_date, machine_id, part_no, planned_qty, produced_qty, remarks,
               created_by, updated_by, created_at, updated_at
        FROM dpr_daily_review
        WHERE review_date = %s
    """
    rows = fetch_all(sql, (review_date,))
    part_nos = [str(r["part_no"]) for r in rows]
    names = _dpr_part_name_map(part_nos)
    machines = {m["id"]: m["label"] for m in get_dpr_machine_options()}
    rm_issued_by_rmid = _dpr_rm_issued_map(review_date)
    strokes_by_tool = _dpr_strokes_consumed_by_tool()
    pm_due_by_tool = _dpr_pm_due_by_tool()
    rm_coverage_by_part = _dpr_rm_coverage_by_part_map()
    rm_allocated_by_part = _dpr_rm_allocated_by_part_map()
    enriched: List[Dict[str, Any]] = []
    for r in rows:
        pid = str(r.get("machine_id") or "")
        pno = str(r.get("part_no") or "").strip()
        rd = r.get("review_date")
        if hasattr(rd, "isoformat"):
            review_date_str = rd.isoformat()
        else:
            review_date_str = str(rd) if rd is not None else ""
        pq = float(r["planned_qty"] or 0)
        derived = _dpr_derived_fields(
            pno,
            pq,
            review_date=review_date,
            rm_issued_by_rmid=rm_issued_by_rmid,
            strokes_by_tool=strokes_by_tool,
            pm_due_by_tool=pm_due_by_tool,
            rm_coverage_by_part=rm_coverage_by_part,
            rm_allocated_by_part=rm_allocated_by_part,
        )
        produced_raw = r.get("produced_qty")
        produced_val = None if produced_raw is None else float(produced_raw)
        pct = _dpr_produced_percent(pq, produced_val)
        created_raw = r.get("created_at")
        enriched.append(
            {
                "id": r["id"],
                "reviewDate": review_date_str,
                "machineId": pid,
                "machineLabel": machines.get(pid, pid),
                "partNo": pno,
                "partName": names.get(pno, ""),
                "plannedQty": pq,
                "producedQty": produced_val,
                "producedPct": pct,
                "rmIssued": derived.get("rmIssued"),
                "rmAvailable": derived.get("rmAvailable"),
                "rmCode": derived.get("rmCode"),
                "rmCoverageNos": derived.get("rmCoverageNos"),
                "rmAllocated": derived.get("rmAllocated"),
                "toolNo": derived.get("toolNo"),
                "strokesConsumed": derived.get("strokesConsumed"),
                "pmDue": derived.get("pmDue"),
                "remarks": r.get("remarks") or "",
                "createdAt": _dpr_iso_datetime(created_raw),
            }
        )
    enriched.sort(
        key=lambda r: (
            str(r.get("machineLabel") or "").strip().lower(),
            str(r.get("machineId") or "").strip().lower(),
            _dpr_row_created_sort_key(r.get("createdAt"), r.get("id")),
        )
    )
    return enriched


def get_machine_dpr_payload(qr_token: str, review_date: str) -> Optional[Dict[str, Any]]:
    """Shop-floor Machine DPR JSON: rows for one machine on a date (from QR token)."""
    row = fetch_dpr_machine_by_qr_token(qr_token)
    if not row:
        return None
    mid = str(row.get("machine_id") or "").strip()
    machines = {m["id"]: m["label"] for m in get_dpr_machine_options()}
    label = machines.get(mid, mid)
    all_rows = list_dpr_rows(review_date)
    machine_rows = [r for r in all_rows if str(r.get("machineId") or "") == mid]
    machine_rows.sort(
        key=lambda r: _dpr_row_created_sort_key(r.get("createdAt"), r.get("id"))
    )
    out_rows: List[Dict[str, Any]] = []
    for r in machine_rows:
        out_rows.append(
            {
                "id": r["id"],
                "partName": r.get("partName") or "",
                "partNo": r.get("partNo") or "",
                "plannedQty": r.get("plannedQty"),
                "producedQty": r.get("producedQty"),
                "rmCode": r.get("rmCode"),
                "rmIssued": r.get("rmIssued"),
                "toolNo": r.get("toolNo"),
                "remarks": r.get("remarks") or "",
            }
        )
    return {
        "date": review_date,
        "machineId": mid,
        "machineLabel": label,
        "rows": out_rows,
    }


def upsert_dpr_row(
    review_date: str,
    machine_id: str,
    part_no: str,
    planned_qty: float,
    produced_qty: Optional[float],
    remarks: Optional[str],
    updated_by: Optional[str],
    row_id: Optional[int] = None,
) -> int:
    """Insert or update a DPR row. Returns row id."""
    machine_id = str(machine_id or "").strip()
    part_no = str(part_no or "").strip()
    if not machine_id or not part_no:
        raise ValueError("machine_id and part_no are required")

    if row_id:
        sql = """
            UPDATE dpr_daily_review
            SET review_date = %s, machine_id = %s, part_no = %s,
                planned_qty = %s, produced_qty = %s, remarks = %s, updated_by = %s
            WHERE id = %s
        """
        execute(
            sql,
            (review_date, machine_id, part_no, planned_qty, produced_qty, remarks or "", updated_by, row_id),
        )
        one = fetch_one("SELECT id FROM dpr_daily_review WHERE id = %s", (row_id,))
        if not one:
            raise ValueError("Row not found")
        return int(row_id)

    sql = """
        INSERT INTO dpr_daily_review
            (review_date, machine_id, part_no, planned_qty, produced_qty, remarks, created_by, updated_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            planned_qty = VALUES(planned_qty),
            produced_qty = VALUES(produced_qty),
            remarks = VALUES(remarks),
            updated_by = VALUES(updated_by)
    """
    execute(
        sql,
        (
            review_date,
            machine_id,
            part_no,
            planned_qty,
            produced_qty,
            remarks or "",
            updated_by,
            updated_by,
        ),
    )
    found = fetch_one(
        """
        SELECT id FROM dpr_daily_review
        WHERE review_date = %s AND machine_id = %s AND part_no = %s
        LIMIT 1
        """,
        (review_date, machine_id, part_no),
    )
    if not found:
        raise RuntimeError("Failed to resolve row id after save")
    return int(found["id"])


def delete_dpr_row(row_id: int) -> bool:
    """Delete a DPR row by id. Returns True if a row was removed."""
    sql = "DELETE FROM dpr_daily_review WHERE id = %s"
    n = execute(sql, (row_id,))
    return n > 0


def get_dpr_summary(review_date: str) -> Dict[str, Any]:
    """Aggregates for the selected day and its calendar month."""
    from datetime import date
    from calendar import monthrange

    d = str(review_date or "").strip()
    if not d:
        raise ValueError("review_date is required")
    dt = date.fromisoformat(d)
    y, m = dt.year, dt.month
    last_mday = monthrange(y, m)[1]
    month_start = f"{y:04d}-{m:02d}-01"
    month_end = f"{y:04d}-{m:02d}-{last_mday:02d}"

    sql_day = """
        SELECT
            COALESCE(SUM(planned_qty), 0) AS planned,
            COALESCE(SUM(IFNULL(produced_qty, 0)), 0) AS produced
        FROM dpr_daily_review
        WHERE review_date = %s
    """
    sql_last_day = """
        SELECT
            COALESCE(SUM(planned_qty), 0) AS planned,
            COALESCE(SUM(IFNULL(produced_qty, 0)), 0) AS produced
        FROM dpr_daily_review
        WHERE review_date = (
            SELECT MAX(review_date) FROM dpr_daily_review WHERE review_date < %s
        )
    """
    sql_planned_machines = """
        SELECT COUNT(DISTINCT machine_id) AS planned_machines
        FROM dpr_daily_review
        WHERE review_date = %s
          AND COALESCE(planned_qty, 0) > 0
    """

    day_row = fetch_one(sql_day, (d,))
    last_day_row = fetch_one(sql_last_day, (d,))
    planned_machines_row = fetch_one(sql_planned_machines, (d,))

    def pack(row):
        if not row:
            return {"planned": 0.0, "produced": 0.0, "variance": 0.0}
        pl = float(row.get("planned") or 0)
        pr = float(row.get("produced") or 0)
        return {"planned": pl, "produced": pr, "variance": round(pr - pl, 4)}

    daily = pack(day_row)

    # Monthly: planned from enriched reports, produced from production_details
    report_rows = _get_enriched_rows_for_reports()
    monthly_planned = 0.0
    for row in report_rows:
        monthly_planned += max(0.0, float(row.get("production_pending") or 0))

    try:
        sql_monthly_produced = """
            SELECT COALESCE(SUM(pd.PD_PRODQTY), 0) AS produced
            FROM production_details pd
            WHERE (pd.PD_TOOLID, pd.pd_psid) IN (
                SELECT t.ps_toolid, t.first_ps_id
                FROM (
                    SELECT
                        sp.PS_TOOLID AS ps_toolid,
                        FIRST_VALUE(sp.PS_ID) OVER (
                            PARTITION BY sp.PS_TOOLID
                            ORDER BY sp.ps_date ASC
                        ) AS first_ps_id
                    FROM scheduled_production sp
                    WHERE sp.ps_smid = (
                        SELECT sm_id
                        FROM schedule_master
                        WHERE sm_month = %s
                          AND sm_year = %s
                        LIMIT 1
                    )
                ) t
                GROUP BY t.ps_toolid, t.first_ps_id
            )
        """
        monthly_produced_row = fetch_one(sql_monthly_produced, (m, y))
        monthly_produced = float((monthly_produced_row or {}).get("produced") or 0)
    except Exception:
        monthly_produced = 0.0

    monthly = {
        "planned": monthly_planned,
        "produced": monthly_produced,
        "variance": round(monthly_produced - monthly_planned, 4),
    }

    daily_pct = round((100.0 * daily["produced"] / daily["planned"]), 2) if daily["planned"] > 0 else None
    monthly_pct = (
        round((100.0 * monthly["produced"] / monthly["planned"]), 2)
        if monthly["planned"] > 0
        else None
    )
    total_machines = len(get_dpr_machine_options())
    planned_machines = int((planned_machines_row or {}).get("planned_machines") or 0)
    last_day_planned = float((last_day_row or {}).get("planned") or 0)
    last_day_produced = float((last_day_row or {}).get("produced") or 0)
    last_day_achievement_pct = (
        round((100.0 * last_day_produced / last_day_planned), 2) if last_day_planned > 0 else None
    )

    snap_row = fetch_one(
        """
        SELECT operator_planned, operator_actual, bottleneck_pending
        FROM dpr_daily_snapshot
        WHERE review_date = %s
        LIMIT 1
        """,
        (d,),
    ) or {}

    return {
        "date": d,
        "monthStart": month_start,
        "monthEnd": month_end,
        "dailyPlanned": daily["planned"],
        "dailyProduced": daily["produced"],
        "dailyVariance": daily["variance"],
        "monthlyPlanned": monthly["planned"],
        "monthlyProduced": monthly["produced"],
        "monthlyVariance": monthly["variance"],
        "dailyProducedPct": daily_pct,
        "monthlyProducedPct": monthly_pct,
        "totalMachines": total_machines,
        "plannedMachines": planned_machines,
        "lastDayPlanned": last_day_planned,
        "lastDayProduced": last_day_produced,
        "lastDayAchievementPct": last_day_achievement_pct,
        "operatorPlanned": snap_row.get("operator_planned"),
        "operatorActual": snap_row.get("operator_actual"),
        "bottleneckPending": (snap_row.get("bottleneck_pending") or "") or "",
    }


# ═══════════════════════════════════════════════════════════════════════
# DPR Version Tracking & Snapshot (ported from Original Dashboard)
# ═══════════════════════════════════════════════════════════════════════

def get_dpr_version(review_date: str) -> str:
    """Lightweight version token for a DPR date, used for polling-based realtime.

    Combines:
    - max(updated_at/created_at) from dpr_daily_review for that date
    - row count
    - snapshot values (operators + bottlenecks)
    """
    import hashlib

    d = str(review_date or "").strip()
    if not d:
        raise ValueError("review_date is required")

    row_meta = fetch_one(
        """
        SELECT
            COALESCE(UNIX_TIMESTAMP(MAX(COALESCE(updated_at, created_at))), 0) AS row_ts,
            COUNT(*) AS row_count
        FROM dpr_daily_review
        WHERE review_date = %s
        """,
        (d,),
    ) or {}
    row_ts = int(row_meta.get("row_ts") or 0)
    row_count = int(row_meta.get("row_count") or 0)

    snap_row = fetch_one(
        """
        SELECT operator_planned, operator_actual, bottleneck_pending
        FROM dpr_daily_snapshot
        WHERE review_date = %s
        LIMIT 1
        """,
        (d,),
    ) or {}
    op_planned = snap_row.get("operator_planned")
    op_actual = snap_row.get("operator_actual")
    bottleneck = str(snap_row.get("bottleneck_pending") or "")
    bottleneck_hash = hashlib.md5(bottleneck.encode("utf-8")).hexdigest()[:8]

    parts = [
        str(row_ts),
        str(row_count),
        "op",
        "n" if op_planned is None else str(op_planned),
        "oa",
        "n" if op_actual is None else str(op_actual),
        "b",
        bottleneck_hash,
    ]
    return "|".join(parts)


def upsert_dpr_snapshot(
    review_date: str,
    operator_planned: Optional[float],
    operator_actual: Optional[float],
    bottleneck_pending: Optional[str],
    updated_by: Optional[str],
) -> None:
    """Insert/update daily DPR board values (operator planned/actual, bottleneck)."""
    execute(
        """
        INSERT INTO dpr_daily_snapshot
            (review_date, operator_planned, operator_actual, bottleneck_pending, updated_by)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            operator_planned = VALUES(operator_planned),
            operator_actual = VALUES(operator_actual),
            bottleneck_pending = VALUES(bottleneck_pending),
            updated_by = VALUES(updated_by)
        """,
        (
            review_date,
            operator_planned,
            operator_actual,
            (bottleneck_pending or "").strip(),
            updated_by,
        ),
    )

