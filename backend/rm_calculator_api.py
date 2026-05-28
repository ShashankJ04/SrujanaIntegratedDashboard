"""RM Calculator API — part lookup and Input RM from quantity × conval."""

from __future__ import annotations

from functools import wraps
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request, g

from .auth import api_login_required
from . import rbac
from .db import fetch_one
from .models import get_rm_calculator_part_options

rm_calculator_bp = Blueprint("rm_calculator_bp", __name__, url_prefix="/api/rm-calculator")


@rm_calculator_bp.before_request
def _auth():
    result = api_login_required()
    if result is not None:
        return result


def _require_rept_access(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = g.get("current_user") or {}
        perms = rbac.get_effective_permissions(
            user.get("userId", 0),
            user.get("login", ""),
            user.get("userId") == 43,
        )
        if "rept" not in perms.get("access", []):
            return jsonify({"message": "Forbidden"}), 403
        return f(*args, **kwargs)

    return decorated


def _part_conval_row(part_no: str) -> Optional[Dict[str, Any]]:
    key = str(part_no or "").strip()
    if not key:
        return None
    return fetch_one(
        """
        SELECT
            TRIM(c.CO_PARTNO) AS partNo,
            TRIM(c.CO_PARTNAME) AS partName,
            TRIM(ct.CT_TOOLNO) AS toolNo,
            m.MM_RawMtPartNo AS rmCode,
            ROUND(
                1000 / (
                    (1 / ((mt.MT_Density * m.MM_Thickness) * m.MM_StripWidth))
                    * ((1000 * ct.CT_NO_OF_CAVITY) / ct.CT_Pitch)
                ),
                10
            ) AS rmConvalGrams
        FROM components c
        INNER JOIN components_tool ct ON ct.CT_COMPID = c.CO_ID
            AND ct.CT_ID = (
                SELECT MAX(ct2.CT_ID)
                FROM components_tool ct2
                WHERE ct2.CT_COMPID = c.CO_ID
                  AND ct2.CT_ActiveYN = 'Y'
                  AND ct2.CT_PPC = 'Y'
                  AND ct2.CT_PITCH > 0
                  AND ct2.CT_NO_OF_CAVITY > 0
            )
        INNER JOIN materialmaster m ON ct.CT_RMID = m.MM_Id
        INNER JOIN materialtypemaster mt ON m.MM_MTID = mt.MT_Id
        WHERE c.CO_ACTIVEYN = 'Y'
          AND TRIM(c.CO_PARTNO) = %s
        LIMIT 1
        """,
        (key,),
    )


@rm_calculator_bp.get("/parts")
@_require_rept_access
def list_parts():
    """Same part list as DPR, excluding NPD-* new product development entries."""
    return jsonify(get_rm_calculator_part_options())


@rm_calculator_bp.get("/calculate")
@_require_rept_access
def calculate():
    part_no = str(request.args.get("partNo") or "").strip()
    if not part_no:
        return jsonify({"error": "partNo is required"}), 400

    qty_raw = request.args.get("quantity", "")
    if qty_raw in (None, ""):
        return jsonify({"error": "quantity is required"}), 400
    try:
        quantity = float(qty_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid quantity"}), 400
    if quantity < 0:
        return jsonify({"error": "quantity cannot be negative"}), 400

    row = _part_conval_row(part_no)
    if not row:
        return jsonify({"error": "Part not found or missing active PPC tool data"}), 404

    conval = float(row.get("rmConvalGrams") or 0)
    input_rm_grams = round(quantity * conval, 10)
    input_rm_kg = round(input_rm_grams / 1000, 10)
    rm_conval_kg = round(conval / 1000, 10)

    return jsonify(
        {
            "partNo": row.get("partNo"),
            "partName": row.get("partName"),
            "toolNo": row.get("toolNo"),
            "rmCode": row.get("rmCode"),
            "quantity": quantity,
            "rmConvalKg": rm_conval_kg,
            "inputRmKg": input_rm_kg,
        }
    )
