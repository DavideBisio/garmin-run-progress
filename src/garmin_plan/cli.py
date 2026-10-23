"""Command line: python -m garmin_plan profile | plan | push (later: replan).

push logs in through garmin_grab.garmin (garminconnect), imported only when it really calls Garmin;
profile, plan and push --dry-run are standard library only.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .config import EXPORT_DIR, PLAN_JSON, PLAN_MD, PROFILE, PUSH_STATE, RUNS
from .levels import describe
from .physiology import hr_zones, load_rules, pace_zones
from . import push as garmin_push
from .phases import PhaseError
from .plan_io import read_plan, write_plan
from .replan import replan
from .profile import ProfileError, load_profile
from .render_md import fmt_pace, fmt_time, render_plan  # noqa: F401  (fmt_* used to live here)
from .skeleton import SkeletonError
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
            known = any(w in k for w in ("trial", "race", "days off"))
            src = f"derived: {k} on {day}" if known else f"derived (training efforts): best {k} on {day}"
            if p.layoff:
                src += f", x{p.layoff['vdot_factor']:g} after {p.layoff['days_off']} days off"
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
    line("Volume level", p.volume_level, "volume_level")
    line("Quality level", p.quality_level, "quality_level")
    line("Volume unit", p.unit or "the level's", "unit")
    print(f"\nLevels: {describe(p.volume_level, p.quality_level, p.level_reasons)}")

    print(f"\nPace zones at VDOT {p.vdot:.1f} (min/km)")
    for k, s in pace_zones(p.vdot).items():
        print(f"  {k}  {fmt_pace(s)}")
    b = hr_zones(p.hr_max, p.hr_rest)
    print(f"\nHR zones, % of heart-rate reserve ({p.hr_max:g} max, {p.hr_rest:g} rest; bpm)")
    print(f"  Z1  < {b[0]}\n  Z2  {b[0]}-{b[1]}\n  Z3  {b[1]}-{b[2]}\n  Z4  {b[2]}-{b[3]}\n  Z5  {b[3]}+")


def resolve_profile(args):
    """(export dir, Profile, runs, the last plan.json or None, rhr) for --export / --today; profile errors
    exit with 'error: ...'."""
    out = Path(args.export)
    runs, rhr = load_runs(out / RUNS)
    prev = None                         # the last plan: its levels, progress and time trials
    if (out / PLAN_JSON).exists():
        try:
            prev = read_plan(out / PLAN_JSON)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            print(f"warning: {out / PLAN_JSON}: can't read it, ignored as the last plan: the levels are "
                  f"detected afresh and the block, run/walk ladder and time trials start over ({e})", file=sys.stderr)
    try:
        p = load_profile(out / PROFILE, runs, rhr, args.today, plan=prev)
    except ProfileError as e:
        sys.exit(f"error: {e}")
    for w in p.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return out, p, runs, prev, rhr


def cmd_profile(args):
    out, p, *_ = resolve_profile(args)
    show_profile(p, out / PROFILE)


def cmd_plan(args):
    out, p, runs, prev, rhr = resolve_profile(args)
    try:
        rules = load_rules()
        plan = replan(prev, p, runs, load_templates(), rules, args.today or date.today(), args.weeks,
                      wellness={"rhr": rhr})
    except (ProfileError, TemplateError, SkeletonError, PhaseError) as e:
        sys.exit(f"error: {e}")
    write_plan(plan, out / PLAN_JSON)
    (out / PLAN_MD).write_text(render_plan(plan), encoding="utf-8", newline="\n")
    new = [w for w in plan["weeks"] if w["start"] >= plan["progress"].get("plan_start", "")]
    km = sum(w["target_km"] for w in new)
    total = f"{km:.1f} km"
    if new and all(w.get("unit") == "min" for w in new):
        total = f"{sum(w['target_min'] for w in new)} min (~{km:.1f} km)"
    n = len(plan["warnings"]) + sum(len(w.get("warnings") or []) for w in new)
    print(f"Wrote {out / PLAN_JSON} and {out / PLAN_MD}: {len(new)} week(s) from "
          f"{new[0]['start']}, {total}" + (f"; {n} warning(s), listed in plan.md" if n else ""))


def cmd_push(args):
    out = Path(args.export)
    path = out / PLAN_JSON
    if not path.exists():
        sys.exit(f"error: {path} not found; write it first with make plan")
    try:
        plan = read_plan(path)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        sys.exit(f"error: {path}: can't read plan.json ({e})")
    if args.dry_run:
        try:
            garmin_push.push(None, plan, args.today or date.today(), out, dry_run=True, weeks=args.weeks)
        except (garmin_push.PushError, KeyError, ValueError) as e:
            sys.exit(f"error: {e}")
        return
    from garmin_grab.garmin import login, with_retry   # garminconnect only for real pushes
    g = login()
    garmin_push.check_library(g)
    try:
        today = garmin_push.local_today(g, args.today)
        garmin_push.push(g, plan, today, out, weeks=args.weeks, retry=with_retry)
    except KeyboardInterrupt:
        sys.exit("interrupted; re-run to resume")
    except Exception as e:  # noqa: BLE001  (Garmin's errors, PushError, a broken plan.json: all resumable)
        sys.exit(f"error: {e} (re-run to resume; state is in {out / PUSH_STATE})")


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
                        help="generate plan.json and plan.md from profile.toml and runs.json "
                             "([week] days override the generated ones)")
    pl.add_argument("--weeks", type=positive_int, default=None,
                    help="weeks to plan from the Monday after today (default: to the race week, or 8 "
                         "without a race; with a race it only shortens the plan)")
    pl.set_defaults(run=cmd_plan)
    pu = sub.add_parser("push", parents=[shared],
                        help="upload plan.json's future sessions to Garmin Connect and schedule them")
    pu.add_argument("--weeks", type=positive_int, default=None,
                    help="push only the first N plan weeks from today (default: every future session)")
    pu.add_argument("--dry-run", action="store_true",
                    help="write the payloads to <export>/push/ and call nothing")
    pu.set_defaults(run=cmd_push)
    args = ap.parse_args(argv)
    args.run(args)
