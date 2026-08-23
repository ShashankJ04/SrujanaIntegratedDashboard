"""Ensure overview-linked reports (and drilldown children) exist in the runtime store."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from . import reports_store

logger = logging.getLogger(__name__)

# Reports linked directly from hub_overview.html and related KPI modules.
# Pinned Reports catalog — Component Stock interactive viewer (same widget as Overview).
COMPONENT_STOCK_REPORT_ID = "e6f7a8b9-0c1d-4e2f-9a3b-4c5d6e7f8a9b"
COMPONENT_STOCK_GROUP_NAME = "Component Stock"

OVERVIEW_LINKED_REPORT_IDS: tuple[str, ...] = (
    "88a9ed8d-8131-44cb-8fef-fc2782449986",  # Tool BreakDowns
    "5749a7ed-e4be-4b41-a73b-78bd416f46b2",  # Distinct Component Details - With Tools
    "ed95ec7b-1c11-4e58-8adb-524421ea224c",  # Distinct Tools with PartNos
    "3b289936-891a-4770-b669-b8b724672431",  # Distinct Customers
    "51a29798-a36d-4933-bbfe-05e4097ba83d",  # Distinct Raw Materials
    "97e39414-c6d7-4392-aa6f-1972c41cfc1e",  # BOM Dispatch Pivot
    "44f78950-7e3e-46f2-a278-ba88e0c7d8c9",  # BOM Dispatch Details
)


def _drilldown_target_ids(report: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for item in report.get("drilldowns") or []:
        if not isinstance(item, dict):
            continue
        target_id = str(item.get("targetReportId") or "").strip()
        if target_id:
            out.append(target_id)
    return out


def _collect_required_report_ids(
    root_ids: List[str],
    catalog_by_id: Dict[str, Dict[str, Any]],
) -> Set[str]:
    needed: Set[str] = set()
    stack = list(root_ids)
    while stack:
        rid = stack.pop()
        if rid in needed:
            continue
        needed.add(rid)
        report = catalog_by_id.get(rid)
        if not report:
            continue
        for child_id in _drilldown_target_ids(report):
            if child_id not in needed:
                stack.append(child_id)
    return needed


def _topological_insert_order(
    report_ids: Set[str],
    catalog_by_id: Dict[str, Dict[str, Any]],
) -> List[str]:
    ordered: List[str] = []
    visiting: Set[str] = set()
    done: Set[str] = set()

    def visit(rid: str) -> None:
        if rid in done:
            return
        if rid in visiting:
            return
        visiting.add(rid)
        report = catalog_by_id.get(rid)
        if report:
            for child_id in _drilldown_target_ids(report):
                if child_id in report_ids:
                    visit(child_id)
        visiting.remove(rid)
        done.add(rid)
        ordered.append(rid)

    for rid in sorted(report_ids):
        visit(rid)
    return ordered


def ensure_overview_reports() -> Dict[str, Any]:
    """Create missing overview-linked reports from the immutable seed file."""
    seed = reports_store.load_overview_reports_seed()
    if not (seed.get("reports") or []):
        seed_path = reports_store.overview_reports_seed_path()
        logger.error(
            "Overview report bootstrap: no seed data (expected at %s)",
            seed_path,
        )
        return {
            "createdGroups": [],
            "createdReports": [],
            "missingFromCatalog": list(OVERVIEW_LINKED_REPORT_IDS),
            "seedPath": seed_path,
        }

    catalog_reports = seed.get("reports") or []
    catalog_groups = {
        str(g.get("id")): g
        for g in (seed.get("groups") or [])
        if isinstance(g, dict) and g.get("id")
    }
    catalog_by_id = {
        str(r.get("id")): r
        for r in catalog_reports
        if isinstance(r, dict) and r.get("id")
    }

    required_ids = _collect_required_report_ids(
        list(OVERVIEW_LINKED_REPORT_IDS),
        catalog_by_id,
    )
    missing_from_catalog = sorted(
        rid for rid in required_ids if rid not in catalog_by_id
    )
    if missing_from_catalog:
        logger.warning(
            "Overview report bootstrap: seed missing report ids: %s",
            ", ".join(missing_from_catalog),
        )

    runtime_reports = reports_store.get_reports()
    report_by_id = {
        str(r.get("id")): r
        for r in runtime_reports
        if isinstance(r, dict) and r.get("id")
    }

    created_groups: List[str] = []
    created_reports: List[str] = []
    insert_order = _topological_insert_order(
        {rid for rid in required_ids if rid in catalog_by_id},
        catalog_by_id,
    )

    for rid in insert_order:
        if rid in report_by_id:
            continue
        catalog_report = catalog_by_id[rid]
        group_id = str(catalog_report.get("groupId") or "").strip()
        group = catalog_groups.get(group_id)
        if group and reports_store.ensure_group_by_id(group_id, str(group.get("name") or "")):
            created_groups.append(group_id)

        try:
            if reports_store.upsert_catalog_report(catalog_report, report_by_id):
                created_reports.append(rid)
                logger.info(
                    "Overview report bootstrap: created report %s (%s)",
                    rid,
                    catalog_report.get("name"),
                )
        except Exception as exc:
            logger.warning(
                "Overview report bootstrap: failed to create report %s: %s",
                rid,
                exc,
            )

    return {
        "createdGroups": created_groups,
        "createdReports": created_reports,
        "missingFromCatalog": missing_from_catalog,
        "seedPath": reports_store.overview_reports_seed_path(),
    }


def ensure_component_stock_report() -> Dict[str, Any]:
    """Insert Component Stock Sections report into the existing Component Stock group."""
    group_id = reports_store.find_group_id_by_name(COMPONENT_STOCK_GROUP_NAME)
    if not group_id:
        logger.warning(
            "Component Stock report bootstrap: group %r not found — skipping",
            COMPONENT_STOCK_GROUP_NAME,
        )
        return {
            "createdReport": False,
            "groupId": "",
            "reportId": COMPONENT_STOCK_REPORT_ID,
            "skipped": True,
        }

    catalog_report = {
        "id": COMPONENT_STOCK_REPORT_ID,
        "groupId": group_id,
        "name": "Component Stock Sections",
        "queryTemplate": "",
        "handler": "component_stock",
        "variables": [],
        "pinned": True,
        "drilldowns": [],
    }
    runtime_reports = reports_store.get_reports()
    report_by_id = {
        str(r.get("id")): r
        for r in runtime_reports
        if isinstance(r, dict) and r.get("id")
    }
    created_report = False
    try:
        created_report = reports_store.upsert_catalog_report(
            catalog_report,
            report_by_id,
        )
        if created_report:
            logger.info(
                "Component Stock report bootstrap: created report %s in group %s",
                COMPONENT_STOCK_REPORT_ID,
                group_id,
            )
    except Exception as exc:
        logger.warning(
            "Component Stock report bootstrap failed: %s",
            exc,
        )
    return {
        "createdReport": created_report,
        "groupId": group_id,
        "reportId": COMPONENT_STOCK_REPORT_ID,
        "skipped": False,
    }
