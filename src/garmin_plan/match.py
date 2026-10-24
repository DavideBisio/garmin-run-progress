"""Match runs to planned sessions (roadmap 09): what was done of a plan, day by day.

match(plan, runs, today, rules) -> {date: {"status", "activity_id"}} for each planned session up to
today. A session matches the runs on its own day first, then an unmatched run the day before or
after (moved). Statuses:

- done: run on its day, at least [adapt] partial of the planned distance or time;
- moved: done, but on the day before or after;
- swapped: a terrain swap, a trail run for a road session or a road run for a trail one;
- partial: under [adapt] partial of both the planned distance and the planned time, or a Q session
  with 10+ min of hard work planned (not a time trial) run with under 10 min at Z4 and above (an
  easy run instead);
- missed: no run within a day. A session dated today with no run yet is left out: it's still to come.

The run picked for a session: the longest for L, one with 10+ min at Z4+ for a hard Q, else the one
closest to the planned distance. Two runs on one day both count for that day's session (one session
run in two parts) unless the second one is the moved run of the day before or after; activity_id is
the main run's. Q detection reads the HR as history.q_sessions does; a run without HR counts as
either kind. This module imports no planner module that imports profile.py (profile imports it).
"""
from datetime import date, timedelta

from .history import Q_MIN_S, dated, z4_seconds
from .metrics import run_km
from .physiology import hr_zones

DONE = ("done", "moved", "swapped")          # a session counted as done (Q compliance)


def _iso(d):
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


def hard_seconds(steps):
    """Planned seconds of the hard steps of a plan.json workout's steps (repeats n times)."""
    out = 0.0
    for s in steps or []:
        if s.get("type") == "repeat":
            out += (s.get("n") or 0) * hard_seconds(s.get("steps"))
        elif s.get("hard"):
            out += s.get("seconds") or 0
    return out


def sessions(plan, until):
    """[(date iso, slot, workout dict)] of plan's sessions dated until (iso) or earlier, in date order."""
    out = []
    for wk in (plan or {}).get("weeks") or []:
        for d in wk.get("days") or []:
            if isinstance(d, dict) and isinstance(d.get("workout"), dict) and isinstance(d.get("date"), str) \
                    and d["date"] <= until:
                out.append((d["date"], d.get("slot"), d["workout"]))
    return sorted(out, key=lambda s: s[0])


def _run(r, z4):
    secs = r.get("moving") or r.get("dur") or 0
    has_hr = z4 is not None and bool(r.get("avgHr") or any(h > 0 for h in r.get("hr") or []))
    return {"id": r.get("id"), "date": r["date"][:10], "km": run_km(r), "secs": secs,
            "trail": "trail" in (r.get("type") or ""),
            "q": z4_seconds(r, z4) >= Q_MIN_S if has_hr else None}


def _wants_q(slot, w):
    """A Q session the HR can confirm: 10+ min of hard steps (not strides), and not a time trial,
    whose few minutes all-out the HR lags behind (history.time_trials reads it from its pace)."""
    return slot == "Q" and w.get("kind") != "tt" and hard_seconds(w.get("steps")) >= Q_MIN_S


def _fits(slot, w, run):
    return not (_wants_q(slot, w) and run["q"] is False)


def _pick(slot, w, cands):
    if not cands:
        return None
    if slot == "L":
        return max(cands, key=lambda r: r["km"])
    if _wants_q(slot, w):
        return min(cands, key=lambda r: ({True: 0, None: 1, False: 2}[r["q"]], -r["km"]))
    return min(cands, key=lambda r: abs(r["km"] - (w.get("km") or 0)))


def _status(slot, w, day, runs, partial):
    main = runs[0]
    km, secs = sum(r["km"] for r in runs), sum(r["secs"] for r in runs)
    # a time trial is judged by its best 2 km (history.time_trials), not by the planned warm-up
    short = w.get("kind") != "tt" and km < partial * (w.get("km") or 0) and secs < partial * (w.get("seconds") or 0)
    if short or not _fits(slot, w, main):
        return "partial"
    if main["trail"] != (w.get("kind") == "trail"):
        return "swapped"
    return "moved" if main["date"] != day else "done"


def match(plan, runs, today, rules, hr_max=None, hr_rest=None):
    """{date: {"status", "activity_id"}} of plan's sessions up to today (module docstring). hr_max
    and hr_rest set the Z4 bound that tells a Q run; without them any run fits a Q session."""
    today = _iso(today)
    partial = rules["adapt"]["partial"]
    z4 = hr_zones(hr_max, hr_rest)[2] if hr_max and hr_rest else None
    plan_days = sessions(plan, today)
    if not plan_days:
        return {}
    first = (date.fromisoformat(plan_days[0][0]) - timedelta(days=1)).isoformat()
    pool = [_run(r, z4) for _, r in dated(runs) if first <= r["date"][:10] <= today]
    used, got = set(), {}

    def free(day):
        return [r for i, r in enumerate(pool) if i not in used and r["date"] == day]

    def take(r):
        used.add(next(i for i, x in enumerate(pool) if x is r and i not in used))

    for day, slot, w in plan_days:                       # 1. the session's own day
        r = _pick(slot, w, free(day))
        if r is not None:
            take(r)
            got[day] = [r]
    for day, slot, w in plan_days:                       # 2. a free run the day before or after
        if day in got:
            continue
        d = date.fromisoformat(day)
        near = [r for k in (-1, 1) for r in free((d + timedelta(days=k)).isoformat()) if _fits(slot, w, r)]
        r = _pick(slot, w, near)
        if r is not None:
            take(r)
            got[day] = [r]
    for day in got:                                      # 3. a second run on the same day: one session
        for r in free(day):
            take(r)
            got[day].append(r)
    out = {}
    for day, slot, w in plan_days:
        if day in got:
            out[day] = {"status": _status(slot, w, day, got[day], partial), "activity_id": got[day][0]["id"]}
        elif day < today:
            out[day] = {"status": "missed", "activity_id": None}
    return out


def last_block(plan, monday):
    """The weeks of plan before `monday` back to the start of the block they end in (the week after
    a deload, else the plan's first week)."""
    weeks = [wk for wk in (plan or {}).get("weeks") or [] if isinstance(wk, dict)
             and isinstance(wk.get("start"), str) and wk["start"] < _iso(monday)]
    i = max([0] + [k for k in range(1, len(weeks)) if weeks[k - 1].get("deload")])
    return weeks[i:]


def q_compliance(plan, runs, today, monday, rules, hr_max=None, hr_rest=None):
    """Q sessions done (done, moved or swapped) over Q sessions planned up to today in the block
    that ends before `monday` (last_block); None when that block planned none."""
    block = {"weeks": last_block(plan, monday)}
    got = match(block, runs, today, rules, hr_max, hr_rest)
    qs = [day for day, slot, _ in sessions(block, _iso(today)) if slot == "Q" and day in got]
    if not qs:
        return None
    return sum(got[d]["status"] in DONE for d in qs) / len(qs)
