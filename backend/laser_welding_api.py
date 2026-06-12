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


@laser_welding_bp.route("/meta", methods=["GET"])
@require_access("lw")
def meta() -> Any:
    work_date = request.args.get("date", "").strip()
    try:
        data = lw.get_meta(work_date)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(data)


@laser_welding_bp.route("/parts", methods=["GET"])
@require_access("lw")
def parts() -> Any:
    mode = request.args.get("mode", "production").strip()
    try:
        rows = lw.get_parts(mode)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "parts": rows})


@laser_welding_bp.route("/source-lots", methods=["GET"])
@require_access("lw")
def source_lots() -> Any:
    part_no = request.args.get("partNo", "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    try:
        lots = lw.get_source_lots(part_no)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/operators", methods=["GET"])
@require_access("lw")
def operators() -> Any:
    try:
        rows = lw.get_operators()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "operators": rows})


@laser_welding_bp.route("/rework-lots", methods=["GET"])
@require_access("lw")
def rework_lots() -> Any:
    part_no = request.args.get("partNo", "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    try:
        lots = lw.get_rework_lots(part_no)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/child-parts/rows", methods=["GET"])
@require_access("lw")
def child_parts_rows() -> Any:
    work_date = request.args.get("date", "").strip()
    batch_mode = request.args.get("mode", "production").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        rows = lw.get_child_parts_rows(work_date, batch_mode)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/child-parts/save", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def child_parts_save() -> Any:
    body = request.get_json(silent=True) or {}
    part_number = str(body.get("partNumber") or "").strip()
    work_date = str(body.get("workDate") or "").strip()
    batch_mode = str(body.get("batchMode") or "production").strip()
    lines = body.get("lines") or []
    lot_id = body.get("lotId")

    if not part_number or not work_date:
        return jsonify({"error": "partNumber and workDate are required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.save_child_parts(
            part_number=part_number,
            work_date=work_date,
            batch_mode=batch_mode,
            lines=lines,
            lot_id=int(lot_id) if lot_id else None,
            created_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/child-parts/pending", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def child_parts_pending() -> Any:
    body = request.get_json(silent=True) or {}
    part_number = str(body.get("partNumber") or "").strip()
    work_date = str(body.get("workDate") or "").strip()
    operator_id = body.get("operatorId")
    if not part_number or not work_date:
        return jsonify({"error": "partNumber and workDate are required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_lot(
            part_number=part_number,
            operator_id=int(operator_id),
            work_date=work_date,
            created_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/child-parts/inspect", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def child_parts_inspect() -> Any:
    body = request.get_json(silent=True) or {}
    lot_id = body.get("lotId")
    work_date = str(body.get("workDate") or "").strip()
    lines = body.get("lines") or []
    time_taken = body.get("timeTakenMinutes")
    if not lot_id:
        return jsonify({"error": "Pending inspection row is required — add part and operator first"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.inspect_production(
            lot_id=int(lot_id),
            work_date=work_date,
            lines=lines,
            time_taken_minutes=int(time_taken or 0),
            processed_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/child-parts/process", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def child_parts_process() -> Any:
    body = request.get_json(silent=True) or {}
    part_number = str(body.get("partNumber") or "").strip()
    work_date = str(body.get("workDate") or "").strip()
    if not part_number or not work_date:
        return jsonify({"error": "partNumber and workDate are required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.process_production(
            part_number=part_number,
            work_date=work_date,
            processed_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/child-parts/reinspect", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def child_parts_reinspect() -> Any:
    body = request.get_json(silent=True) or {}
    lot_id = body.get("lotId")
    work_date = str(body.get("workDate") or "").strip()
    line_id = body.get("lineId")
    if not lot_id:
        return jsonify({"error": "lotId is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not line_id:
        return jsonify({"error": "lineId is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.process_reinspect(
            lot_id=int(lot_id),
            work_date=work_date,
            line_id=int(line_id),
            processed_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/qa/rows", methods=["GET"])
@require_access("lw")
def qa_rows() -> Any:
    try:
        rows = lw.get_qa_rows()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/qa/lot/<int:lot_id>", methods=["GET"])
@require_access("lw")
def qa_lot_detail(lot_id: int) -> Any:
    lot = lw.get_lot_by_id(lot_id)
    if not lot:
        return jsonify({"error": "Lot not found"}), 404
    return jsonify(lot)


@laser_welding_bp.route("/qa/approve", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def qa_approve() -> Any:
    body = request.get_json(silent=True) or {}
    lot_id = body.get("lotId")
    if not lot_id:
        return jsonify({"error": "lotId is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.approve_qa(
            lot_id=int(lot_id),
            qa_passed=int(body.get("qaPassed") or 0),
            scrap=int(body.get("scrap") or 0),
            rework=int(body.get("rework") or 0),
            approved_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/rework/rows", methods=["GET"])
@require_access("lw")
def rework_rows() -> Any:
    try:
        rows = lw.get_rework_rows()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/rework/inward", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def rework_inward() -> Any:
    body = request.get_json(silent=True) or {}
    lot_id = body.get("lotId")
    if not lot_id:
        return jsonify({"error": "lotId is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.inward_rework(int(lot_id), user_id=user.get("userId"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/bom-customers", methods=["GET"])
@require_access("lw")
def bom_customers() -> Any:
    try:
        rows = lw.get_bom_customers()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "customers": rows})


@laser_welding_bp.route("/boms", methods=["GET"])
@require_access("lw")
def boms() -> Any:
    cust_raw = request.args.get("custId", "").strip()
    cust_id = int(cust_raw) if cust_raw else None
    try:
        rows = lw.get_boms(cust_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "boms": rows})


@laser_welding_bp.route("/boms/<bom_id>/children", methods=["GET"])
@require_access("lw")
def bom_children(bom_id: str) -> Any:
    try:
        rows = lw.get_bom_children(bom_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "children": rows})


@laser_welding_bp.route("/assembly/rows", methods=["GET"])
@require_access("lw")
def assembly_rows() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        rows = lw.get_assembly_rows(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/assembly/pending", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def assembly_pending() -> Any:
    body = request.get_json(silent=True) or {}
    bom_id = body.get("bomId")
    work_date = str(body.get("workDate") or "").strip()
    operator_id = body.get("operatorId")
    if not bom_id:
        return jsonify({"error": "bomId is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_assembly(
            bom_id=str(bom_id).strip(),
            operator_id=int(operator_id),
            work_date=work_date,
            created_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/assembly/child-lots", methods=["GET"])
@require_access("lw")
def assembly_child_lots() -> Any:
    part_no = request.args.get("partNo", "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    try:
        lots = lw.get_assembly_child_lots(part_no)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/assembly/weld", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def assembly_weld() -> Any:
    body = request.get_json(silent=True) or {}
    lot_id = body.get("lotId")
    work_date = str(body.get("workDate") or "").strip()
    weld_qty = body.get("weldQty")
    time_taken = body.get("timeTakenMinutes")
    consumptions = body.get("consumptions") or []
    if not lot_id:
        return jsonify({"error": "lotId is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.weld_assembly(
            lot_id=int(lot_id),
            work_date=work_date,
            weld_qty=int(weld_qty or 0),
            time_taken_minutes=int(time_taken or 0),
            consumptions=consumptions,
            processed_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/cleaning/rows", methods=["GET"])
@require_access("lw")
def cleaning_rows() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        rows = lw.get_cleaning_rows(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/cleaning/clean", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def cleaning_clean() -> Any:
    body = request.get_json(silent=True) or {}
    lot_id = body.get("lotId")
    lot_no = str(body.get("lotNo") or "").strip()
    qty = body.get("qty")
    operator_id = body.get("operatorId")
    work_date = str(body.get("workDate") or "").strip()
    if not lot_id:
        return jsonify({"error": "lotId is required"}), 400
    if not lot_no:
        return jsonify({"error": "lotNo is required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.clean_assembly(
            lot_id=int(lot_id),
            lot_no=lot_no,
            qty=int(qty or 0),
            operator_id=int(operator_id),
            work_date=work_date,
            processed_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/inspection/store-inspect", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def inspection_store_inspect() -> Any:
    body = request.get_json(silent=True) or {}
    lot_id = body.get("lotId")
    qty = body.get("qty")
    qa_qty = body.get("qaQty")
    time_taken = body.get("timeTakenMinutes")
    if not lot_id:
        return jsonify({"error": "lotId is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.inspect_store_assembly(
            lot_id=int(lot_id),
            qty=int(qty or 0),
            qa_qty=int(qa_qty or 0),
            time_taken_minutes=int(time_taken or 0),
            processed_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)
