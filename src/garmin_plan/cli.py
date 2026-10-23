"""Command line: python -m garmin_plan profile | plan (later: push, replan)."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .config import EXPORT_DIR, PLAN_JSON, PLAN_MD, PROFILE, RUNS
from .physiology import hr_zones, load_rules, pace_zones
from .plan_io import build_plan, write_plan
from .profile import ProfileError, load_profile
from .render_md import fmt_pace, fmt_time, render_plan  # noqa: F401  (fmt_* used to live here)
from .templates import TemplateError, load_templates


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


def resolve_profile(args):
    """(export dir, Profile) for --export / --today; profile errors exit with 'error: ...'."""
    out = Path(args.export)
    runs, rhr = load_runs(out / RUNS)
    try:
        p = load_profile(out / PROFILE, runs, rhr, args.today)
    except ProfileError as e:
        sys.exit(f"error: {e}")
    for w in p.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return out, p


def cmd_profile(args):
    out, p = resolve_profile(args)
    show_profile(p, out / PROFILE)


def cmd_plan(args):
    out, p = resolve_profile(args)
    try:
        rules = load_rules()
        plan = build_plan(p, load_templates(), rules, args.today or date.today(), args.weeks)
    except (ProfileError, TemplateError) as e:
        sys.exit(f"error: {e}")
    write_plan(plan, out / PLAN_JSON)
    (out / PLAN_MD).write_text(render_plan(plan), encoding="utf-8", newline="\n")
    km = sum(w["target_km"] for w in plan["weeks"])
    print(f"Wrote {out / PLAN_JSON} and {out / PLAN_MD}: {args.weeks} week(s) from "
          f"{plan['weeks'][0]['start']}, {km:.1f} km")


def positive_int(v):
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {v}")
    return n


def main(argv=None):
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--export", default=str(EXPORT_DIR), help="folder with runs.json and profile.toml")
    shared.add_argument("--today", type=date.fromisoformat, help="pretend today is YYYY-MM-DD")
    ap = argparse.ArgumentParser(prog="garmin_plan", description="Training planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("profile", parents=[shared],
                   help="print the resolved runner profile and where each value came from"
                   ).set_defaults(run=cmd_profile)
    pl = sub.add_parser("plan", parents=[shared],
                        help="write plan.json and plan.md from the [week] table in profile.toml")
    pl.add_argument("--weeks", type=positive_int, default=1, help="weeks to plan, from the Monday after today")
    pl.set_defaults(run=cmd_plan)
    args = ap.parse_args(argv)
    args.run(args)
