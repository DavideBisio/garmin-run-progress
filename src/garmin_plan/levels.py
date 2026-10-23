"""Runner levels (data/levels.toml): the planning numbers that depend on the runner's level (roadmap 08).

A runner has two levels, one per axis: a volume level (how much they run) and a quality level (what
sessions they're ready for). detect(stats, levels) reads both from the runner's history, promote()
moves them on from the last plan's at a block's start, layoff(days) scales VDOT and volume after a
break, and params(levels, volume_level, quality_level, rules) gives the rules the planner uses: a copy
of rules.toml with each levels.toml key set to its value at the right level.
"""
import copy
import tomllib
from datetime import date

from .config import DATA_DIR, MIN_HISTORY_DAYS
from .physiology import load_rules
from .templates import LEVELS

DEFAULT_LEVEL = "intermediate"     # a Profile built without levels (tests, old callers)
SECTIONS = ("volume", "split", "skeleton", "checks", "rotation")
# keys set by the quality level; every other levels.toml key follows the volume level
QUALITY = {"skeleton": {"q_from_days"},
           "rotation": {"base", "rt", "it", "tm", "taper", "time_trial", "time_trial_week"}}
UNITS = ("km", "min")


def load_levels(path=None):
    with open(path or DATA_DIR / "levels.toml", "rb") as f:
        return tomllib.load(f)


def _check(level):
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}; use {', '.join(LEVELS)}")


def _per_level(v):
    """A {level: value} table (every key a level name), as opposed to a plain value."""
    return isinstance(v, dict) and v and set(v) <= set(LEVELS)


def params(levels, volume_level, quality_level, rules=None):
    """rules.toml with levels.toml laid over [volume], [split], [skeleton], [checks] and [rotation].

    A levels.toml key holds {level: value}: the volume level's value, or the quality level's for the
    QUALITY keys; a level missing from the table keeps rules.toml's value. A plain value applies at
    every level. [rotation] level is the quality level (select.py's template filter). The other
    sections are rules.toml's, and rules itself is never changed.
    """
    _check(volume_level)
    _check(quality_level)
    out = copy.deepcopy(rules or load_rules())
    for sec in SECTIONS:
        dst = out.setdefault(sec, {})
        for key, v in (levels.get(sec) or {}).items():
            level = quality_level if key in QUALITY.get(sec, ()) else volume_level
            if not _per_level(v):
                dst[key] = copy.deepcopy(v)
            elif level in v:
                dst[key] = copy.deepcopy(v[level])
    out["rotation"]["level"] = quality_level
    return out


def unit(prof, levels=None):
    """The plan's volume unit: profile.toml's, else the volume level's (levels.toml [volume] unit)."""
    return prof.unit or (levels or load_levels())["volume"]["unit"][prof.volume_level]


def _num(x):
    """3.0 -> '3', 3.25 -> '3.2': counts and averages in a reason."""
    return f"{round(x, 1):g}"


def _volume(stats, d):
    """(volume level, reason) from the history numbers: the highest level whose minimums all hold."""
    if (stats.get("history_days") or 0) < MIN_HISTORY_DAYS or stats.get("km_4w") is None:
        return LEVELS[0], "under 4 weeks of runs"
    lay, km = stats.get("layoff"), stats["km_4w"]
    if lay:
        text = (f"{km:.0f} km/wk: {lay['km_before']:.0f} km/wk before {lay['days_off']} days off, "
                f"x{lay['volume_factor']:g}")
    else:
        text = f"{km:.0f} km/wk over 4 wk"
    have = {"km": (km, f"{km:.0f} km/wk"),
            "km_12w": (stats["km_12w"], f"{stats['km_12w']:.0f} km/wk over 12 wk"),
            "runs_per_week": (stats["runs_per_week"], f"{_num(stats['runs_per_week'])} runs/wk"),
            "consistency_weeks": (round(stats["consistency"] * 12), f"{round(stats['consistency'] * 12)} of 12 "
                                                                    "weeks with 2+ runs"),
            "longest": (stats["longest_8w"], f"longest run {stats['longest_8w']:.1f} km"),
            "history_weeks": (stats["history_days"] / 7, f"{stats['history_days'] // 7} weeks of history")}
    level = LEVELS[0]
    for nxt in LEVELS[1:]:
        fails = [f"{label} (needs {_num(d[k][nxt])})" for k, (v, label) in have.items() if v < d[k][nxt]]
        if fails:
            if have["km"][0] >= d["km"][nxt]:          # the volume is there: say what holds it back
                text += f"; not {nxt}: {', '.join(fails)}"
            break
        level = nxt
    return level, text


def _quality(stats, d):
    """(quality level, reason) from VDOT and the Q sessions of the last 8 weeks."""
    v, q = stats.get("vdot"), stats.get("q_8w") or 0
    if v is None:
        return LEVELS[0], "no VDOT yet: no 5 km, 10 km or half effort and no time trial"
    level = LEVELS[0]
    for nxt in LEVELS[1:]:
        if v < d["vdot"][nxt] or q < d["q_8w"][nxt]:
            break
        level = nxt
    return level, f"VDOT {v:.0f}, {q} Q sessions in 8 wk"


def detect(stats, levels):
    """(volume_level, quality_level, {"volume": reason, "quality": reason}) from levels.toml [detect].

    stats: km_4w, km_12w, runs_per_week, longest_8w (None with under 4 weeks of runs), consistency
    (share of the last 12 weeks with 2+ runs), history_days, vdot (None when unknown), q_8w, and
    layoff ({days_off, km_before, volume_factor}) when km_4w is the restart volume after a break.
    """
    d = levels["detect"]
    vol, vwhy = _volume(stats, d)
    qual, qwhy = _quality(stats, d)
    return vol, qual, {"volume": vwhy, "quality": qwhy}


def describe(volume_level, quality_level, reasons):
    """'volume: novice (16 km/wk over 4 wk); quality: intermediate (VDOT 40, 3 Q sessions in 8 wk)'."""
    return "; ".join(f"{axis}: {level} ({reasons[axis]})" if reasons.get(axis) else f"{axis}: {level}"
                     for axis, level in (("volume", volume_level), ("quality", quality_level)))


def block_start(plan, monday):
    """Whether the week from `monday` starts a block of `plan` (a plan.json dict): its first week,
    the week after a deload, or a week the plan doesn't reach."""
    starts = [date.fromisoformat(wk["start"]) for wk in plan.get("weeks", [])]
    if monday not in starts:
        return True
    i = starts.index(monday)
    return i == 0 or bool(plan["weeks"][i - 1].get("deload"))


def promote(current, stats, levels, *, block_start, compliance=None):
    """({"volume": level, "quality": level}, notes) from the last plan's levels `current`.

    After a break (stats["layoff"]) each axis drops right away to what detect() finds, if lower:
    the plan restarts. Otherwise levels change only at a block's start, one level at a time and
    never down: volume when each of the last promote_weeks weeks (stats["weeks"], {km, runs},
    oldest first) holds the next level's km plus the margin and its runs a week; quality when
    detect() finds the next level and VDOT is vdot_margin over its minimum. Mid-block a promotion
    waits, with a note. compliance, the share of planned Q sessions done (roadmap 09), holds both
    back under [detect] compliance; None skips that check with a note. Notes about one axis start
    with "volume: " or "quality: ".
    """
    d = levels["detect"]
    vol, qual, why = detect(stats, levels)
    found, out, notes = {"volume": vol, "quality": qual}, dict(current), []
    lay = stats.get("layoff")
    if lay:
        for axis, level in found.items():
            if LEVELS.index(level) < LEVELS.index(current[axis]):
                out[axis] = level
                notes.append(f"{axis}: {current[axis]} -> {level} after {lay['days_off']} days off ({why[axis]})")
        return out, notes
    if compliance is None:
        notes.append("Q compliance not checked: the adaptation loop (roadmap 09) counts the sessions done")
    elif compliance < d["compliance"]:
        notes.append(f"{compliance * 100:.0f} % of the planned Q sessions done, under {d['compliance'] * 100:.0f} %: "
                     "no promotion this block")
        return out, notes
    i = LEVELS.index(current["volume"])
    if i + 1 < len(LEVELS):
        nxt, n = LEVELS[i + 1], d["promote_weeks"]
        km, runs = d["km"][nxt] * (1 + d["margin"]), d["runs_per_week"][nxt]
        last = (stats.get("weeks") or [])[-n:]
        if len(last) == n and all(w["km"] >= km and w["runs"] >= runs for w in last):
            out["volume"] = nxt
            notes.append(f"volume: {current['volume']} -> {nxt} ({n} weeks at {km:.1f}+ km and {_num(runs)}+ runs)")
    i = LEVELS.index(current["quality"])
    if i + 1 < len(LEVELS):
        nxt = LEVELS[i + 1]
        if LEVELS.index(qual) > i and (stats.get("vdot") or 0) >= d["vdot"][nxt] + d["vdot_margin"]:
            out["quality"] = nxt
            notes.append(f"quality: {current['quality']} -> {nxt} ({why['quality']})")
    if not block_start:                         # levels change at a block's start only
        held = []
        for n in notes:
            axis, _, rest = n.partition(": ")
            held.append(f"{axis}: {current[axis]} until the next block, then {rest.split(' -> ', 1)[1]}"
                        if axis in current else n)
        return dict(current), held
    return out, notes


def layoff(days_off, levels=None):
    """(vdot_factor, volume_factor) after days_off days without running ([layoff] table): 1 and 1 up
    to the first row's days, then the VDOT factor runs linearly from row to row and the volume
    factor is the row's; past the last row, the last row's."""
    rows = (levels or load_levels())["layoff"]["table"]
    if days_off <= rows[0][0]:
        return float(rows[0][1]), float(rows[0][2])
    for (d0, v0, _), (d1, v1, vol) in zip(rows, rows[1:]):
        if days_off <= d1:
            return round(v0 + (v1 - v0) * (days_off - d0) / (d1 - d0), 4), float(vol)
    return float(rows[-1][1]), float(rows[-1][2])
