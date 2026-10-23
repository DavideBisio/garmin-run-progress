"""Command line: python -m garmin_plan profile (later: plan, push, replan)."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .config import EXPORT_DIR, PROFILE, RUNS
from .physiology import hr_zones, pace_zones
from .profile import ProfileError, load_profile


def fmt_pace(s):
    s = int(s + 0.5)
    return f"{s // 60}:{s % 60:02d}"


def fmt_time(s):
    s = int(s + 0.5)
    h, m, x = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m}:{x:02d}"


def load_runs(path):
    """(runs, rhr) from runs.json; a missing file is an empty history."""
    if not path.exists():
        print(f"warning: {path} not found, deriving nothing from history", file=sys.stderr)
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        sys.exit(f"error: {path}: can't read runs.json ({e})")
    return data.get("runs") or [], data.get("rhr") or []


def show_profile(p, path):
    def line(label, value, key):
        src = p.sources[key]
        if key == "vdot" and src == "derived":
            k, day = p.vdot_from
            src = f"derived (training efforts): best {k} on {day}"
        print(f"  {label:<18}{value:<24}{src}")

    print(f"Profile ({path})")
    line("HR max", f"{p.hr_max:g} bpm", "hr_max")
    line("HR rest", f"{p.hr_rest:g} bpm", "hr_rest")
    line("VDOT", f"{p.vdot:.1f}", "vdot")
    line("Weekly km, 4 wk", f"{p.km_4w:.1f} km", "km_4w")
    line("Weekly km, 12 wk", f"{p.km_12w:.1f} km", "km_12w")
    line("Runs per week", f"{p.runs_per_week:.1f}", "runs_per_week")
    line("Longest, 8 wk", f"{p.longest_8w:.1f} km", "longest_8w")
    race = "none"
    if p.race:
        race = f"{p.race['distance_m'] / 1000:g} km on {p.race['date']}"
        if p.race["goal_s"]:
            race += f" in {fmt_time(p.race['goal_s'])}"
    line("Race", race, "race")
    line("Days", ", ".join(p.days), "days")
    line("Long run day", p.long_run_day, "long_run_day")
    line("Hill days", ", ".join(p.hill_days) or "none", "hill_days")

    print(f"\nPace zones at VDOT {p.vdot:.1f} (min/km)")
    for k, s in pace_zones(p.vdot).items():
        print(f"  {k}  {fmt_pace(s)}")
    b = hr_zones(p.hr_max, p.hr_rest)
    print(f"\nHR zones, % of heart-rate reserve ({p.hr_max:g} max, {p.hr_rest:g} rest; bpm)")
    print(f"  Z1  < {b[0]}\n  Z2  {b[0]}-{b[1]}\n  Z3  {b[1]}-{b[2]}\n  Z4  {b[2]}-{b[3]}\n  Z5  {b[3]}+")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="garmin_plan", description="Training planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("profile", help="print the resolved runner profile and where each value came from")
    pr.add_argument("--export", default=str(EXPORT_DIR), help="folder with runs.json and profile.toml")
    pr.add_argument("--today", type=date.fromisoformat, help="pretend today is YYYY-MM-DD")
    args = ap.parse_args(argv)

    out = Path(args.export)
    runs, rhr = load_runs(out / RUNS)
    try:
        p = load_profile(out / PROFILE, runs, rhr, args.today)
    except ProfileError as e:
        sys.exit(f"error: {e}")
    for w in p.warnings:
        print(f"warning: {w}", file=sys.stderr)
    show_profile(p, out / PROFILE)
