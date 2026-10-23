"""Safety checks on a planned week (rules.toml [checks]) and the goal's feasibility ([feasibility])."""
from dataclasses import dataclass
from datetime import timedelta
from typing import NamedTuple

from .config import WEEKDAYS
from .history import acwr
from .load import flat_steps, projected_daily
from .metrics import day_index
from .model import Workout
from .templates import ZONE_HR, zone_span
from .terrain import workout_flat_km

HARD_KINDS = ("L", "hill", "trail")      # long runs are hard days whatever their zones (skeleton.HARD)


@dataclass
class Day:
    """One planned session. manual: from profile.toml's [week] (never changed by the fixer);
    forced: why its variant is the smallest one although over its cap ("" when it isn't)."""
    date: object
    slot: str | None
    workout: Workout
    manual: bool = False
    forced: str = ""


class Violation(NamedTuple):
    code: str          # easy_share, hard_count, hard_adjacent, volume_rise, acwr_high, acwr_low, long_share
    detail: str        # (notes: acwr_skipped, forced_size)


class Feasibility(NamedTuple):
    level: str         # "ambitious" or "unrealistic"
    gap: float
    detail: str


def is_easy(step):
    """Z1-2 only, the page's Easy share: the step's HR target, else its pace zone's (E and jog Z2).
    'Z3 cap' and 'Z2-3' reach Z3, so they are not easy; a step with neither isn't either."""
    spec = step.hr_zone or ZONE_HR.get(step.zone)
    return bool(spec) and zone_span(spec)[1] <= 2


def is_hard(w):
    return w.kind in HARD_KINDS or w.hard_km > 0


def easy_share(days):
    """Share of the week's running time that is easy (is_easy); None for a week without running."""
    total = easy = 0
    for d in days:
        for s, n in flat_steps(d.workout):
            total += s.seconds * n
            easy += s.seconds * n if is_easy(s) else 0
    return easy / total if total else None


def week_km(days):
    """The week's volume: hill and trail sessions as flat-equivalent km (terrain.py)."""
    return sum(workout_flat_km(d.workout) for d in days)


def _wd(d):
    return f"{WEEKDAYS[d.weekday()]} {d.isoformat()}"


def _pct(x):
    return f"{x * 100:.0f} %"


def check_week(days, rules, *, e_min, hr_max, hr_rest, prev_km=None, prev_days=(), daily=None, end=None,
               exempt=()):
    """([Violation], [note]) for a week of Days.

    prev_km: last week's volume (volume_rise; skipped when None or in `exempt`). prev_days: last
    week's Days, for back-to-back hard days across the weekend. daily: {day index: TRIMP} of the
    history and the planned weeks before this one; the week's projected load is added and the 7:28
    ratio taken on `end` (its Sunday). daily None, or under 28 days of it, skips the ratio with an
    acwr_skipped note. exempt: codes not checked this week (volume_rise after a deload, acwr_low in
    a deload or the taper). L may exceed its share up to the E minimum, as in the split. A forced
    variant is a forced_size note, never a violation.
    """
    c, out, notes = rules["checks"], [], []
    share = easy_share(days)
    if share is not None and share < c["easy_share"]:
        out.append(Violation("easy_share", f"{_pct(share)} of the running time is easy (Z1-2), under "
                                           f"{_pct(c['easy_share'])}"))
    hard = [d for d in days if is_hard(d.workout)]
    if len(hard) > c["max_hard"]:
        out.append(Violation("hard_count", f"{len(hard)} hard sessions "
                                           f"({', '.join(_wd(d.date) for d in hard)}), more than {c['max_hard']}"))
    mine = {d.date for d in hard}
    dates = sorted(mine | {d.date for d in prev_days if is_hard(d.workout)})
    pairs = [(a, b) for a, b in zip(dates, dates[1:]) if b - a == timedelta(days=1) and b in mine]
    if pairs:
        out.append(Violation("hard_adjacent", "hard sessions on consecutive days: "
                                              + "; ".join(f"{_wd(a)} and {_wd(b)}" for a, b in pairs)))
    km = week_km(days)
    if prev_km and "volume_rise" not in exempt and km > prev_km * (1 + c["max_rise"]) + 0.05:
        out.append(Violation("volume_rise", f"{km:.1f} km is {_pct(km / prev_km - 1)} over last week's "
                                            f"{prev_km:.1f} km, more than {_pct(c['max_rise'])}"))
    ratio = None
    if daily is not None:
        loads = dict(daily)
        for i, v in projected_daily([(d.date, d.workout) for d in days], hr_max, hr_rest).items():
            loads[i] = loads.get(i, 0) + v
        ratio = acwr(loads, day_index(end.isoformat()))
    lo, hi = c["acwr"]
    if ratio is None:
        notes.append(Violation("acwr_skipped", "less than 28 days of history, so the 7:28-day load ratio "
                                               "isn't checked"))
    elif ratio > hi:
        out.append(Violation("acwr_high", f"7:28-day load ratio {ratio:.2f}, over {hi}"))
    elif ratio < lo and "acwr_low" not in exempt:
        out.append(Violation("acwr_low", f"7:28-day load ratio {ratio:.2f}, under {lo}"))
    cap = rules["split"]["long_share_cap"]
    for d in days:
        long_km = workout_flat_km(d.workout)
        if d.slot == "L" and km and long_km > max(cap * km, e_min) + 0.05:
            out.append(Violation("long_share", f"L is {long_km:.1f} km, {_pct(long_km / km)} of the week's "
                                               f"{km:.1f} km, over the {_pct(cap)} cap"))
    notes += [Violation("forced_size", d.forced) for d in days if d.forced]
    return out, notes


def feasibility(current, goal, weeks, rules):
    """Feasibility(level, gap, detail) when the goal VDOT is more than 1 point per realistic_weeks
    above the current one over `weeks` weeks, else None. Boundaries count on the lenient side."""
    f = rules["feasibility"]
    gap = goal - current
    if gap <= weeks / f["realistic_weeks"] + 1e-9:
        return None
    level = "ambitious" if gap <= weeks / f["ambitious_weeks"] + 1e-9 else "unrealistic"
    return Feasibility(level, gap, f"the goal needs VDOT {goal:.1f}, {gap:.1f} above the current {current:.1f}, "
                                   f"in {weeks} weeks: {level} (about 1 point per {f['ambitious_weeks']}-"
                                   f"{f['realistic_weeks']} weeks is realistic)")
