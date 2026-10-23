"""Phase calendar: Monday-based weeks counted back from the race date (rules.toml [phases])."""
import math
from datetime import timedelta
from typing import NamedTuple

PHASES = ("base", "rt", "it", "tm", "taper")   # E + strides/hills, R + T, I + T, T + M, taper


class PhaseError(ValueError):
    """The race can't be planned for (it is already past)."""


class PhaseWeek(NamedTuple):
    start: object          # the week's Monday (date)
    phase: str             # one of PHASES
    partial: bool          # the first week when the plan starts after its Monday: not ramped


def race_key(distance_m, rules):
    """The [phases.*] table whose distance_m is nearest to distance_m (by ratio)."""
    tables = {k: v for k, v in rules["phases"].items() if isinstance(v, dict)}
    return min(tables, key=lambda k: abs(math.log(distance_m / tables[k]["distance_m"])))


def _allocate(n, lengths, order, key):
    """Weeks per phase for n weeks to the race, and a warning when the build is shortened."""
    alloc = {p: lengths[p] for p in PHASES}
    alloc["taper"] = min(lengths["taper"], n)
    left = n - alloc["taper"]
    build = sum(alloc[p] for p in PHASES[:-1])
    if left >= build:
        alloc["base"] += left - build           # more time: a longer base
        return alloc, []
    deficit, cuts = build - left, []
    for p in order:
        cut = min(alloc[p], deficit)
        if cut:
            cuts.append(f"{p} {alloc[p]} -> {alloc[p] - cut}")
            alloc[p] -= cut
            deficit -= cut
    if alloc["taper"] < lengths["taper"]:
        cuts.append(f"taper {lengths['taper']} -> {alloc['taper']}")
    full = build + lengths["taper"]
    return alloc, [f"only {n} weeks to the race, the full {key} plan has {full}: shortened phases "
                   f"{', '.join(cuts)} (weeks, in that order; the ramp is not compressed)"]


def phase_calendar(today, race_date, distance_m, rules, weeks=None):
    """([PhaseWeek(start, phase, partial)], warnings) from the Monday of today's week.

    With a race the calendar ends on the race week (or after `weeks` weeks if fewer); with no
    race it cycles [phases] no_race_cycle for `weeks` weeks (one cycle by default).
    """
    p = rules["phases"]
    first = today - timedelta(days=today.weekday())
    if race_date is None:
        cycle, per = p["no_race_cycle"], p["no_race_weeks"]
        n = weeks or len(cycle) * per
        names, warnings = [cycle[(i // per) % len(cycle)] for i in range(n)], []
    else:
        if race_date < today:
            raise PhaseError(f"the race date {race_date} is before today ({today})")
        n = ((race_date - timedelta(days=race_date.weekday())) - first).days // 7 + 1
        key = race_key(distance_m, rules)
        alloc, warnings = _allocate(n, p[key], p["shorten_order"], key)
        names = [ph for ph in PHASES for _ in range(alloc[ph])]
        if weeks:
            names = names[:weeks]
    return [PhaseWeek(first + timedelta(weeks=i), ph, i == 0 and today != first)
            for i, ph in enumerate(names)], warnings
