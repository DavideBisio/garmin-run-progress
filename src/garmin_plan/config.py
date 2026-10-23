"""Paths and defaults shared by the planner modules."""
from pathlib import Path

EXPORT_DIR = Path("garmin_export")       # gitignored: personal files only
PROFILE = "profile.toml"
RUNS = "runs.json"
PLAN_JSON = "plan.json"
PLAN_MD = "plan.md"
DATA_DIR = Path(__file__).resolve().parent / "data"   # committed generic data (rules.toml, ...)

# fallbacks when neither profile.toml nor runs.json gives a value (HR as on the page's Data tab)
DEFAULTS = {
    "hr_max": 190,
    "hr_rest": 50,
    "vdot": 30.0,
    "km_4w": 0.0,
    "km_12w": 0.0,
    "runs_per_week": 0.0,
    "longest_8w": 0.0,
}
DEFAULT_DAYS = ["tue", "thu", "sat", "sun"]
DEFAULT_LONG_RUN_DAY = "sun"
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MIN_HISTORY_DAYS = 28        # less than 4 weeks of runs: volume and VDOT fall back to defaults
