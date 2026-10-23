"""Projected training load of planned workouts: TRIMP per step at its HR zone's midpoint (metrics.trimp)."""
from .metrics import day_index, trimp
from .model import Repeat
from .templates import ZONE_HR, hr_range


def flat_steps(w):
    """[(Step, count)] of a workout in order: a repeat's steps n times each, its last recovery once
    less when skip_last_rest (as the workout's totals count it)."""
    out = []
    for p in w.parts:
        if not isinstance(p, Repeat):
            out.append((p, 1))
            continue
        for i, s in enumerate(p.steps):
            last = i == len(p.steps) - 1 and s.role == "recovery" and p.skip_last_rest
            out.append((s, p.n - 1 if last else p.n))
    return out


def hr_mid(step, hr_max, hr_rest):
    """The midpoint (bpm) of the step's HR target, else of its pace zone's usual HR zone (E and jog
    Z2, T Z4 ...); None for a step with neither."""
    hr = step.hr
    if hr is None and ZONE_HR.get(step.zone):
        hr = hr_range(ZONE_HR[step.zone], hr_max, hr_rest)
    return None if hr is None else (hr.lo + hr.hi) / 2


def step_trimp(step, hr_max, hr_rest):
    """Banister TRIMP of one step: its duration at hr_mid, through the page's trimp (resting HR
    clamped to max - 20 first, as the page does). 0 without an HR to project."""
    hr = hr_mid(step, hr_max, hr_rest)
    if hr is None:
        return 0
    return trimp({"moving": step.seconds, "avgHr": hr}, hr_max, min(hr_rest, hr_max - 20))


def workout_trimp(w, hr_max, hr_rest):
    return sum(step_trimp(s, hr_max, hr_rest) * n for s, n in flat_steps(w))


def projected_daily(days, hr_max, hr_rest):
    """{day index (metrics.day_index): TRIMP} of [(date, Workout)], workouts on one day added up."""
    out = {}
    for d, w in days:
        i = day_index(d.isoformat())
        out[i] = out.get(i, 0) + workout_trimp(w, hr_max, hr_rest)
    return out
