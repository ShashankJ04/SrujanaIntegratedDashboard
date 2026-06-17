"""Dataclasses used throughout the scheduling engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Default weights ──────────────────────────────────────────────────────

DEFAULT_WEIGHTS: Dict[str, float] = {
    "w_urgency": 0.35,
    "w_utilize": 0.20,
    "w_primary": 0.15,
    "w_pm_risk": 0.15,
    "w_changeover": 0.10,
    "w_idle": 0.05,
}


# ── Core domain objects ──────────────────────────────────────────────────

@dataclass
class Job:
    part_no: str
    part_name: str
    total_qty: float
    rm_cap_qty: float
    dispatch_days: Dict[int, float]
    primary_machine_id: Optional[int]
    alt_machines: List[Tuple[int, int]]  # (machine_id, alt_rank)
    is_supplier: bool
    tool_no: str
    spm: float
    cavity: int
    part_tools: List[str] = field(default_factory=list)  # all tools that can produce this part
    machine_tools: Dict[int, str] = field(default_factory=dict)  # capable machine_id -> default tool
    user_priority: int = 0
    pinned_machine: Optional[int] = None
    pinned_day: Optional[int] = None

    def tool_for_machine(self, machine_id: int) -> str:
        """Tool assigned to this part on the given machine (inferred from mappings)."""
        mid = int(machine_id)
        if mid in self.machine_tools:
            return self.machine_tools[mid]
        if self.primary_machine_id == mid and self.tool_no:
            return self.tool_no
        return ""

    def has_tool_on_machine(self, machine_id: int) -> bool:
        return bool(self.tool_for_machine(machine_id))

    @property
    def effective_qty(self) -> float:
        """Production qty capped at RM availability."""
        return min(self.total_qty, self.rm_cap_qty) if self.rm_cap_qty > 0 else self.total_qty

    @property
    def earliest_dispatch_day(self) -> int:
        if not self.dispatch_days:
            return 31
        return min(self.dispatch_days.keys())

    @property
    def parts_per_minute(self) -> float:
        return self.spm * max(self.cavity, 1)

    def cumulative_dispatch_targets(self) -> Dict[int, float]:
        """Running cumulative qty required by each dispatch day."""
        if not self.dispatch_days:
            return {}
        cum = 0.0
        out: Dict[int, float] = {}
        for day in sorted(self.dispatch_days.keys()):
            cum += self.dispatch_days[day]
            out[day] = cum
        return out


@dataclass
class MachineDay:
    machine_id: int
    machine_name: str
    day: int
    available_minutes: float
    used_minutes: float = 0.0
    overflow_limit: float = 30.0
    overflow_minutes_used: float = 0.0
    parts_scheduled: List[str] = field(default_factory=list)

    @property
    def remaining_minutes(self) -> float:
        return max(0.0, self.available_minutes - self.used_minutes)

    @property
    def remaining_with_overflow(self) -> float:
        overflow_left = max(0.0, self.overflow_limit - self.overflow_minutes_used)
        return self.remaining_minutes + overflow_left

    @property
    def utilization(self) -> float:
        if self.available_minutes <= 0:
            return 0.0
        return self.used_minutes / self.available_minutes

    @property
    def changeover_count(self) -> int:
        return max(0, len(set(self.parts_scheduled)) - 1)

    @property
    def uses_overflow(self) -> bool:
        return self.overflow_minutes_used > 0


@dataclass
class ToolState:
    tool_no: str
    current_strokes: int
    next_pm_stroke: int
    total_life: int
    pm_interval: int
    is_in_breakdown: bool
    accumulated_scheduled_strokes: int = 0

    @property
    def strokes_to_pm(self) -> int:
        return max(0, self.next_pm_stroke - (self.current_strokes + self.accumulated_scheduled_strokes))

    @property
    def strokes_to_eol(self) -> int:
        return max(0, self.total_life - (self.current_strokes + self.accumulated_scheduled_strokes))

    @property
    def pm_proximity(self) -> float:
        """0..1 — 1.0 means at PM threshold."""
        if self.pm_interval <= 0:
            return 0.0
        used_since_pm = self.pm_interval - self.strokes_to_pm
        return min(1.0, max(0.0, used_since_pm / self.pm_interval))


# ── Score / Assignment ───────────────────────────────────────────────────

@dataclass
class ScoreFactor:
    key: str
    weight: float
    factor: float
    contribution: float
    reason: str


@dataclass
class ScoreResult:
    total: float
    breakdown: List[ScoreFactor]
    alternatives_rejected: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class Assignment:
    part_no: str
    part_name: str
    machine_id: int
    machine_name: str
    day: int
    qty: float
    run_minutes: float
    strokes: int
    score: ScoreResult
    tool_no: str = ""
    constraints_checked: Dict[str, bool] = field(default_factory=dict)
    is_actual: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_no": self.part_no,
            "part_name": self.part_name,
            "machine_id": self.machine_id,
            "machine_name": self.machine_name,
            "tool_no": self.tool_no,
            "day": self.day,
            "qty": round(self.qty, 2),
            "run_minutes": round(self.run_minutes, 2),
            "strokes": self.strokes,
            "is_actual": self.is_actual,
            "score": {
                "total": round(self.score.total, 4),
                "breakdown": [
                    {
                        "key": f.key,
                        "weight": f.weight,
                        "factor": round(f.factor, 4),
                        "contribution": round(f.contribution, 4),
                        "reason": f.reason,
                    }
                    for f in self.score.breakdown
                ],
                "alternatives_rejected": self.score.alternatives_rejected,
            },
            "constraints_checked": self.constraints_checked,
        }


@dataclass
class UnscheduledPart:
    part_no: str
    part_name: str
    qty_remaining: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_no": self.part_no,
            "part_name": self.part_name,
            "qty_remaining": round(self.qty_remaining, 2),
            "reason": self.reason,
        }


# ── Scenario / Run ───────────────────────────────────────────────────────

@dataclass
class Scenario:
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    overrides: Dict[str, Any] = field(default_factory=dict)
    frozen_days: int = 0  # kept for DB compat; ignored by engine

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "Scenario":
        import json
        weights = row.get("weights_json")
        if isinstance(weights, (bytes, bytearray)):
            weights = json.loads(weights.decode())
        elif isinstance(weights, str):
            weights = json.loads(weights)
        overrides = row.get("overrides_json")
        if isinstance(overrides, (bytes, bytearray)):
            overrides = json.loads(overrides.decode())
        elif isinstance(overrides, str):
            overrides = json.loads(overrides)
        merged_weights = dict(DEFAULT_WEIGHTS)
        if isinstance(weights, dict):
            merged_weights.update(weights)
        return cls(
            weights=merged_weights,
            overrides=overrides or {},
            frozen_days=int(row.get("frozen_days") or 0),
        )


@dataclass
class RunResult:
    assignments: List[Assignment]
    kpi: Dict[str, Any]
    unscheduled: List[UnscheduledPart]
    improvement_log: List[str] = field(default_factory=list)
    actuals: List[Dict[str, Any]] = field(default_factory=list)
    schedule_from_day: int = 1
    analysis: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assignments": [a.to_dict() for a in self.assignments],
            "kpi": self.kpi,
            "unscheduled": [u.to_dict() for u in self.unscheduled],
            "improvement_log": self.improvement_log,
            "actuals": self.actuals,
            "schedule_from_day": self.schedule_from_day,
            "analysis": self.analysis,
        }


# ── Scheduler input bundle ───────────────────────────────────────────────

@dataclass
class SchedulerInput:
    month: int
    year: int
    jobs: List[Job]
    machine_days: Dict[Tuple[int, int], MachineDay]  # (machine_id, day)
    tool_states: Dict[str, ToolState]  # keyed by tool_no
    scenario: Scenario
    work_hours_per_day: int = 6
    overflow_minutes: int = 30
    schedule_from_day: int = 1
    actuals: List[Dict[str, Any]] = field(default_factory=list)
    # (tool_no, day) -> machine_id — tool cannot be on two machines same day
    tool_day_machine: Dict[Tuple[str, int], int] = field(default_factory=dict)
    # (tool_no, day) -> part_no holding the tool that day (cross-part awareness)
    tool_day_part: Dict[Tuple[str, int], str] = field(default_factory=dict)
    # tool_no -> part numbers that share this physical tool
    parts_by_tool: Dict[str, List[str]] = field(default_factory=dict)
