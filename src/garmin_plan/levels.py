"""Runner levels (data/levels.toml): the planning numbers that depend on the runner's level (roadmap 08).

A runner has two levels, one per axis: a volume level (how much they run) and a quality level (what
sessions they're ready for). params(levels, volume_level, quality_level, rules) gives the rules the
planner uses: a copy of rules.toml with each levels.toml key set to its value at the right level.
"""
import copy
import tomllib

from .config import DATA_DIR
from .physiology import load_rules
from .templates import LEVELS

DEFAULT_LEVEL = "intermediate"     # a Profile built without levels (tests, old callers)
SECTIONS = ("volume", "split", "skeleton", "checks", "rotation")
# keys set by the quality level; every other levels.toml key follows the volume level
QUALITY = {"skeleton": {"q_min_days"}, "checks": {"max_hard"}, "rotation": {"base", "rt", "it", "tm", "taper"}}


def load_levels(path=None):
    with open(path or DATA_DIR / "levels.toml", "rb") as f:
        return tomllib.load(f)


def _check(level):
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}; use {', '.join(LEVELS)}")


def _per_level(v):
    """A {level: value} table (every key a level name), as opposed to a plain value."""
    return isinstance(v, dict) and v and set(v) <= set(LEVELS)


def params(levels, volume_level, quality_level, rules=None):
    """rules.toml with levels.toml laid over [volume], [split], [skeleton], [checks] and [rotation].

    A levels.toml key holds {level: value}: the volume level's value, or the quality level's for the
    QUALITY keys; a level missing from the table keeps rules.toml's value. A plain value applies at
    every level. [rotation] level is the quality level (select.py's template filter). The other
    sections are rules.toml's, and rules itself is never changed.
    """
    _check(volume_level)
    _check(quality_level)
    out = copy.deepcopy(rules or load_rules())
    for sec in SECTIONS:
        dst = out.setdefault(sec, {})
        for key, v in (levels.get(sec) or {}).items():
            level = quality_level if key in QUALITY.get(sec, ()) else volume_level
            if not _per_level(v):
                dst[key] = copy.deepcopy(v)
            elif level in v:
                dst[key] = copy.deepcopy(v[level])
    out["rotation"]["level"] = quality_level
    return out
