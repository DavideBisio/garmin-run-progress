"""Weekly skeleton: which available day gets the long run (L), quality (Q), easy (E) or flex (F) slot."""
import itertools

from .config import WEEKDAYS
from .physiology import load_rules

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
    Soft: Q as far from L as possible, then as few back-to-back runs as possible once F is dropped.
    """
    hard = [d for d, s in week.items() if s in HARD]
    if any(_gap(a, b) == 1 for a, b in itertools.permutations(hard, 2)):
        return None
    q_dist = [min(_gap(long_day, d), _gap(d, long_day)) for d, s in week.items() if s == "Q"]
    if any(g < 2 for g in q_dist):
        return None
    runs = [d for d, s in week.items() if s != "F"]
    crowd = sum(_gap(a, b) == 1 for a, b in itertools.permutations(runs, 2))
    return (-min(q_dist, default=7), crowd)


def _best(days, long_day, n_q, n_f):
    """The best week with L on long_day, or None. Brute force over the other days' slots (at most
    3^6); ties keep the first in WEEKDAYS order, Q before E before F, so re-plans don't shuffle."""
    others = [d for d in days if d != long_day]
    best, best_score = None, None
    for combo in itertools.product(("Q", "E", "F"), repeat=len(others)):
        if combo.count("Q") != n_q or combo.count("F") != n_f:
            continue
        week = dict(zip(others, combo), **{long_day: "L"})
        score = _score(week, long_day)
        if score is not None and (best_score is None or score < best_score):
            best, best_score = week, score
    return best


def place_slots(days, long_day, rules=None):
    """{weekday: "L" | "Q" | "E" | "F"} for every available day, Monday first.

    L goes on long_day; a Sat/Sun long run falls back to the other weekend day when the preferred
    one leaves no room for Q. Raises SkeletonError naming the rule an impossible set breaks.
    """
    s = (rules or load_rules())["skeleton"]
    for d in days:
        if d not in WEEKDAYS:
            raise SkeletonError(f"unknown day {d!r}; use {', '.join(WEEKDAYS)}")
    days = sorted(set(days), key=WEEKDAYS.index)
    if not days:
        raise SkeletonError("the week needs at least one available day")
    if long_day not in days:
        raise SkeletonError(f"L goes on the preferred day, but {long_day} is not one of the available days "
                            f"({', '.join(days)})")
    n_q = 1 if len(days) >= s["q_min_days"] else 0
    n_f = 1 if len(days) >= s["f_min_days"] else 0
    homes = [long_day]
    if long_day in WEEKEND:
        other = WEEKEND[1 - WEEKEND.index(long_day)]
        if other in days:
            homes.append(other)
    for home in homes:
        week = _best(days, home, n_q, n_f)
        if week is not None:
            return {d: week[d] for d in days}
    raise SkeletonError(f"48 h rule: no day among {', '.join(days)} is at least 48 h from L on "
                        f"{' or '.join(homes)} in both directions, so Q has nowhere to go "
                        "(Q is never the day before or after L)")
