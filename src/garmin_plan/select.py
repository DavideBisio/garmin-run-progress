"""Session choice: which template each Q and L slot gets, from the phase rotations (rules.toml [rotation])."""
from .templates import LEVELS


def block_week(i, deloads, every):
    """Week i's place (1-based) in its block: the deload week is `every`, the build weeks count from
    the week after the previous deload (or the plan's first week). A build week past every - 1, in a
    block lengthened by a deload moved later, stays at every - 1 (the block's biggest week)."""
    if i in deloads:
        return every
    prev = max((d for d in deloads if d < i), default=-1)
    return min(i - prev, every - 1)


def _entry(table, key, bw, deload):
    rows = table.get(key) or []
    if not rows:
        return []
    return rows[-1] if deload else rows[(bw - 1) % len(rows)]


def candidates(phase, bw, slot, rules, *, deload=False, hill_day=False, level=None, library):
    """Template ids for a Q or L slot, in order of preference: the hill swap first on a hill day (never
    in a deload), then the phase's rotation for block week bw. Ids above the runner's level are left
    out; when none is left, the one with the lowest min_level is kept."""
    table = rules["rotation"][phase]
    level = LEVELS.index(level or rules["rotation"]["level"])
    ids = (_entry(table, f"{slot}_hill", bw, deload) if hill_day and not deload else []) + \
        _entry(table, slot, bw, deload)
    ok = [t for t in ids if LEVELS.index(library[t]["min_level"]) <= level]
    return ok or [min(ids, key=lambda t: LEVELS.index(library[t]["min_level"]))]


def rotation(phase, bw, slot, rules, *, deload=False, hill_day=False, level=None, library):
    """The template id for a Q or L slot in block week bw of `phase`: the first of candidates()."""
    return candidates(phase, bw, slot, rules, deload=deload, hill_day=hill_day, level=level, library=library)[0]
