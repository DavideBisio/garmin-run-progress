"""Week checks, the auto-fixer and goal feasibility (TC-10, standard library only)."""
import copy
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import checks, fix, load, physiology, profile, size, templates  # noqa: E402

RULES = physiology.load_rules()
LIB = templates.load_templates()
MON = date(2024, 6, 10)
E_MIN = 4.85          # 30 min at VDOT 40's E pace (6:11/km), under the 5 km minimum


def generic_profile(**kw):
    """The fixed generic runner of the golden files: VDOT 40, HR 190/50."""
    vals = dict(hr_max=190, hr_rest=50, vdot=40.0, km_4w=0.0, km_12w=0.0, runs_per_week=0.0, longest_8w=0.0)
    vals.update(kw)
    return profile.Profile(**vals)


PROF = generic_profile()
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def day(wd, slot, tid, variant, monday=MON, **kw):
    w = templates.instantiate(LIB[tid], variant, PROF, RULES)
    return checks.Day(monday + timedelta(days=DAYS[wd]), slot, w, **kw)


def week(q=("cruise_tempo", 1), long=("steady_long", 1), monday=MON):
    """The passing week: easy Tue and Sat, Q Thu, L Sun (25.7 km, 92 % easy, L 39 %)."""
    return [day("tue", "E", "easy", 2, monday), day("thu", "Q", *q, monday=monday), day("sat", "F", "easy", 2, monday),
            day("sun", "L", *long, monday=monday)]


def history(days, factor=1.0, weeks=4):
    """Daily load of `weeks` weeks before the week of `days`, each a copy of it scaled by factor."""
    one = load.projected_daily([(d.date, d.workout) for d in days], 190, 50)
    return {i - 7 * k: v * factor for k in range(1, weeks + 1) for i, v in one.items()}


def run_checks(days, **kw):
    kw.setdefault("daily", history(days))
    kw.setdefault("end", MON + timedelta(days=6))
    return checks.check_week(days, RULES, e_min=E_MIN, hr_max=190, hr_rest=50, **kw)


def codes(result):
    return [v.code for v in result[0]]


class Checks(unittest.TestCase):
    def test_passing_week(self):
        violations, notes = run_checks(week(), prev_km=24.0)
        self.assertEqual(violations, [])
        self.assertEqual(notes, [])
        self.assertAlmostEqual(checks.week_km(week()), 25.685, places=2)
        self.assertGreater(checks.easy_share(week()), 0.9)

    def test_easy_share(self):
        days = week(q=("cruise_tempo", 4), long=("progression_long", 1))     # 6 km at T, 3 km at M
        self.assertEqual(codes(run_checks(days)), ["easy_share"])
        self.assertIn("76 %", run_checks(days)[0][0].detail)

    def test_easy_means_z1_z2(self):
        # the trail run's Z3 cap and the hilly run's Z2-3 are not easy; E and jogs (Z2) are
        trail = day("sun", "L", "trail_long", 1)
        main = next(p for p in trail.workout.parts if p.label == "Trail")
        self.assertAlmostEqual(checks.easy_share([trail]), 1 - main.seconds / trail.workout.seconds)
        self.assertEqual(checks.easy_share([day("tue", "E", "easy", 3)]), 1.0)
        self.assertTrue(checks.is_easy(templates.instantiate(LIB["r_220"], 1, PROF, RULES).parts[1].steps[1]))
        self.assertFalse(checks.is_easy(templates.instantiate(LIB["hilly_long"], 1, PROF, RULES).parts[1]))

    def test_hard_count(self):
        days = week()
        days[0] = day("tue", "Q", "r_220", 1)                          # Tue, Thu, Sun: none back to back
        self.assertEqual(codes(run_checks(days)), ["hard_count"])

    def test_hard_adjacent(self):
        days = week()
        days[1] = day("sat", "Q", "cruise_tempo", 1)
        days[2] = day("thu", "E", "easy", 2)
        days.sort(key=lambda d: d.date)
        self.assertEqual(codes(run_checks(days)), ["hard_adjacent"])
        # across weeks: last Sunday's long run, then a Monday Q
        prev = week(monday=MON - timedelta(days=7))
        days = week()
        days[1] = day("mon", "Q", "cruise_tempo", 1)
        days.sort(key=lambda d: d.date)
        self.assertEqual(codes(run_checks(days, prev_days=prev)), ["hard_adjacent"])
        self.assertEqual(codes(run_checks(days)), [])

    def test_volume_rise(self):
        result = run_checks(week(), prev_km=20.0)                      # +28 %
        self.assertEqual(codes(result), ["volume_rise"])
        self.assertIn("28 %", result[0][0].detail)
        self.assertEqual(codes(run_checks(week(), prev_km=23.4)), [])  # +9.8 %
        self.assertEqual(codes(run_checks(week(), prev_km=20.0, exempt={"volume_rise"})), [])

    def test_acwr(self):
        self.assertEqual(codes(run_checks(week(), daily=history(week(), 0.5))), ["acwr_high"])   # 1.6
        self.assertEqual(codes(run_checks(week(), daily=history(week(), 2.0))), ["acwr_low"])    # 0.57
        self.assertEqual(codes(run_checks(week(), daily=history(week(), 2.0), exempt={"acwr_low"})), [])
        self.assertIn("1.60", run_checks(week(), daily=history(week(), 0.5))[0][0].detail)

    def test_long_share(self):
        result = run_checks(week(long=("steady_long", 5)))             # 18 of 33.7 km
        self.assertEqual(codes(result), ["long_share"])
        self.assertIn("53 %", result[0][0].detail)
        # a long run at the E minimum is allowed over the share in a small week
        small = [day("tue", "E", "easy", 2),
                 checks.Day(MON + timedelta(days=6), "L", size.fit(LIB["easy"], 1, PROF, RULES, km=4.8))]
        self.assertEqual(codes(run_checks(small)), [])                  # 4.8 of 9.8 km: 49 %

    def test_short_history_skips_acwr_with_a_note(self):
        violations, notes = run_checks(week(), daily=None)
        self.assertEqual(violations, [])
        self.assertEqual([n.code for n in notes], ["acwr_skipped"])
        # under 28 days from the first day of history to the week's last day
        violations, notes = run_checks(week(), daily=history(week(), 0.5, weeks=2))
        self.assertEqual(violations, [])
        self.assertEqual([n.code for n in notes], ["acwr_skipped"])

    def test_forced_size_is_a_note(self):
        days = week()
        days[1].forced = "over its cap"
        violations, notes = run_checks(days)
        self.assertEqual(violations, [])
        self.assertEqual([(n.code, n.detail) for n in notes], [("forced_size", "over its cap")])


class Fixer(unittest.TestCase):
    """fix_week drives a build(adjust) -> days function; this one builds the passing week's layout
    with Q at variant q - adjust.q_down, L at long_km - adjust.trim_l_km and F dropped on request."""

    @staticmethod
    def builder(q=("cruise_tempo", 1), long_km=10.0, long=("steady_long", 1), manual_l=False, forced=""):
        def build(adj):
            tid, v = q
            qd = day("thu", "Q", tid, max(1, v - adj.q_down), forced=forced)
            km = long_km if manual_l else max(long_km - adj.trim_l_km, E_MIN)
            ld = checks.Day(MON + timedelta(days=6), "L", size.fit(LIB[long[0]], long[1], PROF, RULES, km=km),
                            manual=manual_l)
            days = [day("tue", "E", "easy", 2), qd]
            if not adj.drop_f:
                days.append(day("sat", "F", "easy", 2))
            return days + [ld]
        return build

    @staticmethod
    def check(prev_km=None, daily=None):
        return lambda days: run_checks(days, prev_km=prev_km, daily=daily)

    def test_converges(self):
        res = fix.fix_week(self.builder(long_km=18), self.check(), RULES)
        self.assertEqual(res.violations, [])
        self.assertFalse(res.stopped)
        # L <= 45 % of (15.7 km + L): 12.8 km, so 6 trims of 1 km
        self.assertEqual(res.actions, ["trim_l"] * 6)
        self.assertAlmostEqual(res.days[-1].workout.km, 12.0)
        self.assertEqual(res.adjust.trim_l_km, 6.0)

    def test_order_shrink_q_first(self):
        # easy share: Q shrinks until the week passes (variant 2), L stays
        build = self.builder(q=("cruise_tempo", 4), long_km=13, long=("progression_long", 1))
        self.assertEqual(codes(run_checks(build(fix.Adjust()))), ["easy_share"])
        res = fix.fix_week(build, self.check(), RULES)
        self.assertEqual(res.violations, [])
        self.assertTrue(res.actions and set(res.actions) == {"shrink_q"}, res.actions)
        passing = [v for v in range(4, 0, -1)
                   if not run_checks(self.builder(q=("cruise_tempo", v), long_km=13,
                                                  long=("progression_long", 1))(fix.Adjust()))[0]]
        self.assertEqual(res.days[1].workout.variant, passing[0])
        self.assertEqual(res.days[1].workout.variant, 2)
        self.assertEqual(res.actions, ["shrink_q", "shrink_q"])
        self.assertEqual(res.days[-1].workout.km, 13)
        # volume: shrinking Q doesn't cut it, so trim L, then drop F
        res = fix.fix_week(self.builder(long_km=10), self.check(prev_km=15.0), RULES)
        self.assertEqual(res.violations, [])
        self.assertEqual(res.actions[:5], ["trim_l"] * 5)               # L down to the E minimum
        self.assertEqual(res.actions[-1], "drop_f")
        self.assertTrue(res.adjust.drop_f)

    def test_deterministic(self):
        a = fix.fix_week(self.builder(long_km=18), self.check(prev_km=20.0), RULES)
        b = fix.fix_week(self.builder(long_km=18), self.check(prev_km=20.0), RULES)
        self.assertEqual(a.actions, b.actions)
        self.assertEqual([(d.date, d.workout.id, d.workout.variant, d.workout.km) for d in a.days],
                         [(d.date, d.workout.id, d.workout.variant, d.workout.km) for d in b.days])

    def test_stops_after_n(self):
        rules = copy.deepcopy(RULES)
        rules["fix"]["max_iter"] = 2
        res = fix.fix_week(self.builder(long_km=18), self.check(), rules)
        self.assertTrue(res.stopped)
        self.assertEqual(res.actions, ["trim_l", "trim_l"])
        self.assertEqual([v.code for v in res.violations], ["long_share"])

    def test_unfixable_and_forced_weeks_end(self):
        # nothing in the fix order helps hard_adjacent: no change, no loop
        def adjacent(adj):
            days = self.builder()(adj)
            days[0] = day("sat", "Q", "r_220", 1)
            return sorted(days, key=lambda d: d.date)
        res = fix.fix_week(adjacent, self.check(), RULES)
        self.assertEqual(res.actions, [])
        self.assertFalse(res.stopped)
        self.assertIn("hard_adjacent", [v.code for v in res.violations])
        # a forced smallest Q can't shrink: the easy-share fix has nothing left and ends at once
        def always_hard(days):
            violations, notes = run_checks(days)
            return violations + [checks.Violation("easy_share", "always")], notes
        res = fix.fix_week(self.builder(q=("cruise_tempo", 1), forced="over its cap"), always_hard, RULES)
        self.assertEqual(res.actions, [])
        self.assertFalse(res.stopped)
        self.assertEqual([n.code for n in res.notes], ["forced_size"])

    def test_manual_days_stay(self):
        res = fix.fix_week(self.builder(long_km=18, manual_l=True), self.check(), RULES)
        self.assertEqual(res.days[-1].workout.km, 18)
        self.assertNotIn("trim_l", res.actions)
        self.assertEqual([v.code for v in res.violations], ["long_share"])


class Feasibility(unittest.TestCase):
    def test_gaps(self):
        # 1 VDOT point per 6 weeks is realistic, up to 1 per 4 ambitious, more unrealistic
        want = {8: [None, "ambitious", "unrealistic"],                 # 1.33 and 2 points
                20: [None, None, "unrealistic"]}                       # 3.33 and 5 points
        for weeks, levels in want.items():
            for gap, level in zip((0, 2, 6), levels):
                with self.subTest(weeks=weeks, gap=gap):
                    got = checks.feasibility(40.0, 40.0 + gap, weeks, RULES)
                    self.assertEqual(got and got.level, level)
                    if got:
                        self.assertIn(f"{gap:.1f}", got.detail)

    def test_boundaries_are_lenient(self):
        self.assertIsNone(checks.feasibility(40, 42, 12, RULES))                 # exactly 12 / 6
        self.assertEqual(checks.feasibility(40, 43, 12, RULES).level, "ambitious")   # exactly 12 / 4
        self.assertEqual(checks.feasibility(40, 43.01, 12, RULES).level, "unrealistic")
        self.assertIsNone(checks.feasibility(45, 40, 4, RULES))                  # already there


if __name__ == "__main__":
    unittest.main()
