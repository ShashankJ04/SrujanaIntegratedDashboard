"""Laser Welding API Blueprint."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request

from .auth import api_login_required
from .rbac import require_access, require_plus_access
from . import laser_welding as lw

laser_welding_bp = Blueprint("laser_welding_bp", __name__, url_prefix="/api/laser-welding")


@laser_welding_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


@laser_welding_bp.route("/stages", methods=["GET"])
@require_access("rept")
def list_stages() -> Any:
    return jsonify(lw.get_stages())


@laser_welding_bp.route("/rows", methods=["GET"])
@require_access("rept")
def list_rows() -> Any:
    tab = request.args.get("tab", "child_parts").strip()
    try:
        rows = lw.get_rows(tab)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/production-details", methods=["GET"])
@require_access("rept")
def production_details() -> Any:
    part_no = request.args.get("partNo", "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    try:
        entries = lw.get_production_details(part_no)
    except Exception as exc:
        return jsonify({"error": "Database query failed", "details": str(exc)}), 500
    return jsonify({"count": len(entries), "entries": entries})


@laser_welding_bp.route("/save", methods=["POST"])
@require_access("rept")
@require_plus_access("edit_dpr")
def save() -> Any:
    body = request.get_json(silent=True) or {}
    tab = str(body.get("tab") or "child_parts").strip()
    part_number = str(body.get("partNumber") or "").strip()
    stage_id = body.get("stageId")
    items = body.get("items") or []

    if not part_number or not stage_id:
        return jsonify({"error": "partNumber and stageId are required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.save_rows(
            tab_type=tab,
            part_number=part_number,
            stage_id=int(stage_id),
            items=items,
            created_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(result)


@laser_welding_bp.route("/process", methods=["POST"])
@require_access("rept")
@require_plus_access("edit_dpr")
def process() -> Any:
    body = request.get_json(silent=True) or {}
    tab = str(body.get("tab") or "child_parts").strip()
    part_number = str(body.get("partNumber") or "").strip()
    stage_id = body.get("stageId")

    if not part_number or not stage_id:
        return jsonify({"error": "partNumber and stageId are required"}), 400

    user = g.get("current_user") or {}
    try:
        new_lot_no = lw.process_batch(
            tab_type=tab,
            part_number=part_number,
            stage_id=int(stage_id),
            processed_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"newLotNo": new_lot_no})


@laser_welding_bp.route("/check-open", methods=["GET"])
@require_access("rept")
def check_open() -> Any:
    tab = request.args.get("tab", "child_parts").strip()
    part_number = request.args.get("partNumber", "").strip()
    stage_id = request.args.get("stageId", type=int)
    if not part_number or not stage_id:
        return jsonify({"error": "partNumber and stageId are required"}), 400
    return jsonify({"hasOpenRow": lw.has_open_row(tab, part_number, stage_id)})
