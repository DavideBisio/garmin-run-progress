"""Weekly skeleton: which available day gets the long run (L), quality (Q), easy (E) or flex (F) slot."""
import itertools

from .config import WEEKDAYS
from .levels import DEFAULT_LEVEL, load_levels, params

HARD = ("L", "Q")
WEEKEND = ("sat", "sun")


class SkeletonError(ValueError):
    """The available days can't hold a week that keeps the placement rules."""


def _gap(a, b):
    """Days from a forward to b in a repeating week, 1..7 (sun -> mon is 1)."""
    return (WEEKDAYS.index(b) - WEEKDAYS.index(a)) % 7 or 7


def _score(week, long_day):
    """Lower is better; None when a hard rule breaks.

    Hard: no back-to-back hard days; Q at least 48 h from L both ways (so never the day after L).
    Soft: Q as far from L as possible, then the Q days as far apart as possible, then as few
    back-to-back runs as possible once F is dropped.
    """
    hard = [d for d, s in week.items() if s in HARD]
    if any(_gap(a, b) == 1 for a, b in itertools.permutations(hard, 2)):
        return None
    qs = [d for d, s in week.items() if s == "Q"]
    q_dist = [min(_gap(long_day, d), _gap(d, long_day)) for d in qs]
    if any(g < 2 for g in q_dist):
        return None
    q_apart = min((_gap(a, b) for a, b in itertools.permutations(qs, 2)), default=7)
    runs = [d for d, s in week.items() if s != "F"]
    crowd = sum(_gap(a, b) == 1 for a, b in itertools.permutations(runs, 2))
    return (-min(q_dist, default=7), -q_apart, crowd)


def _best(days, long_day, n_q, n_f, n_runs):
    """(score, week) of the best week of n_runs of the days with L on long_day, or None. Brute force
    over the run days (the other days rest) and their slots (at most 3^6 each); ties keep the first in
    WEEKDAYS order, Q before E before F, so re-plans don't shuffle."""
    others = [d for d in days if d != long_day]
    best = None
    for kept in itertools.combinations(others, n_runs - 1):
        for combo in itertools.product(("Q", "E", "F"), repeat=len(kept)):
            if combo.count("Q") != n_q or combo.count("F") != n_f:
                continue
            week = dict(zip(kept, combo), **{long_day: "L"})
            score = _score(week, long_day)
            if score is not None and (best is None or score < best[0]):
                best = (score, week)
    return best


def q_count(n_runs, rules):
    """Q days the level wants in a week of n_runs runs: one more from each [skeleton] q_from_days."""
    return sum(n_runs >= k for k in rules["skeleton"]["q_from_days"])


def place_slots(days, long_day, rules=None):
    """{weekday: "L" | "Q" | "E" | "F"} for the run days, Monday first.

    At most [skeleton] max_runs of the days are run days: the extra ones rest, chosen by the same
    score. L goes on long_day; a Sat/Sun long run falls back to the other weekend day when the
    preferred one leaves no room for Q. The week gets q_count Q days, or as many as the placement
    rules allow (at least one when it wants any). Raises SkeletonError naming the rule an impossible
    set breaks.
    """
    s = (rules or params(load_levels(), DEFAULT_LEVEL, DEFAULT_LEVEL))["skeleton"]
    for d in days:
        if d not in WEEKDAYS:
            raise SkeletonError(f"unknown day {d!r}; use {', '.join(WEEKDAYS)}")
    days = sorted(set(days), key=WEEKDAYS.index)
    if not days:
        raise SkeletonError("the week needs at least one available day")
    if long_day not in days:
        raise SkeletonError(f"L goes on the preferred day, but {long_day} is not one of the available days "
                            f"({', '.join(days)})")
    n_runs = min(len(days), s.get("max_runs", len(days)))
    n_q = q_count(n_runs, {"skeleton": s})
    n_f = 1 if n_runs >= s["f_min_days"] else 0
    homes = [long_day]
    if long_day in WEEKEND:
        other = WEEKEND[1 - WEEKEND.index(long_day)]
        if other in days:
            homes.append(other)
    for home in homes:
        for q in range(n_q, 0 if n_q else -1, -1):
            best = _best(days, home, q, n_f, n_runs)
            if best is not None:
                return {d: best[1][d] for d in days if d in best[1]}
    raise SkeletonError(f"48 h rule: no day among {', '.join(days)} is at least 48 h from L on "
                        f"{' or '.join(homes)} in both directions, so Q has nowhere to go "
                        "(Q is never the day before or after L)")
