"""Preventive Maintenance data-access layer.

Port of dashboards/backend/src/db/pmStore.ts — uses the existing db.py
helpers (fetch_all, fetch_one, execute) with raw SQL.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote

from .db import execute, fetch_all, fetch_one


# ── Helpers ─────────────────────────────────────────────────────────────

def _format_date(d: Any) -> str:
    if isinstance(d, datetime):
        return d.isoformat()
    if isinstance(d, str):
        try:
            return datetime.fromisoformat(d).isoformat()
        except Exception:
            return d
    return str(d)


def _resolve_tool_number(tool_id: int) -> Optional[str]:
    row = fetch_one(
        "SELECT TL_tool_number AS toolNo FROM tool_life WHERE TL_tool_id = %s",
        (tool_id,),
    )
    if row and row.get("toolNo"):
        return row["toolNo"]

    row = fetch_one(
        "SELECT CT_TOOLNO AS toolNo FROM components_tool WHERE CT_ID = %s",
        (tool_id,),
    )
    return row["toolNo"] if row and row.get("toolNo") else None


def _get_tool_strokes_by_tool_no(tool_no: str) -> int:
    row = fetch_one(
        """
        SELECT COALESCE(MAX(comp.componentStrokes), 0) AS totalQty
        FROM (
            SELECT
                ct.CT_COMPID,
                SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
            FROM production_details pd
            INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
            WHERE ct.CT_TOOLNO = %s
            GROUP BY ct.CT_COMPID
        ) comp
        """,
        (tool_no,),
    )
    return int(row["totalQty"]) if row else 0


def _safe_pm_attachment_relpath(raw: str) -> Optional[str]:
    """Build a safe relative path (forward slashes) under pm-attachments; None if invalid."""
    s = unquote(raw.strip()).replace("\\", "/")
    if not s:
        return None
    s = s.lstrip("/")
    low = s.lower()
    if low.startswith("pm-attachments/"):
        s = s[len("pm-attachments/") :]
    parts: List[str] = []
    for p in s.split("/"):
        if not p or p == ".":
            continue
        if p == "..":
            return None
        parts.append(p)
    return "/".join(parts) if parts else None


def _normalize_attachment_path(value: Optional[str]) -> Optional[str]:
    """Return API-served PM attachment URL for legacy/raw DB values.

    Preserves nested folders (e.g. ``S1/PT041/01A/file.pdf``) instead of basename-only,
    so URLs match files stored under ``pm-attachments/<subdirs>/``.
    """
    if not value:
        return None

    attachment = str(value).strip()
    if not attachment:
        return None

    if attachment.startswith(("http://", "https://")):
        return attachment

    if attachment.startswith("/api/pm/attachment/"):
        inner = attachment[len("/api/pm/attachment/") :]
        safe = _safe_pm_attachment_relpath(inner)
        if not safe:
            return attachment
        return f"/api/pm/attachment/{quote(safe, safe='/')}"

    safe = _safe_pm_attachment_relpath(attachment)
    if not safe:
        return None
    return f"/api/pm/attachment/{quote(safe, safe='/')}"


# ── Public API ──────────────────────────────────────────────────────────

def get_entries() -> List[Dict[str, Any]]:
    """Get all tool_life rows with their maintenance history attached."""
    tools = fetch_all("SELECT * FROM tool_life")
    pm_rows = fetch_all(
        "SELECT * FROM preventive_maintenance ORDER BY PM_id ASC"
    )

    history_by_tool_id: Dict[int, List[Dict[str, Any]]] = {}
    for pm in pm_rows:
        tid = pm["PM_tool_id"]
        rec = {
            "id": pm["PM_id"],
            "date": _format_date(pm["PM_date"]),
            "currentStroke": int(pm["PM_current_stroke"]),
            "nextStroke": int(pm["PM_next_stroke"]),
            "attachment": _normalize_attachment_path(pm.get("PM_maintenance_attachment")),
        }
        history_by_tool_id.setdefault(tid, []).append(rec)

    result = []
    for t in tools:
        tid = t["TL_tool_id"]
        history = history_by_tool_id.get(tid, [])
        result.append({
            "toolId": tid,
            "toolNo": t["TL_tool_number"],
            "toolLife": int(t["TL_life_span"]),
            "spm": int(t["TL_spm"]),
            "pmStrokes": int(t["TL_preventive_maintenance_strokes"]),
            "maintenanceHistory": history,
            "createdAt": _format_date(t["TL_created_at"]),
        })

    return result


def add_entry(
    tool_id: int,
    tool_no: str,
    tool_life: int,
    spm: int,
    pm_strokes: int,
    next_stroke: Optional[int] = None,
) -> Dict[str, Any]:
    """Add a new tool_life row. Optionally creates an initial PM record."""
    existing = fetch_one(
        "SELECT TL_tool_number FROM tool_life WHERE TL_tool_number = %s",
        (tool_no,),
    )
    if existing:
        raise ValueError(f"Tool {tool_no} (ID: {tool_id}) is already added")

    execute(
        """
        INSERT INTO tool_life
            (TL_tool_id, TL_tool_number, TL_life_span, TL_spm, TL_preventive_maintenance_strokes)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (tool_id, tool_no, tool_life, spm, pm_strokes),
    )

    if next_stroke is not None:
        current_stroke = get_tool_strokes(tool_id)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        execute(
            """
            INSERT INTO preventive_maintenance
                (PM_tool_id, PM_tool_number, PM_date, PM_current_stroke, PM_next_stroke, PM_maintenance_attachment)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (tool_id, tool_no, now_str, current_stroke, next_stroke, None),
        )

    entries = get_entries()
    return next((e for e in entries if e["toolId"] == tool_id), entries[0])


def update_entry(
    tool_id: int,
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """Update tool_life fields for a given toolId."""
    row = fetch_one(
        "SELECT * FROM tool_life WHERE TL_tool_id = %s",
        (tool_id,),
    )
    if not row:
        raise ValueError(f"Tool ID {tool_id} not found")

    set_parts = []
    params: list = []
    if "toolLife" in updates and updates["toolLife"] is not None:
        set_parts.append("TL_life_span = %s")
        params.append(updates["toolLife"])
    if "pmStrokes" in updates and updates["pmStrokes"] is not None:
        set_parts.append("TL_preventive_maintenance_strokes = %s")
        params.append(updates["pmStrokes"])
    if "spm" in updates and updates["spm"] is not None:
        set_parts.append("TL_spm = %s")
        params.append(updates["spm"])

    if set_parts:
        params.append(tool_id)
        execute(
            f"UPDATE tool_life SET {', '.join(set_parts)} WHERE TL_tool_id = %s",
            tuple(params),
        )

    entries = get_entries()
    entry = next((e for e in entries if e["toolId"] == tool_id), None)
    if not entry:
        raise ValueError(f"Tool ID {tool_id} not found after update")
    return entry


def get_tool_strokes(tool_id: int) -> int:
    """Get total strokes for any tool from production_details."""
    tool_no = _resolve_tool_number(tool_id)
    if not tool_no:
        return 0
    return _get_tool_strokes_by_tool_no(tool_no)


def get_stroke_info(tool_id: int) -> Dict[str, int]:
    """Get current total strokes and suggested next PM stroke."""
    row = fetch_one(
        "SELECT * FROM tool_life WHERE TL_tool_id = %s",
        (tool_id,),
    )
    if not row:
        raise ValueError(f"Tool ID {tool_id} not found")

    current_stroke = get_tool_strokes(tool_id)
    suggested = current_stroke + int(row["TL_preventive_maintenance_strokes"])
    return {"currentStroke": current_stroke, "suggestedNextStroke": suggested}


def confirm_maintenance(
    tool_id: int,
    next_stroke: int,
    attachment: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a maintenance event."""
    row = fetch_one(
        "SELECT * FROM tool_life WHERE TL_tool_id = %s",
        (tool_id,),
    )
    if not row:
        raise ValueError(f"Tool ID {tool_id} not found")

    current_stroke = get_tool_strokes(tool_id)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    execute(
        """
        INSERT INTO preventive_maintenance
            (PM_tool_id, PM_tool_number, PM_date, PM_current_stroke, PM_next_stroke, PM_maintenance_attachment)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (tool_id, row["TL_tool_number"], now_str, current_stroke, next_stroke, attachment),
    )

    entries = get_entries()
    return next((e for e in entries if e["toolId"] == tool_id), entries[0])


def delete_entry(tool_id: int) -> None:
    """Delete a tool_life row and its maintenance records."""
    row = fetch_one(
        "SELECT TL_tool_id FROM tool_life WHERE TL_tool_id = %s",
        (tool_id,),
    )
    if not row:
        raise ValueError(f"Tool ID {tool_id} not found")

    execute(
        "DELETE FROM preventive_maintenance WHERE PM_tool_id = %s",
        (tool_id,),
    )
    execute(
        "DELETE FROM tool_life WHERE TL_tool_id = %s",
        (tool_id,),
    )
