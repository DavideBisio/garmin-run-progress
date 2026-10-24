"""The plan generator: phases, volume, sessions, checks and fixes wired together (TC-10, standard library only).

Regenerate the golden plan after a reviewed change: UPDATE_GOLDEN=1 python -m unittest tests.test_planner
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import physiology, plan_io, planner, profile, render_md, templates  # noqa: E402
from garmin_plan.config import WEEKDAYS  # noqa: E402
from garmin_plan.terrain import workout_flat_km  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "plan_golden.md"
RULES = physiology.load_rules()
LIB = templates.load_templates()
TODAY = date(2024, 6, 5)                     # a Wednesday: plans start on Monday 2024-06-10
START = date(2024, 6, 10)
RACE = START + timedelta(weeks=15, days=6)   # Sunday of the 16th week
GENERATED = "2024-06-05T08:00:00"


def generic_profile(**kw):
    """The fixed generic runner of the golden files: VDOT 40, HR 190/50; at the novice level, whose
    numbers are 06 and 07's (one Q a week, L at most 45 % of it)."""
    vals = dict(hr_max=190, hr_rest=50, vdot=40.0, km_4w=0.0, km_12w=0.0, runs_per_week=0.0, longest_8w=0.0,
                volume_level="novice", quality_level="novice")
    vals.update(kw)
    return profile.Profile(**vals)


def hm_runner(**kw):
    """The golden plan's runner: 30 km a week, longest run 12 km, five days, hills on Thu and Sun,
    a half marathon in 16 weeks with a 1:43:30 goal (VDOT 43.4); intermediate on both axes."""
    vals = dict(km_4w=30.0, km_12w=28.0, runs_per_week=4.0, longest_8w=12.0,
                volume_level="intermediate", quality_level="intermediate",
                days=["tue", "wed", "thu", "sat", "sun"], long_run_day="sun", hill_days=["thu", "sun"],
                race={"date": RACE, "distance_m": 21097.5, "goal_s": 6210})
    vals.update(kw)
    return generic_profile(**vals)


def build(prof=None, runs=(), weeks=None):
    return planner.build_plan(prof or hm_runner(), list(runs), LIB, RULES, TODAY, weeks, generated=GENERATED)


def summary_run(day, km, hr=140):
    return {"date": f"{day} 07:00:00", "type": "running", "dist": km * 1000, "dur": km * 370, "avgHr": hr}


def steady_history(km=7):
    """A run of km every other day over the 6 weeks before TODAY."""
    return [summary_run((TODAY - timedelta(days=k)).isoformat(), km) for k in range(1, 43, 2)]


def day_km(d):
    """A day's km in the week's unit, as plan.md shows it (0.1 km): hill and trail sessions as
    flat-equivalent km."""
    w = plan_io.workout_from_dict(d["workout"])
    return round(workout_flat_km(w), 1) if w.climb_m_per_km else plan_io.shown_km(d["workout"])


def week_sum(wk):
    return round(sum(day_km(d) for d in wk["days"]), 1)


class Golden(unittest.TestCase):
    def test_golden_half_marathon(self):
        got = render_md.render_plan(build())
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.write_text(got, encoding="utf-8", newline="\n")
        self.assertEqual(got, GOLDEN.read_text(encoding="utf-8"))

    def test_shape(self):
        plan = build()
        self.assertEqual(plan["version"], 1)
        self.assertEqual(plan["generated"], GENERATED)
        weeks = plan["weeks"]
        self.assertEqual(len(weeks), 16)
        self.assertEqual(weeks[0]["start"], START.isoformat())
        self.assertEqual([w["phase"] for w in weeks], ["base"] * 6 + ["rt"] * 2 + ["tm"] * 6 + ["taper"] * 2)
        deloads = [i for i, w in enumerate(weeks) if w["deload"]]
        self.assertTrue(deloads)
        self.assertFalse({0, 6, 8, 14, 15} & set(deloads))             # no phase starts lighter; no taper deload
        rules = {w["rule"] for w in plan["warnings"]}
        self.assertIn("phases", rules)                                 # 16 of the 24 weeks
        self.assertIn("feasibility", rules)                            # 3.4 points in 16 weeks
        self.assertIn("acwr_skipped", rules)                           # no runs.json history
        for w in plan["warnings"] + [x for wk in weeks for x in wk["warnings"]]:
            self.assertEqual(set(w), {"rule", "detail", "action"})
            self.assertTrue(w["rule"] and w["detail"] and w["action"], w)
        # race week: nothing from race day on
        self.assertTrue(all(d["date"] < RACE.isoformat() for d in weeks[-1]["days"]))

    def test_weeks_are_sane(self):
        plan = build()
        taper_from = None
        for i, wk in enumerate(plan["weeks"]):
            with self.subTest(week=wk["start"]):
                kms = [d["workout"]["km"] for d in wk["days"]]
                self.assertTrue(all(0 < k < 30 for k in kms), kms)
                self.assertGreater(wk["target_km"], 10)
                self.assertLess(wk["target_km"], 60)
                self.assertEqual(sorted(d["date"] for d in wk["days"]), [d["date"] for d in wk["days"]])
                monday = date.fromisoformat(wk["start"])
                self.assertTrue(all(0 <= (date.fromisoformat(d["date"]) - monday).days < 7 for d in wk["days"]))
                slots = [d["slot"] for d in wk["days"]]
                self.assertLessEqual(slots.count("Q"), 1 if wk["deload"] or wk["phase"] == "taper" else 2)
                self.assertLessEqual(slots.count("L"), 1)
                if wk["phase"] == "taper" and taper_from is None:
                    taper_from = i
        peak = max(w["target_km"] for w in plan["weeks"][:taper_from])
        self.assertLess(plan["weeks"][-1]["target_km"], peak * 0.7)   # the race week is light
        self.assertLess(plan["weeks"][taper_from]["target_km"], peak)

    def test_deterministic(self):
        self.assertEqual(build(), build())

    def test_hill_swaps_follow_the_hill_days(self):
        plan = build()
        ids = {(d["date"], d["workout"]["id"]) for wk in plan["weeks"] for d in wk["days"]}
        hill_q = [dt for dt, i in ids if i == "hill_repeats"]
        hill_l = [dt for dt, i in ids if i in ("hilly_long", "trail_long")]
        self.assertTrue(hill_q)
        self.assertTrue(all(date.fromisoformat(dt).weekday() == 3 for dt in hill_q))      # Thu
        self.assertTrue(all(date.fromisoformat(dt).weekday() == 6 for dt in hill_l))      # Sun
        # a hilly long run is an hour or more at Z2-3, which isn't easy (Z1-2): at 35 km a week it
        # would leave about 71 % of the time easy, so the planner keeps the flat one and says why
        swaps = [w for wk in plan["weeks"] for w in wk["warnings"] if w["rule"] == "hill_swap"]
        self.assertTrue(swaps)
        self.assertFalse(hill_l)
        self.assertTrue(all("on sun" in w["detail"] and w["action"] == "kept the flat long run" for w in swaps))
        self.assertFalse([w for wk in plan["weeks"] for w in wk["warnings"]
                          if w["rule"] == "easy_share" and not w["action"].startswith("fixed: ")])
        # without the check in the way the swap stands: at the same time budget as the flat run
        week = next(wk for wk in plan["weeks"] if any(w["rule"] == "hill_swap" for w in wk["warnings"]))
        steady = next(d["workout"] for d in week["days"] if d["slot"] == "L")
        rules = json.loads(json.dumps(RULES))
        rules["checks"]["easy_share"] = 0.5
        loose = planner.build_plan(hm_runner(), [], LIB, rules, TODAY, None, generated=GENERATED)
        lw = next(wk for wk in loose["weeks"] if wk["start"] == week["start"])
        hilly = next(d["workout"] for d in lw["days"] if d["slot"] == "L")
        self.assertEqual(hilly["id"], "hilly_long")
        self.assertAlmostEqual(hilly["seconds"], steady["seconds"], delta=2)
        flat = build(hm_runner(hill_days=[]))
        self.assertFalse({d["workout"]["kind"] for wk in flat["weeks"] for d in wk["days"]} & {"hill", "trail"})


class Generator(unittest.TestCase):
    def test_no_race_defaults_to_eight_weeks(self):
        plan = build(generic_profile(km_4w=25.0, longest_8w=10.0))
        self.assertEqual(len(plan["weeks"]), 8)
        self.assertEqual([w["phase"] for w in plan["weeks"]], ["base"] * 4 + ["rt"] * 4)
        self.assertEqual(len(build(generic_profile(km_4w=25.0), weeks=3)["weeks"]), 3)

    def test_weeks_only_truncate(self):
        full = build()
        part = build(weeks=5)
        self.assertEqual(part["weeks"], full["weeks"][:5])

    def test_target_follows_the_curve(self):
        plan = build(generic_profile(km_4w=30.0, longest_8w=12.0, days=["tue", "thu", "sat", "sun"]))
        self.assertEqual([w["target_km"] for w in plan["weeks"][:4]], [30.0, 32.4, 34.8, 25.5])
        self.assertEqual([w["deload"] for w in plan["weeks"][:4]], [False, False, False, True])

    def test_manual_days_override(self):
        week = {"tue": {"id": "r_220", "variant": 1, "line": 'tue = "r_220:1"'},
                "sun": {"id": "steady_long", "variant": 2, "line": 'sun = "steady_long:2"'}}
        plan = build(generic_profile(km_4w=30.0, longest_8w=12.0, week=week), weeks=2)
        for wk in plan["weeks"]:
            by_day = {WEEKDAYS[date.fromisoformat(d["date"]).weekday()]: d for d in wk["days"]}
            self.assertEqual((by_day["tue"]["workout"]["id"], by_day["tue"]["slot"]), ("r_220", None))
            self.assertEqual(by_day["sun"]["workout"]["km"], 12.0)          # never trimmed by the fixer
            self.assertIn("thu", by_day)                                  # the other days are generated
            self.assertEqual(wk["target_km"], round(sum(plan_io.shown_km(d["workout"]) for d in wk["days"]), 1))
        with self.assertRaises(profile.ProfileError):
            build(generic_profile(week={"tue": {"id": "nope", "variant": 1, "line": 'tue = "nope:1"'}}))

    def test_history_feeds_the_load_ratio(self):
        runs = [summary_run((TODAY - timedelta(days=k)).isoformat(), 7) for k in range(1, 43, 2)]
        plan = build(generic_profile(km_4w=25.0, longest_8w=7.0), runs=runs)
        self.assertNotIn("acwr_skipped", {w["rule"] for w in plan["warnings"]})
        plan = build(generic_profile(km_4w=25.0, longest_8w=7.0), runs=runs[:5])
        self.assertIn("acwr_skipped", {w["rule"] for w in plan["warnings"]})

    def test_history_after_today_is_ignored(self):
        # runs dated after `today` (an export newer than --today) would count twice in the planned
        # weeks: once as history and once as projected load
        prof = generic_profile(km_4w=25.0, longest_8w=7.0)
        later = [summary_run((START + timedelta(days=k)).isoformat(), 15, hr=170) for k in range(-4, 14)]
        self.assertEqual(build(prof, runs=steady_history() + later), build(prof, runs=steady_history()))

    def test_planned_weeks_extend_the_history_load(self):
        prof = generic_profile(km_4w=25.0, longest_8w=7.0)
        rules = [[w["rule"] for w in wk["warnings"]] for wk in build(prof, runs=steady_history())["weeks"]]
        # week 3's 7:28 ratio takes in the history and the projected weeks 1-2: over 1.3, fixed
        self.assertIn("acwr_high", rules[2])
        # from week 5 the 28 days are planned weeks only: without their projected load each week
        # would be its own whole chronic load (a ratio of 4) and fail
        self.assertFalse([r for wk in rules[4:] for r in wk if r.startswith("acwr")], rules)
        # a lighter history makes the first week's ratio too high: the history counts
        light = build(prof, runs=steady_history(km=2))
        self.assertIn("acwr_high", [w["rule"] for w in light["weeks"][0]["warnings"]])
        self.assertNotIn("acwr_high", rules[0])

    def test_race_before_the_plan(self):
        with self.assertRaises(planner.PhaseError):
            build(hm_runner(race={"date": TODAY + timedelta(days=2), "distance_m": 5000, "goal_s": None}))


class Consistency(unittest.TestCase):
    """A generated week's heading adds up its days, and each day is what the split gave it."""

    def assert_weeks_add_up(self, plan):
        for wk in plan["weeks"]:
            with self.subTest(week=wk["start"]):
                self.assertEqual(wk["target_km"], week_sum(wk))

    def test_golden_weeks_add_up(self):
        self.assert_weeks_add_up(build())

    def test_q_leftover_without_a_warmup(self):
        # 10 weeks to a 10 km race, 12 km a week, longest run 6 km: the T + M block's second week
        # (11 km) holds a 5 km progression run and a 4.95 km L (45 %), and the 1.05 km left goes to
        # the Q day. The progression run has no warm-up: its easy block takes the km
        race = {"date": START + timedelta(weeks=9, days=6), "distance_m": 10000, "goal_s": None}
        plan = build(generic_profile(km_4w=12.0, longest_8w=6.0, days=["tue", "thu", "sun"], race=race,
                                     quality_level="intermediate"))          # M sessions from intermediate
        self.assert_weeks_add_up(plan)
        wk = plan["weeks"][7]
        q = next(d["workout"] for d in wk["days"] if d["slot"] == "Q")
        self.assertEqual((wk["phase"], q["id"], wk["target_km"]), ("tm", "progression", 11.0))
        self.assertEqual([d["workout"]["km"] for d in wk["days"]], [6.1, 4.9])
        self.assertEqual(q["steps"][0]["meters"], 4100)                 # the easy block: 3 km + 1.1 km

    def test_q_leftover_nowhere_to_go(self):
        # a Q template with neither a warm-up nor an easy main step can't take the leftover: the
        # week is the sum of its sessions and says so
        lib = json.loads(json.dumps(LIB))
        lib["progression"]["main"][0]["pace"] = "T"
        race = {"date": START + timedelta(weeks=9, days=6), "distance_m": 10000, "goal_s": None}
        prof = generic_profile(km_4w=12.0, longest_8w=6.0, days=["tue", "thu", "sun"], race=race,
                               quality_level="intermediate")
        plan = planner.build_plan(prof, [], lib, RULES, TODAY, None, generated=GENERATED)
        self.assert_weeks_add_up(plan)
        wk = plan["weeks"][7]
        self.assertEqual(wk["target_km"], 9.9)                          # 5 km Q + 4.9 km L
        self.assertIn("leftover", " ".join(w["detail"] for w in wk["warnings"] if w["rule"] == "split"))

    def test_manual_long_run_counts_as_the_longest(self):
        # a [week] long run on the long-run day replaces L: from week 9, when the profile's longest
        # run leaves the 8-week window, L's cap must still come from it, not collapse to the E
        # minimum and push the generated easy runs up
        week = {"sun": {"id": "steady_long", "variant": 3, "line": 'sun = "steady_long:3"'}}
        novice = {"volume_level": "novice", "quality_level": "novice"}      # one Q, L up to 45 %
        manual = build(hm_runner(week=week, **novice))["weeks"]
        plain = build(hm_runner(**novice))["weeks"]
        for i in range(1, 15):
            with self.subTest(week=manual[i]["start"]):
                easy = [d["workout"]["km"] for d in manual[i]["days"] if d["slot"] in ("E", "F")]
                plain_easy = [d["workout"]["km"] for d in plain[i]["days"] if d["slot"] in ("E", "F")]
                self.assertLessEqual(max(easy), max(plain_easy) + 0.5)       # no longer than without [week]
                self.assertAlmostEqual(manual[i]["target_km"], plain[i]["target_km"], delta=4.0)


class FixPath(unittest.TestCase):
    """The fixer end to end: what it did shows in plan.json and plan.md, and the week adds up."""

    def test_fixed_week(self):
        plan = build(generic_profile(km_4w=25.0, longest_8w=7.0), runs=steady_history())
        md = render_md.render_plan(plan)
        wk = plan["weeks"][2]
        fixed = [w for w in wk["warnings"] if w["action"].startswith("fixed: ")]
        self.assertEqual([w["rule"] for w in fixed], ["acwr_high"])
        w = fixed[0]
        self.assertRegex(w["detail"], r"^7:28-day load ratio \d\.\d\d, over 1\.3$")
        self.assertIn("L 1.0 km shorter (week 29.0 -> 28.0 km)", w["action"])
        self.assertIn(render_md.fmt_warning(w), md)
        self.assertIn(f"## Week of {wk['start']} - 28.0 km", md)
        self.assertEqual(wk["target_km"], week_sum(wk))

    def test_trimmed_and_dropped(self):
        # a light history under 30 km a week on five days: L is trimmed and F dropped
        prof = generic_profile(km_4w=30.0, longest_8w=12.0, days=["tue", "wed", "thu", "sat", "sun"])
        plan = build(prof, runs=steady_history(km=6), weeks=3)
        md = render_md.render_plan(plan)
        fixed = [(wk, w) for wk in plan["weeks"] for w in wk["warnings"] if w["action"].startswith("fixed: ")]
        self.assertTrue(fixed)
        for wk, w in fixed:
            with self.subTest(week=wk["start"], rule=w["rule"]):
                self.assertTrue(w["detail"])
                self.assertRegex(w["action"], r"L \d+\.\d km shorter")
                self.assertTrue(w["action"].endswith(f" -> {wk['target_km']:.1f} km)"), w["action"])
                self.assertIn(render_md.fmt_warning(w), md)
                self.assertEqual(wk["target_km"], week_sum(wk))

    def test_stopped_after_max_iter(self):
        rules = json.loads(json.dumps(RULES))
        rules["fix"]["max_iter"] = 1
        plan = planner.build_plan(generic_profile(km_4w=25.0, longest_8w=7.0), steady_history(), LIB, rules,
                                  TODAY, None, generated=GENERATED)
        wk = plan["weeks"][2]
        w = next(w for w in wk["warnings"] if w["rule"] == "acwr_high")
        self.assertEqual(w["action"], "stopped after 1 fixes (Q strides variant 4 -> 3); still failing")
        self.assertIn(render_md.fmt_warning(w), render_md.render_plan(plan))
        self.assertEqual(wk["target_km"], week_sum(wk))


class Render(unittest.TestCase):
    def test_headings_and_warnings(self):
        md = render_md.render_plan(build())
        self.assertIn("## Warnings", md)
        self.assertRegex(md, r"(?m)^## Week of 2024-06-10 - \d+\.\d km · Base$")
        self.assertRegex(md, r"(?m)^## Week of \S+ - \d+\.\d km · Base, deload$")
        self.assertRegex(md, r"(?m)^## Week of \S+ - \d+\.\d km · T \+ M$")
        self.assertRegex(md, r"(?m)^- \*\*feasibility\*\*: .+\. Planner: .+\.$")

    def test_manual_plan_is_unchanged(self):
        # a plan without phases or warnings (plan_io's manual schedule) renders as before
        w = {"tue": {"id": "easy", "variant": 1, "line": ""}}
        md = render_md.render_plan(plan_io.build_plan(generic_profile(week=w), LIB, RULES, TODAY, 1,
                                                      generated=GENERATED))
        self.assertNotIn("Warnings", md)
        self.assertRegex(md, r"(?m)^## Week of 2024-06-10 - 4\.0 km$")


class CliPlan(unittest.TestCase):
    def plan(self, d, *extra, check=True):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        return subprocess.run([sys.executable, "-m", "garmin_plan", "plan", "--export", d,
                               "--today", TODAY.isoformat(), *extra],
                              capture_output=True, text=True, encoding="utf-8", env=env, check=check)

    def test_generator(self):
        text = ('vdot = 40\nhr_max = 190\nhr_rest = 50\nkm_4w = 30\nlongest_8w = 12\n'
                'days = ["tue", "thu", "sat", "sun"]\nlong_run_day = "sun"\nhill_days = []\n'
                f'[race]\ndate = {RACE.isoformat()}\ndistance = "hm"\ngoal = "1:45:00"\n')
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text(text, encoding="utf-8")
            res = self.plan(d)
            plan = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))
            md = (Path(d) / "plan.md").read_text(encoding="utf-8")
            self.assertEqual(len(plan["weeks"]), 16)                    # to the race week
            self.assertIn("16 week(s)", res.stdout)
            self.assertIn("## Warnings", md)
            self.assertLessEqual({"L", "Q", "E"}, {d["slot"] for w in plan["weeks"] for d in w["days"]})
            self.plan(d, "--weeks", "3")
            self.assertEqual(len(json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))["weeks"]), 3)

    def test_week_overrides_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text('vdot = 40\n[week]\nthu = "cruise_tempo:2"\n', encoding="utf-8")
            self.plan(d, "--weeks", "2")
            plan = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))
            thu = [x for w in plan["weeks"] for x in w["days"] if date.fromisoformat(x["date"]).weekday() == 3]
            self.assertEqual([(x["workout"]["id"], x["workout"]["variant"], x["slot"]) for x in thu],
                             [("cruise_tempo", 2, None)] * 2)
            (Path(d) / "profile.toml").write_text('days = ["mon", "tue", "wed"]\nlong_run_day = "tue"\n',
                                                  encoding="utf-8")
            res = self.plan(d, check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertTrue(res.stderr.strip().splitlines()[-1].startswith("error: "), res.stderr)
        self.assertIn("48 h", res.stderr)
        self.assertNotIn("Traceback", res.stderr)


class CliReplan(unittest.TestCase):
    """make replan: plan (matched and adapted), then push unless --no-push or auto_push = false."""
    TEXT = 'vdot = 40\nhr_max = 190\nhr_rest = 50\nkm_4w = 30\nlongest_8w = 12\n'

    def replan(self, d, *extra, today=TODAY, check=True):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        return subprocess.run([sys.executable, "-m", "garmin_plan", "replan", "--export", d,
                               "--today", today.isoformat(), *extra],
                              capture_output=True, text=True, encoding="utf-8", env=env, check=check)

    def test_dry_run_pushes_the_new_plan(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text(self.TEXT, encoding="utf-8")
            res = self.replan(d, "--dry-run", "--weeks", "2")
            self.assertIn("Dry run", res.stdout)
            plan = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))
            files = sorted(p.name[:10] for p in (Path(d) / "push").glob("*.json"))
            self.assertEqual(files, sorted(x["date"] for w in plan["weeks"] for x in w["days"] if x["workout"]))

    def test_no_push(self):
        for extra, text in ((["--no-push"], self.TEXT), ([], self.TEXT + "auto_push = false\n")):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as d:
                (Path(d) / "profile.toml").write_text(text, encoding="utf-8")
                res = self.replan(d, "--dry-run", *extra)
                self.assertTrue((Path(d) / "plan.json").exists())
                self.assertFalse((Path(d) / "push").exists())
                self.assertIn("not pushed", res.stdout)

    def test_bad_auto_push(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text(self.TEXT + 'auto_push = "yes"\n', encoding="utf-8")
            res = self.replan(d, "--dry-run", check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("error: auto_push", res.stderr)

    def test_dry_run_leaves_a_day_already_run(self):
        # a run dated --today in runs.json: that day's session is not pushed again
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text(self.TEXT, encoding="utf-8")
            self.replan(d, "--no-push")
            plan = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))
            later = date.fromisoformat(next(x["date"] for w in plan["weeks"] for x in w["days"]
                                            if x["workout"] and x["slot"] == "E"))
            runs = {"format": "garmin-runs/1", "rhr": [], "hrv": [], "readiness": [],
                    "runs": [{"id": 5, "date": f"{later} 07:00:00", "type": "running", "dist": 6000, "dur": 2160,
                              "avgHr": 140}]}
            (Path(d) / "runs.json").write_text(json.dumps(runs), encoding="utf-8")
            res = self.replan(d, "--dry-run", "--weeks", "2", today=later)
            self.assertIn("Dry run", res.stdout)
            plan = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))
            ran = next(x for w in plan["weeks"] for x in w["days"] if x["date"] == later.isoformat())
            self.assertTrue(ran["workout"])
            files = sorted(p.name[:10] for p in (Path(d) / "push").glob("*.json"))
            self.assertTrue(files)
            self.assertNotIn(later.isoformat(), files)
            self.assertNotIn(later.isoformat(), res.stdout)
            self.assertEqual(files, sorted(x["date"] for w in plan["weeks"] for x in w["days"]
                                           if x["workout"] and x["date"] > later.isoformat()))

    def test_wellness_from_runs_json(self):
        # runs.json's HRV status reaches the adaptation: a low status today makes the next Q easy
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text(self.TEXT, encoding="utf-8")
            self.replan(d, "--no-push")
            later = TODAY + timedelta(days=7)
            runs = {"format": "garmin-runs/1", "runs": [], "rhr": [],
                    "hrv": [[later.isoformat(), "LOW"]], "readiness": []}
            (Path(d) / "runs.json").write_text(json.dumps(runs), encoding="utf-8")
            self.replan(d, "--no-push", today=later)
            plan = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual([(c["from"], c["to"], c["reason"]) for c in plan["changes"]],
                             [("Q", "E", "HRV status low")])
            self.assertIn("## What changed", (Path(d) / "plan.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
