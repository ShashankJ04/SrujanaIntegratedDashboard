"""Machine capacity model — working days, machine-day grid, rate computations."""

from __future__ import annotations

import calendar
import math
from datetime import date
from typing import Any, Dict, List, Tuple

from .models import MachineDay


def get_working_days(month: int, year: int, calendar_rows: List[Dict[str, Any]]) -> Dict[int, float]:
    """Return {day_num: shift_hours} for each working day in the month.

    *calendar_rows* come from ``scheduler_working_calendar`` for the month.
    Days without an explicit row default to Mon–Sat working, Sun off.
    """
    days_in_month = calendar.monthrange(year, month)[1]
    explicit: Dict[int, Tuple[bool, float]] = {}
    for r in calendar_rows:
        d = r.get("cal_date")
        if d is None:
            continue
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        if d.month != month or d.year != year:
            continue
        is_working = bool(r.get("is_working", 1))
        shift = float(r["shift_hours"]) if r.get("shift_hours") is not None else None
        explicit[d.day] = (is_working, shift)

    out: Dict[int, float] = {}
    for day_num in range(1, days_in_month + 1):
        if day_num in explicit:
            is_working, shift = explicit[day_num]
            if not is_working:
                continue
            out[day_num] = shift if shift is not None else 0.0
        else:
            weekday = date(year, month, day_num).weekday()  # Mon=0 … Sun=6
            if weekday < 6:  # Mon–Sat
                out[day_num] = 0.0  # 0.0 means "use global default"
    return out


def build_machine_day_grid(
    machines: List[Dict[str, Any]],
    working_days: Dict[int, float],
    work_hours: int,
) -> Dict[Tuple[int, int], MachineDay]:
    """Build the (machine_id, day) → MachineDay grid."""
    grid: Dict[Tuple[int, int], MachineDay] = {}
    for m in machines:
        mid = int(m["id"])
        mname = str(m.get("label") or m.get("name") or mid)
        for day_num, shift in working_days.items():
            hours = shift if shift > 0 else work_hours
            grid[(mid, day_num)] = MachineDay(
                machine_id=mid,
                machine_name=mname,
                day=day_num,
                available_minutes=hours * 60,
            )
    return grid


def compute_run_minutes(qty: float, spm: float, cavity: int) -> float:
    """Minutes needed to produce *qty* parts at *spm* strokes/min with *cavity*."""
    rate = spm * max(cavity, 1)
    if rate <= 0:
        return 0.0
    return math.ceil(qty / rate)


def compute_strokes(qty: float, cavity: int) -> int:
    """Number of press strokes for *qty* parts."""
    c = max(cavity, 1)
    return math.ceil(qty / c)
