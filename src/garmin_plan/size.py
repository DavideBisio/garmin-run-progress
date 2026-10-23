"""Session sizing: the ladder variant a slot gets (rules.toml [caps]), and easy and long runs fitted to
their slot's km or time with templates.instantiate overrides."""
import math

from .model import Repeat
from .templates import HARD_ZONES, instantiate

EPS = 1e-9


def cap_km(kind, week_km, caps):
    """The most hard km a session of `kind` may hold in a week of week_km: share x week_km, at most the
    cap's km. A kind may name another kind's cap (L -> M); kinds without one have no cap (inf)."""
    c = caps.get(kind)
    if isinstance(c, str):
        c = caps[c]
    if c is None:
        return math.inf
    return min([c[0] * week_km, *c[1:]])


def pick_variant(template, slot_km, week_km, caps, profile, rules, *, lighter=0, slot_s=None):
    """(variant, forced): the last ladder variant whose hard km fit under the cap and whose total fits
    the slot (slot_km, or slot_s seconds for a time budget), scanning every variant because hard km
    need not grow along a ladder. When none fits, the smallest with forced=True: a known exception
    at low volume, not a violation. `lighter` steps that many variants down (the deload week)."""
    cap = cap_km(template["kind"], week_km, caps)
    fit = None
    for v in range(1, len(template["ladder"]) + 1):
        w = instantiate(template, v, profile, rules)
        room = w.seconds <= slot_s + EPS if slot_s is not None else w.km <= slot_km + EPS
        if w.hard_km <= cap + EPS and room:
            fit = v
    if fit is None:
        return 1, True
    return max(1, fit - lighter), False


def _filler(template):
    """(step dict) the first main step, outside any repeat, whose end is a ladder variable and that
    isn't hard: the easy part a fitted run stretches or shrinks. None when there is none."""
    for b in template["main"]:
        if "repeat" in b:
            continue
        end = next((k for k in ("dist", "time") if k in b), None)
        if end and isinstance(b[end], str) and b.get("pace") not in HARD_ZONES and not b.get("hard"):
            return b, end
    return None


def _main_step(w, step):
    """The resolved Step of template step dict `step` in workout w (matched by label and end)."""
    label = step.get("label", "Rep")
    return next(p for p in w.parts if not isinstance(p, Repeat) and p.label == label and p.role == "rep")


def fit(template, variant, profile, rules, *, km=None, seconds=None, warmup_km=0.0):
    """The variant resized for one slot, or None when it can't be.

    km / seconds: the filler step (see _filler) takes the difference, so the run is km long or lasts
    `seconds` (the hill and trail swaps keep the time budget of the long run they replace); None
    when that would leave the filler at 0 or less. warmup_km: that much more warm-up (the split's
    leftover on the Q day). Values are rounded to whole metres and seconds.
    """
    w = instantiate(template, variant, profile, rules)
    over = {}
    if km is not None or seconds is not None:
        f = _filler(template)
        if f is None:
            return None
        step, end = f
        s = _main_step(w, step)
        pace = s.seconds / s.meters * 1000                        # s/km of the filler
        delta_m = (km - w.km) * 1000 if km is not None else (seconds - w.seconds) / pace * 1000
        value = s.value + (delta_m if end == "dist" else delta_m * pace / 1000)
        if value < 1:
            return None
        over[step[end]] = round(value)
    if warmup_km:
        s = w.parts[0]
        if s.role != "warmup":
            return None
        pace = s.seconds / s.meters * 1000
        over["warmup"] = round(s.value + (warmup_km * 1000 if s.end == "dist" else warmup_km * pace))
    return instantiate(template, variant, profile, rules, overrides=over) if over else w
