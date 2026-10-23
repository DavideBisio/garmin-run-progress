"""Runner levels: per-level planning numbers, detection, layoff and promotion (TC-11, standard library only)."""
import copy
import itertools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import history, levels, physiology, plan_io, planner, profile, render_md, select, skeleton, templates  # noqa: E402,E501
from garmin_plan.config import WEEKDAYS  # noqa: E402

RULES = physiology.load_rules()
LEVELS = levels.load_levels()
LIB = templates.load_templates()
TODAY = date(2024, 6, 5)                     # a Wednesday: plans start on Monday 2024-06-10
GENERATED = "2024-06-05T08:00:00"
SECTIONS = ("volume", "split", "skeleton", "checks", "rotation")
HARD = {"L", "Q"}


def rules_at(vol, qual=None):
    return levels.params(LEVELS, vol, qual or vol, RULES)


def gap(a, b):
    """Days from a forward to b in a repeating week, 1..7."""
    return (WEEKDAYS.index(b) - WEEKDAYS.index(a)) % 7 or 7


def generic_profile(**kw):
    """The fixed generic runner of the golden files: VDOT 40, HR 190/50."""
    vals = dict(hr_max=190, hr_rest=50, vdot=40.0, km_4w=0.0, km_12w=0.0, runs_per_week=0.0, longest_8w=0.0)
    vals.update(kw)
    return profile.Profile(**vals)


def summary_run(day, km, hr=140, secs=None):
    """A run without streams: day is a date, secs defaults to 6 min/km."""
    return {"date": f"{day.isoformat()} 07:00:00", "type": "running", "dist": km * 1000,
            "dur": secs or km * 360, "avgHr": hr}


def stream_run(day, km, secs, hr=150):
    """A GPS run with a steady 10-second stream covering km in secs at a steady hr."""
    n = int(secs // 10) + 1
    return {"date": f"{day.isoformat()} 07:00:00", "type": "running", "dist": km * 1000, "dur": secs,
            "t": [i * 10 for i in range(n)], "d": [round(km * 1000 * i / (n - 1)) for i in range(n)],
            "hr": [hr] * n}


def training(weeks, per_week, km, end=TODAY, q_per_week=0):
    """`weeks` weeks of `per_week` easy runs of km up to the day before `end`, the first q_per_week
    runs of each week at 170 bpm (Z4 at 190/50) for 40 min."""
    out = []
    for w in range(weeks):
        for k in range(per_week):
            day = end - timedelta(days=7 * w + 1 + k * (7 // per_week))
            out.append(summary_run(day, km, 170 if k < q_per_week else 140))
    return sorted(out, key=lambda r: r["date"])


class Params(unittest.TestCase):
    def test_every_level_resolves(self):
        for vol in templates.LEVELS:
            for qual in templates.LEVELS:
                with self.subTest(volume=vol, quality=qual):
                    r = levels.params(LEVELS, vol, qual, RULES)
                    self.assertEqual(r["rotation"]["level"], qual)
                    for sec in SECTIONS:
                        self.assertIsInstance(r[sec], dict)
                    self.assertIn("ramp", r["volume"])
                    self.assertIn("long_share_cap", r["split"])
                    self.assertIn("easy_share", r["checks"])

    def test_daniels_values(self):
        # the roadmap 08 table: L cap share and minutes, block length, ramp, runs and Q a week
        want = {"beginner": (0.5, 60, 3, 0.06, 3, [3]), "novice": (0.45, 90, 4, 0.08, 4, [3]),
                "intermediate": (0.35, 120, 4, 0.08, 5, [3, 5]), "advanced": (0.25, 150, 4, 0.05, 7, [3, 4])}
        for level, (share, minutes, every, ramp, runs, q) in want.items():
            with self.subTest(level=level):
                r = rules_at(level)
                self.assertEqual((r["split"]["long_share_cap"], r["split"]["long_time_cap_min"],
                                  r["volume"]["deload_every"], r["volume"]["ramp"], r["skeleton"]["max_runs"],
                                  r["skeleton"]["q_from_days"]), (share, minutes, every, ramp, runs, q))
                # the same at every level: in rules.toml
                self.assertEqual((r["volume"]["deload"], r["volume"]["next_block_from_week"], r["volume"]["taper"],
                                  r["split"]["long_over_longest_km"], r["skeleton"]["f_min_days"],
                                  r["rotation"]["deload_lighter"]), (0.85, 2, [0.7, 0.5], 2, 4, 1))

    def test_axes(self):
        # the volume level sets the volume, the split and the run count; the quality level the Q days
        r = rules_at("advanced", "novice")
        self.assertEqual((r["split"]["long_share_cap"], r["skeleton"]["max_runs"]), (0.25, 7))
        self.assertEqual((r["skeleton"]["q_from_days"], r["rotation"]["level"]), ([3], "novice"))

    def test_overlay_leaves_other_sections_intact(self):
        before = copy.deepcopy(RULES)
        r = levels.params(LEVELS, "beginner", "advanced", RULES)
        self.assertEqual(RULES, before)                      # a copy: the shared rules never change
        for sec in ("paces", "bands", "phases", "caps", "fix", "feasibility"):
            self.assertEqual(r[sec], RULES[sec], sec)
        for phase in ("base", "rt", "it", "tm", "taper"):
            self.assertIn(phase, r["rotation"])

    def test_moved_numbers_left_rules_toml(self):
        self.assertNotIn("level", RULES["rotation"])
        self.assertNotIn("ramp", RULES["volume"])
        self.assertNotIn("long_share_cap", RULES.get("split", {}))
        self.assertNotIn("max_hard", RULES.get("checks", {}))

    def test_default_rules(self):
        self.assertEqual(levels.params(LEVELS, "novice", "novice"), levels.params(LEVELS, "novice", "novice", RULES))

    def test_unknown_level(self):
        with self.assertRaises(ValueError):
            levels.params(LEVELS, "elite", "novice", RULES)


class Overrides(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "profile.toml"
            p.write_text(text, encoding="utf-8")
            return profile.load_profile(p, [], [], TODAY)

    def test_set_in_profile(self):
        p = self.load('volume_level = "novice"\nquality_level = "Advanced"\n')
        self.assertEqual((p.volume_level, p.quality_level), ("novice", "advanced"))
        self.assertEqual((p.sources["volume_level"], p.sources["quality_level"]), ("set", "set"))

    def test_rejected(self):
        for text in ('volume_level = "elite"\n', "quality_level = 3\n", 'quality_level = ""\n'):
            with self.subTest(text=text), self.assertRaisesRegex(profile.ProfileError, "beginner, novice"):
                self.load(text)



def stats(**kw):
    """detect()'s input for a runner with 6 months of history and nothing else."""
    out = dict(km_4w=0.0, km_12w=0.0, runs_per_week=0.0, longest_8w=0.0, consistency=0.0, history_days=180,
               vdot=None, q_8w=0)
    out.update(kw)
    return out


class Detect(unittest.TestCase):
    FIXTURES = {
        # level: the synthetic history's numbers
        "beginner": stats(km_4w=8, km_12w=6, runs_per_week=2, longest_8w=4, consistency=0.4),
        "novice": stats(km_4w=20, km_12w=18, runs_per_week=3, longest_8w=8, consistency=0.8, vdot=33.0),
        "intermediate": stats(km_4w=40, km_12w=38, runs_per_week=4.5, longest_8w=14, consistency=0.9,
                              vdot=42.0, q_8w=4),
        "advanced": stats(km_4w=75, km_12w=70, runs_per_week=6.5, longest_8w=24, consistency=1.0, history_days=400,
                          vdot=55.0, q_8w=12),
    }

    def test_one_fixture_per_level(self):
        for level, s in self.FIXTURES.items():
            with self.subTest(level=level):
                vol, qual, why = levels.detect(s, LEVELS)
                self.assertEqual((vol, qual), (level, level))
                self.assertEqual(set(why), {"volume", "quality"})

    def test_reasons(self):
        _, _, why = levels.detect(stats(km_4w=16, km_12w=17, runs_per_week=3, longest_8w=8, consistency=0.8,
                                        vdot=40.4, q_8w=3), LEVELS)
        self.assertEqual(levels.describe("novice", "intermediate", why),
                         "volume: novice (16 km/wk over 4 wk); quality: intermediate (VDOT 40, 3 Q sessions in 8 wk)")

    def test_twelve_week_gate(self):
        # 4 weeks at a level's volume count when the 12-week average is at least half of it: a
        # recent ramp from 8 to 18 km a week is novice...
        vol, _, why = levels.detect(stats(km_4w=18, km_12w=8, runs_per_week=2.2, longest_8w=14, consistency=0.5),
                                    LEVELS)
        self.assertEqual((vol, why["volume"]), ("novice", "18 km/wk over 4 wk"))
        # ...a single big month after a quiet quarter isn't
        vol, _, why = levels.detect(stats(km_4w=40, km_12w=12, runs_per_week=4, longest_8w=12, consistency=0.9),
                                    LEVELS)
        self.assertEqual(vol, "novice")
        self.assertEqual(why["volume"], "40 km/wk over 4 wk; not intermediate: 12 km/wk over 12 wk (needs 15)")

    def test_split_axis_runner(self):
        # a big aerobic base and no speed work: intermediate volume, novice sessions
        vol, qual, why = levels.detect(stats(km_4w=45, km_12w=44, runs_per_week=5, longest_8w=16, consistency=0.9,
                                             vdot=36.0), LEVELS)
        self.assertEqual((vol, qual), ("intermediate", "novice"))
        self.assertIn("VDOT 36", why["quality"])

    def test_gates(self):
        # 35 km in two runs a week: novice, and the reason says why not intermediate
        vol, _, why = levels.detect(stats(km_4w=35, km_12w=35, runs_per_week=2, longest_8w=17, consistency=0.9),
                                    LEVELS)
        self.assertEqual(vol, "novice")
        self.assertIn("2 runs/wk", why["volume"])
        # a fast runner with no hard sessions lately stays novice by quality
        _, qual, why = levels.detect(stats(vdot=52.0, q_8w=0), LEVELS)
        self.assertEqual(qual, "novice")
        self.assertIn("0 Q sessions", why["quality"])

    def test_new_runner(self):
        vol, qual, why = levels.detect(stats(km_4w=None, km_12w=None, runs_per_week=None, longest_8w=None,
                                             consistency=None, history_days=0), LEVELS)
        self.assertEqual((vol, qual), ("beginner", "beginner"))
        self.assertIn("under 4 weeks", why["volume"])
        self.assertIn("no VDOT", why["quality"])


class Layoff(unittest.TestCase):
    def test_table(self):
        self.assertEqual(levels.layoff(0, LEVELS), (1.0, 1.0))
        self.assertEqual(levels.layoff(5, LEVELS), (1.0, 1.0))
        self.assertEqual(levels.layoff(28, LEVELS), (0.935, 0.5))
        v, vol = levels.layoff(42, LEVELS)
        self.assertEqual(vol, 0.33)
        self.assertTrue(0.86 < v < 0.935, v)
        self.assertEqual(levels.layoff(365, LEVELS), (0.8, 0.33))
        got = [levels.layoff(d, LEVELS) for d in range(0, 120)]
        for a, b in zip(got, got[1:]):
            self.assertLessEqual(b[0], a[0])
            self.assertLessEqual(b[1], a[1])

    def test_default_levels(self):
        self.assertEqual(levels.layoff(42), levels.layoff(42, LEVELS))


class HistoryStats(unittest.TestCase):
    def test_consistency(self):
        self.assertEqual(history.recent_stats(training(12, 3, 6), TODAY)["consistency"], 1.0)
        self.assertEqual(history.recent_stats(training(12, 1, 6), TODAY)["consistency"], 0.0)
        runs = training(6, 2, 6) + training(6, 1, 6, end=TODAY - timedelta(weeks=6))
        self.assertEqual(history.recent_stats(runs, TODAY)["consistency"], 0.5)

    def test_q_sessions(self):
        runs = training(10, 4, 8, q_per_week=1)
        self.assertEqual(history.q_sessions(runs, TODAY, 190, 50), 8)               # the last 8 weeks
        z4 = physiology.hr_zones(190, 50)[2]
        day = TODAY - timedelta(days=2)
        self.assertEqual(history.q_sessions([stream_run(day, 3, 900, z4)], TODAY, 190, 50), 1)    # 15 min in Z4
        self.assertEqual(history.q_sessions([stream_run(day, 1, 300, z4)], TODAY, 190, 50), 0)    # 5 min
        self.assertEqual(history.q_sessions([summary_run(day, 3, z4 - 1, 900)], TODAY, 190, 50), 0)

    def test_days_off_and_volume_before(self):
        runs = training(10, 5, 10, end=TODAY - timedelta(days=42))
        s = history.recent_stats(runs, TODAY)
        self.assertEqual(s["days_off"], 43)
        self.assertEqual(s["km_4w"], 0.0)
        self.assertAlmostEqual(s["km_before"], 50.0)
        self.assertAlmostEqual(s["runs_before"], 5.0)


class ProfileLevels(unittest.TestCase):
    def load(self, text, runs):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "profile.toml"
            p.write_text(text, encoding="utf-8")
            return profile.load_profile(p, runs, [], TODAY)

    def test_detected(self):
        runs = training(12, 3, 6, q_per_week=1) + [stream_run(TODAY - timedelta(days=10), 5, 1440)]
        prof = self.load("hr_max = 190\nhr_rest = 50\n", runs)
        self.assertEqual((prof.volume_level, prof.quality_level), ("novice", "intermediate"))
        self.assertEqual((prof.sources["volume_level"], prof.sources["quality_level"]), ("derived", "derived"))
        self.assertRegex(levels.describe(prof.volume_level, prof.quality_level, prof.level_reasons),
                         r"^volume: novice \(\d+ km/wk over 4 wk\); quality: intermediate \(VDOT 4\d, \d+ Q sessions "
                         r"in 8 wk\)$")

    def test_override_wins(self):
        prof = self.load('hr_max = 190\nhr_rest = 50\nvolume_level = "advanced"\n', training(12, 3, 6))
        self.assertEqual((prof.volume_level, prof.sources["volume_level"]), ("advanced", "set"))
        self.assertEqual(prof.level_reasons["volume"], "set in profile.toml")
        self.assertEqual(prof.quality_level, "beginner")              # no VDOT: still detected

    def test_return_after_six_weeks_off(self):
        # 50 km a week on 5 days and a 5 km effort, then 6 weeks off: the plan restarts at 33 % of the
        # volume and a lower VDOT, at the level that volume matches
        end = TODAY - timedelta(days=42)
        runs = sorted(training(20, 5, 10, end=end, q_per_week=1) + [stream_run(end - timedelta(days=8), 5, 1320)],
                      key=lambda r: r["date"])
        prof = self.load("hr_max = 190\nhr_rest = 50\n", runs)
        self.assertEqual(prof.layoff["days_off"], 43)
        self.assertAlmostEqual(prof.km_4w, prof.layoff["km_before"] * 0.33)
        effort = physiology.vdot(5000, 1320)
        self.assertAlmostEqual(prof.vdot, effort * levels.layoff(43, LEVELS)[0], places=6)
        self.assertEqual(prof.volume_level, "novice")
        self.assertIn("43 days off", prof.level_reasons["volume"])
        self.assertIn("days off", prof.sources["km_4w"])
        fresh = self.load("hr_max = 190\nhr_rest = 50\n", training(20, 5, 10, q_per_week=1))
        self.assertEqual(fresh.volume_level, "intermediate")
        self.assertIsNone(fresh.layoff)

    def test_new_runner(self):
        prof = self.load("", [])
        self.assertEqual((prof.volume_level, prof.quality_level), ("beginner", "beginner"))
        self.assertEqual(prof.sources["volume_level"], "default")

    def test_profile_command_prints_levels(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
            res = subprocess.run([sys.executable, "-m", "garmin_plan", "profile", "--export", d,
                                  "--today", TODAY.isoformat()], capture_output=True, text=True, env=env, check=True)
        self.assertIn("Levels: volume: beginner (under 4 weeks of runs); quality: beginner (no VDOT", res.stdout)


class Placement(unittest.TestCase):
    def assert_rules(self, slots, days):
        L = next(d for d, s in slots.items() if s == "L")
        for q in (d for d, s in slots.items() if s == "Q"):
            self.assertGreaterEqual(min(gap(L, q), gap(q, L)), 2)                  # 48 h from L
        hard = [d for d in slots if slots[d] in HARD]
        for a, b in itertools.permutations(hard, 2):
            self.assertNotEqual(gap(a, b), 1)                                      # no back-to-back hard days
        self.assertTrue(set(slots) <= set(days))

    def test_run_count_cap(self):
        for level, n in (("beginner", 3), ("novice", 4), ("intermediate", 5), ("advanced", 7)):
            with self.subTest(level=level):
                slots = skeleton.place_slots(WEEKDAYS, "sun", rules_at(level))
                self.assertEqual(len(slots), n)
                self.assertEqual(slots["sun"], "L")
                self.assert_rules(slots, WEEKDAYS)
        # the days kept are spread out: no two runs on consecutive days at 3 a week
        slots = skeleton.place_slots(WEEKDAYS, "sun", rules_at("beginner"))
        self.assertFalse([(a, b) for a, b in itertools.permutations(slots, 2) if gap(a, b) == 1])

    def test_q_count(self):
        r = rules_at("intermediate")
        self.assertEqual([skeleton.q_count(n, r) for n in range(1, 8)], [0, 0, 1, 1, 2, 2, 2])
        r = rules_at("advanced")
        self.assertEqual([skeleton.q_count(n, r) for n in range(1, 8)], [0, 0, 1, 2, 2, 2, 2])

    def test_two_q_days(self):
        r = rules_at("intermediate")
        two = 0
        for days in itertools.combinations(WEEKDAYS, 5):
            for long_day in days:
                with self.subTest(days=days, long_day=long_day):
                    try:
                        slots = skeleton.place_slots(list(days), long_day, r)
                    except skeleton.SkeletonError:
                        continue
                    self.assert_rules(slots, days)
                    qs = [d for d, s in slots.items() if s == "Q"]
                    L = next(d for d, s in slots.items() if s == "L")
                    if len(qs) == 2:
                        two += 1
                        continue
                    # one Q only when no pair of days fits the rules with L there
                    ok = [d for d in days if d != L and min(gap(L, d), gap(d, L)) >= 2]
                    self.assertFalse([(a, b) for a, b in itertools.combinations(ok, 2)
                                      if gap(a, b) != 1 and gap(b, a) != 1], slots)
        self.assertGreater(two, 30)

    def test_three_q_never_fit(self):
        # Q x 3 + L are four hard days: a 7-day cycle holds at most 3 without two in a row, so the
        # skeleton places as many Q as fit
        r = copy.deepcopy(rules_at("advanced"))
        r["skeleton"]["q_from_days"] = [3, 4, 7]
        self.assertEqual(skeleton.q_count(7, r), 3)
        slots = skeleton.place_slots(WEEKDAYS, "sun", r)
        self.assertEqual(sum(s == "Q" for s in slots.values()), 2)
        self.assert_rules(slots, WEEKDAYS)

    def test_three_week_blocks(self):
        self.assertEqual(rules_at("beginner")["volume"]["deload_every"], 3)
        deloads = [2, 5, 8]
        self.assertEqual([select.block_week(i, deloads, 3) for i in range(9)], [1, 2, 3] * 3)
        # build weeks take the rotation's first rows, the deload its last
        q = [select.rotation("rt", select.block_week(i, deloads, 3), "Q", RULES, deload=i in deloads, library=LIB,
                             level="intermediate") for i in range(3)]
        self.assertEqual(q, ["r_300", "cruise_tempo", "cruise_tempo"])


def build(prof, runs=(), weeks=None, level_data=None):
    return planner.build_plan(prof, list(runs), LIB, RULES, TODAY, weeks, generated=GENERATED,
                              level_data=level_data)


class Plans(unittest.TestCase):
    RACE = {"date": date(2024, 9, 29), "distance_m": 21097.5, "goal_s": None}

    def test_two_q_a_week(self):
        prof = generic_profile(km_4w=40.0, longest_8w=14.0, days=["tue", "wed", "thu", "sat", "sun"], race=self.RACE)
        plan = build(prof)
        for wk in plan["weeks"]:
            slots = [d["slot"] for d in wk["days"]]
            with self.subTest(week=wk["start"]):
                if wk["deload"] or wk["phase"] == "taper":
                    self.assertLessEqual(slots.count("Q"), 1)
                else:
                    self.assertEqual(slots.count("Q"), 2)
                rules = [w["rule"] for w in wk["warnings"]]
                self.assertNotIn("hard_count", rules)
                self.assertNotIn("hard_adjacent", rules)
        ids = [d["workout"]["id"] for wk in plan["weeks"] if not wk["deload"] for d in wk["days"] if d["slot"] == "Q"]
        self.assertIn("cruise_tempo", ids)

    def test_run_cap_and_three_week_blocks(self):
        prof = generic_profile(km_4w=10.0, longest_8w=5.0, days=WEEKDAYS, volume_level="beginner",
                               quality_level="novice")
        plan = build(prof, weeks=8)
        self.assertEqual([i for i, wk in enumerate(plan["weeks"]) if wk["deload"]], [2, 5])
        self.assertTrue(all(len(wk["days"]) <= 3 for wk in plan["weeks"]))
        prof = generic_profile(km_4w=20.0, longest_8w=8.0, days=WEEKDAYS, volume_level="novice", quality_level="novice")
        self.assertTrue(all(len(wk["days"]) <= 4 for wk in build(prof, weeks=8)["weeks"]))

    def test_q_that_dont_fit_are_said(self):
        data = copy.deepcopy(LEVELS)
        data["skeleton"]["q_from_days"]["advanced"] = [3, 4, 7]
        prof = generic_profile(km_4w=70.0, longest_8w=22.0, days=WEEKDAYS, volume_level="advanced",
                               quality_level="advanced")
        plan = build(prof, weeks=4, level_data=data)
        w = [w for w in plan["warnings"] if w["rule"] == "skeleton"]
        self.assertEqual(len(w), 1)
        self.assertIn("3 Q", w[0]["detail"])

    def test_levels_in_plan_json_and_md(self):
        prof = generic_profile(km_4w=20.0, longest_8w=8.0, volume_level="novice", quality_level="intermediate",
                               level_reasons={"volume": "20 km/wk over 4 wk",
                                              "quality": "VDOT 40, 3 Q sessions in 8 wk"})
        plan = build(prof, weeks=2)
        self.assertEqual(plan["levels"], {"volume": "novice", "quality": "intermediate",
                                          "reasons": {"volume": "20 km/wk over 4 wk",
                                                      "quality": "VDOT 40, 3 Q sessions in 8 wk"}})
        md = render_md.render_plan(plan)
        self.assertIn("Runner levels: volume: novice (20 km/wk over 4 wk); quality: intermediate "
                      "(VDOT 40, 3 Q sessions in 8 wk).", md)
        self.assertNotIn("starting point", md)
        adv = build(generic_profile(km_4w=70.0, longest_8w=22.0, volume_level="advanced", quality_level="advanced"),
                    weeks=2)
        self.assertIn("starting point to edit", render_md.render_plan(adv))
        self.assertEqual(json.loads(json.dumps(plan)), plan)

    def test_hash_follows_the_levels(self):
        h = plan_io.profile_hash(generic_profile(), RULES)
        self.assertNotEqual(h, plan_io.profile_hash(generic_profile(volume_level="novice"), RULES))
        self.assertNotEqual(h, plan_io.profile_hash(generic_profile(quality_level="novice"), RULES))


def steps_of(workout):
    for s in workout["steps"]:
        yield from (s["steps"] if s["type"] == "repeat" else [s])


def beginner(**kw):
    vals = dict(vdot=30.0, km_4w=6.0, longest_8w=3.0, days=["tue", "thu", "sat"], long_run_day="sat",
                volume_level="beginner", quality_level="beginner")
    vals.update(kw)
    return generic_profile(**vals)


class BeginnerPlans(unittest.TestCase):
    def setUp(self):
        self.plan = build(beginner(), weeks=12)

    def test_volume_in_minutes(self):
        for wk in self.plan["weeks"]:
            with self.subTest(week=wk["start"]):
                self.assertEqual(wk["unit"], "min")
                self.assertIsInstance(wk["target_min"], int)
                self.assertEqual(wk["target_min"], sum(int(d["workout"]["seconds"] / 60 + 0.5) for d in wk["days"]))
                self.assertEqual(wk["target_km"], round(sum(plan_io.shown_km(d["workout"]) for d in wk["days"]), 1))
                self.assertTrue(all(18 <= d["workout"]["seconds"] / 60 <= 75 for d in wk["days"]), wk["days"])
        mins = [wk["target_min"] for wk in self.plan["weeks"] if not wk["deload"]]
        self.assertGreater(mins[-1], mins[0])                       # the volume grows
        deloads = [i for i, wk in enumerate(self.plan["weeks"]) if wk["deload"]]
        self.assertEqual(deloads[:2], [2, 5])                       # every 3rd week, moved off phase starts
        self.assertTrue(all(2 <= b - a <= 4 for a, b in zip(deloads, deloads[1:])), deloads)
        md = render_md.render_plan(self.plan)
        self.assertRegex(md, r"(?m)^## Week of 2024-06-10 - \d+ min \(~\d+\.\d km\) · Base$")
        self.assertRegex(md, r"(?m)^### Tue 2024-06-11 · .+ - \d+ min \(~\d+\.\d km\)$")

    def test_no_pace_targets(self):
        for wk in self.plan["weeks"]:
            for d in wk["days"]:
                for s in steps_of(d["workout"]):
                    with self.subTest(day=d["date"], step=s["label"]):
                        self.assertIsNone(s["pace_s_per_km"])
                        self.assertTrue(s["effort"] or s["zone"] == "jog", s)

    def test_run_walk_ladder(self):
        # the easy runs climb the run/walk ladder, one step a build week, from 8 x (2 min + 1 min walk)
        first = next(d["workout"] for d in self.plan["weeks"][0]["days"] if d["slot"] == "E")
        self.assertEqual((first["id"], first["variant"]), ("run_walk", 1))
        rep = next(s for s in first["steps"] if s["type"] == "repeat")
        self.assertEqual([(x["label"], x["value"]) for x in rep["steps"]], [("Run", 120), ("Walk", 60)])
        # a week's longest run takes the week's variant (a short easy run may step one back)
        top = [max(d["workout"]["variant"] for d in wk["days"] if d["workout"]["id"] == "run_walk")
               for wk in self.plan["weeks"] if any(d["workout"]["id"] == "run_walk" for d in wk["days"])]
        self.assertEqual(top, sorted(top))
        self.assertEqual(top[-1], len(LIB["run_walk"]["ladder"]))
        last = LIB["run_walk"]["ladder"][-1]
        self.assertEqual((last["n"], last["c"]), (0, 1800))                    # 30 minutes continuous
        later = {d["workout"]["id"] for d in self.plan["weeks"][-1]["days"]}
        self.assertTrue(later & {"easy_time", "long_time"}, later)               # past the ladder

    def test_time_trial(self):
        tts = [(i, d) for i, wk in enumerate(self.plan["weeks"]) for d in wk["days"] if d["workout"]["kind"] == "tt"]
        self.assertEqual(len(tts), 1)
        i, d = tts[0]
        self.assertIn(i, (1, 2, 3))                                             # weeks 2-4
        self.assertEqual((d["workout"]["id"], d["slot"]), ("time_trial", "Q"))
        self.assertNotIn("hard_count", [w["rule"] for w in self.plan["weeks"][i]["warnings"]])
        # a beginner with two run days has no Q day: the time trial takes an easy day
        two = build(beginner(days=["wed", "sat"]), weeks=4)
        self.assertEqual([d["workout"]["id"] for d in two["weeks"][2]["days"]].count("time_trial"), 1)
        # no time trial for a runner with a quality level
        nov = build(beginner(quality_level="novice"), weeks=6)
        self.assertFalse([d for wk in nov["weeks"] for d in wk["days"] if d["workout"]["kind"] == "tt"])

    def test_time_trial_fills_vdot(self):
        day = next(date.fromisoformat(d["date"]) for wk in self.plan["weeks"] for d in wk["days"]
                   if d["workout"]["kind"] == "tt")
        runs = sorted(training(5, 3, 3, end=day) + [stream_run(day, 2, 660)], key=lambda r: r["date"])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.toml"
            path.write_text("hr_max = 190\nhr_rest = 50\n", encoding="utf-8")
            prof = profile.load_profile(path, runs, [], day + timedelta(days=1), plan=self.plan)
            self.assertAlmostEqual(prof.vdot, physiology.vdot(2000, 660), places=6)
            self.assertEqual((prof.sources["vdot"], prof.vdot_from), ("derived", ("2 km time trial", day.isoformat())))
            self.assertNotEqual(prof.quality_level, "beginner")
            # the same effort on another day, or no plan, isn't a time trial
            moved = [dict(r, date=f"{day + timedelta(days=1)} 07:00:00") if "t" in r else r for r in runs]
            other = profile.load_profile(path, moved, [], day + timedelta(days=2), plan=self.plan)
            self.assertEqual(other.sources["vdot"], "default")
            self.assertEqual(profile.load_profile(path, runs, [], day + timedelta(days=1)).sources["vdot"], "default")

    def test_unit(self):
        km = build(beginner(unit="km"), weeks=2)
        self.assertEqual([wk["unit"] for wk in km["weeks"]], ["km", "km"])
        self.assertNotIn("target_min", km["weeks"][0])
        mins = build(generic_profile(km_4w=20.0, longest_8w=8.0, volume_level="novice", quality_level="novice",
                                     unit="min"), weeks=2)
        self.assertEqual(mins["weeks"][0]["unit"], "min")
        self.assertNotEqual(plan_io.profile_hash(beginner(), RULES), plan_io.profile_hash(beginner(unit="km"), RULES))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.toml"
            path.write_text('unit = "min"\n', encoding="utf-8")
            self.assertEqual(profile.load_profile(path, [], [], TODAY).unit, "min")
            path.write_text('unit = "miles"\n', encoding="utf-8")
            with self.assertRaisesRegex(profile.ProfileError, "unit"):
                profile.load_profile(path, [], [], TODAY)

    def test_cli_summary_in_minutes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text('volume_level = "beginner"\nquality_level = "beginner"\n',
                                                  encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
            res = subprocess.run([sys.executable, "-m", "garmin_plan", "plan", "--export", d, "--today",
                                  TODAY.isoformat(), "--weeks", "3"],
                                 capture_output=True, text=True, env=env, check=True)
            self.assertRegex(res.stdout, r"3 week\(s\) from 2024-06-10, \d+ min \(~\d+\.\d km\)")
            plan = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["version"], 1)



def weeks_at(*kms, runs=4):
    """history.recent_stats' "weeks": the last full weeks, oldest first."""
    return [{"km": float(k), "runs": runs} for k in kms]


def promote_stats(*kms, runs=4, **kw):
    s = stats(km_4w=sum(kms[-4:]) / 4, km_12w=sum(kms[-4:]) / 4, runs_per_week=runs, longest_8w=15,
              consistency=1.0, vdot=40.0, q_8w=4, weeks=weeks_at(*kms, runs=runs))
    s.update(kw)
    return s


NOVICE = {"volume": "novice", "quality": "novice"}


class Promotion(unittest.TestCase):
    def test_only_at_a_block_boundary(self):
        s = promote_stats(35, 35, 36, 34)          # 4 weeks over intermediate's 30 km + 10 %, 4 runs
        got, notes = levels.promote(NOVICE, s, LEVELS, block_start=False)
        self.assertEqual(got, NOVICE)
        self.assertTrue(any(n.startswith("volume: novice until the next block") for n in notes), notes)
        got, notes = levels.promote(NOVICE, s, LEVELS, block_start=True)
        self.assertEqual(got, {"volume": "intermediate", "quality": "intermediate"})
        self.assertTrue(any(n.startswith("volume: novice -> intermediate") for n in notes), notes)

    def test_four_weeks_needed(self):
        got, _ = levels.promote(NOVICE, promote_stats(35, 35, 28, 36), LEVELS, block_start=True)
        self.assertEqual(got["volume"], "novice")
        got, _ = levels.promote(NOVICE, promote_stats(35, 35, 35, 35, runs=2), LEVELS, block_start=True)
        self.assertEqual(got["volume"], "novice")                         # the frequency too

    def test_hysteresis(self):
        # detection says intermediate from 30 km a week; promotion needs 10 % more, and a level never
        # drops without a break: re-planned every week across the boundary, the level doesn't flap
        levels_seen, cur = [], dict(NOVICE)
        kms = [29, 31, 32, 29, 31, 32, 31, 30, 29, 31, 32, 31]
        for i in range(4, len(kms) + 1):
            cur, _ = levels.promote(cur, promote_stats(*kms[:i], q_8w=0), LEVELS, block_start=True)
            levels_seen.append(cur["volume"])
        self.assertEqual(set(levels_seen), {"novice"})
        cur = {"volume": "intermediate", "quality": "intermediate"}
        for i in range(4, len(kms) + 1):
            cur, _ = levels.promote(cur, promote_stats(*[k - 8 for k in kms[:i]]), LEVELS, block_start=True)
            self.assertEqual(cur["volume"], "intermediate")

    def test_one_level_a_block(self):
        got, _ = levels.promote({"volume": "beginner", "quality": "beginner"}, promote_stats(70, 70, 70, 70, runs=6),
                                LEVELS, block_start=True)
        self.assertEqual(got, {"volume": "novice", "quality": "novice"})

    def test_demotion_after_a_layoff(self):
        cur = {"volume": "intermediate", "quality": "intermediate"}
        lay = {"days_off": 43, "km_before": 45.0, "volume_factor": 0.33}
        s = promote_stats(0, 0, 0, 0, km_4w=45 * 0.33, km_12w=45 * 0.33, runs_per_week=5, consistency=0.5,
                          vdot=38.5, q_8w=1, layoff=lay)
        got, notes = levels.promote(cur, s, LEVELS, block_start=False)        # a restart: right away
        self.assertEqual(got, {"volume": "beginner", "quality": "novice"})
        self.assertTrue(any("43 days off" in n for n in notes), notes)
        # without a break, the same low weeks keep the level
        got, _ = levels.promote(cur, promote_stats(10, 10, 10, 10), LEVELS, block_start=True)
        self.assertEqual(got, cur)

    def test_compliance(self):
        s = promote_stats(35, 35, 36, 34)
        got, notes = levels.promote(NOVICE, s, LEVELS, block_start=True, compliance=0.5)
        self.assertEqual(got, NOVICE)
        self.assertTrue(any("50 % of the planned Q" in n for n in notes), notes)
        got, _ = levels.promote(NOVICE, s, LEVELS, block_start=True, compliance=0.8)
        self.assertEqual(got["volume"], "intermediate")
        _, notes = levels.promote(NOVICE, s, LEVELS, block_start=True)
        self.assertTrue(any("not checked" in n for n in notes), notes)

    def test_block_start(self):
        plan = build(generic_profile(km_4w=20.0, longest_8w=8.0, volume_level="novice", quality_level="novice"), weeks=8)
        starts = [date.fromisoformat(wk["start"]) for wk in plan["weeks"]]
        self.assertTrue(levels.block_start(plan, starts[0]))
        self.assertFalse(levels.block_start(plan, starts[1]))
        self.assertTrue(levels.block_start(plan, starts[4]))                  # after the week-4 deload
        self.assertTrue(levels.block_start(plan, starts[-1] + timedelta(weeks=1)))   # past the plan

    def test_profile_keeps_or_promotes_the_last_plan_levels(self):
        prev = build(generic_profile(km_4w=20.0, longest_8w=8.0, volume_level="novice", quality_level="novice"),
                     weeks=8)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.toml"
            path.write_text("hr_max = 190\nhr_rest = 50\n", encoding="utf-8")
            mid = date.fromisoformat(prev["weeks"][1]["start"]) - timedelta(days=2)       # before week 3
            kept = profile.load_profile(path, training(12, 4, 9, end=mid), [], mid, plan=prev)   # 36 km a week
            self.assertEqual(kept.volume_level, "novice")                    # mid-block: it waits
            self.assertIn("novice until the next block, then intermediate", kept.level_reasons["volume"])
            at = date.fromisoformat(prev["weeks"][4]["start"]) - timedelta(days=2)        # the next block
            up = profile.load_profile(path, training(12, 4, 9, end=at), [], at, plan=prev)
            self.assertEqual(up.volume_level, "intermediate")
            self.assertIn("novice -> intermediate", up.level_reasons["volume"])


BEGINNER_TOML = ('hr_max = 190\nhr_rest = 50\nvolume_level = "beginner"\nquality_level = "beginner"\n'
                 'days = ["tue", "thu", "sat"]\nlong_run_day = "sat"\n'
                 '[race]\ndate = 2024-09-29\ndistance = "10k"\n')        # a race keeps the phases put
DETECTED_TOML = "hr_max = 190\nhr_rest = 50\n"


def replan(text, runs, today, plan=None, weeks=8):
    """(profile, plan.json dict) of `make plan` on `today` with `plan` the plan.json on disk."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "profile.toml"
        path.write_text(text, encoding="utf-8")
        prof = profile.load_profile(path, list(runs), [], today, plan=plan)
    out = planner.build_plan(prof, list(runs), LIB, RULES, today, weeks, generated=GENERATED)
    return prof, json.loads(json.dumps(out))


def tt_dates(plan):
    return [d["date"] for wk in plan["weeks"] for d in wk["days"] if d["workout"]["kind"] == "tt"]


def weekday(iso):
    return WEEKDAYS[date.fromisoformat(iso).weekday()]


def ladder_stage(wk):
    """The week's run/walk variant: its longest run's (a short easy run may step one back)."""
    return max((d["workout"]["variant"] for d in wk["days"] if d["workout"]["id"] == "run_walk"), default=None)


class Progress(unittest.TestCase):
    """plan.json's progress: the block, the run/walk ladder and the time trials across re-plans."""

    def test_same_week_replans_stay_held(self):
        p0 = json.loads(json.dumps(build(generic_profile(km_4w=20.0, longest_8w=8.0, volume_level="novice",
                                                         quality_level="novice"), weeks=8)))
        day = date(2024, 6, 12)                     # in P0's first week: the re-plans start on its second
        runs = training(12, 4, 9, end=day)           # 36 km a week: intermediate's volume
        prof1, p1 = replan(DETECTED_TOML, runs, day, p0)
        self.assertEqual(prof1.volume_level, "novice")
        self.assertIn("novice until the next block, then intermediate", prof1.level_reasons["volume"])
        prof2, p2 = replan(DETECTED_TOML, runs, day, p1)             # the same day again: still mid-block
        self.assertEqual(prof2.volume_level, "novice")
        self.assertIn("novice until the next block, then intermediate", prof2.level_reasons["volume"])
        self.assertEqual(p2["progress"]["block_start"], p0["weeks"][0]["start"])
        # the block keeps P0's deload, and the week after it starts the next block
        self.assertEqual(next(wk["start"] for wk in p2["weeks"] if wk["deload"]), "2024-07-01")
        at = date(2024, 7, 3)
        prof3, p3 = replan(DETECTED_TOML, training(12, 4, 9, end=at), at, p2)
        self.assertEqual(prof3.volume_level, "intermediate")
        self.assertEqual(p3["progress"]["block_start"], "2024-07-08")

    def test_time_trial_result_carries_over(self):
        _, a = replan(BEGINNER_TOML, [], TODAY)
        day = date.fromisoformat(tt_dates(a)[0])
        runs = sorted(training(6, 3, 3, end=day + timedelta(days=9)) + [stream_run(day, 2, 840)],
                      key=lambda r: r["date"])
        want = physiology.vdot(2000, 840)
        prof_b, b = replan(BEGINNER_TOML, runs, day + timedelta(days=2), a)
        self.assertAlmostEqual(prof_b.vdot, want, places=6)
        self.assertEqual(tt_dates(b), [])                        # done: not scheduled again
        self.assertEqual([t["date"] for t in b["progress"]["time_trials"]], [day.isoformat()])
        prof_c, c = replan(BEGINNER_TOML, runs, day + timedelta(days=8), b)   # plan.json no longer plans it
        self.assertAlmostEqual(prof_c.vdot, want, places=6)
        self.assertEqual((prof_c.sources["vdot"], prof_c.vdot_from), ("derived", ("2 km time trial", day.isoformat())))
        self.assertEqual(tt_dates(c), [])
        self.assertEqual(c["progress"]["time_trials"], b["progress"]["time_trials"])

    def test_ladder_and_time_trial_continue(self):
        _, a = replan(BEGINNER_TOML, [], TODAY)
        plan = a
        for k, today in enumerate((date(2024, 6, 12), date(2024, 6, 19)), 1):     # weekly re-plans
            with self.subTest(today=today):
                _, plan = replan(BEGINNER_TOML, [], today, plan)
                self.assertEqual(plan["weeks"][0]["start"], a["weeks"][k]["start"])
                self.assertEqual(tt_dates(plan), tt_dates(a))                    # the time trial keeps its date
                self.assertEqual([wk["deload"] for wk in plan["weeks"][:4]],
                                 [wk["deload"] for wk in a["weeks"][k:k + 4]])
                self.assertEqual([ladder_stage(wk) for wk in plan["weeks"][:3]],
                                 [ladder_stage(wk) for wk in a["weeks"][k:k + 3]])     # the ladder goes on
        self.assertEqual((a["progress"]["run_walk_stage"], plan["progress"]["run_walk_stage"]), (0, 2))

    def test_time_trial_later_this_week_moves_to_the_new_plan(self):
        # a re-plan the day before a pending time trial starts next Monday: the trial moves to that
        # week instead of staying pending on a day no plan holds (push removes it from the watch)
        _, a = replan(BEGINNER_TOML, [], TODAY)
        day = date.fromisoformat(tt_dates(a)[0])
        _, b = replan(BEGINNER_TOML, [], day - timedelta(days=1), a)
        first = date.fromisoformat(b["weeks"][0]["start"])
        self.assertGreater(first, day)
        self.assertEqual(tt_dates(b), [(first + timedelta(days=day.weekday())).isoformat()])
        self.assertEqual(b["progress"]["time_trial"], tt_dates(b)[0])
        # a run on the old date is no time trial
        prof, _ = replan(BEGINNER_TOML, [stream_run(day, 2, 840)], day + timedelta(days=1), b)
        self.assertNotEqual(prof.vdot_from, ("2 km time trial", day.isoformat()))

    def test_restart_after_sixty_days_off(self):
        # 50 km a week on 5 days, then 60 days off: the 8-week longest run and the 12-week consistency
        # are empty, but the restart volume (33 % of 50 km) is novice's
        runs = training(20, 5, 10, end=TODAY - timedelta(days=59))
        prev = build(generic_profile(km_4w=50.0, longest_8w=15.0, volume_level="intermediate",
                                     quality_level="intermediate"), weeks=8)
        for plan in (None, prev):
            with self.subTest(plan=bool(plan)):
                prof, _ = replan(DETECTED_TOML, runs, TODAY, plan)
                self.assertEqual(prof.layoff["days_off"], 60)
                self.assertAlmostEqual(prof.km_4w, 16.5)
                self.assertEqual(prof.volume_level, "novice")

    def test_beginner_in_km_adds_up(self):
        plan = build(beginner(unit="km"), weeks=12)
        for wk in plan["weeks"]:
            with self.subTest(week=wk["start"]):
                self.assertEqual(wk["target_km"], round(sum(plan_io.shown_km(d["workout"]) for d in wk["days"]), 1))

    def test_malformed_plan_json_is_no_plan(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        bad = ({"version": 1, "levels": {"volume": "novice", "quality": "novice"}, "weeks": [{"days": []}]},
               {"version": 1, "levels": {"volume": "novice", "quality": "novice"}, "weeks": None},
               {"version": 1, "levels": {"volume": "novice", "quality": "novice"},
                "weeks": [{"start": "2024-06-10", "days": [{"date": "2024-06-11", "workout": "x"}]}]})
        for plan in bad:
            for cmd in ("profile", "plan"):
                with self.subTest(plan=plan, cmd=cmd), tempfile.TemporaryDirectory() as d:
                    (Path(d) / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
                    res = subprocess.run([sys.executable, "-m", "garmin_plan", cmd, "--export", d, "--today",
                                          TODAY.isoformat()], capture_output=True, text=True, env=env)
                    self.assertEqual(res.returncode, 0, res.stderr)
                    self.assertRegex(res.stderr, r"warning: .*plan\.json.*ignored")

    def test_time_trial_day(self):
        # the Q day is a hill day: the time trial (a flat route) takes the easy day 48 h from L
        plan = build(beginner(hill_days=["tue"]), weeks=4)
        self.assertEqual([weekday(d) for d in tt_dates(plan)], ["thu"])
        self.assertNotIn("time_trial", [w["rule"] for w in plan["warnings"]])
        # no Q day: an easy day 48 h from L, else the day next to L, with a warning
        far = build(beginner(days=["wed", "sun"], long_run_day="sun"), weeks=4)
        self.assertEqual([weekday(d) for d in tt_dates(far)], ["wed"])
        self.assertNotIn("time_trial", [w["rule"] for w in far["warnings"]])
        near = build(beginner(days=["sat", "sun"], long_run_day="sun"), weeks=4)
        self.assertEqual([weekday(d) for d in tt_dates(near)], ["sat"])
        self.assertIn("time_trial", [w["rule"] for w in near["warnings"]])


GOLDEN_RACE = {"date": date(2024, 9, 1), "distance_m": 10000, "goal_s": None}       # Sunday of week 12
GOLDEN_RUNNERS = {
    # level: the runner of tests/fixtures/plan_golden_<level>.md, the same 10 km race in 12 weeks
    "beginner": dict(vdot=30.0, km_4w=6.0, longest_8w=3.0, days=["tue", "thu", "sat"], long_run_day="sat"),
    "novice": dict(vdot=36.0, km_4w=20.0, longest_8w=8.0, days=["tue", "thu", "sat", "sun"]),
    "intermediate": dict(vdot=44.0, km_4w=40.0, longest_8w=14.0, days=["tue", "wed", "thu", "sat", "sun"]),
    "advanced": dict(vdot=55.0, km_4w=70.0, longest_8w=22.0, days=WEEKDAYS),
}


class GoldenLevels(unittest.TestCase):
    """One 12-week plan per level for the same race. Regenerate after a reviewed change:
    UPDATE_GOLDEN=1 python -m unittest tests.test_levels"""

    def test_golden_per_level(self):
        for level, vals in GOLDEN_RUNNERS.items():
            with self.subTest(level=level):
                prof = generic_profile(**vals, race=GOLDEN_RACE, volume_level=level, quality_level=level)
                plan = build(prof)
                self.assertEqual(len(plan["weeks"]), 12)
                got = render_md.render_plan(plan)
                path = ROOT / "tests" / "fixtures" / f"plan_golden_{level}.md"
                if os.environ.get("UPDATE_GOLDEN"):
                    path.write_text(got, encoding="utf-8", newline="\n")
                self.assertEqual(got, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
