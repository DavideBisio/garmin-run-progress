"""Workouts and plans as markdown, in the format of the hand-written training plan.

Each workout is a '### Title - X.X km (~time)' heading over a Lap | Pace range | FC range |
Duration | Comment table; repeats are a '**Repeat Nx**' row followed by '↳' rows. Numbers are
rounded here and only here. Write the output as UTF-8 (the arrows are not ASCII).
"""
from datetime import date

from .model import Repeat
from .plan_io import workout_from_dict

ZONE_NAMES = {"E": "Easy", "M": "Marathon", "T": "Threshold", "I": "Interval", "R": "Repetition"}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt_pace(s):
    s = int(s + 0.5)
    return f"{s // 60}:{s % 60:02d}"


def fmt_time(s):
    s = int(s + 0.5)
    h, m, x = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m}:{x:02d}"


def fmt_dur(s):
    """'45 s' under a minute, 'm:ss' under 10 min, 'N min' under an hour, '1 h 05' from an hour
    (hours and zero-padded minutes; on the hour '1 h 00')."""
    s = int(s + 0.5)
    if s < 60:
        return f"{s} s"
    if s < 600:
        return f"{s // 60}:{s % 60:02d}"
    m = int(s / 60 + 0.5)
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d}"


def fmt_est(s):
    return "~" + fmt_dur(s)


def fmt_dist(m):
    """'220 m' under a kilometre, else '1.5 km'."""
    m = int(m + 0.5)
    return f"{m} m" if m < 1000 else f"{m / 1000:.1f} km"


def esc(text):
    return (text or "").replace("|", "\\|")


def _pace_cell(s):
    if s.pace:
        return f"{ZONE_NAMES[s.zone]} {fmt_pace(s.pace.fast_s)} - {fmt_pace(s.pace.slow_s)} /km"
    if s.zone == "jog":
        return "Jog"
    return s.effort or "Open"


def _hr_cell(s):
    if not s.hr:
        return ""
    return f"Zone {s.hr_zone[1:]} {s.hr.lo} - {s.hr.hi} bpm"


def _duration_cell(s):
    if s.end == "dist":
        return f"{fmt_dist(s.meters)} ({fmt_est(s.seconds)})"
    if s.end == "time":
        return f"{fmt_dur(s.value)} (~{fmt_dist(s.meters)})"
    return f"Lap button ({fmt_est(s.seconds)}, ~{fmt_dist(s.meters)})"


def _row(cells):
    return "| " + " | ".join(esc(c) for c in cells) + " |"


def _step_row(s, nested=False, note=None):
    lap = f"{'↳ ' if nested else ''}**{s.label}**"
    return _row([lap, _pace_cell(s), _hr_cell(s), _duration_cell(s), s.note if note is None else note])


def render_workout(w, prefix=""):
    """One workout as a markdown section (heading and table), ending with a newline."""
    out = [f"### {esc(prefix + w.title)} - {w.km:.1f} km ({fmt_est(w.seconds)})", "",
           _row(["Lap", "Pace range", "FC range", "Duration", "Comment"]),
           "| :---- | :---- | :---- | :---- | :---- |"]
    for p in w.parts:
        if not isinstance(p, Repeat):
            out.append(_step_row(p))
        elif p.n == 1:
            # a repeat of 1 is just its steps (a skipped last rest is left out); the repeat's note
            # goes in front of the first step's comment
            steps = p.steps[:-1] if p.skip_last_rest and p.steps[-1].role == "recovery" else p.steps
            first = "; ".join(x for x in (p.note, steps[0].note if steps else "") if x)
            out += [_step_row(s, note=first if i == 0 else None) for i, s in enumerate(steps)]
        else:
            note = p.note
            if p.skip_last_rest and p.steps[-1].role == "recovery":
                note = "; ".join(x for x in (note, "no recovery after the last rep") if x)
            out.append(_row([f"**Repeat {p.n}x**", "", "", f"{fmt_dist(p.meters)} ({fmt_est(p.seconds)})", note]))
            out += [_step_row(s, nested=True) for s in p.steps]
    return "\n".join(out) + "\n"


def render_plan(plan):
    """plan.md from a plan dict (plan_io's format): a section per week, a workout per day."""
    out = ["# Training plan", "",
           f"Generated {plan['generated']} from profile `{plan['profile_hash'][:12]}`. "
           "Durations are estimates at the middle of each pace range; recovery jogs at the slow end of "
           "Easy plus 30 s/km.", ""]
    for wk in plan["weeks"]:
        out += [f"## Week of {wk['start']} - {wk['target_km']:.1f} km", ""]
        if not wk["days"]:
            out += ["No sessions.", ""]
        for d in wk["days"]:
            w = workout_from_dict(d["workout"])
            day = DAY_NAMES[date.fromisoformat(d["date"]).weekday()]
            out.append(render_workout(w, prefix=f"{day} {d['date']} · "))
    return "\n".join(out).rstrip("\n") + "\n"
