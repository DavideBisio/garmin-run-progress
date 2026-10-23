"""The workout template library (data/workouts.toml): loading, validation and instantiation.

instantiate(template, variant, profile, rules) resolves one ladder variant (1-based) for a runner:
pace zones become PaceRanges (point pace from physiology.pace_zones plus the [bands] in rules.toml),
HR zones become bpm HrRanges (Karvonen, as physiology.hr_zones). See docs/features/plan-workouts.md.
"""
import math
import re
import tomllib
from pathlib import Path

from .config import DATA_DIR
from .model import ROLES, HrRange, PaceRange, Repeat, Step, Workout
from .physiology import hr_zones, pace_zones

KINDS = ("E", "L", "R", "T", "I", "M", "hill", "trail")
LEVELS = ("beginner", "novice", "intermediate", "advanced")
PACE_ZONES = ("E", "M", "T", "I", "R")
HARD_ZONES = ("M", "T", "I", "R")
# a step's HR target when the template gives none: its pace zone's usual HR zone
ZONE_HR = {"E": "Z2", "M": "Z3", "T": "Z4", "I": "Z4-5", "R": "Z4-5", "jog": "Z2"}
LABELS = {"warmup": "Warmup", "rep": "Rep", "recovery": "Recovery", "cooldown": "Cooldown"}

TEMPLATE_KEYS = {"id", "title", "kind", "min_level", "warmup", "main", "cooldown", "ladder", "climb_m_per_km"}
STEP_KEYS = {"role", "label", "dist", "time", "lap", "pace", "hr", "est_pace", "est_dist", "est_time",
             "effort", "note", "hard"}
REPEAT_KEYS = {"repeat", "steps", "rep", "recovery", "skip_last_rest", "note"}
NUMBERS = ("dist", "time", "est_dist", "est_time")
_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_VAR = re.compile(r"^[a-z_][a-z0-9_]*$")
_HR = re.compile(r"^Z([1-5])(?:-([1-5])| (cap))?$")
_EST = re.compile(r"^(?:(E|M|T|I|R|jog)([+-]\d+)?|(\d+):([0-5]\d))$")


class TemplateError(ValueError):
    """workouts.toml holds a template the planner can't use."""


# ---------------------------------------------------------------- zones

def pace_range(zone, paces, rules):
    """PaceRange of a pace zone: the point pace minus/plus the zone's [bands] offsets (s/km)."""
    faster, slower = rules["bands"][zone]
    return PaceRange(paces[zone] - faster, paces[zone] + slower)


def jog_pace(paces, rules):
    """Recovery jog: the slow end of E plus jog_offset_s. Used for duration estimates only."""
    return pace_range("E", paces, rules).slow_s + rules["bands"]["jog_offset_s"]


def _parse_hr(spec):
    m = _HR.match(spec) if isinstance(spec, str) else None
    if not m or (m[2] and int(m[2]) < int(m[1])):
        raise TemplateError(f"unknown HR zone {spec!r}; use Z1 … Z5, a span such as Z4-5, "
                            "a cap such as Z3 cap, or open")
    return int(m[1]), int(m[2] or m[1]), bool(m[3])


def hr_range(spec, hr_max, hr_rest):
    """'Z2' -> Z2's bpm; 'Z4-5' -> Z4 low to Z5 high; 'Z3 cap' -> Z1 low to Z3 high.

    Z1 starts at 50% of the heart-rate reserve and Z5 ends at hr_max; the bounds in between are
    physiology.hr_zones (same clamping and rounding as the page).
    """
    a, b, cap = _parse_hr(spec)
    rest = min(hr_rest, hr_max - 20)
    edges = [math.floor(rest + 0.5 * (hr_max - rest) + 0.5), *hr_zones(hr_max, hr_rest), math.floor(hr_max + 0.5)]
    return HrRange(edges[0], edges[b]) if cap else HrRange(edges[a - 1], edges[b])


def _parse_est(spec):
    m = _EST.match(spec) if isinstance(spec, str) else None
    if not m:
        raise TemplateError(f"est_pace must be a zone (E, M, T, I, R, jog), a zone plus or minus "
                            f"seconds such as I+30, or M:SS; got {spec!r}")
    return m


def est_pace(spec, paces, rules):
    """'E', 'jog', 'I+30' (a zone's mid pace plus seconds per km) or an absolute 'M:SS' -> s/km."""
    m = _parse_est(spec)
    if m[3]:
        return int(m[3]) * 60 + int(m[4])
    base = jog_pace(paces, rules) if m[1] == "jog" else pace_range(m[1], paces, rules).mid
    return base + int(m[2] or 0)


# ---------------------------------------------------------------- validation

def _num_or_var(v, key, where, used):
    if isinstance(v, str):
        if not _VAR.match(v):
            raise TemplateError(f"{where}: {key} = {v!r} is neither a number nor a ladder variable")
        used.add(v)
    elif isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise TemplateError(f"{where}: {key} must be a non-negative number or a ladder variable, got {v!r}")


def _effective_zone(s, role):
    """The pace zone a step resolves to: its pace, else jog for a recovery without an effort text."""
    return s.get("pace") or ("jog" if role == "recovery" and "effort" not in s else None)


def _check_step(s, role, where, used):
    if not isinstance(s, dict):
        raise TemplateError(f"{where}: a step must be a table, got {s!r}")
    extra = set(s) - STEP_KEYS
    if extra:
        raise TemplateError(f"{where}: unknown step key(s) {', '.join(sorted(extra))}")
    role = s.get("role", role)
    if role not in ROLES:
        raise TemplateError(f"{where}: unknown role {role!r}; use {', '.join(ROLES)}")
    where = f"{where} ({s.get('label', LABELS[role])})"
    ends = [k for k in ("dist", "time", "lap") if k in s]
    if len(ends) != 1:
        raise TemplateError(f"{where}: a step needs exactly one end: dist (m), time (s) or lap = true")
    if "lap" in s and s["lap"] is not True:
        raise TemplateError(f"{where}: lap must be true")
    for k in NUMBERS:
        if k in s:
            _num_or_var(s[k], k, where, used)
    if "pace" in s and s["pace"] not in (*PACE_ZONES, "jog"):
        raise TemplateError(f"{where}: unknown pace zone {s['pace']!r}; use E, M, T, I, R or jog")
    if "pace" in s and "effort" in s:
        raise TemplateError(f"{where}: give a pace zone or an effort text, not both")
    if s.get("hr", "open") != "open":
        try:
            _parse_hr(s["hr"])
        except TemplateError as e:
            raise TemplateError(f"{where}: {e}") from None
    if "est_pace" in s:
        try:
            _parse_est(s["est_pace"])
        except TemplateError as e:
            raise TemplateError(f"{where}: {e}") from None
    for k in ("label", "effort", "note"):
        if k in s and not isinstance(s[k], str):
            raise TemplateError(f"{where}: {k} must be text")
    if "hard" in s and not isinstance(s["hard"], bool):
        raise TemplateError(f"{where}: hard must be true or false")
    zone = _effective_zone(s, role)
    if "time" in s and zone != "jog" and "est_pace" not in s:
        raise TemplateError(f"{where}: a time-ended step needs est_pace for its distance estimate")
    if "dist" in s and zone not in (*PACE_ZONES, "jog") and "est_pace" not in s:
        raise TemplateError(f"{where}: a distance-ended step without a pace target needs est_pace "
                            "for its duration estimate")
    if "lap" in s and not ("est_time" in s and "est_dist" in s):
        raise TemplateError(f"{where}: a lap-button step needs est_time and est_dist")


def _check_block(b, where, used, counts):
    if not isinstance(b, dict):
        raise TemplateError(f"{where}: a main block must be a table, got {b!r}")
    if "repeat" not in b:
        _check_step(b, "rep", where, used)
        return
    extra = set(b) - REPEAT_KEYS
    if extra:
        raise TemplateError(f"{where}: unknown repeat key(s) {', '.join(sorted(extra))}")
    n = b["repeat"]
    if not isinstance(n, str) and (isinstance(n, bool) or not isinstance(n, int)):
        raise TemplateError(f"{where}: repeat must be a whole number or a ladder variable, got {n!r}")
    _num_or_var(n, "repeat", where, used)
    if isinstance(n, str):
        counts.add(n)
    if ("steps" in b) == ("rep" in b):
        raise TemplateError(f"{where}: a repeat needs either steps = [...] or rep = {{...}}")
    if "recovery" in b and "rep" not in b:
        raise TemplateError(f"{where}: recovery goes with rep, not with steps")
    if "skip_last_rest" in b and not isinstance(b["skip_last_rest"], bool):
        raise TemplateError(f"{where}: skip_last_rest must be true or false")
    if "steps" in b:
        if not isinstance(b["steps"], list) or not b["steps"]:
            raise TemplateError(f"{where}: steps must be a non-empty list")
        for s in b["steps"]:
            _check_step(s, "rep", where, used)
    else:
        _check_step(b["rep"], "rep", where, used)
        if "recovery" in b:
            _check_step(b["recovery"], "recovery", where, used)


def check_template(t, where):
    if not isinstance(t, dict):
        raise TemplateError(f"{where}: a [[workout]] must be a table")
    extra = set(t) - TEMPLATE_KEYS
    if extra:
        raise TemplateError(f"{where}: unknown key(s) {', '.join(sorted(extra))}")
    if not isinstance(t.get("id"), str) or not _ID.match(t["id"]):
        raise TemplateError(f"{where}: id must be lower-case letters, digits and _, got {t.get('id')!r}")
    if not isinstance(t.get("title"), str) or not t["title"].strip():
        raise TemplateError(f"{where}: title must be non-empty text")
    if t.get("kind") not in KINDS:
        raise TemplateError(f"{where}: unknown kind {t.get('kind')!r}; use {', '.join(KINDS)}")
    if t.get("min_level") not in LEVELS:
        raise TemplateError(f"{where}: unknown min_level {t.get('min_level')!r}; use {', '.join(LEVELS)}")
    c = t.get("climb_m_per_km", 0)
    if isinstance(c, bool) or not isinstance(c, (int, float)) or c < 0:
        raise TemplateError(f"{where}: climb_m_per_km must be a non-negative number")
    used, counts = set(), set()        # every ladder variable; those used as repeat counts
    for part in ("warmup", "cooldown"):
        if part in t:
            _check_step(t[part], part, f"{where} {part}", used)
    main = t.get("main")
    if isinstance(main, dict):
        main = t["main"] = [main]
    if not isinstance(main, list) or not main:
        raise TemplateError(f"{where}: main must be a block or a non-empty list of blocks")
    for b in main:
        _check_block(b, f"{where} main", used, counts)
    ladder = t.get("ladder")
    if not isinstance(ladder, list) or not ladder or not all(isinstance(e, dict) for e in ladder):
        raise TemplateError(f"{where}: ladder must be a non-empty list of tables, smallest first")
    for i, e in enumerate(ladder, 1):
        missing = used - set(e)
        if missing:
            raise TemplateError(f"{where}: ladder variant {i} is missing {', '.join(sorted(missing))}")
        for k, v in e.items():
            if k == "title":
                if not isinstance(v, str) or not v.strip():
                    raise TemplateError(f"{where}: ladder variant {i} title must be non-empty text")
            elif isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise TemplateError(f"{where}: ladder variant {i}: {k} must be a non-negative number")
            elif k in counts and not isinstance(v, int):
                raise TemplateError(f"{where}: ladder variant {i}: {k} is a repeat count and must be a "
                                    f"whole number, got {v!r}")


def load_templates(path=None):
    """{id: template} in file order, validated. Raises TemplateError."""
    path = Path(path or DATA_DIR / "workouts.toml")
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise TemplateError(f"{path}: {e}") from e
    items = data.get("workout")
    if not isinstance(items, list) or not items:
        raise TemplateError(f"{path.name}: no [[workout]] templates")
    out = {}
    for i, t in enumerate(items, 1):
        where = f"{path.name}: workout {t.get('id', i) if isinstance(t, dict) else i}"
        check_template(t, where)
        if t["id"] in out:
            raise TemplateError(f"{path.name}: duplicate id {t['id']!r}")
        out[t["id"]] = t
    return out


# ---------------------------------------------------------------- instantiation

class _Ctx:
    def __init__(self, t, variant, prof, rules):
        self.id, self.vars, self.rules, self.prof = t["id"], t["ladder"][variant - 1], rules, prof
        self.paces = pace_zones(prof.vdot, rules)

    def value(self, v):
        return self.vars[v] if isinstance(v, str) else v


def _step(s, role, ctx):
    role = s.get("role", role)
    end = next(k for k in ("dist", "time", "lap") if k in s)
    value = None if end == "lap" else ctx.value(s[end])
    if value == 0:
        return None                      # a zero ladder value leaves an optional step out
    zone = _effective_zone(s, role)
    pace = pace_range(zone, ctx.paces, ctx.rules) if zone in PACE_ZONES else None
    spec = s.get("hr") or ZONE_HR.get(zone)
    spec = None if spec == "open" else spec
    hr = hr_range(spec, ctx.prof.hr_max, ctx.prof.hr_rest) if spec else None
    if "est_pace" in s:
        est = est_pace(s["est_pace"], ctx.paces, ctx.rules)
    else:
        est = jog_pace(ctx.paces, ctx.rules) if zone == "jog" else None
    return Step(role, s.get("label", LABELS[role]), end, value, zone=zone, pace=pace, hr_zone=spec, hr=hr,
                est_pace=est,
                est_dist=ctx.value(s["est_dist"]) if "est_dist" in s else None,
                est_time=ctx.value(s["est_time"]) if "est_time" in s else None,
                effort=s.get("effort"), note=s.get("note", ""),
                hard=zone in HARD_ZONES or s.get("hard", False))


def _block(b, ctx):
    if "repeat" not in b:
        return _step(b, "rep", ctx)
    n = ctx.value(b["repeat"])
    if n != int(n):
        raise TemplateError(f"{ctx.id}: repeat count {n} is not a whole number")
    if n == 0:
        return None                      # a repeat of 0 leaves an optional block out
    raw = b["steps"] if "steps" in b else [b["rep"]] + ([b["recovery"]] if "recovery" in b else [])
    roles = ["rep"] * len(raw) if "steps" in b else ["rep", "recovery"]
    steps = [s for s in (_step(x, r, ctx) for x, r in zip(raw, roles)) if s]
    if not steps:
        return None
    # a single rep has no recovery "between reps": a repeat of 1 always skips its last recovery
    skip = b.get("skip_last_rest", False) or n == 1
    return Repeat(int(n), steps, skip_last_rest=skip, note=b.get("note", ""))


def instantiate(template, variant, profile, rules):
    """The Workout of ladder variant `variant` (1-based) for `profile` (vdot, hr_max, hr_rest)."""
    n = len(template["ladder"])
    if isinstance(variant, bool) or not isinstance(variant, int) or not 1 <= variant <= n:
        raise TemplateError(f"{template['id']}: variant {variant!r} doesn't exist (variants 1-{n})")
    ctx = _Ctx(template, variant, profile, rules)
    parts = []
    if "warmup" in template:
        parts.append(_step(template["warmup"], "warmup", ctx))
    parts += [_block(b, ctx) for b in template["main"]]
    if "cooldown" in template:
        parts.append(_step(template["cooldown"], "cooldown", ctx))
    parts = [p for p in parts if p]
    if not parts:
        raise TemplateError(f"{template['id']}: variant {variant} has no steps")
    return Workout(template["id"], variant, ctx.vars.get("title", template["title"]), template["kind"], parts,
                   template.get("climb_m_per_km"))
