"""KPI computation, run analysis, and comparison."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from .models import Assignment, RunResult, SchedulerInput, UnscheduledPart


def compute_kpis(
    assignments: List[Assignment],
    unscheduled: List[UnscheduledPart],
    inp: SchedulerInput,
) -> Dict[str, Any]:
    """Compute summary and per-machine KPIs from a completed scheduler run."""

    # Machine utilization (full month for total view)
    machine_scheduled: Dict[int, float] = defaultdict(float)
    machine_produced: Dict[int, float] = defaultdict(float)
    machine_avail: Dict[int, float] = defaultdict(float)
    machine_names: Dict[int, str] = {}
    machine_changeovers: Dict[int, int] = defaultdict(int)
    machine_overflow: Dict[int, float] = defaultdict(float)

    for (_mid, _day), md in inp.machine_days.items():
        machine_avail[md.machine_id] += md.available_minutes
        machine_names[md.machine_id] = md.machine_name

    for a in assignments:
        if not a.is_actual:
            machine_scheduled[a.machine_id] += a.run_minutes

    for act in inp.actuals:
        mid = act.get("machine_id")
        if mid is not None:
            machine_produced[mid] += float(act.get("run_minutes") or 0)

    # Tool utilization accumulators
    tool_scheduled: Dict[str, float] = defaultdict(float)
    tool_produced: Dict[str, float] = defaultdict(float)
    tool_slots: Dict[str, Set[Tuple[int, int]]] = defaultdict(set)

    for a in assignments:
        if not a.is_actual and a.tool_no:
            tool_scheduled[a.tool_no] += a.run_minutes
            tool_slots[a.tool_no].add((a.machine_id, a.day))

    for act in inp.actuals:
        tool_no = act.get("tool_no") or ""
        if not tool_no:
            pk = act.get("part_no", "")
            for tno, parts in inp.parts_by_tool.items():
                if pk in parts:
                    tool_no = tno
                    break
        if tool_no:
            tool_produced[tool_no] += float(act.get("run_minutes") or 0)
            mid = act.get("machine_id")
            day = act.get("day")
            if mid is not None and day is not None:
                tool_slots[tool_no].add((mid, day))

    # Per-machine-per-day breakdown
    per_machine_day: List[Dict[str, Any]] = []
    machine_day_parts_map: Dict[Tuple[int, int], Set[str]] = defaultdict(set)
    for a in assignments:
        if not a.is_actual:
            machine_day_parts_map[(a.machine_id, a.day)].add(a.part_no)

    for (mid, day), md in sorted(inp.machine_days.items()):
        if day < inp.schedule_from_day:
            continue
        used = sum(a.run_minutes for a in assignments
                   if a.machine_id == mid and a.day == day and not a.is_actual)
        parts = list(machine_day_parts_map.get((mid, day), set()))
        util_pct = round((used / md.available_minutes) * 100, 1) if md.available_minutes > 0 else 0.0
        per_machine_day.append({
            "machine_id": mid,
            "machine_name": md.machine_name,
            "day": day,
            "used_minutes": round(used, 1),
            "available_minutes": round(md.available_minutes, 1),
            "utilization_pct": util_pct,
            "overflow_used": round(md.overflow_minutes_used, 1),
            "parts": parts,
            "changeovers": max(0, len(parts) - 1),
        })
        machine_changeovers[mid] = machine_changeovers.get(mid, 0) + max(0, len(parts) - 1)
        machine_overflow[mid] = machine_overflow.get(mid, 0.0) + md.overflow_minutes_used

    per_machine: List[Dict[str, Any]] = []
    total_used = 0.0
    total_avail = 0.0
    for mid in sorted(machine_avail.keys()):
        avail = machine_avail[mid]
        sched = machine_scheduled.get(mid, 0.0)
        prod = machine_produced.get(mid, 0.0)
        total = sched + prod
        total_used += total
        total_avail += avail
        pct = round((total / avail) * 100, 1) if avail > 0 else 0.0
        per_machine.append({
            "machine_id": mid,
            "machine_name": machine_names.get(mid, str(mid)),
            "scheduled_minutes": round(sched, 1),
            "produced_minutes": round(prod, 1),
            "total_minutes": round(total, 1),
            "used_minutes": round(total, 1),
            "available_minutes": round(avail, 1),
            "utilization_pct": pct,
            "changeovers": machine_changeovers.get(mid, 0),
            "overflow_minutes": round(machine_overflow.get(mid, 0.0), 1),
        })

    per_tool: List[Dict[str, Any]] = []
    all_tool_keys = set(tool_scheduled.keys()) | set(tool_produced.keys())
    for tool_no in sorted(all_tool_keys):
        sched = tool_scheduled.get(tool_no, 0.0)
        prod = tool_produced.get(tool_no, 0.0)
        total = sched + prod
        avail = sum(
            inp.machine_days[slot].available_minutes
            for slot in tool_slots.get(tool_no, set())
            if slot in inp.machine_days
        )
        pct = round((total / avail) * 100, 1) if avail > 0 else 0.0
        per_tool.append({
            "tool_no": tool_no,
            "scheduled_minutes": round(sched, 1),
            "produced_minutes": round(prod, 1),
            "total_minutes": round(total, 1),
            "used_minutes": round(total, 1),
            "available_minutes": round(avail, 1),
            "utilization_pct": pct,
        })

    overall_util = round((total_used / total_avail) * 100, 1) if total_avail > 0 else 0.0

    # Bottleneck machines (top 5 by utilization)
    bottlenecks = sorted(per_machine, key=lambda m: -m["utilization_pct"])[:5]

    # Idle machine-days (forward horizon only)
    idle_machine_days = sum(
        1 for pmd in per_machine_day
        if pmd["used_minutes"] == 0 and pmd["day"] >= inp.schedule_from_day
    )

    # Overflow total
    overflow_total = round(sum(machine_overflow.values()), 1)

    # On-time delivery
    scheduled_by_part: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for a in assignments:
        if not a.is_actual:
            scheduled_by_part[a.part_no][a.day] += a.qty

    jobs_by_part = {j.part_no: j for j in inp.jobs}
    on_time_count = 0
    late_count = 0
    total_delay_days = 0.0

    for part_no, job in jobs_by_part.items():
        if not job.dispatch_days:
            continue
        sched = scheduled_by_part.get(part_no, {})
        for disp_day in sorted(job.dispatch_days.keys()):
            disp_qty = job.dispatch_days[disp_day]
            produced_by_day = sum(q for d, q in sched.items() if d <= disp_day)
            if produced_by_day >= disp_qty - 0.5:
                on_time_count += 1
            else:
                late_count += 1
                shortfall = disp_qty - produced_by_day
                days_late = 0
                for future_day in sorted(sched.keys()):
                    if future_day > disp_day:
                        shortfall -= sched[future_day]
                        if shortfall <= 0.5:
                            days_late = future_day - disp_day
                            break
                if shortfall > 0.5:
                    days_late = 31 - disp_day
                total_delay_days += days_late

    total_dispatches = on_time_count + late_count
    on_time_pct = round((on_time_count / total_dispatches) * 100, 1) if total_dispatches > 0 else 100.0

    # RM coverage
    total_demand = sum(j.effective_qty for j in inp.jobs if not j.is_supplier and j.total_qty > 0)
    total_scheduled = sum(a.qty for a in assignments if not a.is_actual)
    rm_coverage_pct = round((total_scheduled / total_demand) * 100, 1) if total_demand > 0 else 0.0

    # Tool risk
    pm_risk_tools: List[str] = []
    eol_risk_tools: List[str] = []
    for tool_no, ts in inp.tool_states.items():
        if ts.pm_proximity >= 0.8:
            pm_risk_tools.append(tool_no)
        if ts.total_life > 0:
            frac = (ts.current_strokes + ts.accumulated_scheduled_strokes) / ts.total_life
            if frac >= 0.8:
                eol_risk_tools.append(tool_no)

    # Changeover count
    total_changeovers = sum(machine_changeovers.values())
    active_machine_days = sum(1 for pmd in per_machine_day if pmd["used_minutes"] > 0)
    avg_changeovers = round(total_changeovers / active_machine_days, 2) if active_machine_days > 0 else 0.0

    # Makespan
    sched_days = [a.day for a in assignments if not a.is_actual]
    makespan = max(sched_days) if sched_days else 0

    return {
        "overall_utilization_pct": overall_util,
        "per_machine": per_machine,
        "per_tool": per_tool,
        "per_machine_per_day": per_machine_day,
        "bottleneck_machines": bottlenecks,
        "idle_machine_days": idle_machine_days,
        "overflow_minutes_total": overflow_total,
        "on_time_pct": on_time_pct,
        "on_time_count": on_time_count,
        "late_count": late_count,
        "total_delay_days": round(total_delay_days, 1),
        "rm_coverage_pct": rm_coverage_pct,
        "total_scheduled": round(total_scheduled, 1),
        "total_demand": round(total_demand, 1),
        "pm_risk_tool_count": len(pm_risk_tools),
        "pm_risk_tools": pm_risk_tools,
        "eol_risk_tool_count": len(eol_risk_tools),
        "eol_risk_tools": eol_risk_tools,
        "total_changeovers": total_changeovers,
        "avg_changeovers_per_machine_day": avg_changeovers,
        "makespan_day": makespan,
        "unscheduled_count": len(unscheduled),
        "schedule_from_day": inp.schedule_from_day,
        "weight_profile": inp.scenario.weights,
    }


def compute_run_analysis(
    assignments: List[Assignment],
    unscheduled: List[UnscheduledPart],
    inp: SchedulerInput,
) -> Dict[str, Any]:
    """Run-level narrative, per-part trace, and constraint failure histogram."""
    jobs_by_part = {j.part_no: j for j in inp.jobs}

    # Per-part trace with dispatch checkpoint progress
    part_traces: List[Dict[str, Any]] = []
    scheduled_by_part: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for a in assignments:
        if not a.is_actual:
            scheduled_by_part[a.part_no][a.day] += a.qty

    for part_no, job in jobs_by_part.items():
        if job.is_supplier or job.total_qty <= 0:
            continue
        sched = scheduled_by_part.get(part_no, {})
        total_sched = sum(sched.values())
        checkpoints = []
        for disp_day in sorted(job.dispatch_days.keys()):
            disp_qty = job.dispatch_days[disp_day]
            produced_by = sum(q for d, q in sched.items() if d <= disp_day)
            status = "on-time" if produced_by >= disp_qty - 0.5 else (
                "at-risk" if produced_by >= disp_qty * 0.5 else "late"
            )
            checkpoints.append({
                "dispatch_day": disp_day,
                "required_qty": round(disp_qty, 2),
                "scheduled_by_day": round(produced_by, 2),
                "status": status,
            })

        unsched_entry = next((u for u in unscheduled if u.part_no == part_no), None)
        part_traces.append({
            "part_no": part_no,
            "part_name": job.part_name,
            "total_qty": round(job.effective_qty, 2),
            "total_scheduled": round(total_sched, 2),
            "unscheduled_qty": round(unsched_entry.qty_remaining, 2) if unsched_entry else 0,
            "dispatch_checkpoints": checkpoints,
            "machines_used": list(set(
                a.machine_name for a in assignments
                if a.part_no == part_no and not a.is_actual
            )),
        })

    # Constraint failure histogram from rejected alternatives
    failure_counts: Dict[str, int] = defaultdict(int)
    for a in assignments:
        for rej in (a.score.alternatives_rejected or []):
            reason = str(rej.get("reason", "Unknown"))
            key = reason.split("(")[0].strip() if "(" in reason else reason
            failure_counts[key] = failure_counts.get(key, 0) + 1

    # Narrative bullets
    narrative: List[str] = []
    total_parts = len([j for j in inp.jobs if not j.is_supplier and j.total_qty > 0])
    total_sched_parts = len(set(a.part_no for a in assignments if not a.is_actual))
    narrative.append(f"{total_sched_parts} of {total_parts} parts scheduled across {len(assignments)} assignments")

    if unscheduled:
        rm_blocked = sum(1 for u in unscheduled if "RM" in u.reason.upper() or "rm" in u.reason)
        cap_blocked = len(unscheduled) - rm_blocked
        if rm_blocked:
            narrative.append(f"{rm_blocked} part(s) unscheduled due to RM constraints")
        if cap_blocked:
            narrative.append(f"{cap_blocked} part(s) unscheduled due to capacity constraints")

    # Machine utilization highlights
    machine_used: Dict[int, float] = defaultdict(float)
    machine_avail: Dict[int, float] = defaultdict(float)
    machine_names: Dict[int, str] = {}
    for (mid, day), md in inp.machine_days.items():
        if day >= inp.schedule_from_day:
            machine_avail[mid] += md.available_minutes
            machine_names[mid] = md.machine_name
    for a in assignments:
        if not a.is_actual:
            machine_used[a.machine_id] += a.run_minutes

    high_util = [(machine_names[mid], round(machine_used[mid] / machine_avail[mid] * 100, 1))
                 for mid in machine_avail if machine_avail[mid] > 0 and machine_used.get(mid, 0) / machine_avail[mid] > 0.85]
    if high_util:
        top = sorted(high_util, key=lambda x: -x[1])[:3]
        machines_str = ", ".join(f"{name} ({pct}%)" for name, pct in top)
        narrative.append(f"High utilization: {machines_str}")

    idle = [machine_names[mid] for mid in machine_avail if machine_used.get(mid, 0) == 0]
    if idle:
        narrative.append(f"Idle machines: {', '.join(idle[:5])}")

    if inp.schedule_from_day > 1:
        narrative.append(f"Scheduling from day {inp.schedule_from_day} (today); earlier days show actuals")

    return {
        "narrative": narrative,
        "part_traces": part_traces,
        "constraint_failure_histogram": dict(failure_counts),
    }


def compare_runs(run_a: RunResult, run_b: RunResult) -> Dict[str, Any]:
    """Diff two run results — identify added, removed, and moved assignments."""
    key_fn = lambda a: (a.part_no, a.machine_id, a.day)
    set_a = {key_fn(a): a for a in run_a.assignments if not a.is_actual}
    set_b = {key_fn(a): a for a in run_b.assignments if not a.is_actual}

    keys_a = set(set_a.keys())
    keys_b = set(set_b.keys())

    added = [set_b[k].to_dict() for k in (keys_b - keys_a)]
    removed = [set_a[k].to_dict() for k in (keys_a - keys_b)]

    changed = []
    for k in keys_a & keys_b:
        a, b = set_a[k], set_b[k]
        if abs(a.qty - b.qty) > 0.5 or abs(a.run_minutes - b.run_minutes) > 0.5:
            changed.append({
                "key": {"part_no": k[0], "machine_id": k[1], "day": k[2]},
                "before": {"qty": round(a.qty, 2), "run_minutes": round(a.run_minutes, 2)},
                "after": {"qty": round(b.qty, 2), "run_minutes": round(b.run_minutes, 2)},
            })

    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added": added,
        "removed": removed,
        "changed": changed,
        "kpi_a": run_a.kpi,
        "kpi_b": run_b.kpi,
    }
