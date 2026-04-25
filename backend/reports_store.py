"""Reports store — manages report groups and definitions in a JSON file.

Port of dashboards/backend/src/db/reportsStore.ts.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _store_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "reports.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_store() -> None:
    path = _store_path()
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"groups": [], "reports": []}, f, indent=2)


def _read_store() -> Dict[str, Any]:
    _ensure_store()
    with open(_store_path(), "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return {"groups": [], "reports": []}
        parsed = json.loads(content)
    reports = _normalize_reports(parsed.get("reports") or [])
    return {
        "groups": parsed.get("groups") or [],
        "reports": reports,
    }


def _write_store(data: Dict[str, Any]) -> None:
    _ensure_store()
    with open(_store_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _extract_variables(query_template: str) -> List[str]:
    found: List[str] = []
    seen = set()
    for m in re.finditer(r"\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}", query_template):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            found.append(name)
    return found


def _is_safe_drilldown_column_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_ .()/%-]+", str(name or "")))


def _normalize_reports(reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    report_by_id = {
        str(r.get("id")): r
        for r in reports
        if isinstance(r, dict) and isinstance(r.get("id"), str)
    }
    normalized: List[Dict[str, Any]] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        next_report = dict(report)
        next_report["pinned"] = bool(report.get("pinned", False))
        drilldowns = _normalize_drilldowns(
            report,
            report_by_id,
            source_report_vars=report.get("variables") or [],
        )
        if drilldowns:
            next_report["drilldowns"] = drilldowns
        else:
            next_report.pop("drilldowns", None)
        normalized.append(next_report)
    return normalized


def _normalize_source_spec(
    source: Any,
    source_report_vars: List[str],
) -> Optional[Dict[str, str]]:
    # Backward compatible format: "Part No" => column source
    if isinstance(source, str):
        col = source.strip()
        if not col or not _is_safe_drilldown_column_name(col):
            return None
        return {"type": "column", "value": col}

    if not isinstance(source, dict):
        return None

    source_type = str(source.get("type", "")).strip().lower()
    source_value = str(source.get("value", "")).strip()
    if not source_type or not source_value:
        return None

    if source_type == "column":
        if not _is_safe_drilldown_column_name(source_value):
            return None
        return {"type": "column", "value": source_value}

    if source_type == "parentvariable":
        if source_value not in set(source_report_vars or []):
            return None
        return {"type": "parentVariable", "value": source_value}

    return None


def _normalize_drilldowns(
    report: Dict[str, Any],
    report_by_id: Dict[str, Dict[str, Any]],
    source_report_vars: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    raw = report.get("drilldowns")
    if not isinstance(raw, list):
        return []

    out: List[Dict[str, Any]] = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        column = str(item.get("column", "")).strip()
        target_id = str(item.get("targetReportId", "")).strip()
        mapping = item.get("variables")
        if not column or not target_id or not isinstance(mapping, dict):
            continue
        if not _is_safe_drilldown_column_name(column):
            continue
        target = report_by_id.get(target_id)
        if not target:
            continue
        target_vars = set(target.get("variables") or [])
        normalized_map: Dict[str, Dict[str, str]] = {}
        src_vars = source_report_vars or []
        for target_var, source_spec in mapping.items():
            t = str(target_var).strip()
            if not t:
                continue
            if t not in target_vars:
                continue
            normalized_source = _normalize_source_spec(source_spec, src_vars)
            if not normalized_source:
                continue
            normalized_map[t] = normalized_source
        if not normalized_map:
            continue
        dedupe_key = (column.lower(), target_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        out.append({
            "column": column,
            "targetReportId": target_id,
            "variables": normalized_map,
        })
    return out


def _normalize_drilldowns_from_input(
    drilldowns: Any,
    report_by_id: Dict[str, Dict[str, Any]],
    source_report_vars: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(drilldowns, list):
        return []
    return _normalize_drilldowns(
        {"drilldowns": drilldowns},
        report_by_id,
        source_report_vars=source_report_vars or [],
    )


def _validate_and_normalize_drilldowns_from_input(
    drilldowns: Any,
    report_by_id: Dict[str, Dict[str, Any]],
    source_report_vars: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Strict validator for user-supplied drilldowns.

    Rules:
    1) A hyperlink column can link to only one child report.
    2) If child report has multiple inputs, mapping must include ALL child inputs.
    """
    if drilldowns is None:
        return []
    if not isinstance(drilldowns, list):
        raise ValueError("drilldowns must be a list")

    src_vars = list(source_report_vars or [])
    src_var_set = set(src_vars)
    by_col_target: Dict[Tuple[str, str], Dict[str, Any]] = {}
    column_target: Dict[str, str] = {}

    for idx, item in enumerate(drilldowns):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid drilldown rule at index {idx}")

        column = str(item.get("column", "")).strip()
        target_id = str(item.get("targetReportId", "")).strip()
        mapping = item.get("variables")

        if not column:
            raise ValueError(f"Drilldown rule {idx + 1}: column is required")
        if not _is_safe_drilldown_column_name(column):
            raise ValueError(f"Drilldown rule {idx + 1}: invalid column name")
        if not target_id:
            raise ValueError(f"Drilldown rule {idx + 1}: targetReportId is required")
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError(f"Drilldown rule {idx + 1}: variables mapping is required")

        # A hyperlink column can link to exactly one child report.
        col_key = column.lower()
        existing_target = column_target.get(col_key)
        if existing_target and existing_target != target_id:
            raise ValueError(
                f'Drilldown column "{column}" cannot link to multiple child reports'
            )
        column_target[col_key] = target_id

        target = report_by_id.get(target_id)
        if not target:
            raise ValueError(f"Drilldown rule {idx + 1}: target report not found")
        target_vars = list(target.get("variables") or [])
        target_var_set = set(target_vars)

        normalized_map: Dict[str, Dict[str, str]] = {}
        for child_var, source_spec in mapping.items():
            t = str(child_var).strip()
            if not t:
                raise ValueError(f"Drilldown rule {idx + 1}: child variable is required")
            if t not in target_var_set:
                raise ValueError(
                    f'Drilldown rule {idx + 1}: "{t}" is not an input of child report'
                )
            normalized_source = _normalize_source_spec(source_spec, src_vars)
            if not normalized_source:
                raise ValueError(
                    f'Drilldown rule {idx + 1}: invalid source mapping for child input "{t}"'
                )
            normalized_map[t] = normalized_source

        # If the child report has multiple inputs, all must be mapped.
        if len(target_vars) > 1:
            missing = [v for v in target_vars if v not in normalized_map]
            if missing:
                raise ValueError(
                    f'Drilldown rule {idx + 1}: child report requires all inputs; missing {", ".join(missing)}'
                )

        # Consolidate duplicate rules for same column+target by merging variable mappings.
        key = (col_key, target_id)
        if key not in by_col_target:
            by_col_target[key] = {
                "column": column,
                "targetReportId": target_id,
                "variables": {},
            }
        existing_map = by_col_target[key]["variables"]
        for k, v in normalized_map.items():
            existing_map[k] = v

    # Re-check merged mappings after consolidation.
    out = list(by_col_target.values())
    for item in out:
        target = report_by_id.get(str(item.get("targetReportId", "")))
        if not target:
            continue
        target_vars = list(target.get("variables") or [])
        if len(target_vars) > 1:
            missing = [v for v in target_vars if v not in item["variables"]]
            if missing:
                raise ValueError(
                    f'Drilldown column "{item["column"]}" mapping is incomplete; missing {", ".join(missing)}'
                )
        # Ensure parentVariable mappings still refer to this report's variables.
        for _, src in item["variables"].items():
            if src.get("type") == "parentVariable" and src.get("value") not in src_var_set:
                raise ValueError("Invalid parent variable mapping in drilldown")

    return out


def assert_read_only_query(query_template: str) -> None:
    cleaned = query_template.strip().lstrip("(").lower()
    if not cleaned.startswith("select"):
        raise ValueError("Only read-only SELECT queries are allowed")


def _sanitize_pymysql_percent(sql: str) -> str:
    """PyMySQL treats % in SQL as bind markers. Literal % (e.g. DATE_FORMAT '%%d-%%m-%%Y') must be doubled.

    Leaves %s placeholders intact; all other % become %%.
    """
    out: List[str] = []
    i = 0
    for m in re.finditer(r"%s", sql):
        out.append(sql[i : m.start()].replace("%", "%%"))
        out.append("%s")
        i = m.end()
    out.append(sql[i:].replace("%", "%%"))
    return "".join(out)


def _coerce_variable_value(var_name: str, raw: Any) -> Any:
    """Coerce JSON/form string values to int for MONTH/YEAR/DAY-style parameters."""
    if raw is None:
        raise ValueError(f"Missing value for variable {{{var_name}}}")
    s = str(raw).strip()
    if s == "":
        raise ValueError(f"Missing value for variable {{{var_name}}}")
    u = var_name.upper()

    def _parse_int() -> int:
        try:
            return int(s, 10) if "." not in s else int(float(s))
        except ValueError as e:
            raise ValueError(f"Invalid integer for {{{var_name}}}") from e

    if u == "MONTH" or u.endswith("_MONTH"):
        m = _parse_int()
        if m < 1 or m > 12:
            raise ValueError(f"Month must be 1–12 for {{{var_name}}}")
        return m
    if u in ("YEAR", "Y") or u.endswith("_YEAR"):
        y = _parse_int()
        if y < 1900 or y > 2100:
            raise ValueError(f"Year out of range for {{{var_name}}}")
        return y
    if (u in ("DAY", "DOM") or u == "D") and "DATE" not in u:
        d = _parse_int()
        if d < 1 or d > 31:
            raise ValueError(f"Day must be 1–31 for {{{var_name}}}")
        return d

    # Common numeric report filters (coerce when value is numeric; else keep string)
    if u in (
        "PLANT",
        "PLANT_ID",
        "PLANTID",
        "PID",
        "FACTORY",
        "FACTORY_ID",
        "SM_ID",
        "MC_ID",
        "DEPT_ID",
    ) or u.endswith("_PLANT") or u.endswith("_PID"):
        try:
            return _parse_int()
        except ValueError:
            return s

    return s


def compile_report_query(
    query_template: str,
    provided_variables: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Any]]:
    """Compile a query template by replacing {var} placeholders with %s params."""
    query_template = query_template.strip()
    assert_read_only_query(query_template)

    provided = provided_variables or {}
    params: List[Any] = []
    pattern = re.compile(r"\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}")

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name not in provided:
            raise ValueError(f"Missing value for variable {{{var_name}}}")
        raw_value = provided[var_name]
        if raw_value is None:
            raise ValueError(f"Missing value for variable {{{var_name}}}")
        params.append(_coerce_variable_value(var_name, raw_value))
        return "%s"

    sql = pattern.sub(replacer, query_template)
    sql = _sanitize_pymysql_percent(sql)
    return sql, params


# ── Groups ──────────────────────────────────────────────────────────────

def get_groups() -> List[Dict[str, Any]]:
    store = _read_store()
    return sorted(store["groups"], key=lambda g: g.get("name", ""))


def create_group(name: str) -> Dict[str, Any]:
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("Group name is required")

    store = _read_store()
    for g in store["groups"]:
        if g["name"].lower() == trimmed.lower():
            raise ValueError("A group with this name already exists")

    now = _iso_now()
    group = {
        "id": str(uuid.uuid4()),
        "name": trimmed,
        "createdAt": now,
        "updatedAt": now,
    }
    store["groups"].append(group)
    _write_store(store)
    return group


def delete_group(group_id: str) -> None:
    store = _read_store()
    initial = len(store["groups"])
    store["groups"] = [g for g in store["groups"] if g["id"] != group_id]
    if len(store["groups"]) == initial:
        raise ValueError("Group not found")
    store["reports"] = [r for r in store["reports"] if r.get("groupId") != group_id]
    _write_store(store)


# ── Reports ─────────────────────────────────────────────────────────────

def get_reports(group_id: Optional[str] = None, pinned_only: bool = False) -> List[Dict[str, Any]]:
    store = _read_store()
    filtered = store["reports"]
    if group_id:
        filtered = [r for r in filtered if r.get("groupId") == group_id]
    if pinned_only:
        filtered = [r for r in filtered if bool(r.get("pinned", False))]
    return sorted(filtered, key=lambda r: r.get("name", ""))


def get_report_by_id(report_id: str) -> Optional[Dict[str, Any]]:
    store = _read_store()
    for r in store["reports"]:
        if r["id"] == report_id:
            return r
    return None


def create_report(
    group_id: str,
    name: str,
    query_template: str,
    drilldowns: Optional[List[Dict[str, Any]]] = None,
    pinned: bool = False,
) -> Dict[str, Any]:
    group_id = group_id.strip()
    name = name.strip()
    query_template = query_template.strip()

    if not group_id:
        raise ValueError("groupId is required")
    if not name:
        raise ValueError("Report name is required")
    if not query_template:
        raise ValueError("queryTemplate is required")

    assert_read_only_query(query_template)

    store = _read_store()
    if not any(g["id"] == group_id for g in store["groups"]):
        raise ValueError("Group not found")

    for r in store["reports"]:
        if r.get("groupId") == group_id and r["name"].lower() == name.lower():
            raise ValueError("A report with this name already exists in this group")

    now = _iso_now()
    report_by_id = {
        str(r.get("id")): r
        for r in store["reports"]
        if isinstance(r, dict) and isinstance(r.get("id"), str)
    }
    report_vars = _extract_variables(query_template)
    normalized_drilldowns = _validate_and_normalize_drilldowns_from_input(
        drilldowns or [],
        report_by_id,
        source_report_vars=report_vars,
    )
    report = {
        "id": str(uuid.uuid4()),
        "groupId": group_id,
        "name": name,
        "queryTemplate": query_template,
        "variables": report_vars,
        "pinned": bool(pinned),
        "drilldowns": normalized_drilldowns,
        "createdAt": now,
        "updatedAt": now,
    }
    store["reports"].append(report)
    _write_store(store)
    return report


def update_report(
    report_id: str,
    name: str,
    query_template: str,
    drilldowns: Optional[List[Dict[str, Any]]] = None,
    pinned: Optional[bool] = None,
) -> Dict[str, Any]:
    name = name.strip()
    query_template = query_template.strip()

    if not name:
        raise ValueError("Report name is required")
    if not query_template:
        raise ValueError("queryTemplate is required")

    assert_read_only_query(query_template)

    store = _read_store()
    idx = next(
        (i for i, r in enumerate(store["reports"]) if r["id"] == report_id),
        None,
    )
    if idx is None:
        raise ValueError("Report not found")

    current = store["reports"][idx]
    for r in store["reports"]:
        if (
            r["id"] != report_id
            and r.get("groupId") == current.get("groupId")
            and r["name"].lower() == name.lower()
        ):
            raise ValueError("A report with this name already exists in this group")

    report_by_id = {
        str(r.get("id")): r
        for r in store["reports"]
        if isinstance(r, dict) and isinstance(r.get("id"), str)
    }
    report_vars = _extract_variables(query_template)
    normalized_drilldowns = _validate_and_normalize_drilldowns_from_input(
        drilldowns or [],
        report_by_id,
        source_report_vars=report_vars,
    )

    updated = {
        **current,
        "name": name,
        "queryTemplate": query_template,
        "variables": report_vars,
        "pinned": bool(current.get("pinned", False)) if pinned is None else bool(pinned),
        "drilldowns": normalized_drilldowns,
        "updatedAt": _iso_now(),
    }
    store["reports"][idx] = updated
    _write_store(store)
    return updated


def delete_report(report_id: str) -> None:
    store = _read_store()
    initial = len(store["reports"])
    store["reports"] = [r for r in store["reports"] if r["id"] != report_id]
    if len(store["reports"]) == initial:
        raise ValueError("Report not found")
    _write_store(store)
