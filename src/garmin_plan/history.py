"""What runs.json says about recent training: weekly volume, recent VDOT, resting and max HR, daily load."""
import math
from datetime import date

from .config import MIN_HISTORY_DAYS
from .metrics import best_effort, best_efforts, day_index, has_stream, hr_ok, hr_peak, run_km, trimp, week_of
from .physiology import hr_zones, vdot

VDOT_DISTS = {"5k": 5000, "10k": 10000, "hm": 21097.5}   # 1 km overstates VDOT, as on the page
Q_MIN_S = 600          # a Q session: at least 10 minutes in Z4 or above (roadmap 08)


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
    consistency: share of the last 12 full weeks with 2 or more runs; days_off: days from the last
    run to today; km_before / runs_before: weekly km and runs over the 4 weeks up to the last run
    (the volume before a break); longest_before / consistency_before: longest_8w and consistency
    up to the last run (what a break leaves out); weeks: {km, runs} of the last 4 full weeks, oldest
    first.
    """
    now = day_index(today.isoformat() if isinstance(today, date) else today)
    rs = [(d, r) for d, r in dated(runs) if d <= now]
    out = {"history_days": now - rs[0][0] if rs else 0, "km_4w": None, "km_12w": None,
           "runs_per_week": None, "longest_8w": None, "vdot": None, "vdot_from": None,
           "consistency": None, "days_off": None, "km_before": None, "runs_before": None,
           "longest_before": None, "consistency_before": None, "weeks": []}
    if out["history_days"] < MIN_HISTORY_DAYS:
        return out
    weeks, cur = weekly_km([r for _, r in rs]), week_of(now)

    def span(n):
        return [weeks.get(w, {"km": 0.0, "runs": 0}) for w in range(cur - n, cur)]

    out["km_4w"] = sum(w["km"] for w in span(4)) / 4
    out["km_12w"] = sum(w["km"] for w in span(12)) / 12
    out["runs_per_week"] = sum(w["runs"] for w in span(4)) / 4
    out["consistency"] = sum(w["runs"] >= 2 for w in span(12)) / 12
    out["weeks"] = [{"km": w["km"], "runs": w["runs"]} for w in span(4)]
    last = rs[-1][0]
    out["days_off"] = now - last
    before = [r for d, r in rs if last - 28 < d <= last]
    out["km_before"] = sum(run_km(r) for r in before) / 4
    out["runs_before"] = len(before) / 4
    out["longest_8w"] = max((run_km(r) for d, r in rs if d > now - 56), default=0.0)
    out["longest_before"] = max(run_km(r) for d, r in rs if d > last - 56)
    lw = week_of(last)
    out["consistency_before"] = sum(weeks.get(w, {"runs": 0})["runs"] >= 2 for w in range(lw - 11, lw + 1)) / 12
    for d, r in rs:
        if d <= now - 84:
            continue
        for k, s in best_efforts(r).items():
            if k in VDOT_DISTS and s:
                v = vdot(VDOT_DISTS[k], s)
                if out["vdot"] is None or v > out["vdot"]:
                    out["vdot"], out["vdot_from"] = v, (k, r["date"][:10])
    return out


def q_sessions(runs, today, hr_max, hr_rest, weeks=8):
    """Runs in the `weeks` weeks up to today with Q_MIN_S or more at Z4 and above (the Z4 bound of
    physiology.hr_zones): from the HR stream when it has one (gaps over 30 s skipped, as trimp), else
    the whole moving time when the average HR is at Z4 or above."""
    now = day_index(today.isoformat() if isinstance(today, date) else today)
    z4 = hr_zones(hr_max, hr_rest)[2]
    n = 0
    for d, r in dated(runs):
        if not now - 7 * weeks < d <= now:
            continue
        if hr_ok(r):
            t, h = r["t"], r["hr"]
            secs = sum(t[i] - t[i - 1] for i in range(1, len(t)) if 0 < t[i] - t[i - 1] <= 30 and h[i] >= z4)
        else:
            secs = (r.get("moving") or r.get("dur") or 0) if (r.get("avgHr") or 0) >= z4 else 0
        n += secs >= Q_MIN_S
    return n


def time_trials(runs, days, today, recorded=()):
    """[{date, dist_m, time_s, vdot}] of the time trials run up to today, oldest first: the recorded
    ones (plan.json's progress) and each run with a GPS stream on one of `days` ("YYYY-MM-DD", the
    days a plan planned a time trial), from its best 2 km (metrics.best_effort; the page's
    best-effort distances don't include 2 km). A recorded day whose run is still in runs.json is
    read again from it."""
    now = today.isoformat() if isinstance(today, date) else str(today)
    out = {t["date"]: t for t in recorded if t["date"] <= now}
    for _, r in dated(runs):
        day = r["date"][:10]
        if day in days and day <= now and has_stream(r):
            s = best_effort(r["t"], r["d"], 2000)
            if s:
                out[day] = {"date": day, "dist_m": 2000, "time_s": round(s, 1), "vdot": vdot(2000, s)}
    return [out[d] for d in sorted(out)]


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
