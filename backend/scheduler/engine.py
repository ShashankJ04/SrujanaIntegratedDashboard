"""3-pass scheduling engine: normalize → greedy assign → local improve."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .capacity import compute_run_minutes, compute_strokes
from .constraints import check_all
from .models import (
    DEFAULT_WEIGHTS,
    Assignment,
    Job,
    MachineDay,
    RunResult,
    SchedulerInput,
    ScoreResult,
    ToolState,
    UnscheduledPart,
)
from .scoring import score_assignment


# ── Helpers ──────────────────────────────────────────────────────────────

PM_BLOCK_MINUTES = 240  # 4 hours for a PM event


def _sorted_working_days(working_days: Dict[int, float], from_day: int = 1) -> List[int]:
    return sorted(d for d in working_days.keys() if d >= from_day)


def _candidate_machines(job: Job) -> List[int]:
    """Primary first, then alternates in rank order."""
    ids: List[int] = []
    if job.pinned_machine is not None:
        return [int(job.pinned_machine)]
    if job.primary_machine_id is not None:
        ids.append(int(job.primary_machine_id))
    for mid, _rank in sorted(job.alt_machines, key=lambda x: x[1]):
        mid = int(mid)
        if mid not in ids:
            ids.append(mid)
    return ids


def _machine_name(inp: SchedulerInput, machine_id: int) -> str:
    for (mid, _day), md in inp.machine_days.items():
        if mid == machine_id:
            return md.machine_name
    return str(machine_id)


def _tool_share_suffix(tool_no: str, inp: SchedulerInput, exclude_part: str = "") -> str:
    siblings = [
        p for p in inp.parts_by_tool.get(tool_no, [])
        if p and p.lower() != (exclude_part or "").lower()
    ]
    if not siblings:
        return ""
    shown = ", ".join(siblings[:4])
    if len(siblings) > 4:
        shown += f", +{len(siblings) - 4} more"
    return f" (shared with parts: {shown})"


def _machine_names(inp: SchedulerInput) -> Dict[int, str]:
    names: Dict[int, str] = {}
    for (mid, _day), md in inp.machine_days.items():
        names[mid] = md.machine_name
    return names


def _unscheduled_reason(
    job: Job,
    remaining: float,
    inp: SchedulerInput,
) -> str:
    """Build a specific reason when qty could not be scheduled."""
    qty = f"{remaining:,.0f}"
    if job.part_tools:
        tools = set(job.part_tools)
    elif job.machine_tools:
        tools = set(job.machine_tools.values())
    elif job.tool_no:
        tools = {job.tool_no}
    else:
        tools = set()
    tools.discard("")

    needed_strokes = compute_strokes(remaining, job.cavity)
    for tn in tools:
        ts = inp.tool_states.get(tn)
        if ts and ts.is_in_breakdown:
            return f"Tool {tn} is in breakdown; {qty} pcs unscheduled"
        if ts and ts.strokes_to_eol <= 0:
            share = _tool_share_suffix(tn, inp, job.part_no)
            return f"Tool {tn} stroke budget exhausted (end of life reached){share}; {qty} pcs unscheduled"
        if ts and needed_strokes > ts.strokes_to_eol:
            share = _tool_share_suffix(tn, inp, job.part_no)
            return (
                f"Tool {tn} stroke budget insufficient "
                f"({ts.strokes_to_eol:,} strokes remaining, need {needed_strokes:,} for {qty} pcs){share}"
            )

    if not tools:
        return f"{qty} pcs unscheduled: no tool defined for this part in components_tool"

    if len(tools) == 1 and job.alt_machines and job.primary_machine_id:
        tn = next(iter(tools))
        primary_name = _machine_name(inp, job.primary_machine_id)
        return (
            f"{qty} pcs unscheduled: {primary_name} capacity exhausted for the month. "
            f"Alternate machine(s) share tool {tn} and cannot run on days when "
            f"that tool is already committed to the primary machine"
        )

    return f"{qty} pcs unscheduled after exhausting machine capacity and tool constraints"


def _get_working_days_dict(inp: SchedulerInput) -> Dict[int, float]:
    days: Dict[int, float] = {}
    for (mid, d), md in inp.machine_days.items():
        if d not in days:
            days[d] = md.available_minutes / 60 if md.available_minutes > 0 else 0.0
    return days


# ── Pass A — Demand normalization & weight-sensitive sort ────────────────

def _normalize_and_sort(inp: SchedulerInput) -> List[Job]:
    """Filter valid jobs and sort by weighted composite priority."""
    jobs: List[Job] = []
    for job in inp.jobs:
        if job.is_supplier:
            continue
        if job.total_qty <= 0:
            continue
        if job.parts_per_minute <= 0:
            continue
        if job.primary_machine_id is None and not job.alt_machines:
            continue
        jobs.append(job)

    w = {**DEFAULT_WEIGHTS, **(inp.scenario.weights or {})}
    w_urgency = w.get("w_urgency", 0.35)
    w_utilize = w.get("w_utilize", 0.20)
    w_primary = w.get("w_primary", 0.15)

    def sort_key(j: Job) -> tuple:
        pinned = 0 if (j.pinned_machine is not None or j.pinned_day is not None) else 1

        # Urgency: earlier deadline = higher urgency. Normalize to 0..1
        earliest = j.earliest_dispatch_day
        urgency_score = max(0.0, 1.0 - (earliest / 31.0))

        # Capacity pressure: high qty relative to production rate
        capacity_pressure = 0.0
        if j.parts_per_minute > 0:
            minutes_needed = j.effective_qty / j.parts_per_minute
            capacity_pressure = min(1.0, minutes_needed / (360.0 * 26))

        # RM pressure: how constrained by raw material
        rm_pressure = 0.0
        if j.rm_cap_qty > 0 and j.total_qty > 0:
            rm_pressure = min(1.0, j.rm_cap_qty / j.total_qty)

        composite = -(
            w_urgency * urgency_score
            + w_utilize * capacity_pressure
            + w_primary * rm_pressure
            + j.user_priority * 0.1
        )
        return (pinned, composite, earliest)

    jobs.sort(key=sort_key)
    return jobs


# ── Pass B — Greedy deadline-aware assignment ────────────────────────────

def _try_assign_qty(
    job: Job,
    qty: float,
    day: int,
    mid: int,
    inp: SchedulerInput,
    cumulative_by_part: Dict[str, float],
) -> Tuple[Optional[Assignment], Dict[str, str]]:
    """Try to place *qty* of *job* on machine *mid* on *day*."""
    needed_minutes = compute_run_minutes(qty, job.spm, job.cavity)
    strokes = compute_strokes(qty, job.cavity)
    cum = cumulative_by_part.get(job.part_no, 0.0) + qty
    working_days = _get_working_days_dict(inp)
    md = inp.machine_days.get((mid, day))
    machine_label = md.machine_name if md else str(mid)

    tool_candidates = job.part_tools if job.part_tools else (
        [job.tool_for_machine(mid)] if job.tool_for_machine(mid) else []
    )

    last_reject: Optional[Dict[str, str]] = None
    for tool_no in tool_candidates:
        if not tool_no:
            continue
        tool_state = inp.tool_states.get(tool_no)
        constraint_result = check_all(
            day=day,
            working_days=working_days,
            machine_day=md,
            needed_minutes=needed_minutes,
            cumulative_scheduled=cum,
            rm_cap_qty=job.rm_cap_qty,
            balance_production_qty=job.effective_qty,
            tool_state=tool_state,
            schedule_from_day=inp.schedule_from_day,
            job=job,
            machine_id=mid,
            needed_strokes=strokes,
            tool_no=tool_no,
            tool_day_machine=inp.tool_day_machine,
            tool_day_part=inp.tool_day_part,
            parts_by_tool=inp.parts_by_tool,
            machine_names=_machine_names(inp),
        )
        if not constraint_result["ok"]:
            reason = constraint_result["reasons"].get(
                constraint_result["first_failure"], "Constraint failed"
            )
            last_reject = {
                "machine_id": str(mid),
                "machine": machine_label,
                "reason": reason,
            }
            continue

        sr = score_assignment(job, md, tool_state, inp.scenario.weights)
        assignment = Assignment(
            part_no=job.part_no,
            part_name=job.part_name,
            machine_id=mid,
            machine_name=md.machine_name,
            day=day,
            qty=qty,
            run_minutes=needed_minutes,
            strokes=strokes,
            score=sr,
            tool_no=tool_no,
            constraints_checked=constraint_result["results"],
        )
        return assignment, {}

    if last_reject:
        return None, last_reject
    return None, {
        "machine_id": str(mid),
        "machine": machine_label,
        "reason": f"No tool available for this part on machine {machine_label}",
    }


def _apply_assignment(
    assignment: Assignment,
    inp: SchedulerInput,
    cumulative_by_part: Dict[str, float],
) -> None:
    """Mutate machine-day and tool state after accepting an assignment."""
    key = (assignment.machine_id, assignment.day)
    md = inp.machine_days.get(key)
    if md:
        overflow_needed = max(0.0, assignment.run_minutes - md.remaining_minutes)
        if overflow_needed > 0:
            md.overflow_minutes_used += overflow_needed
        md.used_minutes += assignment.run_minutes
        md.parts_scheduled.append(assignment.part_no)

    cumulative_by_part[assignment.part_no] = (
        cumulative_by_part.get(assignment.part_no, 0.0) + assignment.qty
    )

    tool_no = assignment.tool_no
    if not tool_no:
        job = next((j for j in inp.jobs if j.part_no == assignment.part_no), None)
        if job:
            tool_no = job.tool_for_machine(assignment.machine_id)
    if tool_no:
        key = (tool_no, assignment.day)
        inp.tool_day_machine[key] = assignment.machine_id
        inp.tool_day_part[key] = assignment.part_no
    tool = inp.tool_states.get(tool_no) if tool_no else None
    if tool:
        tool.accumulated_scheduled_strokes += assignment.strokes
        if (tool.current_strokes + tool.accumulated_scheduled_strokes) >= tool.next_pm_stroke:
            if md:
                md.used_minutes += PM_BLOCK_MINUTES
            tool.next_pm_stroke += tool.pm_interval


def _greedy_assign(inp: SchedulerInput, jobs: List[Job]) -> Tuple[List[Assignment], List[UnscheduledPart]]:
    """Deadline-aware greedy: for each job, score all feasible (machine, day) placements."""
    assignments: List[Assignment] = []
    unscheduled: List[UnscheduledPart] = []
    cumulative_by_part: Dict[str, float] = {}
    working_days_sorted = _sorted_working_days(
        _get_working_days_dict(inp), from_day=inp.schedule_from_day
    )

    for job in jobs:
        remaining = job.effective_qty
        if remaining <= 0:
            continue

        candidates = _candidate_machines(job)
        if not candidates:
            unscheduled.append(UnscheduledPart(
                part_no=job.part_no, part_name=job.part_name,
                qty_remaining=remaining, reason="No candidate machines available",
            ))
            continue

        # Determine day iteration order
        if job.pinned_day is not None:
            day_pool = [job.pinned_day] if job.pinned_day in working_days_sorted else []
        else:
            day_pool = list(working_days_sorted)

        for day in day_pool:
            if remaining <= 0.5:
                break

            # Score all candidate machines for this day, pick best
            best_assignment: Optional[Assignment] = None
            all_rejected: List[Dict[str, str]] = []
            feasible: List[Assignment] = []

            for mid in candidates:
                md = inp.machine_days.get((mid, day))
                if md is None:
                    all_rejected.append({
                        "machine_id": str(mid),
                        "machine": _machine_name(inp, mid),
                        "reason": "Machine not available on this working day",
                    })
                    continue

                avail = md.remaining_with_overflow
                if avail <= 0:
                    all_rejected.append({
                        "machine_id": str(mid),
                        "machine": md.machine_name,
                        "reason": "No remaining capacity",
                    })
                    continue

                rate = job.parts_per_minute
                max_parts = avail * rate
                qty_today = min(remaining, max_parts)

                cap_remaining = job.effective_qty - cumulative_by_part.get(job.part_no, 0.0)
                qty_today = min(qty_today, cap_remaining)
                if qty_today <= 0:
                    all_rejected.append({
                        "machine_id": str(mid),
                        "machine": md.machine_name,
                        "reason": "Part quantity already fully scheduled",
                    })
                    continue

                if not job.has_tool_on_machine(mid):
                    all_rejected.append({
                        "machine_id": str(mid),
                        "machine": md.machine_name,
                        "reason": f"No tool available for this part on machine {md.machine_name}",
                    })
                    continue

                asgn, reject_info = _try_assign_qty(
                    job, qty_today, day, mid, inp, cumulative_by_part,
                )
                if reject_info:
                    all_rejected.append(reject_info)
                elif asgn:
                    feasible.append(asgn)

            if feasible:
                feasible.sort(key=lambda a: a.score.total, reverse=True)
                best_assignment = feasible[0]
                for alt in feasible[1:]:
                    all_rejected.append({
                        "machine_id": str(alt.machine_id),
                        "machine": alt.machine_name,
                        "reason": (
                            f"Lower score ({alt.score.total:.4f} vs "
                            f"{best_assignment.score.total:.4f})"
                        ),
                    })

            if best_assignment is not None:
                best_assignment.score.alternatives_rejected = all_rejected
                assignments.append(best_assignment)
                _apply_assignment(best_assignment, inp, cumulative_by_part)
                remaining -= best_assignment.qty

        if remaining > 0.5:
            unscheduled.append(UnscheduledPart(
                part_no=job.part_no,
                part_name=job.part_name,
                qty_remaining=remaining,
                reason=_unscheduled_reason(job, remaining, inp),
            ))

    return assignments, unscheduled


# ── Pass C — Local improvement ───────────────────────────────────────────

def _local_improve(
    assignments: List[Assignment],
    inp: SchedulerInput,
) -> Tuple[List[Assignment], List[str]]:
    """Cross-day consolidation, overload relief, load balancing, and forward pull."""
    log: List[str] = []

    # Step 1: merge same (part, machine, day) assignments
    merged: Dict[Tuple[str, int, int], Assignment] = {}
    for a in assignments:
        key = (a.part_no, a.machine_id, a.day)
        if key in merged:
            existing = merged[key]
            existing.qty += a.qty
            existing.run_minutes += a.run_minutes
            existing.strokes += a.strokes
        else:
            merged[key] = Assignment(
                part_no=a.part_no, part_name=a.part_name,
                machine_id=a.machine_id, machine_name=a.machine_name,
                day=a.day, qty=a.qty, run_minutes=a.run_minutes,
                strokes=a.strokes, score=a.score,
                tool_no=a.tool_no,
                constraints_checked=a.constraints_checked,
            )

    result = list(merged.values())

    # Step 2: cross-day consolidation — absorb small trailing assignments into prior day
    by_part_machine: Dict[Tuple[str, int], List[Assignment]] = {}
    for a in result:
        by_part_machine.setdefault((a.part_no, a.machine_id), []).append(a)

    to_remove = set()
    for (part_no, mid), group in by_part_machine.items():
        group.sort(key=lambda x: x.day)
        for i in range(len(group) - 1, 0, -1):
            curr = group[i]
            prev = group[i - 1]
            if curr.day - prev.day > 2:
                continue
            md_prev = inp.machine_days.get((mid, prev.day))
            if md_prev is None:
                continue
            combined_minutes = prev.run_minutes + curr.run_minutes
            capacity = md_prev.available_minutes + md_prev.overflow_limit
            if combined_minutes <= capacity:
                prev.qty += curr.qty
                prev.run_minutes += curr.run_minutes
                prev.strokes += curr.strokes
                to_remove.add(id(curr))
                log.append(
                    f"Consolidated {part_no} day {curr.day} ({curr.qty:.0f} pcs) "
                    f"into day {prev.day} on machine {prev.machine_name}"
                )

    if to_remove:
        result = [a for a in result if id(a) not in to_remove]

    # Step 3: overload relief — shift lowest-scored assignment off overloaded machine-days
    md_usage: Dict[Tuple[int, int], float] = {}
    md_assignments: Dict[Tuple[int, int], List[Assignment]] = {}
    for a in result:
        k = (a.machine_id, a.day)
        md_usage[k] = md_usage.get(k, 0.0) + a.run_minutes
        md_assignments.setdefault(k, []).append(a)

    for k, total_min in md_usage.items():
        md = inp.machine_days.get(k)
        if md is None:
            continue
        limit = md.available_minutes + md.overflow_limit
        if total_min <= limit:
            continue
        group = md_assignments[k]
        group.sort(key=lambda a: a.score.total)
        while total_min > limit and group:
            worst = group[0]
            total_min -= worst.run_minutes
            result.remove(worst)
            group.pop(0)
            log.append(
                f"Overload relief: removed {worst.part_no} ({worst.qty:.0f} pcs) "
                f"from machine {worst.machine_name} day {worst.day}"
            )

    # Step 4: load balancing — shift from heavily loaded machines to underutilized alternates
    machine_util: Dict[int, float] = {}
    machine_avail: Dict[int, float] = {}
    for (mid, _d), md in inp.machine_days.items():
        machine_avail[mid] = machine_avail.get(mid, 0.0) + md.available_minutes
    for a in result:
        machine_util[a.machine_id] = machine_util.get(a.machine_id, 0.0) + a.run_minutes

    jobs_by_part = {j.part_no: j for j in inp.jobs}
    swaps_made = 0
    for a in list(result):
        if swaps_made >= 20:
            break
        mid = a.machine_id
        avail = machine_avail.get(mid, 1.0)
        util_pct = (machine_util.get(mid, 0.0) / avail) if avail > 0 else 0.0
        if util_pct < 0.85:
            continue

        job = jobs_by_part.get(a.part_no)
        if not job:
            continue
        for alt_mid, _rank in job.alt_machines:
            if not job.has_tool_on_machine(alt_mid):
                continue
            alt_tool = job.tool_for_machine(alt_mid)
            occupied = inp.tool_day_machine.get((alt_tool, a.day))
            if occupied is not None and occupied != alt_mid and occupied != mid:
                continue
            alt_avail = machine_avail.get(alt_mid, 0.0)
            alt_used = machine_util.get(alt_mid, 0.0)
            alt_util = (alt_used / alt_avail) if alt_avail > 0 else 1.0
            if alt_util > 0.5:
                continue
            alt_md = inp.machine_days.get((alt_mid, a.day))
            if alt_md is None or alt_md.remaining_with_overflow < a.run_minutes:
                continue
            old_machine = a.machine_name
            machine_util[mid] = machine_util.get(mid, 0.0) - a.run_minutes
            machine_util[alt_mid] = machine_util.get(alt_mid, 0.0) + a.run_minutes
            a.machine_id = alt_mid
            a.machine_name = alt_md.machine_name
            if alt_tool:
                a.tool_no = alt_tool
                slot_key = (alt_tool, a.day)
                inp.tool_day_machine[slot_key] = alt_mid
                inp.tool_day_part[slot_key] = a.part_no
            swaps_made += 1
            log.append(
                f"Load balance: moved {a.part_no} day {a.day} ({a.qty:.0f} pcs) "
                f"from {old_machine} to {alt_md.machine_name}"
            )
            break

    result.sort(key=lambda a: (a.day, a.machine_id, a.part_no))
    return result, log


# ── Main entry point ─────────────────────────────────────────────────────

def run_scheduler(inp: SchedulerInput) -> RunResult:
    """Execute the full 3-pass scheduling algorithm."""
    from .explainer import compute_kpis, compute_run_analysis

    jobs = _normalize_and_sort(inp)
    assignments, unscheduled = _greedy_assign(inp, jobs)
    assignments, improvement_log = _local_improve(assignments, inp)
    kpi = compute_kpis(assignments, unscheduled, inp)
    analysis = compute_run_analysis(assignments, unscheduled, inp)

    return RunResult(
        assignments=assignments,
        kpi=kpi,
        unscheduled=unscheduled,
        improvement_log=improvement_log,
        actuals=inp.actuals,
        schedule_from_day=inp.schedule_from_day,
        analysis=analysis,
    )
