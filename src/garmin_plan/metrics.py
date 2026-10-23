"""Ports of the page maths the planner needs (src/page/js/metrics.js), line for line.

tests/fixtures/metric_vectors.json is generated from the JS; tests/test_plan.py checks these
functions against it and tests/metrics.test.mjs checks the page still matches it.
"""
import math
import re
from datetime import date

from .physiology import hr_zones, vdot  # noqa: F401  (vdot and hrrZones live in physiology)

DISTS = [("1k", 1000), ("5k", 5000), ("10k", 10000), ("hm", 21097.5)]
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_EPOCH = date(1970, 1, 1).toordinal()


def minetti(i):
    i = max(-0.3, min(0.3, i))
    return 155.4 * i ** 5 - 30.4 * i ** 4 - 43.3 * i ** 3 + 46.3 * i ** 2 + 19.5 * i + 3.6


def gap_factor(g):
    return minetti(g) / 3.6


def day_index(date_str):
    """Days since 1970-01-01 of the date part of 'YYYY-MM-DD[ HH:MM:SS]' (decYear(..).day)."""
    m = _DATE.match(date_str or "")
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3])).toordinal() - _EPOCH
    except ValueError:
        return None


def week_of(day):
    """Monday-based week index (day 0 = Thu 1970-01-01)."""
    return (day + 3) // 7


def week_start(w):
    return w * 7 - 3


def best_effort(t, d, D):
    """Fastest time (s) over D metres in a stream, or None."""
    if t is None or (d and d[-1] < D):
        return None
    best, i = math.inf, 0
    for j in range(1, len(d)):
        if d[j] - d[0] < D:
            continue
        while i + 1 < j and d[j] - d[i + 1] >= D:
            i += 1
        target, span = d[j] - D, d[i + 1] - d[i]
        ts = t[i] + (t[i + 1] - t[i]) * (target - d[i]) / span if span > 0 else t[i]
        dur = t[j] - ts
        if 0 < dur < best:
            best = dur
    if not math.isfinite(best) or D / best > 6.4:
        return None
    return best


def has_stream(run):
    t = run.get("t")
    return bool(t) and len(t) > 5


def hr_ok(run):
    """prepare's _hrOk: a stream with a heart-rate reading in more than 60% of the samples."""
    if not has_stream(run):
        return False
    return sum(1 for h in run.get("hr") or [] if h > 0) > len(run["t"]) * 0.6


def hr_peak(run):
    """prepare's _hrPeak: the 99th percentile of the HR stream (ignores optical spikes)."""
    if not hr_ok(run):
        return None
    hs = sorted(h for h in run["hr"] if h > 0)
    return hs[math.floor(len(hs) * 0.99)]


def run_km(run):
    """prepare's _km: summary distance, else the stream's last distance."""
    if has_stream(run):
        return (run.get("dist") or run["d"][-1]) / 1000
    return (run.get("dist") or 0) / 1000


def best_efforts(run):
    """prepare's _best: {"1k": s or None, ...} for runs with a stream."""
    if not has_stream(run):
        return {}
    return {k: best_effort(run["t"], run["d"], m) for k, m in DISTS}


def trimp(run, hr_max, hr_rest):
    """Banister TRIMP: minutes x HRr x 0.64 e^(1.92 HRr)."""
    def f(hr):
        x = max(0, min(1, (hr - hr_rest) / (hr_max - hr_rest)))
        return x * 0.64 * math.exp(1.92 * x) / 60

    if hr_ok(run):
        s, t, h = 0, run["t"], run["hr"]
        for i in range(1, len(t)):
            dt = t[i] - t[i - 1]
            if 0 < dt <= 30 and h[i]:
                s += dt * f(h[i])
        return s
    avg = run.get("avgHr")
    return (run.get("moving") or run.get("dur") or 0) * f(avg) if avg else 0
