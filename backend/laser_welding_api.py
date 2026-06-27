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
        info = lw.get_source_lots(part_no)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    lots = info.get("lots") or []
    return jsonify({
        "count": len(lots),
        "boMode": bool(info.get("boMode")),
        "availableQty": int(info.get("availableQty") or 0),
        "lots": lots,
    })


@laser_welding_bp.route("/operators", methods=["GET"])
@require_access("lw")
def operators() -> Any:
    try:
        rows = lw.get_operators()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "operators": rows})


@laser_welding_bp.route("/machines", methods=["GET"])
@require_access("lw")
def machines() -> Any:
    type_raw = request.args.get("type", "").strip()
    machine_type = int(type_raw) if type_raw else None
    try:
        rows = lw.get_lw_machines(machine_type)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "machines": rows})


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
    operator_id = body.get("operatorId")

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
            operator_id=int(operator_id) if operator_id else None,
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


@laser_welding_bp.route("/draft-line/delete", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def delete_draft_line() -> Any:
    body = request.get_json(silent=True) or {}
    line_id = body.get("draftLineId") or body.get("lineId")
    if not line_id:
        return jsonify({"error": "draftLineId is required"}), 400
    try:
        lw.delete_pending_draft_line(int(line_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@laser_welding_bp.route("/child-parts/inspect", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def child_parts_inspect() -> Any:
    body = request.get_json(silent=True) or {}
    draft_line_id = body.get("draftLineId") or body.get("lineId")
    work_date = str(body.get("workDate") or "").strip()
    lines = body.get("lines") or []
    time_taken = body.get("timeTakenMinutes")
    if not draft_line_id:
        return jsonify({"error": "Pending inspection row is required — add part and operator first"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.inspect_production(
            draft_line_id=int(draft_line_id),
            work_date=work_date,
            lines=lines,
            time_taken_minutes=int(time_taken or 0),
            processed_by=user.get("userId"),
            ot_flag=body.get("otFlag"),
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
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        rows = lw.get_qa_inspect_rows(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/qa/eligible", methods=["GET"])
@require_access("lw")
def qa_eligible() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        items = lw.get_qa_eligible_parts(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(items), "items": items})


@laser_welding_bp.route("/qa/source-lots", methods=["GET"])
@require_access("lw")
def qa_source_lots() -> Any:
    part_no = request.args.get("partNo", "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    try:
        lots = lw.get_qa_source_lots(part_no)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/qa/pending", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def qa_pending() -> Any:
    body = request.get_json(silent=True) or {}
    part_number = str(body.get("partNumber") or body.get("partNo") or "").strip()
    work_date = str(body.get("workDate") or "").strip()
    operator_id = body.get("operatorId")
    if not part_number or not work_date:
        return jsonify({"error": "partNumber and workDate are required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_qa(
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


@laser_welding_bp.route("/qa/inspect", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def qa_inspect() -> Any:
    body = request.get_json(silent=True) or {}
    draft_line_id = body.get("draftLineId") or body.get("lineId")
    work_date = str(body.get("workDate") or "").strip()
    lines = body.get("lines") or []
    time_taken = body.get("timeTakenMinutes")
    if not draft_line_id:
        return jsonify({"error": "Pending QA row is required — add part and operator first"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.inspect_qa(
            draft_line_id=int(draft_line_id),
            work_date=work_date,
            lines=lines,
            time_taken_minutes=int(time_taken or 0),
            ot_flag=body.get("otFlag"),
            processed_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


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


@laser_welding_bp.route("/packing/rows", methods=["GET"])
@require_access("lw")
def packing_rows() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        rows = lw.get_packing_inspect_rows(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/packing/source-lots", methods=["GET"])
@require_access("lw")
def packing_source_lots() -> Any:
    part_no = request.args.get("partNo", "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    try:
        lots = lw.get_packing_source_lots(part_no)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/packing/parts", methods=["GET"])
@require_access("lw")
def packing_parts_catalog() -> Any:
    try:
        parts = lw.get_packing_parts_catalog()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(parts), "parts": parts})


@laser_welding_bp.route("/packing/pack-materials", methods=["GET"])
@require_access("lw")
def packing_pack_materials() -> Any:
    part_no = request.args.get("partNo", "").strip()
    try:
        catalog = lw.get_packing_pack_materials(part_no or None)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    materials = catalog.get("materials") or []
    return jsonify({
        "count": len(materials),
        "trays": catalog.get("trays") or [],
        "cartons": catalog.get("cartons") or [],
        "materials": materials,
        "hasMapping": catalog.get("hasMapping", False),
        "mapping": catalog.get("mapping"),
    })


@laser_welding_bp.route("/packing/trays-carton", methods=["GET"])
@require_access("lw")
def trays_carton_list() -> Any:
    try:
        from . import lw_packing_materials as pm
        rows = pm.list_part_maps()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({
        "count": len(rows),
        "rows": rows,
        "cartons": pm.list_all_cartons(),
    })


@laser_welding_bp.route("/packing/trays-carton/legend", methods=["GET"])
@require_access("lw")
def trays_carton_legend() -> Any:
    from . import lw_packing_materials as pm
    return jsonify(pm.get_legend())


@laser_welding_bp.route("/packing/trays-carton/preview", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def trays_carton_preview() -> Any:
    from . import lw_packing_materials as pm
    body = request.get_json(silent=True) or {}
    kind = str(body.get("kind") or "tray").strip().lower()
    try:
        if kind == "tray":
            result = pm.preview_tray(body)
        elif kind in ("carton", "bin", "box"):
            result = pm.preview_box(body)
        else:
            result = pm.preview_box(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/packing/trays-carton/parts", methods=["GET"])
@require_access("lw")
def trays_carton_parts_catalog() -> Any:
    cust_id = request.args.get("custId", "").strip()
    try:
        parts = lw.get_trays_carton_parts_catalog(int(cust_id) if cust_id else None)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(parts), "parts": parts})


@laser_welding_bp.route("/packing/trays-carton/matching-trays", methods=["GET"])
@require_access("lw")
def trays_carton_matching_trays() -> Any:
    from . import lw_packing_materials as pm
    cust_id = request.args.get("custId", "").strip()
    tray_type = request.args.get("trayType", "").strip()
    cavity = request.args.get("cavity", "").strip()
    if not tray_type or not cavity:
        return jsonify({"items": []})
    try:
        items = pm.list_matching_trays(
            int(cust_id) if cust_id else None,
            tray_type,
            int(cavity),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"items": items})


@laser_welding_bp.route("/packing/trays-carton/matching-boxes", methods=["GET"])
@require_access("lw")
def trays_carton_matching_boxes() -> Any:
    from . import lw_packing_materials as pm
    cust_id = request.args.get("custId", "").strip()
    box_type = request.args.get("boxType", "C").strip()
    try:
        items = pm.list_matching_boxes(
            int(cust_id) if cust_id else None,
            box_type,
            int(request.args.get("lengthMm", "0")),
            int(request.args.get("widthMm", "0")),
            int(request.args.get("heightMm", "0")),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"items": items})


@laser_welding_bp.route("/packing/trays-carton/resolve-part", methods=["GET"])
@require_access("lw")
def trays_carton_resolve_part() -> Any:
    from . import lw_packing_materials as pm
    part_no = request.args.get("partNo", "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    cust_raw = request.args.get("custId", "").strip()
    bom_id = request.args.get("bomId", "").strip() or None
    cust_id = int(cust_raw) if cust_raw else None
    resolved = pm.resolve_part_for_mapping(
        part_no,
        cust_id=cust_id,
        bom_id=bom_id,
    )
    if not resolved:
        return jsonify({"error": f"Part {part_no} not found in components or BOM"}), 404
    return jsonify(resolved)


@laser_welding_bp.route("/packing/trays-carton", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def trays_carton_create() -> Any:
    from . import lw_packing_materials as pm
    body = request.get_json(silent=True) or {}
    user = g.get("current_user") or {}
    try:
        result = pm.create_trays_carton_mapping(body, created_by=user.get("userId"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/packing/trays-carton/<int:map_id>", methods=["PUT"])
@require_access("lw")
@require_plus_access("lw_plus")
def trays_carton_update(map_id: int) -> Any:
    from . import lw_packing_materials as pm
    body = request.get_json(silent=True) or {}
    user = g.get("current_user") or {}
    try:
        result = pm.update_trays_carton_mapping(map_id, body, updated_by=user.get("userId"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/packing/pending", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def packing_pending() -> Any:
    body = request.get_json(silent=True) or {}
    part_number = str(body.get("partNumber") or body.get("partNo") or "").strip()
    work_date = str(body.get("workDate") or "").strip()
    operator_id = body.get("operatorId")
    if not part_number or not work_date:
        return jsonify({"error": "partNumber and workDate are required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_packing(
            part_no=part_number,
            operator_id=int(operator_id),
            work_date=work_date,
            created_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/packing/inspect", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def packing_inspect() -> Any:
    body = request.get_json(silent=True) or {}
    draft_line_id = body.get("draftLineId") or body.get("lineId")
    work_date = str(body.get("workDate") or "").strip()
    lines = body.get("lines") or []
    time_taken = body.get("timeTakenMinutes")
    if not draft_line_id:
        return jsonify({"error": "Pending packing row is required — add part and operator first"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.inspect_packing(
            draft_line_id=int(draft_line_id),
            work_date=work_date,
            lines=lines,
            tray_qty=int(body.get("trayQty") or 0),
            carton_qty=int(body.get("cartonQty") or 0),
            time_taken_minutes=int(time_taken or 0),
            ot_flag=body.get("otFlag"),
            processed_by=user.get("userId"),
            tray_item_code=body.get("trayItemCode") or body.get("tray_item_code"),
            carton_item_code=body.get("cartonItemCode") or body.get("carton_item_code"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/packing/pack", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def packing_pack() -> Any:
    body = request.get_json(silent=True) or {}
    lot_id = body.get("lotId")
    if not lot_id:
        return jsonify({"error": "lotId is required"}), 400
    pack_qty = body.get("packQty")
    if pack_qty is None:
        return jsonify({"error": "packQty is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.pack_lot(
            lot_id=int(lot_id),
            pack_qty=int(pack_qty),
            work_date=str(body.get("workDate") or "").strip() or None,
            packed_by=user.get("userId"),
        )
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
    machine_id = body.get("machineId")
    if not bom_id:
        return jsonify({"error": "bomId is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400
    if not machine_id:
        return jsonify({"error": "Machine is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_assembly(
            bom_id=str(bom_id).strip(),
            operator_id=int(operator_id),
            machine_id=int(machine_id),
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
    draft_line_id = body.get("draftLineId") or body.get("lineId")
    work_date = str(body.get("workDate") or "").strip()
    weld_qty = body.get("weldQty")
    time_taken = body.get("timeTakenMinutes")
    consumptions = body.get("consumptions") or []
    if not draft_line_id:
        return jsonify({"error": "Pending assembly row is required — add BOM and operator first"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    operator_id = body.get("operatorId")

    user = g.get("current_user") or {}
    try:
        result = lw.weld_assembly(
            draft_line_id=int(draft_line_id),
            work_date=work_date,
            weld_qty=int(weld_qty or 0),
            time_taken_minutes=int(time_taken or 0),
            consumptions=consumptions,
            operator_id=int(operator_id) if operator_id else None,
            processed_by=user.get("userId"),
            ot_flag=body.get("otFlag"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/assembly/rework/boms", methods=["GET"])
@require_access("lw")
def assembly_rework_boms() -> Any:
    cust_raw = request.args.get("custId", "").strip()
    cust_id = int(cust_raw) if cust_raw else None
    try:
        rows = lw.get_rework_weld_boms(cust_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "boms": rows})


@laser_welding_bp.route("/assembly/rework/target-lots", methods=["GET"])
@require_access("lw")
def assembly_rework_target_lots() -> Any:
    bom_id = request.args.get("bomId", "").strip()
    if not bom_id:
        return jsonify({"error": "bomId is required"}), 400
    try:
        lots = lw.get_rework_weld_target_lots(bom_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/assembly/rework/rows", methods=["GET"])
@require_access("lw")
def assembly_rework_rows() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        rows = lw.get_rework_weld_rows(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/assembly/rework/eligible", methods=["GET"])
@require_access("lw")
def assembly_rework_eligible() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        items = lw.get_rework_weld_eligible_items(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(items), "items": items})


@laser_welding_bp.route("/assembly/rework/pending", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def assembly_rework_pending() -> Any:
    body = request.get_json(silent=True) or {}
    bom_id = body.get("bomId")
    work_date = str(body.get("workDate") or "").strip()
    operator_id = body.get("operatorId")
    machine_id = body.get("machineId")
    if not bom_id:
        return jsonify({"error": "bomId is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400
    if not machine_id:
        return jsonify({"error": "Machine is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_rework_weld(
            bom_id=str(bom_id).strip(),
            operator_id=int(operator_id),
            machine_id=int(machine_id),
            work_date=work_date,
            created_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/assembly/rework/weld", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def assembly_rework_weld() -> Any:
    body = request.get_json(silent=True) or {}
    draft_line_id = body.get("draftLineId") or body.get("lineId")
    work_date = str(body.get("workDate") or "").strip()
    target_lot_id = body.get("targetLotId")
    rework_qty = body.get("reworkQty") or body.get("weldQty")
    time_taken = body.get("timeTakenMinutes")
    consumptions = body.get("consumptions") or []
    if not draft_line_id:
        return jsonify({"error": "Pending re-work row is required — add BOM and operator first"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not target_lot_id:
        return jsonify({"error": "Target assembly lot is required"}), 400

    operator_id = body.get("operatorId")
    user = g.get("current_user") or {}
    try:
        result = lw.weld_rework_assembly(
            draft_line_id=int(draft_line_id),
            work_date=work_date,
            target_lot_id=int(target_lot_id),
            rework_qty=int(rework_qty or 0),
            time_taken_minutes=int(time_taken or 0),
            consumptions=consumptions,
            operator_id=int(operator_id) if operator_id else None,
            processed_by=user.get("userId"),
            ot_flag=body.get("otFlag"),
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


@laser_welding_bp.route("/cleaning/source-lots", methods=["GET"])
@require_access("lw")
def cleaning_source_lots() -> Any:
    bom_id = request.args.get("bomId", "").strip()
    sub_assembly_part_no = request.args.get("subAssemblyPartNo", "").strip()
    if not bom_id:
        return jsonify({"error": "bomId is required"}), 400
    try:
        lots = lw.get_cleaning_source_lots(
            bom_id,
            sub_assembly_part_no or None,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/cleaning/pending", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def cleaning_pending() -> Any:
    body = request.get_json(silent=True) or {}
    bom_id = body.get("bomId")
    work_date = str(body.get("workDate") or "").strip()
    operator_id = body.get("operatorId")
    sub_assembly_part_no = body.get("subAssemblyPartNo")
    if not bom_id:
        return jsonify({"error": "bomId is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_cleaning(
            bom_id=str(bom_id).strip(),
            operator_id=int(operator_id),
            work_date=work_date,
            created_by=user.get("userId"),
            sub_assembly_part_no=str(sub_assembly_part_no).strip() if sub_assembly_part_no else None,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/cleaning/inspect", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def cleaning_inspect() -> Any:
    body = request.get_json(silent=True) or {}
    draft_line_id = body.get("draftLineId") or body.get("lineId")
    work_date = str(body.get("workDate") or "").strip()
    lines = body.get("lines") or []
    time_taken = body.get("timeTakenMinutes")
    if not draft_line_id:
        return jsonify({"error": "Pending cleaning row is required — add BOM and operator first"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.inspect_assembly(
            draft_line_id=int(draft_line_id),
            work_date=work_date,
            lines=lines,
            time_taken_minutes=int(time_taken or 0),
            processed_by=user.get("userId"),
            ot_flag=body.get("otFlag"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/sub-assembly/parts", methods=["GET"])
@require_access("lw")
def sub_assembly_parts_catalog() -> Any:
    cust_raw = request.args.get("custId", "").strip()
    bom_id = request.args.get("bomId", "").strip()
    cust_id = int(cust_raw) if cust_raw else None
    try:
        rows = lw.get_all_sub_assembly_parts(
            cust_id=cust_id,
            bom_id=bom_id or None,
            rework_only=False,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "parts": rows})


@laser_welding_bp.route("/sub-assembly/boms", methods=["GET"])
@require_access("lw")
def sub_assembly_boms() -> Any:
    cust_raw = request.args.get("custId", "").strip()
    cust_id = int(cust_raw) if cust_raw else None
    try:
        rows = lw.get_sub_assembly_boms(cust_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "boms": rows})


@laser_welding_bp.route("/sub-assembly/boms/<bom_id>/parts", methods=["GET"])
@require_access("lw")
def sub_assembly_bom_parts(bom_id: str) -> Any:
    try:
        rows = lw.get_sub_assembly_parts(bom_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "parts": rows})


@laser_welding_bp.route("/sub-assembly/boms/<bom_id>/children", methods=["GET"])
@require_access("lw")
def sub_assembly_bom_children(bom_id: str) -> Any:
    sub_assembly_part_no = request.args.get("subAssemblyPartNo", "").strip()
    if not sub_assembly_part_no:
        return jsonify({"error": "subAssemblyPartNo is required"}), 400
    try:
        rows = lw.get_sub_assembly_children(bom_id, sub_assembly_part_no)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "children": rows})


@laser_welding_bp.route("/sub-assembly/rows", methods=["GET"])
@require_access("lw")
def sub_assembly_rows() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        rows = lw.get_sub_assembly_rows(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/sub-assembly/pending", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def sub_assembly_pending() -> Any:
    body = request.get_json(silent=True) or {}
    bom_id = body.get("bomId")
    sub_assembly_part_no = str(body.get("subAssemblyPartNo") or body.get("partNo") or "").strip()
    work_date = str(body.get("workDate") or "").strip()
    operator_id = body.get("operatorId")
    machine_id = body.get("machineId")
    if not sub_assembly_part_no:
        return jsonify({"error": "subAssemblyPartNo is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400
    if not machine_id:
        return jsonify({"error": "Machine is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_sub_assembly(
            sub_assembly_part_no=sub_assembly_part_no,
            operator_id=int(operator_id),
            machine_id=int(machine_id),
            work_date=work_date,
            bom_id=str(bom_id).strip() if bom_id else None,
            created_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/sub-assembly/child-lots", methods=["GET"])
@require_access("lw")
def sub_assembly_child_lots() -> Any:
    part_no = request.args.get("partNo", "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    try:
        lots = lw.get_sub_assembly_child_lots(part_no)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/sub-assembly/weld", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def sub_assembly_weld() -> Any:
    body = request.get_json(silent=True) or {}
    draft_line_id = body.get("draftLineId") or body.get("lineId")
    work_date = str(body.get("workDate") or "").strip()
    weld_qty = body.get("weldQty")
    time_taken = body.get("timeTakenMinutes")
    consumptions = body.get("consumptions") or []
    operator_id = body.get("operatorId")
    if not draft_line_id:
        return jsonify({"error": "Pending sub-assembly row is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.weld_sub_assembly(
            draft_line_id=int(draft_line_id),
            work_date=work_date,
            weld_qty=int(weld_qty or 0),
            time_taken_minutes=int(time_taken or 0),
            consumptions=consumptions,
            operator_id=int(operator_id) if operator_id else None,
            processed_by=user.get("userId"),
            ot_flag=body.get("otFlag"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/sub-assembly/rework/parts", methods=["GET"])
@require_access("lw")
def sub_assembly_rework_parts_catalog() -> Any:
    cust_raw = request.args.get("custId", "").strip()
    bom_id = request.args.get("bomId", "").strip()
    cust_id = int(cust_raw) if cust_raw else None
    try:
        rows = lw.get_all_sub_assembly_parts(
            cust_id=cust_id,
            bom_id=bom_id or None,
            rework_only=True,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "parts": rows})


@laser_welding_bp.route("/sub-assembly/rework/boms", methods=["GET"])
@require_access("lw")
def sub_assembly_rework_boms() -> Any:
    cust_raw = request.args.get("custId", "").strip()
    cust_id = int(cust_raw) if cust_raw else None
    try:
        rows = lw.get_rework_sub_assembly_boms(cust_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "boms": rows})


@laser_welding_bp.route("/sub-assembly/rework/target-lots", methods=["GET"])
@require_access("lw")
def sub_assembly_rework_target_lots() -> Any:
    bom_id = request.args.get("bomId", "").strip()
    sub_assembly_part_no = request.args.get("subAssemblyPartNo", "").strip()
    if not bom_id:
        return jsonify({"error": "bomId is required"}), 400
    try:
        lots = lw.get_rework_sub_assembly_target_lots(
            bom_id,
            sub_assembly_part_no or None,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(lots), "lots": lots})


@laser_welding_bp.route("/sub-assembly/rework/rows", methods=["GET"])
@require_access("lw")
def sub_assembly_rework_rows() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        rows = lw.get_rework_sub_assembly_rows(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(rows), "rows": rows})


@laser_welding_bp.route("/sub-assembly/rework/eligible", methods=["GET"])
@require_access("lw")
def sub_assembly_rework_eligible() -> Any:
    work_date = request.args.get("date", "").strip()
    if not work_date:
        return jsonify({"error": "date is required"}), 400
    try:
        items = lw.get_rework_sub_assembly_eligible_items(work_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"count": len(items), "items": items})


@laser_welding_bp.route("/sub-assembly/rework/pending", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def sub_assembly_rework_pending() -> Any:
    body = request.get_json(silent=True) or {}
    bom_id = body.get("bomId")
    sub_assembly_part_no = str(body.get("subAssemblyPartNo") or body.get("partNo") or "").strip()
    work_date = str(body.get("workDate") or "").strip()
    operator_id = body.get("operatorId")
    if not sub_assembly_part_no:
        return jsonify({"error": "subAssemblyPartNo is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not operator_id:
        return jsonify({"error": "Operator is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.create_pending_rework_sub_assembly(
            sub_assembly_part_no=sub_assembly_part_no,
            operator_id=int(operator_id),
            work_date=work_date,
            bom_id=str(bom_id).strip() if bom_id else None,
            created_by=user.get("userId"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@laser_welding_bp.route("/sub-assembly/rework/weld", methods=["POST"])
@require_access("lw")
@require_plus_access("lw_plus")
def sub_assembly_rework_weld() -> Any:
    body = request.get_json(silent=True) or {}
    draft_line_id = body.get("draftLineId") or body.get("lineId")
    work_date = str(body.get("workDate") or "").strip()
    target_lot_id = body.get("targetLotId")
    rework_qty = body.get("reworkQty") or body.get("weldQty")
    time_taken = body.get("timeTakenMinutes")
    consumptions = body.get("consumptions") or []
    operator_id = body.get("operatorId")
    if not draft_line_id:
        return jsonify({"error": "Pending re-work sub-assembly row is required"}), 400
    if not work_date:
        return jsonify({"error": "workDate is required"}), 400
    if not target_lot_id:
        return jsonify({"error": "Target sub-assembly lot is required"}), 400

    user = g.get("current_user") or {}
    try:
        result = lw.weld_rework_sub_assembly(
            draft_line_id=int(draft_line_id),
            work_date=work_date,
            target_lot_id=int(target_lot_id),
            rework_qty=int(rework_qty or 0),
            time_taken_minutes=int(time_taken or 0),
            consumptions=consumptions,
            operator_id=int(operator_id) if operator_id else None,
            processed_by=user.get("userId"),
            ot_flag=body.get("otFlag"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)
