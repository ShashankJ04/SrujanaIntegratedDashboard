"""Reports API Blueprint.

Port of dashboards/backend/src/routes/reports.ts.
"""

from __future__ import annotations

from io import BytesIO
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

from .auth import api_login_required
from .rbac import require_access, require_plus_access
from . import reports_store
from .db import fetch_all

reports_bp = Blueprint("reports_bp", __name__, url_prefix="/api/reports")


@reports_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


# ── Groups ──────────────────────────────────────────────────────────────

@reports_bp.route("/groups", methods=["GET"])
@require_access("rept")
def list_groups():
    return jsonify(reports_store.get_groups())


@reports_bp.route("/groups", methods=["POST"])
@require_plus_access("rept_plus")
def create_group():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"message": "Name is required"}), 400
    try:
        group = reports_store.create_group(name)
        return jsonify(group), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400


@reports_bp.route("/groups/<group_id>", methods=["DELETE"])
@require_plus_access("rept_plus")
def delete_group(group_id):
    try:
        reports_store.delete_group(group_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"message": str(e)}), 404


# ── Reports ─────────────────────────────────────────────────────────────

@reports_bp.route("/reports", methods=["GET"])
@require_access("rept")
def list_reports():
    group_id = request.args.get("groupId")
    return jsonify(reports_store.get_reports(group_id))


@reports_bp.route("/reports/<report_id>", methods=["GET"])
@require_access("rept")
def get_report(report_id):
    report = reports_store.get_report_by_id(report_id)
    if not report:
        return jsonify({"message": "Report not found"}), 404
    return jsonify(report)


@reports_bp.route("/reports", methods=["POST"])
@require_plus_access("rept_plus")
def create_report():
    data = request.get_json(force=True)
    try:
        report = reports_store.create_report(
            group_id=data.get("groupId", ""),
            name=data.get("name", ""),
            query_template=data.get("queryTemplate", ""),
        )
        return jsonify(report), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400


@reports_bp.route("/reports/<report_id>", methods=["PATCH"])
@require_plus_access("rept_plus")
def update_report(report_id):
    data = request.get_json(force=True)
    try:
        report = reports_store.update_report(
            report_id=report_id,
            name=data.get("name", ""),
            query_template=data.get("queryTemplate", ""),
        )
        return jsonify(report)
    except ValueError as e:
        return jsonify({"message": str(e)}), 400


@reports_bp.route("/reports/<report_id>", methods=["DELETE"])
@require_plus_access("rept_plus")
def delete_report(report_id):
    try:
        reports_store.delete_report(report_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"message": str(e)}), 404


# ── Run report ──────────────────────────────────────────────────────────

@reports_bp.route("/reports/<report_id>/run", methods=["POST"])
@require_access("rept")
def run_report(report_id):
    report = reports_store.get_report_by_id(report_id)
    if not report:
        return jsonify({"message": "Report not found"}), 404

    data = request.get_json(force=True, silent=True) or {}
    variables = data.get("variables", {})

    try:
        sql, params = reports_store.compile_report_query(
            report["queryTemplate"], variables
        )
    except ValueError as e:
        return jsonify({"message": str(e)}), 400

    try:
        rows = fetch_all(sql, tuple(params))
    except Exception as e:
        return jsonify({"message": f"Query error: {str(e)}"}), 400

    columns = list(rows[0].keys()) if rows else []

    return jsonify({
        "reportId": report_id,
        "columns": columns,
        "rows": rows,
        "rowCount": len(rows),
        "executedAt": datetime.utcnow().isoformat(),
    })


# ── Export report to Excel ──────────────────────────────────────────────

@reports_bp.route("/reports/<report_id>/export", methods=["POST"])
@require_access("rept")
def export_report(report_id):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side

    report = reports_store.get_report_by_id(report_id)
    if not report:
        return jsonify({"message": "Report not found"}), 404

    data = request.get_json(force=True, silent=True) or {}
    variables = data.get("variables", {})
    file_name = data.get("fileName", f"{report['name']}.xlsx")

    try:
        sql, params = reports_store.compile_report_query(
            report["queryTemplate"], variables
        )
    except ValueError as e:
        return jsonify({"message": str(e)}), 400

    try:
        rows = fetch_all(sql, tuple(params))
    except Exception as e:
        return jsonify({"message": f"Query error: {str(e)}"}), 400

    columns = list(rows[0].keys()) if rows else []

    wb = Workbook()
    ws = wb.active
    ws.title = report["name"][:31]

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    for ci, col in enumerate(columns, 1):
        cell = ws.cell(row=1, column=ci, value=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    for ri, row in enumerate(rows, 2):
        for ci, col in enumerate(columns, 1):
            cell = ws.cell(row=ri, column=ci, value=row.get(col))
            cell.border = thin_border

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=file_name,
    )
