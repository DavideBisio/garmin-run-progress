"""plan.json: the [week] schedule, workout <-> dict, and reading and writing it (docs/plan-json-format.md).

The file holds resolved steps (pace and HR ranges, estimates), so the Garmin export (05) and the
page (10) need neither the templates nor the profile.
"""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import WEEKDAYS
from .model import HrRange, PaceRange, Repeat, Step, Workout
from .physiology import pace_zones
from .profile import ProfileError
from .templates import PACE_ZONES, hr_range, instantiate, jog_pace, pace_range

VERSION = 1


def _r(x, n=2):
    return None if x is None else round(x, n)


def step_to_dict(s):
    if isinstance(s, Repeat):
        return {"type": "repeat", "n": s.n, "skip_last_rest": s.skip_last_rest, "note": s.note,
                "meters": _r(s.meters, 1), "seconds": _r(s.seconds, 1),
                "steps": [step_to_dict(x) for x in s.steps]}
    return {"type": "step", "role": s.role, "label": s.label, "end": s.end, "value": _r(s.value),
            "zone": s.zone,
            "pace_s_per_km": [_r(s.pace.fast_s), _r(s.pace.slow_s)] if s.pace else None,
            "hr_zone": s.hr_zone, "hr": [s.hr.lo, s.hr.hi] if s.hr else None,
            "est_pace_s_per_km": _r(s.est_pace), "est_dist": _r(s.est_dist), "est_time": _r(s.est_time),
            "effort": s.effort, "note": s.note, "hard": s.hard,
            "meters": _r(s.meters, 1), "seconds": _r(s.seconds, 1)}


def step_from_dict(d):
    if d["type"] == "repeat":
        return Repeat(d["n"], [step_from_dict(x) for x in d["steps"]], d["skip_last_rest"], d.get("note", ""))
    return Step(d["role"], d["label"], d["end"], d["value"], zone=d["zone"],
                pace=PaceRange(*d["pace_s_per_km"]) if d["pace_s_per_km"] else None,
                hr_zone=d["hr_zone"], hr=HrRange(*d["hr"]) if d["hr"] else None,
                est_pace=d["est_pace_s_per_km"], est_dist=d["est_dist"], est_time=d["est_time"],
                effort=d["effort"], note=d["note"], hard=d["hard"])


def workout_to_dict(w):
    return {"id": w.id, "variant": w.variant, "title": w.title, "kind": w.kind,
            "km": _r(w.km), "seconds": _r(w.seconds, 0), "hard_km": _r(w.hard_km),
            "climb_m_per_km": w.climb_m_per_km, "steps": [step_to_dict(p) for p in w.parts]}


def workout_from_dict(d):
    return Workout(d["id"], d["variant"], d["title"], d["kind"], [step_from_dict(x) for x in d["steps"]],
                   d.get("climb_m_per_km"))


def profile_hash(prof, rules):
    """sha256 of what the resolved steps depend on: VDOT, HR max and rest, and the resolved zones
    (pace ranges in s/km to 0.01, the jog pace, HR zone bpm). A changed hash means stale steps."""
    paces = pace_zones(prof.vdot, rules)
    key = {"vdot": prof.vdot, "hr_max": prof.hr_max, "hr_rest": prof.hr_rest,
           "paces": {z: [round(r.fast_s, 2), round(r.slow_s, 2)]
                     for z in PACE_ZONES for r in [pace_range(z, paces, rules)]},
           "jog": round(jog_pace(paces, rules), 2),
           "hr": [[r.lo, r.hi] for r in (hr_range(f"Z{i}", prof.hr_max, prof.hr_rest) for i in range(1, 6))]}
    blob = json.dumps(key, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def shown_km(d):
    """A workout dict's km as its plan.md heading shows it (render_md: one decimal)."""
    return float(f"{workout_from_dict(d).km:.1f}")


def first_monday_after(today):
    return today + timedelta(days=7 - today.weekday())


def manual_days(prof, library, rules):
    """{weekday: Workout} of profile.toml's [week] schedule, Monday first; {} without one. An unknown
    template or variant raises ProfileError quoting the [week] line."""
    out = {}
    for day, e in prof.week.items():
        t = library.get(e["id"])
        if t is None:
            raise ProfileError(f"[week]: unknown template {e['id']!r} ({', '.join(library)}), in line: {e['line']}")
        n = len(t["ladder"])
        if not 1 <= e["variant"] <= n:
            raise ProfileError(f"[week]: {e['id']} has variants 1-{n}, got {e['variant']}, in line: {e['line']}")
        out[day] = instantiate(t, e["variant"], prof, rules)
    return out


def build_plan(prof, library, rules, today, weeks, generated=None):
    """The plan dict for `weeks` weeks of profile.toml's [week] schedule alone, from the Monday after
    today (the generator, planner.build_plan, fills in the other days).

    Every week repeats [week]; target_km is the sum of that week's sessions as plan.md shows them
    (each workout's km rounded to 0.1 first, so the week heading adds up its day headings) and slot
    stays null. Without a [week] table the weeks have no sessions.
    """
    week = {d: workout_to_dict(w) for d, w in manual_days(prof, library, rules).items()}
    target = round(sum(shown_km(w) for w in week.values()), 1)
    start = first_monday_after(today)
    out = []
    for i in range(weeks):
        mon = start + timedelta(days=7 * i)
        days = [{"date": (mon + timedelta(days=WEEKDAYS.index(d))).isoformat(), "slot": None,
                 "workout": json.loads(json.dumps(w))} for d, w in week.items()]
        out.append({"start": mon.isoformat(), "target_km": target, "days": days})
    return {"version": VERSION,
            "generated": generated or datetime.now().isoformat(timespec="seconds"),
            "profile_hash": profile_hash(prof, rules), "weeks": out}


def write_plan(plan, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_plan(path):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("version") != VERSION:
        raise ValueError(f"{path}: not a version {VERSION} plan.json")
    return plan

