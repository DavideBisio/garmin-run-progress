"""What runs.json says about recent training: weekly volume, recent VDOT, resting and max HR, daily load."""
import math
from datetime import date

from .config import MIN_HISTORY_DAYS
from .metrics import best_efforts, day_index, hr_peak, run_km, trimp, week_of
from .physiology import vdot

VDOT_DISTS = {"5k": 5000, "10k": 10000, "hm": 21097.5}   # 1 km overstates VDOT, as on the page


def half_up(x):
    """Math.round: halves go up (Python's round() goes to even)."""
    return math.floor(x + 0.5)


def median(a):
    """stats.js median: the mean of the two middle values for an even count."""
    if not a:
        return None
    s, m = sorted(a), len(a) >> 1
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def dated(runs):
    """(day index, run) for the runs the page keeps (a parseable date), oldest first."""
    out = [(day_index(r.get("date")), r) for r in runs]
    return sorted(((d, r) for d, r in out if d is not None), key=lambda x: x[0])


def weekly_km(runs):
    """{Monday-based week index: {"km", "runs", "longest"}}; runs without streams count by dist."""
    weeks = {}
    for day, r in dated(runs):
        w = weeks.setdefault(week_of(day), {"km": 0.0, "runs": 0, "longest": 0.0})
        km = run_km(r)
        w["km"] += km
        w["runs"] += 1
        w["longest"] = max(w["longest"], km)
    return weeks


def recent_stats(runs, today):
    """Volume and VDOT around `today` (a date). Values are None when there's too little history.

    km_4w / km_12w: average km over the last 4 / 12 full weeks before this week, empty weeks
    included; runs_per_week over the last 4 full weeks; longest_8w: longest run in the last
    56 days; vdot: the best 5 km / 10 km / half effort of the last 12 weeks (training efforts).
    """
    now = day_index(today.isoformat() if isinstance(today, date) else today)
    rs = [(d, r) for d, r in dated(runs) if d <= now]
    out = {"history_days": now - rs[0][0] if rs else 0, "km_4w": None, "km_12w": None,
           "runs_per_week": None, "longest_8w": None, "vdot": None, "vdot_from": None}
    if out["history_days"] < MIN_HISTORY_DAYS:
        return out
    weeks, cur = weekly_km([r for _, r in rs]), week_of(now)

    def span(n):
        return [weeks.get(w, {"km": 0.0, "runs": 0}) for w in range(cur - n, cur)]

    out["km_4w"] = sum(w["km"] for w in span(4)) / 4
    out["km_12w"] = sum(w["km"] for w in span(12)) / 12
    out["runs_per_week"] = sum(w["runs"] for w in span(4)) / 4
    out["longest_8w"] = max((run_km(r) for d, r in rs if d > now - 56), default=0.0)
    for d, r in rs:
        if d <= now - 84:
            continue
        for k, s in best_efforts(r).items():
            if k in VDOT_DISTS and s:
                v = vdot(VDOT_DISTS[k], s)
                if out["vdot"] is None or v > out["vdot"]:
                    out["vdot"], out["vdot_from"] = v, (k, r["date"][:10])
    return out


def resting_hr(rhr):
    """Median resting HR of the 365 days up to the last entry, rounded half up (state.js)."""
    pts = sorted(((day_index(ds), v) for ds, v in rhr or [] if v and v > 0), key=lambda p: p[0] or 0)
    pts = [p for p in pts if p[0] is not None]
    if not pts:
        return None
    last = pts[-1][0]
    med = median([v for d, v in pts if d > last - 365])
    return half_up(med) if med else None


def hr_max(runs):
    """state.js suggestion: the second-highest run peak (_hrPeak, else maxHr) within 120-230 bpm."""
    peaks = sorted((p for p in (hr_peak(r) or r.get("maxHr") or 0 for _, r in dated(runs))
                    if 120 < p < 230), reverse=True)
    return half_up(peaks[min(1, len(peaks) - 1)]) if peaks else None


def daily_load(runs, hr_max, hr_rest, until=None):
    """{day index: TRIMP} of every dated run, as training.js's daily map: runs on one day add up,
    a run without HR counts 0 (its day still starts the history), resting HR is clamped to max - 20.
    until: a date; runs after it are left out (the planner's history ends on `today`)."""
    rest, out = min(hr_rest, hr_max - 20), {}
    last = None if until is None else day_index(until.isoformat() if isinstance(until, date) else until)
    for day, r in dated(runs):
        if last is not None and day > last:
            break
        out[day] = out.get(day, 0) + trimp(r, hr_max, rest)
    return out


def acwr(daily, day):
    """7:28-day load ratio on `day` as training.js's acwr: the last 7 days' load over a quarter of
    the last 28 days'. None before 28 days of history (from the first day in `daily`) or without
    any load in the 28 days."""
    if not daily or day - 27 < min(daily):
        return None
    chronic = sum(daily.get(d, 0) for d in range(day - 27, day + 1)) / 4
    return sum(daily.get(d, 0) for d in range(day - 6, day + 1)) / chronic if chronic > 0 else None
