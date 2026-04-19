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
    return {
        "groups": parsed.get("groups") or [],
        "reports": parsed.get("reports") or [],
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

def get_reports(group_id: Optional[str] = None) -> List[Dict[str, Any]]:
    store = _read_store()
    filtered = store["reports"]
    if group_id:
        filtered = [r for r in filtered if r.get("groupId") == group_id]
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
    report = {
        "id": str(uuid.uuid4()),
        "groupId": group_id,
        "name": name,
        "queryTemplate": query_template,
        "variables": _extract_variables(query_template),
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

    updated = {
        **current,
        "name": name,
        "queryTemplate": query_template,
        "variables": _extract_variables(query_template),
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
