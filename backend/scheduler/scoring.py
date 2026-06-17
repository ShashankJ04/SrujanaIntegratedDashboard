"""Weighted scoring for candidate (job, machine, day) assignments."""

from __future__ import annotations

from typing import Dict, Optional

from .models import (
    DEFAULT_WEIGHTS,
    Job,
    MachineDay,
    ScoreFactor,
    ScoreResult,
    ToolState,
)


def _urgency_factor(job: Job, day: int) -> tuple[float, str]:
    """Higher when production day is close to the earliest dispatch deadline."""
    earliest = job.earliest_dispatch_day
    if earliest <= 0:
        return 0.5, "No dispatch deadline"
    gap = earliest - day
    if gap <= 0:
        return 1.0, f"Dispatch day {earliest} already reached/passed"
    if gap <= 3:
        return 0.9, f"Only {gap} day(s) to dispatch day {earliest}"
    if gap <= 7:
        return 0.6, f"{gap} days to dispatch day {earliest}"
    return max(0.1, 1.0 - (gap / 31.0)), f"{gap} days to dispatch day {earliest}"


def _utilization_factor(machine_day: MachineDay) -> tuple[float, str]:
    """Prefer under-utilized machines so load spreads evenly."""
    util = machine_day.utilization
    factor = 1.0 - util
    pct = round(util * 100, 1)
    return factor, f"Machine at {pct}% utilization before this assignment"


def _primary_machine_factor(job: Job, machine_id: int) -> tuple[float, str]:
    if job.primary_machine_id == machine_id:
        return 1.0, "Primary machine"
    for mid, rank in job.alt_machines:
        if mid == machine_id:
            return max(0.0, 1.0 - rank * 0.25), f"Alternate machine (rank {rank})"
    return 0.0, "Unknown machine for this part"


def _pm_risk_factor(tool_state: Optional[ToolState]) -> tuple[float, str]:
    """Penalty increases as strokes approach PM or end-of-life."""
    if tool_state is None:
        return 0.0, "No tool data"
    proximity = tool_state.pm_proximity
    eol_frac = 0.0
    if tool_state.total_life > 0:
        used = tool_state.current_strokes + tool_state.accumulated_scheduled_strokes
        eol_frac = used / tool_state.total_life
    risk = max(proximity, eol_frac)
    if risk < 0.5:
        return risk * 0.2, f"Tool healthy ({tool_state.strokes_to_pm} to PM, {tool_state.strokes_to_eol} to EOL)"
    if risk < 0.8:
        return risk * 0.6, f"Tool moderate risk ({tool_state.strokes_to_pm} to PM)"
    return risk, f"Tool high risk ({tool_state.strokes_to_pm} to PM, {tool_state.strokes_to_eol} to EOL)"


def _changeover_factor(machine_day: MachineDay, part_no: str) -> tuple[float, str]:
    """Penalty if scheduling a new part on this machine-day."""
    if not machine_day.parts_scheduled:
        return 0.0, "First part on machine this day"
    if part_no in machine_day.parts_scheduled:
        return 0.0, "Same part continues"
    return 1.0, f"New part switch (changeover #{machine_day.changeover_count + 1})"


def _idle_factor(machine_day: MachineDay) -> tuple[float, str]:
    """Penalty for leaving a machine completely idle when work exists."""
    if machine_day.used_minutes > 0:
        return 0.0, "Machine is active"
    return 1.0, "Machine idle — filling reduces idle penalty"


def score_assignment(
    job: Job,
    machine_day: MachineDay,
    tool_state: Optional[ToolState],
    weights: Dict[str, float],
) -> ScoreResult:
    """Score a candidate assignment.  Higher is better."""
    w = {**DEFAULT_WEIGHTS, **weights}

    urgency_val, urgency_reason = _urgency_factor(job, machine_day.day)
    util_val, util_reason = _utilization_factor(machine_day)
    primary_val, primary_reason = _primary_machine_factor(job, machine_day.machine_id)
    pm_val, pm_reason = _pm_risk_factor(tool_state)
    chg_val, chg_reason = _changeover_factor(machine_day, job.part_no)
    idle_val, idle_reason = _idle_factor(machine_day)

    factors = [
        ScoreFactor("dispatch_urgency", w["w_urgency"], urgency_val,
                     w["w_urgency"] * urgency_val, urgency_reason),
        ScoreFactor("utilization", w["w_utilize"], util_val,
                     w["w_utilize"] * util_val, util_reason),
        ScoreFactor("primary_machine", w["w_primary"], primary_val,
                     w["w_primary"] * primary_val, primary_reason),
        ScoreFactor("pm_risk", w["w_pm_risk"], pm_val,
                     -w["w_pm_risk"] * pm_val, pm_reason),
        ScoreFactor("changeover", w["w_changeover"], chg_val,
                     -w["w_changeover"] * chg_val, chg_reason),
        ScoreFactor("idle_penalty", w["w_idle"], idle_val,
                     w["w_idle"] * idle_val, idle_reason),
    ]
    total = sum(f.contribution for f in factors)
    return ScoreResult(total=total, breakdown=factors)
