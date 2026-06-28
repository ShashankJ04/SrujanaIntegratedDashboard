"""Global Search API.

Executes cross-database queries to find Components, Tags, Orders, and Maintenance records.
"""

from __future__ import annotations
from typing import Any, List, Dict
from flask import Blueprint, jsonify, request, g
from .auth import api_login_required
from .db import fetch_all
from . import rbac as rbac_store
from . import reports_store

search_bp = Blueprint("search", __name__, url_prefix="/api/search")

@search_bp.before_request
def _auth():
    return api_login_required()

@search_bp.route("/global", methods=["GET"])
def global_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    q_like = f"%{q}%"
    q_lc = q.lower()

    user = g.get("current_user") or {}
    perms = rbac_store.get_effective_permissions(
        user.get("userId", 0),
        user.get("login", ""),
        user.get("userId") == 43,
    )
    access = set(perms.get("access", []))

    can_production = "production" in access
    can_inventory = "rept" in access
    can_reports = "rept" in access
    can_dpr = "rept" in access

    results: List[Dict[str, Any]] = []
    seen = set()

    def add_result(item: Dict[str, Any]) -> None:
        key = (str(item.get("type", "")), str(item.get("id", "")))
        if key in seen:
            return
        seen.add(key)
        results.append(item)
    
    # 1. Search ERP Components
    if can_production:
        comps = fetch_all("""
            SELECT CO_PARTNO as id, CO_PARTNAME as label, 'Part' as type, '/app?section=production' as link
            FROM components
            WHERE CO_PARTNO LIKE %s OR CO_PARTNAME LIKE %s
            LIMIT 10
        """, (q_like, q_like))
        for r in comps:
            add_result(r)

    # 3. Search customer schedule entries by part
    if can_production:
        schedules = fetch_all("""
            SELECT
                CONCAT(sc.CS_Id, '-', TRIM(c.CO_PARTNO)) AS id,
                CONCAT('Schedule: ', TRIM(c.CO_PARTNO), ' qty ', sc.CS_QTY) AS label,
                'Schedule' AS type,
                '/app?section=hub' AS link
            FROM scheduled_customer sc
            INNER JOIN schedule_details sd ON sd.SC_ID = sc.CS_SCID
            INNER JOIN components c ON c.CO_ID = sd.SC_COMPID
            WHERE TRIM(c.CO_PARTNO) LIKE %s OR TRIM(c.CO_PARTNAME) LIKE %s
            ORDER BY sc.CS_DATE DESC
            LIMIT 10
        """, (q_like, q_like))
        for r in schedules:
            add_result(r)

    # 4. Search report definitions (opens exact report in Reports section)
    if can_reports:
        reports = reports_store.get_reports()
        for r in reports:
            rid = str(r.get("id", "")).strip()
            name = str(r.get("name", "")).strip()
            if not rid or not name:
                continue
            if q_lc not in name.lower():
                continue
            add_result(
                {
                    "id": rid,
                    "label": name,
                    "type": "Report",
                    "link": f"/app?section=reports&report={rid}",
                }
            )

    # 5. Search DPR machine/part records
    if can_dpr:
        dpr_machines = fetch_all(
            """
            SELECT DISTINCT machine_id AS id, CONCAT('Machine: ', machine_id) AS label
            FROM dpr_daily_review
            WHERE machine_id LIKE %s
            ORDER BY machine_id
            LIMIT 10
            """,
            (q_like,),
        )
        for r in dpr_machines:
            add_result(
                {
                    "id": r.get("id"),
                    "label": r.get("label"),
                    "type": "DPR Machine",
                    "link": "/app?section=dpr",
                }
            )

        dpr_parts = fetch_all(
            """
            SELECT DISTINCT part_no AS id, CONCAT('DPR Part: ', part_no) AS label
            FROM dpr_daily_review
            WHERE part_no LIKE %s
            ORDER BY part_no
            LIMIT 10
            """,
            (q_like,),
        )
        for r in dpr_parts:
            add_result(
                {
                    "id": r.get("id"),
                    "label": r.get("label"),
                    "type": "DPR Part",
                    "link": "/app?section=dpr",
                }
            )

    # Relevance ordering: prefix matches first, then by label.
    def _rank(item: Dict[str, Any]) -> Any:
        label = str(item.get("label", "")).lower()
        starts = 0 if label.startswith(q_lc) else 1
        return (starts, label)

    results.sort(key=_rank)

    return jsonify(results)
