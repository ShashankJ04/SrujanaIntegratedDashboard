"""Tool Breakdown API Blueprint."""

from __future__ import annotations

from datetime import date
from functools import wraps
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request, g

from .auth import api_login_required
from . import rbac
from .db import execute, fetch_all, fetch_one
from .pm_api import _norm_tool_no
from . import pm_store

tool_breakdowns_bp = Blueprint("tool_breakdowns_bp", __name__, url_prefix="/api/tool-breakdowns")


@tool_breakdowns_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


def _current_perms() -> Dict[str, Any]:
    user = g.get("current_user") or {}
    return rbac.get_effective_permissions(
        user.get("userId", 0),
        user.get("login", ""),
        user.get("userId") == 43,
    )


def _require_perm(*, access: Optional[str] = None, plus: Optional[str] = None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            perms = _current_perms()
            if access and access not in perms.get("access", []):
                return jsonify({"message": "Forbidden"}), 403
            if plus and plus not in perms.get("plusAccess", []):
                return jsonify({"message": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def _require_breakdown_list_access(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        perms = _current_perms()
        if (
            "preventive_maintenance" not in perms.get("access", [])
            and "edit_dpr" not in perms.get("plusAccess", [])
        ):
            return jsonify({"message": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated


def _require_dpr_or_pm_access(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        perms = _current_perms()
        if (
            "preventive_maintenance" not in perms.get("access", [])
            and "edit_dpr" not in perms.get("plusAccess", [])
        ):
            return jsonify({"message": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated


def _iso_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _format_user_name(row: Dict[str, Any]) -> str:
    first = str(row.get("firstName") or "").strip()
    last = str(row.get("lastName") or "").strip()
    name = " ".join([p for p in (first, last) if p]).strip()
    login = str(row.get("login") or "").strip()
    return name or login


def _user_label(row: Dict[str, Any]) -> str:
    login = str(row.get("login") or "").strip()
    name = _format_user_name(row)
    if not name:
        return login
    if login and name.lower() != login.lower():
        return f"{name} ({login})"
    return name or login


def _fetch_active_user(user_id: Any) -> Optional[Dict[str, Any]]:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    row = fetch_one(
        """
        SELECT
            US_ID AS id,
            US_Login AS login,
            COALESCE(US_FirstName, '') AS firstName,
            COALESCE(US_LastName, '') AS lastName
        FROM users
        WHERE US_CurrentYn = 'Y' AND US_ID = %s
        """,
        (uid,),
    )
    return row


def _operator_label(row: Dict[str, Any]) -> str:
    name = str(row.get("name") or "").strip()
    ecno = str(row.get("ecno") or "").strip()
    if name and ecno and name.lower() != ecno.lower():
        return f"{name} ({ecno})"
    return name or ecno


def _fetch_active_operator(operator_id: Any) -> Optional[Dict[str, Any]]:
    try:
        oid = int(operator_id)
    except (TypeError, ValueError):
        return None
    row = fetch_one(
        """
        SELECT
            OP_ID AS id,
            COALESCE(OP_ECNO, '') AS ecno,
            COALESCE(OP_NAME, '') AS name
        FROM operators
        WHERE OP_ACTIVEYN = 'Y' AND OP_ID = %s
        """,
        (oid,),
    )
    return row


def _resolve_tool_id_for_strokes(tool_no: str) -> Optional[int]:
    norm = _norm_tool_no(tool_no).strip()
    if not norm:
        return None
    row = fetch_one(
        """
        SELECT TL_tool_id AS toolId
        FROM tool_life
        WHERE TL_tool_number = %s
        LIMIT 1
        """,
        (norm,),
    )
    if row and row.get("toolId") is not None:
        try:
            return int(row.get("toolId"))
        except (TypeError, ValueError):
            return None
    return None


def _breakdown_row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "toolNo": row.get("tool_no"),
        "partNo": row.get("part_no"),
        "partName": row.get("part_name"),
        "machineId": row.get("machine_id"),
        "machineName": row.get("machine_name"),
        "dprRowId": row.get("dpr_row_id"),
        "dprReviewDate": _iso_dt(row.get("dpr_review_date")),
        "dprProducedQty": row.get("dpr_produced_qty"),
        "issue": row.get("issue") or "",
        "priority": row.get("priority") or "Immediate",
        "operatorId": row.get("operator_user_id"),
        "operatorLogin": row.get("operator_login") or "",
        "operatorName": row.get("operator_name") or "",
        "downtimeAt": _iso_dt(row.get("downtime_at")),
        "rootCause": row.get("root_cause"),
        "rootCauseAt": _iso_dt(row.get("root_cause_at")),
        "actionTaken": row.get("action_taken"),
        "actionTakenAt": _iso_dt(row.get("action_taken_at")),
        "remarks": row.get("remarks") or "",
        "spareConsumed": row.get("spare_consumed") or "",
        "completedAt": _iso_dt(row.get("completed_at")),
        "completedById": row.get("completed_by_id"),
        "completedByLogin": row.get("completed_by_login"),
        "completedByName": row.get("completed_by_name"),
        "createdBy": row.get("created_by"),
        "updatedBy": row.get("updated_by"),
        "createdAt": _iso_dt(row.get("created_at")),
        "updatedAt": _iso_dt(row.get("updated_at")),
        "status": "closed" if row.get("completed_at") else "active",
    }


@tool_breakdowns_bp.get("/operators")
@_require_perm(access="preventive_maintenance")
def list_breakdown_operators():
    rows = fetch_all(
        """
        SELECT
            US_ID AS id,
            US_Login AS login,
            COALESCE(US_FirstName, '') AS firstName,
            COALESCE(US_LastName, '') AS lastName
        FROM users
        WHERE US_CurrentYn = 'Y'
        ORDER BY US_Login
        """
    )
    result = []
    for r in rows:
        result.append(
            {
                "id": r.get("id"),
                "login": r.get("login"),
                "firstName": r.get("firstName"),
                "lastName": r.get("lastName"),
                "name": _format_user_name(r),
                "label": _user_label(r),
            }
        )
    return jsonify(result)


@tool_breakdowns_bp.get("/operators/dpr")
@_require_dpr_or_pm_access
def list_breakdown_operators_dpr():
    rows = fetch_all(
        """
        SELECT
            OP_ID AS id,
            COALESCE(OP_ECNO, '') AS ecno,
            COALESCE(OP_NAME, '') AS name
        FROM operators
        WHERE OP_ACTIVEYN = 'Y'
        ORDER BY OP_NAME, OP_ECNO
        """
    )
    result = []
    for r in rows:
        result.append(
            {
                "id": r.get("id"),
                "login": r.get("ecno"),
                "firstName": "",
                "lastName": "",
                "name": r.get("name"),
                "label": _operator_label(r),
            }
        )
    return jsonify(result)


@tool_breakdowns_bp.post("")
@_require_perm(plus="edit_dpr")
def create_breakdown():
    payload = request.get_json(silent=True) or {}
    tool_no_raw = payload.get("toolNo")
    tool_no = _norm_tool_no(tool_no_raw).strip()
    if not tool_no:
        return jsonify({"error": "toolNo is required"}), 400

    issue = str(payload.get("issue") or "").strip()
    if not issue:
        return jsonify({"error": "Issue/Problem is required"}), 400

    priority = str(payload.get("priority") or "Immediate").strip()
    if priority not in {"Immediate", "Next Day", "Delayed"}:
        return jsonify({"error": "Invalid priority"}), 400

    operator_id = payload.get("operatorId")
    operator_row = _fetch_active_operator(operator_id)
    if not operator_row:
        return jsonify({"error": "Invalid operator"}), 400

    open_row = fetch_one(
        "SELECT id FROM tool_breakdowns WHERE tool_no = %s AND completed_at IS NULL LIMIT 1",
        (tool_no,),
    )
    if open_row:
        return jsonify({"error": "An open breakdown already exists for this tool"}), 409

    part_no = str(payload.get("partNo") or "").strip() or None
    part_name = str(payload.get("partName") or "").strip() or None
    machine_id = str(payload.get("machineId") or "").strip() or None
    machine_name = str(payload.get("machineName") or "").strip() or None

    dpr_row_id: Optional[int] = None
    dpr_row_raw = payload.get("dprRowId")
    if dpr_row_raw not in (None, ""):
        try:
            dpr_row_id = int(dpr_row_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid dprRowId"}), 400

    dpr_review_date: Optional[date] = None
    dpr_review_raw = str(payload.get("dprReviewDate") or "").strip()
    if dpr_review_raw:
        try:
            dpr_review_date = date.fromisoformat(dpr_review_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid dprReviewDate"}), 400

    dpr_produced_qty: Optional[float] = None
    dpr_prod_raw = payload.get("dprProducedQty")
    if dpr_prod_raw not in (None, ""):
        try:
            dpr_produced_qty = float(dpr_prod_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid dprProducedQty"}), 400

    user_login = str(g.current_user.get("login") or "")
    execute(
        """
        INSERT INTO tool_breakdowns
            (tool_no, part_no, part_name, machine_id, machine_name,
             dpr_row_id, dpr_review_date, dpr_produced_qty, issue,
             priority, operator_user_id, operator_login, operator_name,
             downtime_at, created_by, updated_by)
        VALUES
            (%s, %s, %s, %s, %s,
             %s, %s, %s, %s,
             %s, %s, %s, %s,
             NOW(), %s, %s)
        """,
        (
            tool_no,
            part_no,
            part_name,
            machine_id,
            machine_name,
            dpr_row_id,
            dpr_review_date.isoformat() if dpr_review_date else None,
            dpr_produced_qty,
            issue,
            priority,
            operator_row.get("id"),
            operator_row.get("ecno"),
            operator_row.get("name"),
            user_login,
            user_login,
        ),
    )
    new_id_row = fetch_one("SELECT LAST_INSERT_ID() AS id")
    return jsonify({"id": new_id_row.get("id") if new_id_row else None})


@tool_breakdowns_bp.get("")
@_require_breakdown_list_access
def list_breakdowns():
    status = str(request.args.get("status") or "active").strip().lower()
    tool_no_raw = request.args.get("toolNo")
    limit_raw = request.args.get("limit")

    where_parts = []
    params: List[Any] = []
    if status == "closed":
        where_parts.append("completed_at IS NOT NULL")
    else:
        where_parts.append("completed_at IS NULL")

    if tool_no_raw:
        tool_no = _norm_tool_no(tool_no_raw).strip()
        if tool_no:
            where_parts.append("tool_no = %s")
            params.append(tool_no)

    limit_clause = ""
    if limit_raw not in (None, ""):
        try:
            lim = max(1, min(1000, int(limit_raw)))
            limit_clause = f" LIMIT {lim}"
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid limit"}), 400

    where_sql = " AND ".join(where_parts) if where_parts else "1=1"
    sql = f"""
        SELECT
            id, tool_no, part_no, part_name, machine_id, machine_name,
            dpr_row_id, dpr_review_date, dpr_produced_qty,
            issue, priority, operator_user_id, operator_login, operator_name, downtime_at,
            root_cause, root_cause_at, action_taken, action_taken_at, remarks, spare_consumed,
            completed_at, completed_by_id, completed_by_login, completed_by_name,
            created_by, updated_by, created_at, updated_at
        FROM tool_breakdowns
        WHERE {where_sql}
        ORDER BY downtime_at DESC, id DESC
        {limit_clause}
    """
    rows = fetch_all(sql, params if params else None)
    return jsonify([_breakdown_row_to_dict(r) for r in rows])


@tool_breakdowns_bp.patch("/<int:breakdown_id>")
@_require_perm(plus="preventive_maintenance")
def update_breakdown(breakdown_id: int):
    payload = request.get_json(silent=True) or {}
    if (
        "rootCause" not in payload
        and "actionTaken" not in payload
        and "remarks" not in payload
        and "spareConsumed" not in payload
    ):
        return jsonify({"error": "No fields to update"}), 400

    existing = fetch_one(
        "SELECT id, completed_at FROM tool_breakdowns WHERE id = %s",
        (breakdown_id,),
    )
    if not existing:
        return jsonify({"error": "Breakdown not found"}), 404
    if existing.get("completed_at"):
        return jsonify({"error": "Completed breakdowns cannot be edited"}), 400

    set_parts: List[str] = []
    params: List[Any] = []

    if "rootCause" in payload:
        root_cause = str(payload.get("rootCause") or "").strip()
        if root_cause:
            set_parts.append("root_cause = %s")
            params.append(root_cause)
            set_parts.append("root_cause_at = NOW()")
        else:
            set_parts.append("root_cause = NULL")
            set_parts.append("root_cause_at = NULL")

    if "actionTaken" in payload:
        action_taken = str(payload.get("actionTaken") or "").strip()
        if action_taken:
            set_parts.append("action_taken = %s")
            params.append(action_taken)
            set_parts.append("action_taken_at = NOW()")
        else:
            set_parts.append("action_taken = NULL")
            set_parts.append("action_taken_at = NULL")

    if "remarks" in payload:
        remarks = str(payload.get("remarks") or "").strip()
        if remarks:
            set_parts.append("remarks = %s")
            params.append(remarks)
        else:
            set_parts.append("remarks = NULL")

    if "spareConsumed" in payload:
        spare_consumed = str(payload.get("spareConsumed") or "").strip()
        if spare_consumed:
            set_parts.append("spare_consumed = %s")
            params.append(spare_consumed)
        else:
            set_parts.append("spare_consumed = NULL")

    set_parts.append("updated_by = %s")
    params.append(str(g.current_user.get("login") or ""))
    params.append(breakdown_id)

    execute(
        f"UPDATE tool_breakdowns SET {', '.join(set_parts)} WHERE id = %s",
        params,
    )
    row = fetch_one(
        """
        SELECT
            id, tool_no, part_no, part_name, machine_id, machine_name,
            dpr_row_id, dpr_review_date, dpr_produced_qty,
            issue, priority, operator_user_id, operator_login, operator_name, downtime_at,
            root_cause, root_cause_at, action_taken, action_taken_at, remarks, spare_consumed,
            completed_at, completed_by_id, completed_by_login, completed_by_name,
            created_by, updated_by, created_at, updated_at
        FROM tool_breakdowns
        WHERE id = %s
        """,
        (breakdown_id,),
    )
    return jsonify(_breakdown_row_to_dict(row) if row else {})


@tool_breakdowns_bp.post("/<int:breakdown_id>/complete")
@_require_perm(plus="preventive_maintenance")
def complete_breakdown(breakdown_id: int):
    payload = request.get_json(silent=True) or {}
    completed_by_id = payload.get("completedById")
    operator_row = _fetch_active_operator(completed_by_id)
    if not operator_row:
        return jsonify({"error": "Invalid completion user"}), 400

    row = fetch_one(
        """
        SELECT id, tool_no, root_cause, action_taken, completed_at
        FROM tool_breakdowns
        WHERE id = %s
        """,
        (breakdown_id,),
    )
    if not row:
        return jsonify({"error": "Breakdown not found"}), 404
    if row.get("completed_at"):
        return jsonify({"error": "Breakdown already completed"}), 400

    root_cause = str(row.get("root_cause") or "").strip()
    action_taken = str(row.get("action_taken") or "").strip()
    if not root_cause or not action_taken:
        return jsonify({"error": "Root cause and action taken are required"}), 400

    tool_no = str(row.get("tool_no") or "").strip()
    tool_id = _resolve_tool_id_for_strokes(tool_no)
    if not tool_id:
        return jsonify({"error": "Tool not found for stroke info"}), 404

    try:
        stroke_info = pm_store.get_stroke_info(tool_id, date.today())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    execute(
        """
        UPDATE tool_breakdowns
        SET
            completed_at = NOW(),
            completed_by_id = %s,
            completed_by_login = %s,
            completed_by_name = %s,
            updated_by = %s,
            current_stroke = %s,
            next_stroke = %s
        WHERE id = %s
        """,
        (
            operator_row.get("id"),
            operator_row.get("ecno"),
            operator_row.get("name"),
            str(g.current_user.get("login") or ""),
            stroke_info.get("currentStroke"),
            stroke_info.get("suggestedNextStroke"),
            breakdown_id,
        ),
    )
    return jsonify({"ok": True})
