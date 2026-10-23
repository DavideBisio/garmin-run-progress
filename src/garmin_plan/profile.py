"""The runner profile: profile.toml values, else derived from runs.json, else defaults."""
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import history, levels, match, progress
from .config import DEFAULT_DAYS, DEFAULT_LONG_RUN_DAY, DEFAULTS, MIN_HISTORY_DAYS, WEEKDAYS
from .physiology import load_rules
from .templates import LEVELS

OVERRIDE_ACTIONS = ("skip", "reduce", "lock")
RACE_DISTANCES = {"5k": 5000, "10k": 10000, "hm": 21097.5, "half": 21097.5, "m": 42195, "marathon": 42195}
NUMBERS = ("hr_max", "hr_rest", "vdot", "km_4w", "km_12w", "runs_per_week", "longest_8w")
FULL_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_GOAL = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")
_WEEK_VALUE = re.compile(r"^([a-z][a-z0-9_]*):(\d+)$")
_SECTION = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(?:#.*)?$")
_KEY = re.compile(r"""^\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_-]+))\s*=""")


class ProfileError(ValueError):
    """profile.toml holds a value the planner can't use."""


@dataclass
class Profile:
    hr_max: int
    hr_rest: int
    vdot: float
    km_4w: float
    km_12w: float
    runs_per_week: float
    longest_8w: float
    race: dict | None = None             # {"date", "distance_m", "goal_s"}
    days: list = field(default_factory=lambda: list(DEFAULT_DAYS))
    long_run_day: str = DEFAULT_LONG_RUN_DAY
    hill_days: list = field(default_factory=list)
    week: dict = field(default_factory=dict)  # day -> {"id", "variant", "line"} from [week]
    volume_level: str = levels.DEFAULT_LEVEL     # levels.toml levels (08)
    quality_level: str = levels.DEFAULT_LEVEL
    level_reasons: dict = field(default_factory=dict)   # "volume" / "quality" -> why (levels.detect)
    layoff: dict | None = None           # {days_off, vdot_factor, volume_factor, km_before} after a break
    unit: str | None = None              # "km" or "min"; None: the volume level's (levels.unit)
    vdot_from: tuple | None = None       # ("10k", "2024-05-01") when derived
    progress: dict | None = None         # what the last plan carries over (progress.carry; time_trials: all run)
    vdot_estimate: dict | None = None    # the derived VDOT before any layoff factor, for progress.vdot
    overrides: list = field(default_factory=list)   # [[override]]: {"from", "to", "action"} (roadmap 09)
    auto_push: bool = True               # make replan pushes the new plan (roadmap 09)
    sources: dict = field(default_factory=dict)   # field -> "set" | "derived" | "default"
    warnings: list = field(default_factory=list)


def read_toml(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ProfileError(f"{path}: {e}") from e


def _number(raw, key):
    v = raw[key]
    zero_ok = key not in ("hr_max", "hr_rest", "vdot")      # volume can be 0 after a break
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or (v == 0 and not zero_ok):
        raise ProfileError(f"{key} must be a {'non-negative' if zero_ok else 'positive'} number, got {v!r}")
    return v


def _day(name, key):
    """'Tue' or 'tuesday' -> 'tue'."""
    d = name.strip().lower() if isinstance(name, str) else ""
    if d in WEEKDAYS or d in FULL_DAYS:
        return d[:3]
    raise ProfileError(f"{key}: unknown day {name!r}; use {', '.join(WEEKDAYS)}")


def _day_list(raw, key):
    v = raw[key]
    if not isinstance(v, list):
        raise ProfileError(f"{key} must be a list of day names such as [\"tue\", \"sat\"]")
    return sorted({_day(d, key) for d in v}, key=WEEKDAYS.index)


def _level(raw, key):
    v = raw[key]
    level = v.strip().lower() if isinstance(v, str) else None
    if level not in LEVELS:
        raise ProfileError(f"{key} must be one of {', '.join(LEVELS)}, got {v!r}")
    return level


def parse_goal(v):
    """'1:35:00' or '42:30' -> seconds."""
    m = _GOAL.match(str(v).strip())
    if not m:
        raise ProfileError(f"race.goal must look like H:MM:SS or MM:SS, got {v!r}")
    return int(m[1] or 0) * 3600 + int(m[2]) * 60 + int(m[3])


def parse_race(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("date"), date):
        raise ProfileError("[race] needs date = YYYY-MM-DD (a TOML date, no quotes)")
    dist = raw.get("distance")
    if isinstance(dist, str) and dist.strip().lower() in RACE_DISTANCES:
        dist_m = RACE_DISTANCES[dist.strip().lower()]
    elif isinstance(dist, (int, float)) and not isinstance(dist, bool) and dist > 0:
        dist_m = dist * 1000                     # a number is km
    else:
        raise ProfileError(f"race.distance must be 5k, 10k, hm, m or km as a number, got {dist!r}")
    goal = raw.get("goal")
    return {"date": raw["date"], "distance_m": dist_m, "goal_s": parse_goal(goal) if goal is not None else None}


def parse_overrides(raw):
    """[[override]] tables -> [{"from": date, "to": date, "action": "skip" | "reduce" | "lock"}]; to
    defaults to from. Anything else raises ProfileError naming the table (1-based)."""
    if not isinstance(raw, list) or not all(isinstance(o, dict) for o in raw):
        raise ProfileError('override must be [[override]] tables of from = YYYY-MM-DD, to = YYYY-MM-DD and '
                           'action = "skip", "reduce" or "lock"')
    out = []
    for i, o in enumerate(raw, 1):
        frm, to, action = o.get("from"), o.get("to", o.get("from")), o.get("action")
        if type(frm) is not date:
            raise ProfileError(f"[[override]] {i}: needs from = YYYY-MM-DD (a TOML date, no quotes), got {frm!r}")
        if type(to) is not date:
            raise ProfileError(f"[[override]] {i}: to = YYYY-MM-DD (a TOML date, no quotes), got {to!r}")
        if to < frm:
            raise ProfileError(f"[[override]] {i}: to {to} is before from {frm}")
        act = action.strip().lower() if isinstance(action, str) else None
        if act not in OVERRIDE_ACTIONS:
            raise ProfileError(f"[[override]] {i}: action must be skip, reduce or lock, got {action!r}")
        out.append({"from": frm, "to": to, "action": act})
    return out


def race_vdot(runs, since, today):
    """(VDOT, label, date) of the best race (runs.json event "race") dated after since and up to
    today: the whole run's distance and moving time. None without one."""
    best = None
    for _, r in history.dated(runs):
        day, dist, secs = r["date"][:10], r.get("dist") or 0, r.get("moving") or r.get("dur") or 0
        if r.get("event") == "race" and since < day <= today and dist >= 1500 and secs > 0:
            v = history.vdot(dist, secs)
            if best is None or v > best[0]:
                best = (v, f"race {dist / 1000:g} km", day)
    return best


def _largest_gap(runs, since, today):
    """(days without a run, the day running resumed) of the longest break that ended after since
    (and by today), else None."""
    days = sorted({r["date"][:10] for _, r in history.dated(runs) if r["date"][:10] <= today})
    gaps = [((date.fromisoformat(b) - date.fromisoformat(a)).days - 1, b) for a, b in zip(days, days[1:]) if b > since]
    return max(gaps, default=None)


def reestimate_vdot(est, runs, trials, today, data, rules):
    """The carried VDOT estimate ({value, date, from, from_date}) moved on (roadmap 09): a time trial
    run since the estimate's source replaces it at once (the planned test); otherwise, every
    [adapt] vdot_every_weeks weeks, or as soon as a break has ended since the last estimate, a break
    lowers it by the layoff table and a better race raises it. Training efforts never change it."""
    t = today.isoformat()
    if trials and trials[-1]["date"] > est["from_date"]:
        return {"value": trials[-1]["vdot"], "date": t, "from": "2 km time trial", "from_date": trials[-1]["date"]}
    gap = _largest_gap(runs, est["date"], t)
    factor = levels.layoff(gap[0], data)[0] if gap else 1.0
    due = (today - date.fromisoformat(est["date"])).days >= 7 * rules["adapt"]["vdot_every_weeks"]
    if not due and factor == 1:
        return est
    out = {**est, "date": t}
    if factor < 1:
        out.update(value=est["value"] * factor, **{"from": f"{est['from']}, x{factor:g} after {gap[0]} days off"})
    since = gap[1] if factor < 1 else (date.fromisoformat(t) - timedelta(days=84)).isoformat()
    race = race_vdot(runs, since, t)
    if race and race[0] > out["value"]:
        out.update(value=race[0], **{"from": race[1], "from_date": race[2]})
    return out


def _week_lines(text):
    """{key: stripped source line} for the keys of the [week] table (tomllib has no line numbers)."""
    lines, section = {}, None
    for ln in text.splitlines():
        if ln.lstrip().startswith("["):
            # any header ends [week]: a plain [table] names the new section; [[array]] tables and
            # anything else starting with '[' leave no section to collect from
            m = _SECTION.match(ln)
            section = m[1].strip().strip('"') if m else None
            continue
        k = _KEY.match(ln)
        if section == "week" and k:
            lines.setdefault(next(g for g in k.groups() if g is not None), ln.strip())
    return lines


def parse_week(raw, text=""):
    """[week] day = "template:variant" -> {day: {"id", "variant", "line"}}, Monday first.

    The template and variant are checked against the library when the plan is built
    (plan_io.build_plan); errors quote `line`, the entry as written in profile.toml.
    """
    if not isinstance(raw, dict):
        raise ProfileError('[week] must be a table of day = "template:variant", such as tue = "easy:1"')
    lines, out = _week_lines(text), {}
    for key, v in raw.items():
        line = lines.get(key) or f"{key} = {v!r}"
        day = _day(key, f"[week] (line: {line})")
        if day in out:
            raise ProfileError(f"[week]: {day} is listed twice, in line: {line}")
        m = _WEEK_VALUE.match(v.strip().lower()) if isinstance(v, str) else None
        if not m:
            raise ProfileError(f'[week]: expected "template:variant" such as "easy:1", in line: {line}')
        out[day] = {"id": m[1], "variant": int(m[2]), "line": line}
    return {d: out[d] for d in WEEKDAYS if d in out}


def _layoff(stats, vals, sources, data):
    """The break before today, if any (levels.layoff): derived km_4w restarts from the volume before
    it and derived VDOT drops by the layoff factors. None without a break."""
    if stats["days_off"] is None:
        return None
    vdot_f, vol_f = levels.layoff(stats["days_off"], data)
    if vdot_f == 1 and vol_f == 1:
        return None
    lay = {"days_off": stats["days_off"], "vdot_factor": vdot_f, "volume_factor": vol_f,
           "km_before": stats["km_before"]}
    if sources["km_4w"] == "derived":
        vals["km_4w"] = stats["km_before"] * vol_f
        sources["km_4w"] = f"derived (after {stats['days_off']} days off: x{vol_f:g} of {stats['km_before']:.1f} km/wk)"
    if sources["vdot"] == "derived":
        vals["vdot"] *= vdot_f
    return lay


def _levels(raw, stats, vals, sources, lay, runs, today, data, plan, carried):
    """(volume_level, quality_level, reasons): profile.toml's, else levels.detect on the resolved
    numbers (after a break: the restart volume, and the runs a week, the consistency and the longest
    run, at the VDOT factor, from before it), moved on from the last plan's levels by levels.promote
    at the block's start that the last plan's progress counts (carried, progress.carry), held back
    when under [detect] compliance of the last block's Q sessions were run (match.q_compliance)."""
    longest = vals["longest_8w"]
    if lay and sources["longest_8w"] == "derived":      # the 8 weeks to today may hold no run at all
        longest = stats["longest_before"] * lay["vdot_factor"]
    dstats = {
        "km_4w": vals["km_4w"] if stats["km_4w"] is not None else None,
        "km_12w": vals["km_4w"] if lay else vals["km_12w"],      # a restart is judged on its volume
        "runs_per_week": stats["runs_before"] if lay else vals["runs_per_week"],
        "longest_8w": longest, "consistency": stats["consistency_before"] if lay else stats["consistency"],
        "history_days": stats["history_days"],
        "vdot": vals["vdot"] if sources["vdot"] != "default" else None,
        "q_8w": history.q_sessions(runs, today, vals["hr_max"], vals["hr_rest"]),
        "layoff": lay, "weeks": stats["weeks"]}
    found = levels.detect(dstats, data)
    prev = (plan or {}).get("levels")
    if not (isinstance(prev, dict) and {prev.get("volume"), prev.get("quality")} <= set(LEVELS)):
        prev = None                                   # no plan, a manual one, or one from before 08
    if prev:
        monday = today + timedelta(days=7 - today.weekday())        # the new plan's first week
        compliance = match.q_compliance(plan, runs, today, monday, load_rules(), vals["hr_max"], vals["hr_rest"])
        got, notes = levels.promote({"volume": prev["volume"], "quality": prev["quality"]}, dstats, data,
                                    block_start=carried is None or carried["block_start"] == monday,
                                    compliance=compliance)
    out, reasons = [], {}
    short = stats["history_days"] < MIN_HISTORY_DAYS
    for key, level, why in zip(("volume_level", "quality_level"), found[:2], (found[2]["volume"], found[2]["quality"])):
        axis = key.split("_")[0]
        if prev and key not in raw:
            note = next((n[len(axis) + 2:] for n in notes if n.startswith(f"{axis}: ")), None)
            if note:
                why = note
            elif got[axis] != level:
                why = f"kept from the last plan; detected {level}: {why}"
            level = got[axis]
        if key in raw:
            level, why, sources[key] = _level(raw, key), "set in profile.toml", "set"
        else:
            sources[key] = "default" if short else "derived"
        out.append(level)
        reasons[axis] = why
    return out[0], out[1], reasons


def load_profile(path, runs, rhr=(), today=None, plan=None):
    """Resolve every field: profile.toml ("set"), else runs.json ("derived"), else a default.

    A missing file or a short history never raises; each default adds a warning. Values in the
    file that can't be used raise ProfileError. After a break the derived volume and VDOT drop by
    the layoff table, and the levels are detected from what is left (roadmap 08). plan: the last
    plan.json, whose progress the new plan carries on (progress.carry) and whose time trials, once
    run, give the derived VDOT: the latest one. Once a plan carries a VDOT estimate (progress.vdot)
    it is the derived VDOT, moved on by reestimate_vdot: training efforts no longer change it.
    """
    raw = read_toml(path)
    today = today or date.today()
    stats = history.recent_stats(runs, today)
    carried = progress.carry(plan, today + timedelta(days=7 - today.weekday()))
    trials = history.time_trials(runs, progress.trial_days(plan, carried), today,
                                 carried["time_trials"] if carried else ())
    if carried:
        carried["time_trials"] = trials
    data = levels.load_levels()
    est = carried.get("vdot") if carried else None
    if est:                                   # the last plan's estimate, moved on (roadmap 09)
        est = reestimate_vdot(est, runs, trials, today, data, load_rules())
        stats["vdot"], stats["vdot_from"] = est["value"], (est["from"], est["from_date"])
    elif trials:
        stats["vdot"], stats["vdot_from"] = trials[-1]["vdot"], ("2 km time trial", trials[-1]["date"])
    derived = {"hr_max": history.hr_max(runs), "hr_rest": history.resting_hr(rhr),
               **{k: stats[k] for k in NUMBERS[2:]}}
    vals, sources, warnings = {}, {}, []
    short = stats["history_days"] < MIN_HISTORY_DAYS
    for key in NUMBERS:
        if key in raw:
            vals[key], sources[key] = _number(raw, key), "set"
        elif derived[key] is not None:
            vals[key], sources[key] = derived[key], "derived"
        else:
            vals[key], sources[key] = DEFAULTS[key], "default"
            why = "less than 4 weeks of runs" if short and key in NUMBERS[2:] else "nothing to derive it from"
            if key == "vdot" and not short:
                why = "no 5 km, 10 km or half effort with GPS in the last 12 weeks"
            warnings.append(f"{key}: {why}, using the default {DEFAULTS[key]} (set it in profile.toml)")
    if vals["hr_max"] <= vals["hr_rest"]:
        raise ProfileError(f"hr_max ({vals['hr_max']}) must be above hr_rest ({vals['hr_rest']})")
    if sources["vdot"] == "derived":          # before the layoff factor: progress.vdot carries it
        k, day = stats["vdot_from"]
        est = est or {"value": vals["vdot"], "date": today.isoformat(), "from": k, "from_date": day}
    else:
        est = None
    lay = _layoff(stats, vals, sources, data)
    vol, qual, reasons = _levels(raw, stats, vals, sources, lay, runs, today, data, plan, carried)

    if "days" in raw:
        days, sources["days"] = _day_list(raw, "days"), "set"
        if not days:
            raise ProfileError("days must list at least one day")
    else:
        days, sources["days"] = list(DEFAULT_DAYS), "default"
        warnings.append(f"days: not set, using {', '.join(days)}")
    if "long_run_day" in raw:
        long_day = _day(raw["long_run_day"], "long_run_day")
        if long_day not in days:
            raise ProfileError(f"long_run_day {long_day} is not one of the available days ({', '.join(days)})")
        sources["long_run_day"] = "set"
    else:
        long_day = DEFAULT_LONG_RUN_DAY if DEFAULT_LONG_RUN_DAY in days else days[-1]
        sources["long_run_day"] = "default"
        warnings.append(f"long_run_day: not set, using {long_day}")
    if "hill_days" in raw:
        hills, sources["hill_days"] = _day_list(raw, "hill_days"), "set"
    else:
        hills, sources["hill_days"] = [], "default"
        warnings.append("hill_days: not set, using none (no hill sessions)")
    race, sources["race"] = (parse_race(raw["race"]), "set") if "race" in raw else (None, "default")
    unit, sources["unit"] = None, "default"
    if "unit" in raw:
        unit = raw["unit"].strip().lower() if isinstance(raw["unit"], str) else None
        if unit not in levels.UNITS:
            raise ProfileError(f"unit must be km or min, got {raw['unit']!r}")
        sources["unit"] = "set"
    overrides = parse_overrides(raw["override"]) if "override" in raw else []
    auto_push = raw.get("auto_push", True)
    if not isinstance(auto_push, bool):
        raise ProfileError(f"auto_push must be true or false, got {auto_push!r}")
    week, sources["week"] = {}, "default"
    if "week" in raw:
        week, sources["week"] = parse_week(raw["week"], Path(path).read_text(encoding="utf-8")), "set"

    return Profile(**vals, race=race, days=days, long_run_day=long_day, hill_days=hills, week=week,
                   volume_level=vol, quality_level=qual, level_reasons=reasons, layoff=lay, unit=unit,
                   vdot_from=stats["vdot_from"] if sources["vdot"] == "derived" else None, progress=carried,
                   vdot_estimate=est, overrides=overrides, auto_push=auto_push,
                   sources=sources, warnings=warnings)
