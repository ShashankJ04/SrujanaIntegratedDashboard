"""Scheduler API Blueprint — /api/scheduler/*."""

from __future__ import annotations

import json
import traceback
from datetime import date, datetime
from typing import Any, Dict

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import api_login_required
from ..db import execute, execute_insert, fetch_all, fetch_one
from ..rbac import require_access

from .engine import run_scheduler
from .input_builder import build_scheduler_input
from .models import DEFAULT_WEIGHTS, Scenario

scheduler_bp = Blueprint("scheduler_bp", __name__, url_prefix="/api/scheduler")


@scheduler_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


def _user_login() -> str:
    user = g.get("current_user") or {}
    return str(user.get("login") or user.get("userId") or "")


# ── Working Calendar ─────────────────────────────────────────────────────

@scheduler_bp.route("/working-calendar/<int:month>/<int:year>", methods=["GET"])
@require_access("scdl")
def get_working_calendar(month: int, year: int):
    from .capacity import get_working_days
    try:
        cal_rows = fetch_all(
            "SELECT cal_date, is_working, shift_hours, notes, updated_by "
            "FROM scheduler_working_calendar "
            "WHERE cal_date BETWEEN %s AND %s "
            "ORDER BY cal_date",
            (f"{year}-{month:02d}-01", f"{year}-{month:02d}-31"),
        )
    except Exception:
        cal_rows = []

    working_days = get_working_days(month, year, cal_rows)
    work_hours = int(current_app.config.get("WORK_HOURS_PER_DAY", 6))

    explicit = {}
    for r in cal_rows:
        d = r.get("cal_date")
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        explicit[d.day if isinstance(d, date) else 0] = {
            "date": str(d),
            "is_working": bool(r.get("is_working", 1)),
            "shift_hours": float(r["shift_hours"]) if r.get("shift_hours") is not None else None,
            "notes": r.get("notes"),
        }

    import calendar as cal_mod
    days_in_month = cal_mod.monthrange(year, month)[1]
    days = []
    for day_num in range(1, days_in_month + 1):
        dt = date(year, month, day_num)
        if day_num in explicit:
            entry = explicit[day_num]
        else:
            is_working = day_num in working_days
            entry = {
                "date": dt.isoformat(),
                "is_working": is_working,
                "shift_hours": None,
                "notes": None,
            }
        entry["day"] = day_num
        entry["weekday"] = dt.strftime("%a")
        entry["default_hours"] = work_hours
        days.append(entry)

    return jsonify({"month": month, "year": year, "days": days, "work_hours_default": work_hours})


@scheduler_bp.route("/working-calendar/<date_str>", methods=["PUT"])
@require_access("scdl")
def update_working_day(date_str: str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"message": "Invalid date"}), 400

    body = request.get_json(force=True)
    is_working = body.get("is_working", True)
    shift_hours = body.get("shift_hours")
    notes = body.get("notes")

    execute(
        "INSERT INTO scheduler_working_calendar (cal_date, is_working, shift_hours, notes, updated_by) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE is_working=%s, shift_hours=%s, notes=%s, updated_by=%s",
        (d, int(is_working), shift_hours, notes, _user_login(),
         int(is_working), shift_hours, notes, _user_login()),
    )
    return jsonify({"ok": True, "date": d.isoformat()})


# ── Scenarios ────────────────────────────────────────────────────────────

@scheduler_bp.route("/scenarios", methods=["GET"])
@require_access("scdl")
def list_scenarios():
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    params = []
    where = []
    if month:
        where.append("month = %s")
        params.append(month)
    if year:
        where.append("year = %s")
        params.append(year)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = fetch_all(
        f"SELECT scenario_id, name, month, year, frozen_days, created_by, created_at, updated_at "
        f"FROM scheduler_scenario {clause} ORDER BY updated_at DESC",
        tuple(params),
    )
    return jsonify({"scenarios": rows})


def _scenario_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    weights = row.get("weights_json")
    if isinstance(weights, str):
        weights = json.loads(weights)
    overrides = row.get("overrides_json")
    if isinstance(overrides, str):
        overrides = json.loads(overrides)
    return {
        "scenario_id": row.get("scenario_id"),
        "name": row.get("name"),
        "month": row.get("month"),
        "year": row.get("year"),
        "frozen_days": int(row.get("frozen_days") or 0),
        "weights": weights or dict(DEFAULT_WEIGHTS),
        "overrides": overrides or {},
        "created_by": row.get("created_by"),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


@scheduler_bp.route("/scenario/<int:scenario_id>", methods=["GET"])
@require_access("scdl")
def get_scenario(scenario_id: int):
    row = fetch_one(
        "SELECT * FROM scheduler_scenario WHERE scenario_id = %s",
        (scenario_id,),
    )
    if not row:
        return jsonify({"message": "Scenario not found"}), 404
    return jsonify(_scenario_to_dict(row))


@scheduler_bp.route("/scenario", methods=["POST"])
@require_access("scdl")
def save_scenario():
    body = request.get_json(force=True)
    sid = body.get("scenario_id")
    name = str(body.get("name") or "Untitled")
    month = int(body.get("month") or date.today().month)
    year = int(body.get("year") or date.today().year)
    weights = body.get("weights") or dict(DEFAULT_WEIGHTS)
    overrides = body.get("overrides") or {}
    frozen_days = int(body.get("frozen_days") or 0)

    if sid:
        execute(
            "UPDATE scheduler_scenario SET name=%s, month=%s, year=%s, "
            "weights_json=%s, overrides_json=%s, frozen_days=%s WHERE scenario_id=%s",
            (name, month, year, json.dumps(weights), json.dumps(overrides), frozen_days, sid),
        )
    else:
        sid = execute_insert(
            "INSERT INTO scheduler_scenario (name, month, year, weights_json, overrides_json, frozen_days, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (name, month, year, json.dumps(weights), json.dumps(overrides), frozen_days, _user_login()),
        )
    row = fetch_one("SELECT * FROM scheduler_scenario WHERE scenario_id = %s", (sid,))
    return jsonify(_scenario_to_dict(row) if row else {"scenario_id": sid})


# ── Run Scheduler ────────────────────────────────────────────────────────

@scheduler_bp.route("/run", methods=["POST"])
@require_access("scdl")
def run_schedule():
    body = request.get_json(force=True)
    scenario_id = body.get("scenario_id")
    month = int(body.get("month") or date.today().month)
    year = int(body.get("year") or date.today().year)

    scenario = Scenario()
    request_weights = body.get("weights")
    request_overrides = body.get("overrides")

    if scenario_id:
        row = fetch_one(
            "SELECT * FROM scheduler_scenario WHERE scenario_id = %s",
            (scenario_id,),
        )
        if row:
            scenario = Scenario.from_db_row(row)
            month = int(row.get("month") or month)
            year = int(row.get("year") or year)
        if isinstance(request_weights, dict) and request_weights:
            scenario.weights = {**scenario.weights, **request_weights}
        if isinstance(request_overrides, dict):
            scenario.overrides = request_overrides
    else:
        scenario.weights = request_weights or dict(DEFAULT_WEIGHTS)
        scenario.overrides = request_overrides or {}
        scenario_id = execute_insert(
            "INSERT INTO scheduler_scenario (name, month, year, weights_json, overrides_json, frozen_days, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            ("Quick run", month, year, json.dumps(scenario.weights),
             json.dumps(scenario.overrides), 0, _user_login()),
        )

    run_id = execute_insert(
        "INSERT INTO scheduler_run (scenario_id, status) VALUES (%s, 'running')",
        (scenario_id,),
    )

    try:
        inp = build_scheduler_input(month, year, scenario)
        result = run_scheduler(inp)
        execute(
            "UPDATE scheduler_run SET status='completed', "
            "kpi_json=%s, assignments_json=%s, completed_at=NOW() WHERE run_id=%s",
            (json.dumps(result.kpi), json.dumps(result.to_dict()), run_id),
        )
        return jsonify({"run_id": run_id, "status": "completed", **result.to_dict()})
    except Exception as exc:
        tb = traceback.format_exc()
        execute(
            "UPDATE scheduler_run SET status='failed', "
            "kpi_json=%s, completed_at=NOW() WHERE run_id=%s",
            (json.dumps({"error": str(exc), "traceback": tb}), run_id),
        )
        return jsonify({"run_id": run_id, "status": "failed", "error": str(exc)}), 500


@scheduler_bp.route("/run/<int:run_id>", methods=["GET"])
@require_access("scdl")
def get_run(run_id: int):
    row = fetch_one("SELECT * FROM scheduler_run WHERE run_id = %s", (run_id,))
    if not row:
        return jsonify({"message": "Run not found"}), 404
    assignments_raw = row.get("assignments_json")
    kpi_raw = row.get("kpi_json")
    assignments = json.loads(assignments_raw) if isinstance(assignments_raw, str) else (assignments_raw or {})
    kpi = json.loads(kpi_raw) if isinstance(kpi_raw, str) else (kpi_raw or {})
    return jsonify({
        "run_id": run_id,
        "scenario_id": row.get("scenario_id"),
        "status": row.get("status"),
        "started_at": str(row.get("started_at") or ""),
        "completed_at": str(row.get("completed_at") or ""),
        "kpi": kpi,
        **assignments,
    })


@scheduler_bp.route("/run/<int:run_id>/explain/<int:idx>", methods=["GET"])
@require_access("scdl")
def explain_assignment(run_id: int, idx: int):
    row = fetch_one("SELECT assignments_json FROM scheduler_run WHERE run_id = %s", (run_id,))
    if not row:
        return jsonify({"message": "Run not found"}), 404
    data = row.get("assignments_json")
    if isinstance(data, str):
        data = json.loads(data)
    assignments = (data or {}).get("assignments", [])
    if idx < 0 or idx >= len(assignments):
        return jsonify({"message": "Assignment index out of range"}), 404
    return jsonify(assignments[idx])


@scheduler_bp.route("/run/<int:run_id>/analysis", methods=["GET"])
@require_access("scdl")
def get_run_analysis(run_id: int):
    row = fetch_one("SELECT assignments_json FROM scheduler_run WHERE run_id = %s", (run_id,))
    if not row:
        return jsonify({"message": "Run not found"}), 404
    data = row.get("assignments_json")
    if isinstance(data, str):
        data = json.loads(data)
    analysis = (data or {}).get("analysis", {})
    return jsonify(analysis)


# ── Runs list (for compare dropdown) ─────────────────────────────────────

@scheduler_bp.route("/runs", methods=["GET"])
@require_access("scdl")
def list_runs():
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    params = []
    where = ["r.status = 'completed'"]
    if month or year:
        where.append("s.month = %s")
        params.append(month or date.today().month)
        where.append("s.year = %s")
        params.append(year or date.today().year)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = fetch_all(
        f"SELECT r.run_id, r.scenario_id, s.name AS scenario_name, "
        f"r.status, r.started_at, r.completed_at "
        f"FROM scheduler_run r "
        f"LEFT JOIN scheduler_scenario s ON s.scenario_id = r.scenario_id "
        f"{clause} ORDER BY r.completed_at DESC LIMIT 20",
        tuple(params),
    )
    return jsonify({"runs": [
        {
            "run_id": r.get("run_id"),
            "scenario_id": r.get("scenario_id"),
            "scenario_name": r.get("scenario_name") or "Quick run",
            "status": r.get("status"),
            "started_at": str(r.get("started_at") or ""),
            "completed_at": str(r.get("completed_at") or ""),
        }
        for r in (rows or [])
    ]})


# ── Compare ──────────────────────────────────────────────────────────────

@scheduler_bp.route("/compare", methods=["POST"])
@require_access("scdl")
def compare_runs_endpoint():
    from .explainer import compare_runs as _compare
    from .models import Assignment, RunResult, ScoreFactor, ScoreResult, UnscheduledPart

    body = request.get_json(force=True)
    run_a_id = body.get("run_a")
    run_b_id = body.get("run_b")
    if not run_a_id or not run_b_id:
        return jsonify({"message": "Provide run_a and run_b"}), 400

    row_a = fetch_one("SELECT * FROM scheduler_run WHERE run_id = %s", (run_a_id,))
    row_b = fetch_one("SELECT * FROM scheduler_run WHERE run_id = %s", (run_b_id,))
    if not row_a or not row_b:
        return jsonify({"message": "Run not found"}), 404

    def _parse_result(row: Dict) -> RunResult:
        raw = row.get("assignments_json")
        if isinstance(raw, str):
            raw = json.loads(raw)
        data = raw or {}
        kpi = row.get("kpi_json")
        if isinstance(kpi, str):
            kpi = json.loads(kpi)

        assignments = []
        for a in data.get("assignments", []):
            sb = a.get("score", {}).get("breakdown", [])
            factors = [ScoreFactor(**f) for f in sb]
            sr = ScoreResult(
                total=a.get("score", {}).get("total", 0),
                breakdown=factors,
                alternatives_rejected=a.get("score", {}).get("alternatives_rejected", []),
            )
            assignments.append(Assignment(
                part_no=a["part_no"], part_name=a.get("part_name", ""),
                machine_id=a["machine_id"], machine_name=a.get("machine_name", ""),
                day=a["day"], qty=a["qty"], run_minutes=a["run_minutes"],
                strokes=a.get("strokes", 0), score=sr,
                constraints_checked=a.get("constraints_checked", {}),
                is_actual=a.get("is_actual", False),
            ))

        unsched = [UnscheduledPart(**u) for u in data.get("unscheduled", [])]
        return RunResult(assignments=assignments, kpi=kpi or {}, unscheduled=unsched)

    result_a = _parse_result(row_a)
    result_b = _parse_result(row_b)
    diff = _compare(result_a, result_b)
    return jsonify(diff)
