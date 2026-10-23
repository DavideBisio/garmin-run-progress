"""Auto-fix a generated week (rules.toml [fix]): shrink Q, then trim L, then drop F. Bounded, deterministic."""
from dataclasses import dataclass, replace
from typing import NamedTuple

ORDER = ("shrink_q", "trim_l", "drop_f")
# The fixes that can help each check, tried in ORDER. Shrinking Q keeps the week's km (the split
# gives them to the easy runs), so it can't help a volume rise; nothing here helps too many or
# back-to-back hard days, or a low load ratio: those stay warnings.
FIXES = {
    "easy_share": ("shrink_q",),
    "acwr_high": ("shrink_q", "trim_l", "drop_f"),
    "volume_rise": ("trim_l", "drop_f"),
    "long_share": ("trim_l",),
}


@dataclass(frozen=True)
class Adjust:
    """What the fixer changed, the input of build(): Q variants down, km off L, F dropped."""
    q_down: int = 0
    trim_l_km: float = 0.0
    drop_f: bool = False


class FixResult(NamedTuple):
    days: list
    adjust: Adjust
    violations: list         # what still fails
    notes: list
    actions: list            # the fixes applied, in order
    stopped: bool            # max_iter fixes applied with one still to try


def _apply(adj, action, trim_km):
    if action == "shrink_q":
        return replace(adj, q_down=adj.q_down + 1)
    if action == "trim_l":
        return replace(adj, trim_l_km=adj.trim_l_km + trim_km)
    return replace(adj, drop_f=True)


def _key(days):
    return [(d.date, d.workout.id, d.workout.variant, round(d.workout.km, 3)) for d in days]


def _next(violations, adj, days, build, trim_km):
    """(action, adjust, days) of the first wanted fix that changes the week, else None. A fix that
    changes nothing (Q at variant 1, L at the E minimum, a manual day, no F left) is used up."""
    wanted = {a for v in violations for a in FIXES.get(v.code, ())}
    for action in ORDER:
        if action not in wanted or (action == "drop_f" and adj.drop_f):
            continue
        cand = _apply(adj, action, trim_km)
        new = build(cand)
        if _key(new) != _key(days):
            return action, cand, new
    return None


def fix_week(build, check, rules):
    """FixResult of fixing the week build(Adjust()) until check(days) -> (violations, notes) has
    nothing a fix can help, no fix changes the week, or max_iter fixes were applied (stopped).
    The same inputs always give the same result: one fix at a time, the first in ORDER that helps."""
    f = rules["fix"]
    adj = Adjust()
    days = build(adj)
    violations, notes = check(days)
    actions = []
    for _ in range(f["max_iter"]):
        step = _next(violations, adj, days, build, f["trim_l_km"])
        if step is None:
            return FixResult(days, adj, violations, notes, actions, False)
        action, adj, days = step
        actions.append(action)
        violations, notes = check(days)
    stopped = _next(violations, adj, days, build, f["trim_l_km"]) is not None
    return FixResult(days, adj, violations, notes, actions, stopped)
