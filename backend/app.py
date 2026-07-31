from __future__ import annotations

import os
from typing import Any

from flask import Flask, current_app, g, make_response, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from .config import Config, DPR_POLL_INTERVAL_MS_DEFAULT


def _load_config_class() -> Any:
    """Try to load Config from `config.py`."""
    config_cls = Config()
    if config_cls is not None:
        return config_cls
    raise RuntimeError("No Config class found. Create config.py or use config_example.py.")


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
    )

    config_cls = _load_config_class()
    app.config.from_object(config_cls)
    app.secret_key = app.config.get("JWT_SECRET", "Shrujana")

    from .reports_store import seed_reports_store_from_bundle_if_needed

    seed_reports_store_from_bundle_if_needed()

    from .overview_report_bootstrap import ensure_overview_reports

    try:
        ensure_overview_reports()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Overview report bootstrap failed: %s", exc
        )

    from .api import api_bp

    app.register_blueprint(api_bp, url_prefix="/api")

    # ── Dashboards blueprints ───────────────────────────────────────
    from .pm_api import pm_bp
    from .tools_api import tools_bp
    from .tool_breakdowns_api import tool_breakdowns_bp
    from .production_api import production_bp
    from .rm_variance_api import rm_variance_bp
    from .rm_correction_api import rm_correction_bp
    from .schedule_api import schedule_bp
    from .reports_api import reports_bp
    from .admin_api import admin_bp

    from .search_api import search_bp
    from .rm_calculator_api import rm_calculator_bp
    from .machine_planning_api import machine_planning_bp
    from .laser_welding_api import laser_welding_bp
    from .scheduler.api import scheduler_bp

    app.register_blueprint(pm_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(tool_breakdowns_bp)
    app.register_blueprint(production_bp)
    app.register_blueprint(rm_variance_bp)
    app.register_blueprint(rm_correction_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(rm_calculator_bp)
    app.register_blueprint(machine_planning_bp)
    app.register_blueprint(laser_welding_bp)
    app.register_blueprint(scheduler_bp)

    from .auth import (
        create_token,
        get_current_user,
        has_rept_access,
        has_rept_plus_access,
        has_scdl_access,
        has_lw_access,
        is_dpr_editor,
        is_lw_editor,
        login_required,
        verify_credentials,
    )

    @app.route("/")
    def index() -> str:
        user = get_current_user()
        if user:
            return redirect(url_for("hub"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            user = get_current_user()
            if user:
                return redirect(url_for("hub"))
            next_url = request.args.get("next", "").strip()
            return render_template("login.html", next_url=next_url)

        login_name = request.form.get("login", "").strip()
        password = request.form.get("password", "").strip()
        next_url = request.form.get("next", "").strip()

        if not login_name or not password:
            return render_template(
                "login.html",
                error="Please enter both username and password.",
                next_url=next_url,
            )

        user_info = verify_credentials(login_name, password)
        if not user_info:
            return render_template(
                "login.html",
                error="Invalid username or password.",
                next_url=next_url,
            )

        token = create_token(user_info)
        dest = url_for("hub")
        if next_url.startswith("/") and not next_url.startswith("//"):
            dest = next_url
        response = make_response(redirect(dest))
        response.set_cookie(
            "auth_token",
            token,
            httponly=True,
            samesite="Lax",
            max_age=app.config.get("JWT_EXPIRES_IN", 86400),
        )
        return response

    @app.route("/logout")
    def logout():
        response = make_response(redirect(url_for("login")))
        response.delete_cookie("auth_token")
        return response

    # ══════════════════════════════════════════════════════════════
    # CENTRAL OPERATIONS HUB — Unified entry point
    # ══════════════════════════════════════════════════════════════

    # Hub RM Variance partial — off while under development; set True with hub.js RM_VARIANCE_HUB_ENABLED
    RM_VARIANCE_HUB_ENABLED = False

    VALID_SECTIONS = {
        "overview", "production", "inventory", "maintenance",
        "rm-variance", "rm-correction", "rm-calculator", "reports", "reports-manage",
        "admin", "dpr", "dispatch-calendar", "production-calendar", "machine-planning",
        "laser-welding", "production-scheduler",
    }

    @app.route("/app")
    @login_required
    def hub() -> str:
        user = g.current_user
        from .auth import is_buffer_editor, is_dpr_editor
        from . import rbac
        perms = rbac.get_effective_permissions(
            user.get("userId", 0),
            user.get("login", ""),
            user.get("userId") == 43,
        )

        return render_template(
            "hub.html",
            config=app.config,
            user=user,
            buffer_edit_allowed=is_buffer_editor(user),
            dpr_edit_allowed=is_dpr_editor(user),
            dpr_poll_interval_ms=app.config.get(
                "DPR_POLL_INTERVAL_MS", DPR_POLL_INTERVAL_MS_DEFAULT
            ),
            has_rept=has_rept_access(user),
            has_rept_plus=has_rept_plus_access(user),
            has_scdl=has_scdl_access(user),
            has_lw=has_lw_access(user),
            lw_edit_allowed=is_lw_editor(user),
            effective_permissions=perms,
        )

    @app.route("/app/section/<name>")
    @login_required
    def hub_section(name: str) -> str:
        if name not in VALID_SECTIONS:
            return "Section not found", 404
        if name == "rm-variance" and not RM_VARIANCE_HUB_ENABLED:
            return "Section not found", 404

        # RBAC Check for partials
        from . import rbac
        from .auth import is_dpr_editor
        user = g.current_user
        perms = rbac.get_effective_permissions(user.get("userId", 0), user.get("login", ""), user.get("userId") == 43)
        
        # Mapping section name to RBAC key (access list)
        key_map = {
            "production": "production",
            "inventory": "rept",
            # Maintenance page is visible when user has any maintenance subsection access
            "rm-variance": "rm_variance",
            # Backward compatibility: RM Correction can be granted via either key.
            "rm-correction": "rm_correction",
            "reports": "rept",
            "dpr": "rept",  # View access via reports
            "dispatch-calendar": "rept",
            "production-calendar": "rept",
            "rm-calculator": "rept",
            "machine-planning": "rept",
            "production-scheduler": "scdl",
            "laser-welding": "lw",
        }

        if name == "maintenance":
            if not any(k in perms["access"] for k in ("tools", "preventive_maintenance", "life_report")):
                return "Access denied", 403
        elif name == "reports-manage":
            if "rept_plus" not in perms.get("plusAccess", []):
                return "Access denied", 403
        elif name == "rm-correction":
            if not any(k in perms["access"] for k in ("rm_correction", "rm_variance")):
                return "Access denied", 403
        elif name in key_map and key_map[name] not in perms["access"]:
            return "Access denied", 403

        if name == "admin" and user.get("userId") != 43:
            return "Access denied", 403

        template_name = f"hub_{name.replace('-', '_')}.html"
        extra = {}
        if name == "dpr":
            extra["dpr_edit_allowed"] = is_dpr_editor(user)
        return render_template(template_name, **extra)

    @app.route("/machine/<path:token>")
    def machine_dpr_landing(token: str) -> Any:
        """Shop-floor landing from printed DPR QR: http://MACHINE_IP:PORT/machine/<qr_token>."""
        from .auth import get_current_user, is_dpr_editor
        from .models import fetch_dpr_machine_by_qr_token, get_dpr_machine_options

        tok = str(token or "").strip()
        if not tok:
            return render_template("machine_dpr_not_found.html"), 404
        row = fetch_dpr_machine_by_qr_token(tok)
        if not row:
            return render_template("machine_dpr_not_found.html"), 404
        user = get_current_user()
        return render_template(
            "machine_dpr.html",
            token=tok,
            user=user or {},
            dpr_edit_allowed=is_dpr_editor(user) if user else False,
            dpr_poll_interval_ms=app.config.get(
                "DPR_POLL_INTERVAL_MS", DPR_POLL_INTERVAL_MS_DEFAULT
            ),
        )

    @app.route("/qr-codes/<path:filename>")
    def qr_codes_file(filename: str) -> Any:
        """Pre-generated DPR PNGs (`qr-codes/`). Public GET so hub modal and printed paths work without extra auth."""
        from .models import get_dpr_qr_storage_dir

        base = str(get_dpr_qr_storage_dir())
        safe = secure_filename(os.path.basename(filename))
        if not safe:
            return "Not found", 404
        path = os.path.join(base, safe)
        if not path.startswith(base) or not os.path.isfile(path):
            return "Not found", 404
        return send_from_directory(base, safe, mimetype="image/png")

    from .inventory_snapshot import bootstrap_inventory_report_rows, start_inventory_snapshot_scheduler

    bootstrap_inventory_report_rows(app)
    start_inventory_snapshot_scheduler(app)

    return app


if __name__ == "__main__":
    flask_app = create_app()
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("APP_PORT", os.environ.get("PORT", "5000")))
    flask_app.run(debug=True, host=host, port=port)
