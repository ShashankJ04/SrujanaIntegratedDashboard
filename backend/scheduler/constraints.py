"""Hard constraint checks for candidate assignments."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .models import Job, MachineDay, ToolState


def check_working_day(
    day: int,
    working_days: Dict[int, float],
) -> Tuple[bool, str]:
    if day in working_days:
        return True, "Working day"
    return False, f"Day {day} is not a working day"


def check_machine_capacity(
    machine_day: Optional[MachineDay],
    needed_minutes: float,
) -> Tuple[bool, str]:
    """Allows soft overflow up to machine_day.overflow_limit beyond nominal shift."""
    if machine_day is None:
        return False, "Machine not available on this day"
    available = machine_day.remaining_with_overflow
    if available >= needed_minutes:
        overflow_needed = max(0.0, needed_minutes - machine_day.remaining_minutes)
        if overflow_needed > 0:
            return True, (
                f"{machine_day.remaining_minutes:.0f} min nominal + "
                f"{overflow_needed:.0f} min overflow available"
            )
        return True, f"{machine_day.remaining_minutes:.0f} min available"
    return (
        False,
        f"Only {available:.0f} min remaining (incl. overflow), need {needed_minutes:.0f} min",
    )


def check_rm_cap(
    cumulative_scheduled: float,
    rm_cap_qty: float,
) -> Tuple[bool, str]:
    if rm_cap_qty <= 0:
        return True, "No RM cap defined"
    if cumulative_scheduled <= rm_cap_qty:
        return True, f"RM usage {cumulative_scheduled:.0f}/{rm_cap_qty:.0f}"
    return False, f"RM cap exceeded ({cumulative_scheduled:.0f} > {rm_cap_qty:.0f})"


def check_monthly_cap(
    cumulative_scheduled: float,
    balance_production_qty: float,
) -> Tuple[bool, str]:
    if balance_production_qty <= 0:
        return False, "No production pending"
    if cumulative_scheduled <= balance_production_qty:
        return True, f"Scheduled {cumulative_scheduled:.0f}/{balance_production_qty:.0f}"
    return (
        False,
        f"Monthly cap exceeded ({cumulative_scheduled:.0f} > {balance_production_qty:.0f})",
    )


def check_tool_on_machine(job: Job, machine_id: int, machine_name: str = "") -> Tuple[bool, str]:
    """Machine must be capable of this part and the part must have at least one tool."""
    label = machine_name or str(machine_id)
    if not job.part_tools and not job.tool_no:
        return False, f"No tool defined for this part"
    if not job.has_tool_on_machine(machine_id):
        return False, f"Machine {label} is not capable of producing this part"
    return True, f"Part tool(s) can run on capable machine {label}"


def _shared_tool_parts_label(
    tool_no: str,
    parts_by_tool: Optional[Dict[str, list]],
    exclude_part: str = "",
) -> str:
    if not parts_by_tool:
        return ""
    siblings = [p for p in parts_by_tool.get(tool_no, []) if p and p != exclude_part]
    if not siblings:
        return ""
    shown = ", ".join(siblings[:4])
    if len(siblings) > 4:
        shown += f", +{len(siblings) - 4} more"
    return f" Shared tool — also produces: {shown}"


def check_tool_day_exclusive(
    tool_no: str,
    day: int,
    machine_id: int,
    tool_day_machine: Dict[Tuple[str, int], int],
    machine_names: Optional[Dict[int, str]] = None,
    tool_day_part: Optional[Dict[Tuple[str, int], str]] = None,
    current_part_no: str = "",
    parts_by_tool: Optional[Dict[str, list]] = None,
) -> Tuple[bool, str]:
    """A physical tool cannot run on two machines on the same day (any part)."""
    if not tool_no:
        return True, "No tool specified"
    key = (tool_no, day)
    occupied = tool_day_machine.get(key)
    if occupied is not None and occupied != machine_id:
        other = (machine_names or {}).get(occupied, str(occupied))
        blocking_part = (tool_day_part or {}).get(key, "")
        part_clause = f" for part {blocking_part}" if blocking_part else ""
        share = _shared_tool_parts_label(tool_no, parts_by_tool, current_part_no)
        return False, (
            f"Tool {tool_no} already scheduled on {other}{part_clause} on day {day} "
            f"(cannot run on two machines simultaneously){share}"
        )
    share = _shared_tool_parts_label(tool_no, parts_by_tool, current_part_no)
    return True, f"Tool {tool_no} free on day {day}{share}"


def check_tool_stroke_budget(
    tool_state: Optional[ToolState],
    needed_strokes: int,
    parts_by_tool: Optional[Dict[str, list]] = None,
    current_part_no: str = "",
) -> Tuple[bool, str]:
    if tool_state is None:
        return True, "No tool data (unconstrained)"
    tn = tool_state.tool_no
    share = _shared_tool_parts_label(tn, parts_by_tool, current_part_no)
    if tool_state.is_in_breakdown:
        return False, f"Tool {tn} is in breakdown{share}"
    remaining = tool_state.strokes_to_eol
    if remaining <= 0:
        return False, f"Tool {tn} stroke budget exhausted (end of life reached){share}"
    if needed_strokes > remaining:
        return (
            False,
            f"Tool {tn} stroke budget insufficient "
            f"({remaining:,} remaining, need {needed_strokes:,}){share}",
        )
    return True, f"Tool {tn} OK ({remaining:,} strokes to EOL){share}"


def check_tool_available(tool_state: Optional[ToolState]) -> Tuple[bool, str]:
    """Legacy wrapper — use check_tool_stroke_budget when stroke qty is known."""
    if tool_state is None:
        return True, "No tool data (unconstrained)"
    if tool_state.is_in_breakdown:
        return False, f"Tool {tool_state.tool_no} is in breakdown"
    if tool_state.strokes_to_eol <= 0:
        return False, f"Tool {tool_state.tool_no} stroke budget exhausted (end of life reached)"
    return True, f"Tool {tool_state.tool_no} OK ({tool_state.strokes_to_eol:,} strokes to EOL)"


def check_schedule_horizon(day: int, schedule_from_day: int) -> Tuple[bool, str]:
    """Past days (before schedule_from_day) are display-only, not schedulable."""
    if day < schedule_from_day:
        return False, f"Day {day} is before scheduling horizon (starts day {schedule_from_day})"
    return True, "Within scheduling horizon"


def check_all(
    day: int,
    working_days: Dict[int, float],
    machine_day: Optional[MachineDay],
    needed_minutes: float,
    cumulative_scheduled: float,
    rm_cap_qty: float,
    balance_production_qty: float,
    tool_state: Optional[ToolState],
    schedule_from_day: int = 1,
    job: Optional[Job] = None,
    machine_id: Optional[int] = None,
    needed_strokes: int = 0,
    tool_no: str = "",
    tool_day_machine: Optional[Dict[Tuple[str, int], int]] = None,
    tool_day_part: Optional[Dict[Tuple[str, int], str]] = None,
    parts_by_tool: Optional[Dict[str, list]] = None,
    machine_names: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    """Run every hard constraint and return results.

    Returns ``{"ok": bool, "results": {name: (pass, reason)}, "first_failure": name|None}``.
    """
    machine_name = machine_day.machine_name if machine_day else ""
    checks: Dict[str, Tuple[bool, str]] = {
        "working_day": check_working_day(day, working_days),
        "schedule_horizon": check_schedule_horizon(day, schedule_from_day),
        "machine_capacity": check_machine_capacity(machine_day, needed_minutes),
        "rm_cap": check_rm_cap(cumulative_scheduled, rm_cap_qty),
        "monthly_cap": check_monthly_cap(cumulative_scheduled, balance_production_qty),
    }
    if job is not None and machine_id is not None:
        checks["tool_on_machine"] = check_tool_on_machine(job, machine_id, machine_name)
    current_part = job.part_no if job else ""
    if tool_no and tool_day_machine is not None and machine_id is not None:
        checks["tool_day_exclusive"] = check_tool_day_exclusive(
            tool_no, day, machine_id, tool_day_machine, machine_names,
            tool_day_part=tool_day_part,
            current_part_no=current_part,
            parts_by_tool=parts_by_tool,
        )
    if needed_strokes > 0:
        checks["tool_stroke_budget"] = check_tool_stroke_budget(
            tool_state, needed_strokes, parts_by_tool, current_part,
        )
    else:
        checks["tool_available"] = check_tool_available(tool_state)
    first_fail = None
    for name, (passed, _reason) in checks.items():
        if not passed and first_fail is None:
            first_fail = name
    return {
        "ok": first_fail is None,
        "results": {n: p for n, (p, _r) in checks.items()},
        "reasons": {n: r for n, (_p, r) in checks.items()},
        "first_failure": first_fail,
    }
