"""Global Search API.

Executes cross-database queries to find Components, Tags, Orders, and Maintenance records.
"""

from __future__ import annotations
from typing import Any, List, Dict
from flask import Blueprint, jsonify, request
from .auth import api_login_required
from .db import fetch_all, wh_fetch_all

search_bp = Blueprint("search", __name__, url_prefix="/api/search")

@search_bp.before_request
def _auth():
    return api_login_required()

@search_bp.route("/global", methods=["GET"])
def global_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])

    results = []
    
    # 1. Search ERP Components
    comps = fetch_all("""
        SELECT CO_PARTNO as id, CO_PARTNAME as label, 'Part' as type, '/app?section=production' as link
        FROM components 
        WHERE CO_PARTNO LIKE %s OR CO_PARTNAME LIKE %s
        LIMIT 10
    """, (f"%{q}%", f"%{q}%"))
    for r in comps: results.append(r)

    # 2. Search Warehouse Tags
    tags = wh_fetch_all("""
        SELECT tag_id as id, CONCAT(item_code, ' (', status, ')') as label, 'Tag' as type, '/app' as link
        FROM inventory_grn_item_tag
        WHERE tag_id LIKE %s OR item_code LIKE %s
        LIMIT 10
    """, (f"%{q}%", f"%{q}%"))
    for r in tags: results.append(r)

    # 3. Search Machines
    machines = fetch_all("""
        SELECT MCM_Id as id, MCM_Name as label, 'Machine' as type, CONCAT('/portal/machine/', MCM_Id) as link
        FROM machinemaster
        WHERE MCM_Name LIKE %s
        LIMIT 10
    """, (f"%{q}%",))
    for r in machines: results.append(r)

    # 4. Search Sales Orders
    sos = fetch_all("""
        SELECT SO_NO as id, CONCAT('SO: ', SO_NO, ' for ', PART_NO) as label, 'Order' as type, '/app?section=production' as link
        FROM sales_order
        WHERE SO_NO LIKE %s OR PART_NO LIKE %s
        LIMIT 10
    """, (f"%{q}%", f"%{q}%"))
    for r in sos: results.append(r)

    return jsonify(results)
