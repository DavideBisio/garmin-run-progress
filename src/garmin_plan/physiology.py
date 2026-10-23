"""Daniels VDOT, training paces and Karvonen heart-rate zones."""
import math
import tomllib

from .config import DATA_DIR

# upper bounds of Z1-Z4 as a share of heart-rate reserve, as HRR_ZONES in src/page/js/metrics.js
HRR_ZONES = (.6, .7, .8, .9)
MARATHON_M = 42195


def vo2(v):
    """Oxygen cost (ml/kg/min) of running at v m/min."""
    return -4.6 + 0.182258 * v + 0.000104 * v * v


def pct_max(t):
    """Share of VO2max that can be held for t minutes."""
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)


def vdot(m, s):
    """VDOT of m metres in s seconds (same operation order as vdot in metrics.js)."""
    t = s / 60
    v = m / t
    return vo2(v) / pct_max(t)


def race_time(target, m):
    """Seconds to run m metres at VDOT `target`: bisects vdot(m, t) = target."""
    if not target > 0:
        raise ValueError(f"VDOT must be positive, got {target}")
    lo, hi = m * 0.06, m * 1.2       # 1 to 20 min/km brackets every realistic VDOT
    for _ in range(100):
        mid = (lo + hi) / 2
        if vdot(m, mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def speed_at(vo2_target):
    """Speed (m/min) whose oxygen cost is vo2_target: positive root of VO2(v) = vo2_target."""
    a, b, c = 0.000104, 0.182258, -4.6 - vo2_target
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def load_rules(path=None):
    with open(path or DATA_DIR / "rules.toml", "rb") as f:
        return tomllib.load(f)


def pace_zones(v, rules=None):
    """Daniels E/M/T/I/R paces for VDOT v, in seconds per km."""
    p = (rules or load_rules())["paces"]
    pace = {k: 60000 / speed_at(p[k] * v) for k in ("E", "T", "I")}
    pace["M"] = race_time(v, MARATHON_M) / (MARATHON_M / 1000)
    pace["R"] = pace["I"] - p["R_faster_per_400_s"] * 2.5
    return {k: pace[k] for k in ("E", "M", "T", "I", "R")}


def hr_zones(hr_max, hr_rest):
    """bpm bounds of Z1-Z4 (hrrZones in metrics.js): rest clamped to max - 20, rounded half up."""
    rest = min(hr_rest, hr_max - 20)
    return [math.floor(rest + p * (hr_max - rest) + 0.5) for p in HRR_ZONES]
