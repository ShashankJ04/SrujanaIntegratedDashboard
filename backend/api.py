from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, List

from flask import Blueprint, current_app, g, jsonify, request, url_for

from .auth import api_login_required, is_dpr_editor
from .dispatch_calendar import build_dispatch_calendar_payload
from .rbac import require_access
from .export import generate_excel_response
from .db import execute, fetch_one
from .models import (
    get_dashboard_base_rows,
    get_dashboard_rows_with_buffer,
    get_rm_chart_data,
    get_rows,
    get_table_columns,
    get_buffer_config_for_all_parts,
    get_buffer_config_for_part,
    get_completion_buckets,
    get_pending_treemap,
    get_production_vs_requirement,
    get_report_summary,
    get_top_shortfalls,
    refresh_dashboard_base_cache,
    upsert_buffer_config,
    get_dpr_machine_options,
    fetch_dpr_machine_qr_row,
    fetch_dpr_machine_by_qr_token,
    get_dpr_qr_storage_dir,
    write_dpr_machine_qr_png,
    get_dpr_part_options,
    list_dpr_rows,
    get_machine_dpr_payload,
    upsert_dpr_row,
    delete_dpr_row,
    get_dpr_derived_preview,
    get_dpr_summary,
    get_dpr_version,
    upsert_dpr_snapshot,
    get_hub_pulse_feed,
)


api_bp = Blueprint("api", __name__)


@api_bp.before_request
def _require_auth():
    """Allow anonymous GET for Machine DPR QR scan + DPR version polling on that page."""
    path = request.path or ""
    if request.method == "GET" and (
        (path.startswith("/api/dpr/machine/") and path.endswith("/today"))
        or path.startswith("/api/dpr/version")
    ):
        return None
    return api_login_required()


def _parse_int(name: str, default: int) -> int:
    value = request.args.get(name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_iso_date(name: str) -> str:
    raw = (request.args.get(name) or "").strip()
    if not raw:
        raise ValueError("missing date")
    date.fromisoformat(raw)
    return raw


@api_bp.get("/columns")
def columns() -> Any:
    cols = get_table_columns()
    return jsonify([c.__dict__ for c in cols])


@api_bp.get("/rows")
def rows() -> Any:
    page = _parse_int("page", 1)
    page_size = _parse_int("pageSize", 25)
    search = request.args.get("search") or None
    sort_by = request.args.get("sortBy") or None
    sort_dir = request.args.get("sortDir") or None

    result = get_rows(
        page=page,
        page_size=page_size,
        global_search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return jsonify(result)


@api_bp.get("/dashboard-metrics")
def dashboard_metrics() -> Any:
    page = _parse_int("page", 1)
    page_size = _parse_int("pageSize", 25)
    search = request.args.get("search") or None
    sort_by = request.args.get("sortBy") or None
    sort_dir = request.args.get("sortDir") or None

    result = get_dashboard_base_rows(
        page=page,
        page_size=page_size,
        global_search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return jsonify(result)


@api_bp.get("/dashboard-rows")
def dashboard_rows() -> Any:
    page = _parse_int("page", 1)
    page_size = _parse_int("pageSize", 25)
    search = request.args.get("search") or None
    sort_by = request.args.get("sortBy") or None
    sort_dir = request.args.get("sortDir") or None
    row_filter = request.args.get("rowFilter") or None

    result = get_dashboard_rows_with_buffer(
        page=page,
        page_size=page_size,
        global_search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        row_filter=row_filter,
    )
    return jsonify(result)


@api_bp.post("/dashboard-refresh")
def dashboard_refresh() -> Any:
    cache = refresh_dashboard_base_cache()
    rows = cache.get("rows") or []
    last_refreshed = cache.get("last_refreshed")
    return jsonify(
        {
            "count": len(rows),
            "lastRefreshed": last_refreshed.isoformat() if last_refreshed else None,
        }
    )


@api_bp.get("/buffer-config")
def buffer_config_list() -> Any:
    configs = get_buffer_config_for_all_parts()
    return jsonify(configs)


@api_bp.get("/buffer-config/<part_no>")
def buffer_config_detail(part_no: str) -> Any:
    qty = get_buffer_config_for_part(part_no)
    if qty is None:
        return jsonify({"part_no": part_no, "buffer_qty": 0.0})
    return jsonify({"part_no": part_no, "buffer_qty": qty})


@api_bp.put("/buffer-config/<part_no>")
def buffer_config_update(part_no: str) -> Any:
    user = g.current_user
    from .auth import is_buffer_editor
    if not is_buffer_editor(user):
        return jsonify({"error": "You are not allowed to edit buffer configuration"}), 403

    payload = request.get_json(silent=True) or {}
    try:
        buffer_qty = float(payload.get("buffer_qty", 0.0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid buffer_qty"}), 400

    if buffer_qty > 999999 or buffer_qty < -999999:
        return jsonify({"error": "buffer_qty must be between -999999 and 999999"}), 400

    updated_by = user.get("login")
    upsert_buffer_config(part_no, buffer_qty, updated_by)
    return jsonify({"part_no": part_no, "buffer_qty": buffer_qty})


@api_bp.get("/export")
def export() -> Any:
    search = request.args.get("search") or ""
    sort_by = request.args.get("sortBy") or ""
    sort_dir = request.args.get("sortDir") or ""
    row_filter = request.args.get("rowFilter") or None
    return generate_excel_response(
        global_search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        row_filter=row_filter,
    )


@api_bp.get("/reports/summary")
def reports_summary() -> Any:
    summary = get_report_summary()
    return jsonify(summary)


@api_bp.get("/reports/production-vs-requirement")
def reports_production_vs_requirement() -> Any:
    limit = _parse_int("limit", 15)
    data = get_production_vs_requirement(limit=limit)
    return jsonify(data)


@api_bp.get("/reports/completion-buckets")
def reports_completion_buckets() -> Any:
    data = get_completion_buckets()
    return jsonify(data)


@api_bp.get("/reports/top-shortfalls")
def reports_top_shortfalls() -> Any:
    limit = _parse_int("limit", 20)
    items = get_top_shortfalls(limit=limit)
    return jsonify(items)


@api_bp.get("/reports/pending-treemap")
def reports_pending_treemap() -> Any:
    limit = _parse_int("limit", 40)
    data = get_pending_treemap(limit=limit)
    return jsonify(data)


@api_bp.get("/dashboard/rm-charts")
def dashboard_rm_charts() -> Any:
    limit = _parse_int("limit", 20)
    data = get_rm_chart_data(limit=limit)
    return jsonify(data)


@api_bp.get("/hub/pulse")
def hub_pulse() -> Any:
    """Hub top-bar ticker: recent ERP production + today's DPR line count (no warehouse DB)."""
    try:
        items = get_hub_pulse_feed()
        return jsonify(items)
    except Exception as e:
        current_app.logger.warning("hub_pulse: %s", e)
        return jsonify([])


# ── DPR — Daily Production Review ─────────────────────────────────────

@api_bp.get("/dpr/options")
def dpr_options() -> Any:
    return jsonify(
        {
            "machines": get_dpr_machine_options(),
            "parts": get_dpr_part_options(),
        }
    )


@api_bp.get("/dpr/qr-list")
def dpr_qr_list() -> Any:
    """DPR machine QR: `dpr_machine_qr` table + `qr-codes/` files. Scan URL = http://MACHINE_IP:PORT/machine/<qr_token>."""
    from .dpr_qr_util import build_dpr_machine_scan_url

    cfg = current_app.config
    qr_dir = get_dpr_qr_storage_dir()

    items: List[Dict[str, Any]] = []
    for m in get_dpr_machine_options():
        mid = str(m.get("id") or "").strip()
        if not mid:
            continue
        label = str(m.get("label") or mid)
        row = fetch_dpr_machine_qr_row(mid)
        if not row or not row.get("qr_token"):
            continue
        token = str(row["qr_token"])
        png_fn = str(row.get("png_filename") or "").strip()
        scan_url = build_dpr_machine_scan_url(cfg, token)
        safe_name = os.path.basename(png_fn) if png_fn else f"{token}.png"
        fp = qr_dir / safe_name
        if not fp.is_file():
            try:
                write_dpr_machine_qr_png(fp, scan_url, label)
                if not png_fn:
                    execute(
                        "UPDATE dpr_machine_qr SET png_filename = %s WHERE machine_id = %s",
                        (safe_name, mid),
                    )
            except Exception:
                continue
        if not fp.is_file():
            continue
        # Same-origin URL so the Hub modal img loads regardless of MACHINE_IP / how the user opened the app.
        png_url = url_for("qr_codes_file", filename=safe_name)
        items.append(
            {
                "machineId": mid,
                "machineLabel": label,
                "pngUrl": png_url,
                "scanUrl": scan_url,
                "qrToken": token,
            }
        )
    return jsonify({"items": items})


@api_bp.get("/dpr/derived")
def dpr_derived() -> Any:
    part_no = (request.args.get("partNo") or "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400
    raw = request.args.get("plannedQty", "0")
    try:
        planned = float(raw) if raw not in ("", None) else 0.0
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid plannedQty"}), 400
    review_date = (request.args.get("date") or "").strip()
    if review_date:
        try:
            date.fromisoformat(review_date)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid date"}), 400
    data = get_dpr_derived_preview(part_no, planned, review_date or None)
    return jsonify(data)


@api_bp.get("/dpr/summary")
def dpr_summary() -> Any:
    try:
        d = _parse_iso_date("date")
    except ValueError:
        return jsonify({"error": "Invalid or missing date (use YYYY-MM-DD)"}), 400
    try:
        data = get_dpr_summary(d)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(data)


@api_bp.get("/dpr/rows")
def dpr_rows() -> Any:
    try:
        d = _parse_iso_date("date")
    except ValueError:
        return jsonify({"error": "Invalid or missing date (use YYYY-MM-DD)"}), 400
    rows = list_dpr_rows(d)
    return jsonify({"date": d, "rows": rows})


@api_bp.put("/dpr/rows")
def dpr_rows_save() -> Any:
    if not is_dpr_editor(g.current_user):
        return jsonify({"error": "You are not allowed to edit Daily Production Review"}), 403

    payload = request.get_json(silent=True) or {}
    review_date = str(payload.get("reviewDate") or "").strip()
    try:
        date.fromisoformat(review_date)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid reviewDate"}), 400

    machine_id = str(payload.get("machineId") or "").strip()
    part_no = str(payload.get("partNo") or "").strip()
    try:
        planned_qty = float(payload.get("plannedQty", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid plannedQty"}), 400

    produced_raw = payload.get("producedQty")
    produced_qty: Any = None
    if produced_raw is not None and produced_raw != "":
        try:
            produced_qty = float(produced_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid producedQty"}), 400

    remarks = payload.get("remarks")
    if remarks is not None:
        remarks = str(remarks)
    row_id = payload.get("id")
    rid: Any = None
    if row_id is not None and row_id != "":
        try:
            rid = int(row_id)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid id"}), 400

    updated_by = str(g.current_user.get("login") or "")

    try:
        new_id = upsert_dpr_row(
            review_date=review_date,
            machine_id=machine_id,
            part_no=part_no,
            planned_qty=planned_qty,
            produced_qty=produced_qty,
            remarks=remarks,
            updated_by=updated_by,
            row_id=rid,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    rows = list_dpr_rows(review_date)
    saved = next((r for r in rows if r["id"] == new_id), None)
    return jsonify({"row": saved, "id": new_id})


@api_bp.delete("/dpr/rows/<int:row_id>")
def dpr_rows_delete(row_id: int) -> Any:
    if not is_dpr_editor(g.current_user):
        return jsonify({"error": "You are not allowed to edit Daily Production Review"}), 403
    ok = delete_dpr_row(row_id)
    if not ok:
        return jsonify({"error": "Row not found"}), 404
    return jsonify({"ok": True})


@api_bp.get("/dpr/version")
def dpr_version() -> Any:
    try:
        d = _parse_iso_date("date")
    except ValueError:
        return jsonify({"error": "Invalid or missing date (use YYYY-MM-DD)"}), 400
    try:
        version = get_dpr_version(d)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"date": d, "version": version})


@api_bp.put("/dpr/snapshot")
def dpr_snapshot_save() -> Any:
    if not is_dpr_editor(g.current_user):
        return jsonify({"error": "You are not allowed to edit DPR snapshot fields"}), 403
    payload = request.get_json(silent=True) or {}
    review_date = str(payload.get("reviewDate") or "").strip()
    try:
        date.fromisoformat(review_date)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid reviewDate"}), 400

    op_planned_raw = payload.get("operatorPlanned")
    op_actual_raw = payload.get("operatorActual")
    try:
        op_planned = None if op_planned_raw in (None, "") else float(op_planned_raw)
        op_actual = None if op_actual_raw in (None, "") else float(op_actual_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid operator values"}), 400
    bottleneck = str(payload.get("bottleneckPending") or "")

    upsert_dpr_snapshot(
        review_date=review_date,
        operator_planned=op_planned,
        operator_actual=op_actual,
        bottleneck_pending=bottleneck,
        updated_by=str(g.current_user.get("login") or ""),
    )
    return jsonify({"ok": True})


def _dpr_review_date_str(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "").strip()


@api_bp.get("/dpr/machine/<path:token>/today")
def dpr_machine_today(token: str) -> Any:
    """Public read for printed machine QR — scoped by secret token."""
    tok = str(token or "").strip()
    if not tok or not fetch_dpr_machine_by_qr_token(tok):
        return jsonify({"error": "Unknown machine token"}), 404
    try:
        d = _parse_iso_date("date")
    except ValueError:
        return jsonify({"error": "Invalid or missing date (use YYYY-MM-DD)"}), 400
    payload = get_machine_dpr_payload(tok, d)
    if not payload:
        return jsonify({"error": "Unknown machine token"}), 404
    return jsonify(payload)


@api_bp.put("/dpr/machine/<path:token>/produced")
def dpr_machine_produced(token: str) -> Any:
    """Update produced qty / remarks for one DPR row — requires DPR editor session."""
    if not is_dpr_editor(g.current_user):
        return jsonify({"error": "You are not allowed to edit Daily Production Review"}), 403
    tok = str(token or "").strip()
    qr_row = fetch_dpr_machine_by_qr_token(tok)
    if not qr_row:
        return jsonify({"error": "Unknown machine token"}), 404
    mid = str(qr_row.get("machine_id") or "").strip()

    payload = request.get_json(silent=True) or {}
    review_date = str(payload.get("reviewDate") or "").strip()
    try:
        date.fromisoformat(review_date)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid reviewDate"}), 400

    row_id_raw = payload.get("rowId")
    try:
        row_id = int(row_id_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid rowId"}), 400

    existing = fetch_one(
        """
        SELECT id, review_date, machine_id, part_no, planned_qty
        FROM dpr_daily_review
        WHERE id = %s
        """,
        (row_id,),
    )
    if not existing:
        return jsonify({"error": "Row not found"}), 404
    if str(existing.get("machine_id") or "").strip() != mid:
        return jsonify({"error": "Row does not belong to this machine"}), 403
    if _dpr_review_date_str(existing.get("review_date")) != review_date:
        return jsonify({"error": "Row date does not match reviewDate"}), 400

    pq_raw = existing.get("planned_qty")
    try:
        planned_qty = float(pq_raw or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid planned quantity on row"}), 400

    produced_raw = payload.get("producedQty")
    if produced_raw in (None, ""):
        produced_qty = None
    else:
        try:
            produced_qty = float(produced_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid producedQty"}), 400

    remarks = str(payload.get("remarks") or "")
    part_no = str(existing.get("part_no") or "").strip()
    updated_by = str(g.current_user.get("login") or "")

    try:
        upsert_dpr_row(
            review_date=review_date,
            machine_id=mid,
            part_no=part_no,
            planned_qty=planned_qty,
            produced_qty=produced_qty,
            remarks=remarks,
            updated_by=updated_by,
            row_id=row_id,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    rows = list_dpr_rows(review_date)
    saved = next((r for r in rows if r["id"] == row_id), None)
    return jsonify({"row": saved, "ok": True})


@api_bp.get("/dispatch-calendar")
@require_access("rept")
def api_dispatch_calendar() -> Any:
    """Monthly Order + stock merge for Dispatch Calendar Hub section."""
    t = date.today()
    month = _parse_int("month", t.month)
    year = _parse_int("year", t.year)
    if month < 1 or month > 12:
        month = t.month
    if year < 1900 or year > 2100:
        year = t.year
    try:
        payload = build_dispatch_calendar_payload(month, year)
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    return jsonify(payload)

