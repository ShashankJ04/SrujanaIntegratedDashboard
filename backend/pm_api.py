"""Preventive Maintenance API Blueprint.

Port of dashboards/backend/src/routes/pm.ts.
"""

from __future__ import annotations

import os
from io import BytesIO
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file, send_from_directory, g, current_app

from .auth import api_login_required
from .rbac import require_access, require_plus_access, require_any_access
from . import pm_store

pm_bp = Blueprint("pm_bp", __name__, url_prefix="/api/pm")


@pm_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


# ── GET / — list all PM entries ─────────────────────────────────────────

@pm_bp.route("/", methods=["GET"])
@require_access("preventive_maintenance")
def list_entries():
    entries = pm_store.get_entries()
    return jsonify(entries)


# ── GET /status — PM status with percentage ─────────────────────────────

@pm_bp.route("/status", methods=["GET"])
@require_any_access(["preventive_maintenance", "life_report"])
def pm_status():
    from .db import fetch_all

    threshold = request.args.get("threshold", type=int, default=80)
    mode = request.args.get("mode", "above")

    rows = fetch_all(
        """
        SELECT
            tl.TL_tool_id          AS toolId,
            tl.TL_tool_number      AS toolNo,
            tl.TL_life_span        AS toolLife,
            tl.TL_spm              AS spm,
            tl.TL_preventive_maintenance_strokes AS pmStrokes,
            pm.PM_current_stroke   AS pmCurrentStroke,
            pm.PM_next_stroke      AS nextStroke,
            pm.PM_date             AS lastMaintenanceDate,
            COALESCE(strokes.totalStrokes, 0) AS totalLifetimeStrokes,
            COALESCE(pm_count.cnt, 0)         AS maintenanceCount
        FROM tool_life tl
        INNER JOIN (
            SELECT pm1.*
            FROM preventive_maintenance pm1
            INNER JOIN (
                SELECT PM_tool_number, MAX(PM_id) AS maxId
                FROM preventive_maintenance
                GROUP BY PM_tool_number
            ) latest_pm ON latest_pm.PM_tool_number = pm1.PM_tool_number
                AND latest_pm.maxId = pm1.PM_id
        ) pm ON pm.PM_tool_number = tl.TL_tool_number
        LEFT JOIN (
            SELECT
                comp.toolNo,
                MAX(comp.componentStrokes) AS totalStrokes
            FROM (
                SELECT
                    ct.CT_TOOLNO AS toolNo,
                    ct.CT_COMPID,
                    SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
                FROM production_details pd
                INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
                GROUP BY ct.CT_TOOLNO, ct.CT_COMPID
            ) comp
            GROUP BY comp.toolNo
        ) strokes ON strokes.toolNo = tl.TL_tool_number
        LEFT JOIN (
            SELECT PM_tool_number, COUNT(*) AS cnt
            FROM preventive_maintenance
            GROUP BY PM_tool_number
        ) pm_count ON pm_count.PM_tool_number = tl.TL_tool_number
        WHERE tl.TL_tool_id = (
            SELECT tl2.TL_tool_id
            FROM tool_life tl2
            WHERE tl2.TL_tool_number = tl.TL_tool_number
            ORDER BY tl2.TL_created_at DESC, tl2.TL_tool_id DESC
            LIMIT 1
        )
        """
    )

    results = []
    for r in rows:
        pm_current = int(r["pmCurrentStroke"] or 0)
        next_stroke = int(r["nextStroke"] or 0)
        total_lifetime = int(r["totalLifetimeStrokes"] or 0)

        pm_range = next_stroke - pm_current
        if pm_range > 0:
            pm_pct = round((total_lifetime - pm_current) / pm_range * 100)
        else:
            pm_pct = 0

        entry = {
            "toolId": r["toolId"],
            "toolNo": r["toolNo"],
            "toolLife": int(r["toolLife"]),
            "spm": int(r["spm"]),
            "pmStrokes": int(r["pmStrokes"]),
            "pmCurrentStroke": pm_current,
            "nextStroke": next_stroke,
            "totalLifetimeStrokes": total_lifetime,
            "pmPercentage": pm_pct,
            "maintenanceCount": int(r["maintenanceCount"]),
        }

        if mode == "all":
            results.append(entry)
        elif mode == "above" or mode not in ("all",):
            if pm_pct >= threshold:
                results.append(entry)

    return jsonify(results)


# ── GET /tool-strokes/<tool_id> ─────────────────────────────────────────

@pm_bp.route("/tool-strokes/<int:tool_id>", methods=["GET"])
@require_access("preventive_maintenance")
def tool_strokes(tool_id):
    total = pm_store.get_tool_strokes(tool_id)
    return jsonify({"totalStrokes": total})


# ── POST / — add entry ─────────────────────────────────────────────────

@pm_bp.route("/", methods=["POST"])
@require_plus_access("preventive_maintenance")
def add_entry():
    data = request.get_json(force=True)
    try:
        entry = pm_store.add_entry(
            tool_id=data["toolId"],
            tool_no=data["toolNo"],
            tool_life=data["toolLife"],
            spm=data["spm"],
            pm_strokes=data["pmStrokes"],
            next_stroke=data.get("nextStroke"),
        )
        return jsonify(entry), 201
    except ValueError as e:
        return jsonify({"message": str(e)}), 400


# ── PATCH /<tool_id> — update entry ─────────────────────────────────────

@pm_bp.route("/<int:tool_id>", methods=["PATCH"])
@require_plus_access("preventive_maintenance")
def update_entry(tool_id):
    data = request.get_json(force=True)
    try:
        entry = pm_store.update_entry(tool_id, data)
        return jsonify(entry)
    except ValueError as e:
        return jsonify({"message": str(e)}), 404


# ── GET /<tool_id>/stroke-info ──────────────────────────────────────────

@pm_bp.route("/<int:tool_id>/stroke-info", methods=["GET"])
@require_access("preventive_maintenance")
def stroke_info(tool_id):
    try:
        info = pm_store.get_stroke_info(tool_id)
        return jsonify(info)
    except ValueError as e:
        return jsonify({"message": str(e)}), 404


# ── POST /<tool_id>/confirm — confirm maintenance ──────────────────────

@pm_bp.route("/<int:tool_id>/confirm", methods=["POST"])
@require_plus_access("preventive_maintenance")
def confirm_maintenance(tool_id):
    next_stroke = request.form.get("nextStroke", type=int)
    if next_stroke is None:
        data = request.get_json(force=True, silent=True) or {}
        next_stroke = data.get("nextStroke")
    if next_stroke is None:
        return jsonify({"message": "nextStroke is required"}), 400

    attachment_name = None
    if "attachment" in request.files:
        f = request.files["attachment"]
        if f.filename:
            att_dir = current_app.config.get("PM_ATTACHMENTS_DIR", "pm-attachments")
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_dir = os.path.join(base_dir, att_dir)
            os.makedirs(full_dir, exist_ok=True)
            safe_name = f"{tool_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{f.filename}"
            f.save(os.path.join(full_dir, safe_name))
            attachment_name = f"/api/pm/attachment/{safe_name}"

    try:
        entry = pm_store.confirm_maintenance(tool_id, next_stroke, attachment_name)
        return jsonify(entry)
    except ValueError as e:
        return jsonify({"message": str(e)}), 404


# ── DELETE /<tool_id> ───────────────────────────────────────────────────

@pm_bp.route("/<int:tool_id>", methods=["DELETE"])
@require_plus_access("preventive_maintenance")
def delete_entry(tool_id):
    try:
        pm_store.delete_entry(tool_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"message": str(e)}), 404


# ── GET /attachment/<filename> ──────────────────────────────────────────

@pm_bp.route("/attachment/<path:filename>", methods=["GET"])
def serve_attachment(filename):
    att_dir = current_app.config.get("PM_ATTACHMENTS_DIR", "pm-attachments")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_dir = os.path.join(base_dir, att_dir)
    return send_from_directory(full_dir, filename)


# ── GET /export — Excel export ──────────────────────────────────────────

@pm_bp.route("/export", methods=["GET"])
@require_access("preventive_maintenance")
def export_pm():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from .db import fetch_all

    mode = request.args.get("mode", "all")
    search = request.args.get("search", "").strip().lower()

    # Reuse the same status query
    rows = fetch_all(
        """
        SELECT
            tl.TL_tool_id          AS toolId,
            tl.TL_tool_number      AS toolNo,
            tl.TL_life_span        AS toolLife,
            tl.TL_spm              AS spm,
            tl.TL_preventive_maintenance_strokes AS pmStrokes,
            pm.PM_current_stroke   AS pmCurrentStroke,
            pm.PM_next_stroke      AS nextStroke,
            pm.PM_date             AS lastMaintenanceDate,
            COALESCE(strokes.totalStrokes, 0) AS totalLifetimeStrokes,
            COALESCE(pm_count.cnt, 0)         AS maintenanceCount
        FROM tool_life tl
        INNER JOIN (
            SELECT pm1.*
            FROM preventive_maintenance pm1
            INNER JOIN (
                SELECT PM_tool_number, MAX(PM_id) AS maxId
                FROM preventive_maintenance
                GROUP BY PM_tool_number
            ) latest_pm ON latest_pm.PM_tool_number = pm1.PM_tool_number
                AND latest_pm.maxId = pm1.PM_id
        ) pm ON pm.PM_tool_number = tl.TL_tool_number
        LEFT JOIN (
            SELECT
                comp.toolNo,
                MAX(comp.componentStrokes) AS totalStrokes
            FROM (
                SELECT
                    ct.CT_TOOLNO AS toolNo,
                    ct.CT_COMPID,
                    SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
                FROM production_details pd
                INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
                GROUP BY ct.CT_TOOLNO, ct.CT_COMPID
            ) comp
            GROUP BY comp.toolNo
        ) strokes ON strokes.toolNo = tl.TL_tool_number
        LEFT JOIN (
            SELECT PM_tool_number, COUNT(*) AS cnt
            FROM preventive_maintenance
            GROUP BY PM_tool_number
        ) pm_count ON pm_count.PM_tool_number = tl.TL_tool_number
        WHERE tl.TL_tool_id = (
            SELECT tl2.TL_tool_id
            FROM tool_life tl2
            WHERE tl2.TL_tool_number = tl.TL_tool_number
            ORDER BY tl2.TL_created_at DESC, tl2.TL_tool_id DESC
            LIMIT 1
        )
        ORDER BY tl.TL_tool_number
        """
    )

    processed = []
    for r in rows:
        pm_current = int(r["pmCurrentStroke"] or 0)
        next_stroke = int(r["nextStroke"] or 0)
        total_lifetime = int(r["totalLifetimeStrokes"] or 0)
        pm_range = next_stroke - pm_current
        pm_pct = round((total_lifetime - pm_current) / pm_range * 100) if pm_range > 0 else 0

        tool_no = str(r["toolNo"]).lower()
        if search and search not in tool_no:
            continue
        if mode == "safe" and pm_pct >= 80:
            continue
        if mode == "warning" and not (80 <= pm_pct < 100):
            continue
        if mode == "critical" and pm_pct < 100:
            continue

        processed.append({
            "toolNo": r["toolNo"],
            "toolLife": int(r["toolLife"]),
            "spm": int(r["spm"]),
            "pmStrokes": int(r["pmStrokes"]),
            "totalLifetimeStrokes": total_lifetime,
            "nextStroke": next_stroke,
            "pmPercentage": pm_pct,
            "maintenanceCount": int(r["maintenanceCount"]),
            "lastMaintenanceDate": str(r["lastMaintenanceDate"] or ""),
        })

    wb = Workbook()
    ws = wb.active
    ws.title = "Preventive Maintenance"

    headers = [
        "Sl No", "Tool No", "Tool Life", "SPM", "PM Strokes",
        "Total Strokes", "Next PM Stroke", "PM %", "Maintenance Count",
        "Last Maintenance",
    ]

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    for row_idx, entry in enumerate(processed, 2):
        vals = [
            row_idx - 1, entry["toolNo"], entry["toolLife"], entry["spm"],
            entry["pmStrokes"], entry["totalLifetimeStrokes"], entry["nextStroke"],
            entry["pmPercentage"], entry["maintenanceCount"], entry["lastMaintenanceDate"],
        ]
        for col_idx, v in enumerate(vals, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=v)
            cell.border = thin_border

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="preventive_maintenance.xlsx",
    )
