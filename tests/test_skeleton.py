"""Weekly skeleton, volume curve, phase calendar and week split (TC-9, standard library only)."""
import itertools
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import levels, phases, physiology, skeleton, split, volume  # noqa: E402,F401
from garmin_plan.config import WEEKDAYS  # noqa: E402

# 06's numbers: the novice level (one Q, L at most 45 % of the week) with every profile day a run
# and Daniels' 150-minute long run cap
RULES = levels.params(levels.load_levels(), "novice", "novice")
RULES["skeleton"]["max_runs"] = 7
RULES["split"]["long_time_cap_min"] = 150
TODAY = date(2024, 6, 5)   # a Wednesday: the first week (from Monday 2024-06-03) is partial
HARD = {"L", "Q"}


def gap(a, b):
    """Days from a forward to b in a repeating week, 1..7."""
    return (WEEKDAYS.index(b) - WEEKDAYS.index(a)) % 7 or 7


def by_day(slots):
    return {s: [d for d in WEEKDAYS if slots.get(d) == s] for s in "LQEF"}


class Placement(unittest.TestCase):
    CASES = [
        # days, long day, expected
        (["tue", "sun"], "sun", {"tue": "E", "sun": "L"}),
        (["sat", "sun"], "sun", {"sat": "E", "sun": "L"}),                  # weekend-only
        (["sat", "sun"], "sat", {"sat": "L", "sun": "E"}),
        (["tue", "thu", "sun"], "sun", {"tue": "E", "thu": "Q", "sun": "L"}),
        (["tue", "thu", "sat", "sun"], "sun", {"tue": "E", "thu": "Q", "sat": "F", "sun": "L"}),
        (["tue", "wed", "thu", "sat", "sun"], "sun",
         {"tue": "E", "wed": "F", "thu": "Q", "sat": "E", "sun": "L"}),       # dropping F leaves 1 back-to-back
        (["mon", "tue", "wed", "thu", "sat", "sun"], "sun",
         {"mon": "E", "tue": "E", "wed": "F", "thu": "Q", "sat": "E", "sun": "L"}),
        (["sun"], "sun", {"sun": "L"}),
    ]

    def test_table(self):
        for days, long_day, want in self.CASES:
            with self.subTest(days=days, long_day=long_day):
                got = skeleton.place_slots(days, long_day, RULES)
                self.assertEqual(got, want)
                self.assertEqual(list(got), [d for d in WEEKDAYS if d in got])     # Monday first

    def test_weekend_fallback(self):
        # Sunday long run with Sat/Sun/Mon: Q can't be 48 h from Sunday, so L moves to Saturday
        self.assertEqual(skeleton.place_slots(["sat", "sun", "mon"], "sun", RULES),
                         {"mon": "Q", "sat": "L", "sun": "E"})
        self.assertEqual(skeleton.place_slots(["fri", "sat", "sun"], "sat", RULES),
                         {"fri": "Q", "sat": "E", "sun": "L"})
        # the preferred day wins whenever it works
        self.assertEqual(skeleton.place_slots(["wed", "sat", "sun"], "sat", RULES)["sat"], "L")

    def test_impossible_sets_name_the_rule(self):
        with self.assertRaisesRegex(skeleton.SkeletonError, "48 h"):
            skeleton.place_slots(["mon", "tue", "wed"], "tue", RULES)
        with self.assertRaisesRegex(skeleton.SkeletonError, "preferred day"):
            skeleton.place_slots(["tue", "thu"], "sun", RULES)
        with self.assertRaisesRegex(skeleton.SkeletonError, "at least one"):
            skeleton.place_slots([], "sun", RULES)
        with self.assertRaisesRegex(skeleton.SkeletonError, "unknown day"):
            skeleton.place_slots(["tue", "funday"], "tue", RULES)

    def test_input_order_and_default_rules(self):
        days = ["sun", "tue", "sat", "thu"]
        self.assertEqual(skeleton.place_slots(days, "sun"), skeleton.place_slots(sorted(days), "sun", RULES))


class PlacementProperties(unittest.TestCase):
    def test_every_subset(self):
        checked = 0
        for n in range(3, 7):
            for days in itertools.combinations(WEEKDAYS, n):
                for long_day in days:
                    with self.subTest(days=days, long_day=long_day):
                        try:
                            slots = skeleton.place_slots(list(days), long_day, RULES)
                        except skeleton.SkeletonError as e:
                            self.assertIn("48 h", str(e))
                            homes = [long_day]
                            if long_day in ("sat", "sun") and ({"sat", "sun"} - {long_day}) <= set(days):
                                homes.append("sun" if long_day == "sat" else "sat")
                            for home in homes:     # really no day for Q at 48 h from any L day
                                self.assertFalse([d for d in days if d != home
                                                  and min(gap(home, d), gap(d, home)) >= 2])
                            continue
                        checked += 1
                        self.assertEqual(sorted(slots), sorted(days))
                        s = by_day(slots)
                        self.assertEqual(len(s["L"]), 1)
                        self.assertEqual(len(s["Q"]), 1)
                        self.assertEqual(len(s["F"]), 1 if n >= RULES["skeleton"]["f_min_days"] else 0)
                        self.assertTrue(s["E"])
                        L, q = s["L"][0], s["Q"][0]
                        self.assertNotEqual(gap(L, q), 1)                  # never the day after L
                        self.assertGreaterEqual(gap(L, q), 2)               # 48 h both ways, cyclic
                        self.assertGreaterEqual(gap(q, L), 2)
                        dist = lambda d: min(gap(L, d), gap(d, L))         # noqa: E731
                        self.assertFalse([d for d in days if d != L and dist(d) > dist(q)])  # Q as far as it gets
                        hard = [d for d in slots if slots[d] in HARD]
                        for a, b in itertools.permutations(hard, 2):
                            self.assertNotEqual(gap(a, b), 1)              # no back-to-back hard days
                        if L != long_day:                                  # only the weekend fallback,
                            self.assertEqual({L, long_day}, {"sat", "sun"})    # when the preferred day
                            self.assertFalse([d for d in days if d != long_day   # has no Q at 48 h
                                              and min(gap(long_day, d), gap(d, long_day)) >= 2])
                        self.assertEqual(skeleton.place_slots(list(reversed(days)), long_day, RULES), slots)
        self.assertGreater(checked, 300)


class VolumeCurve(unittest.TestCase):
    def assertCurve(self, got, want):
        self.assertEqual(len(got), len(want))
        for g, w in zip(got, want):
            self.assertAlmostEqual(g, w, places=6)

    def test_three_blocks(self):
        # x1.00, x1.08, x1.16, deload x0.85; the next block starts from the last block's week 2
        self.assertCurve(volume.block_curve(20, 12, ramp=0.08, deload=0.85, deload_every=4, floor=10),
                         [20, 21.6, 23.2, 17.0,
                          21.6, 23.328, 25.056, 18.36,
                          23.328, 25.19424, 27.06048, 19.8288])

    def test_settings_from_rules(self):
        kw = volume.settings(RULES)
        self.assertEqual(kw, {"ramp": 0.08, "deload": 0.85, "deload_every": 4, "floor": 10, "next_from": 2})
        self.assertEqual(RULES["volume"]["unit"], "km")
        self.assertCurve(volume.block_curve(20, 4, **kw), [20, 21.6, 23.2, 17.0])

    def test_settings_take_effect(self):
        self.assertCurve(volume.block_curve(20, 7, ramp=0.05, deload=0.8, deload_every=3, floor=10),
                         [20, 21, 16, 21, 22.05, 16.8, 22.05])
        # next block from week 3 instead of week 2
        self.assertCurve(volume.block_curve(20, 5, ramp=0.08, deload=0.85, deload_every=4, floor=10, next_from=3),
                         [20, 21.6, 23.2, 17.0, 23.2])
        # unit-agnostic: minutes work the same way
        self.assertCurve(volume.block_curve(90, 4, floor=60), [90, 97.2, 104.4, 76.5])
        with self.assertRaises(ValueError):
            volume.block_curve(20, 4, deload_every=1)

    def test_start_floor(self):
        self.assertCurve(volume.block_curve(0, 4, floor=10), [10, 10.8, 11.6, 8.5])
        self.assertCurve(volume.block_curve(3.2, 2, floor=10), [10, 10.8])
        self.assertEqual(volume.block_curve(20, 0), [])

    def test_partial_first_week_is_not_ramped(self):
        self.assertCurve(volume.block_curve(20, 6, partial_first=True), [20, 20, 21.6, 23.2, 17.0, 21.6])

    def test_align_deloads(self):
        self.assertEqual(volume.align_deloads(16, 4, [0, 6, 12]), [3, 7, 11, 15])     # nothing to move
        self.assertEqual(volume.align_deloads(12, 4, [0, 3, 8]), [2, 6, 10])          # earlier first
        self.assertEqual(volume.align_deloads(12, 4, [0, 2, 3, 6]), [4, 8])           # else later
        self.assertEqual(volume.align_deloads(8, 4, [0, 2, 3, 4]), [3, 7])            # not possible: kept
        self.assertEqual(volume.align_deloads(9, 4, [], lead=1), [4, 8])              # partial week skipped
        self.assertCurve(volume.block_curve(20, 12, deloads=[2, 6, 10]),
                         [20, 21.6, 17.0, 21.6, 23.328, 25.056, 18.36, 23.328, 25.19424, 27.06048,
                          19.8288, 25.19424])

    def test_aligned_with_the_calendar(self):
        every = RULES["volume"]["deload_every"]
        for dist, n in itertools.product((5000, 10000, 21097.5, 42195), (6, 12, 16, 20, 30)):
            with self.subTest(dist=dist, weeks=n):
                cal, _ = phases.phase_calendar(TODAY, TODAY + timedelta(weeks=n), dist, RULES)
                build = [w.phase for w in cal if w.phase != "taper"]
                starts = [i for i in range(1, len(build)) if build[i] != build[i - 1]]
                deloads = volume.align_deloads(len(build), every, starts, lead=1)    # the taper has none
                self.assertFalse(set(deloads) & set(starts))


class Phases(unittest.TestCase):
    def counts(self, cal):
        return [(p, len(list(g))) for p, g in itertools.groupby(w.phase for w in cal)]

    def race(self, n, dist=5000, **kw):
        return phases.phase_calendar(TODAY, TODAY + timedelta(weeks=n), dist, RULES, **kw)

    def test_weeks_are_monday_based(self):
        cal, _ = self.race(12)
        self.assertEqual(cal[0].start, date(2024, 6, 3))
        for i, w in enumerate(cal):
            self.assertEqual(w.start.weekday(), 0)
            self.assertEqual(w.start, date(2024, 6, 3) + timedelta(weeks=i))
            self.assertEqual(w.partial, i == 0)                 # today is a Wednesday
        self.assertLessEqual(cal[-1].start, TODAY + timedelta(weeks=12))   # the race week is the last
        monday, _ = phases.phase_calendar(date(2024, 6, 3), date(2024, 9, 1), 5000, RULES)
        self.assertFalse(monday[0].partial)

    def test_race_in_30_weeks(self):
        cal, warnings = self.race(30)
        self.assertEqual(self.counts(cal), [("base", 13), ("rt", 6), ("it", 6), ("tm", 4), ("taper", 2)])
        self.assertEqual(warnings, [])

    def test_race_in_20_weeks(self):
        cal, warnings = self.race(20, 10000)
        self.assertEqual(self.counts(cal), [("base", 6), ("rt", 5), ("it", 3), ("tm", 5), ("taper", 2)])
        self.assertEqual(len(warnings), 1)
        self.assertIn("it 6 -> 3", warnings[0])

    def test_race_in_12_weeks(self):
        cal, warnings = self.race(12, 21097.5)
        self.assertEqual(self.counts(cal), [("base", 6), ("tm", 5), ("taper", 2)])
        self.assertIn("it 6 -> 0, rt 4 -> 0, tm 6 -> 5", warnings[0])

    def test_race_in_6_weeks(self):
        cal, warnings = self.race(6, 42195)
        self.assertEqual(self.counts(cal), [("base", 5), ("taper", 2)])
        self.assertIn("ramp", warnings[0])                       # shortened, not compressed
        cal, _ = self.race(6, 5000)
        self.assertEqual(self.counts(cal), [("base", 5), ("taper", 2)])

    def test_taper_is_two_weeks(self):
        for dist in (5000, 10000, 21097.5, 42195):
            self.assertEqual(RULES["phases"][phases.race_key(dist, RULES)]["taper"], 2)
        cal, _ = self.race(1)
        self.assertEqual(self.counts(cal), [("taper", 2)])
        cal, warnings = phases.phase_calendar(TODAY, TODAY + timedelta(days=2), 5000, RULES)
        self.assertEqual(self.counts(cal), [("taper", 1)])
        self.assertTrue(warnings)

    def test_distances(self):
        self.assertEqual([phases.race_key(d, RULES) for d in (5000, 10000, 21097.5, 42195, 8000, 40000, 3000)],
                         ["5k", "10k", "hm", "m", "10k", "m", "5k"])
        full = {k: sum(RULES["phases"][k][p] for p in phases.PHASES) for k in ("5k", "10k", "hm", "m")}
        for key, dist in (("5k", 5000), ("10k", 10000), ("hm", 21097.5), ("m", 42195)):
            with self.subTest(key=key):
                cal, warnings = self.race(full[key] - 1, dist)       # exactly the full build
                self.assertEqual(warnings, [])
                self.assertEqual(self.counts(cal), [(p, RULES["phases"][key][p]) for p in phases.PHASES
                                                   if RULES["phases"][key][p]])

    def test_no_race_cycles(self):
        cal, warnings = phases.phase_calendar(TODAY, None, None, RULES, weeks=10)
        self.assertEqual(self.counts(cal), [("base", 4), ("rt", 4), ("base", 2)])
        self.assertEqual(warnings, [])
        cal, _ = phases.phase_calendar(TODAY, None, None, RULES)
        self.assertEqual(self.counts(cal), [("base", 4), ("rt", 4)])

    def test_weeks_limit_and_errors(self):
        cal, _ = self.race(20, weeks=4)
        self.assertEqual(len(cal), 4)
        cal, _ = self.race(5, weeks=40)                          # never past the race week
        self.assertEqual(len(cal), 6)
        with self.assertRaisesRegex(phases.PhaseError, "before"):
            phases.phase_calendar(TODAY, TODAY - timedelta(days=1), 5000, RULES)


class Split(unittest.TestCase):
    E_PACE = 360                     # 30 min at E = 5 km: both E minimums agree
    QTEL = {"tue": "Q", "wed": "F", "thu": "E", "sun": "L"}
    THREE = {"tue": "E", "thu": "Q", "sun": "L"}

    @staticmethod
    def e_min(pace):
        return min(RULES["split"]["easy_min_km"], RULES["split"]["easy_min_min"] * 60 / pace)

    @classmethod
    def l_ceiling(cls, target, longest, pace):
        """The tightest L cap, unless it is under the E minimum (the shortest run worth putting on)."""
        s = RULES["split"]
        return max(min(s["long_share_cap"] * target, longest + s["long_over_longest_km"],
                       s["long_time_cap_min"] * 60 / pace), cls.e_min(pace))

    def test_invariants(self):
        layouts = [{"tue": "E", "sun": "L"}, {"tue": "E", "thu": "Q", "sun": "L"},
                   {"tue": "E", "thu": "Q", "sat": "F", "sun": "L"},
                   {"tue": "E", "wed": "Q", "thu": "E", "sat": "F", "sun": "L"},
                   {"mon": "E", "tue": "F", "wed": "Q", "thu": "E", "sat": "E", "sun": "L"}]
        targets = [t / 2 for t in range(4, 40)] + list(range(20, 121, 3))     # from 2 km up
        for slots, target, longest, pace, q_km in itertools.product(layouts, targets, (0, 8, 15, 25),
                                                                    (300, 360, 450), (5.0, 7.0)):
            with self.subTest(slots=slots, target=target, longest=longest, pace=pace, q_km=q_km):
                km, warnings = split.split_week(target, slots, longest, q_km, RULES, pace)
                self.assertEqual(list(km), [d for d in WEEKDAYS if d in slots])
                self.assertTrue(all(isinstance(w, str) for w in warnings))
                self.assertAlmostEqual(sum(km.values()), target, delta=0.5)
                self.assertTrue(all(v >= 0 for v in km.values()))
                e_min = self.e_min(pace)
                L = next(km[d] for d in slots if slots[d] == "L")
                self.assertLessEqual(L, self.l_ceiling(target, longest, pace) + 0.05)
                if target >= e_min:
                    self.assertGreaterEqual(L, e_min - 0.05)
                has_q = "Q" in slots.values()
                dropped = any("Q dropped" in w for w in warnings)
                self.assertEqual(dropped, has_q and target - q_km < e_min)
                short = any("under the E minimum" in w for w in warnings)
                over_l = any("longer than L" in w for w in warnings)
                for d, s in slots.items():
                    if s == "Q" and not dropped:
                        self.assertGreaterEqual(km[d], q_km)
                        self.assertLess(km[d], q_km + e_min)               # + a leftover too small for E
                    if (s in "EF" or s == "Q" and dropped) and km[d]:
                        if not short:
                            self.assertGreaterEqual(km[d], e_min - 0.05)
                        if not over_l:
                            self.assertLessEqual(km[d], L)

    def test_parts_add_up_to_the_rounded_target(self):
        # each part rounds to 0.1 km and the parts still add up to the target rounded to 0.1 km:
        # the plan.md heading is the sum of its days
        layouts = [{"tue": "E", "thu": "Q", "sun": "L"}, {"tue": "E", "wed": "Q", "thu": "E", "sun": "L"},
                   {"tue": "E", "wed": "Q", "thu": "E", "sat": "F", "sun": "L"},
                   {"mon": "E", "tue": "F", "wed": "Q", "thu": "E", "sat": "E", "sun": "L"}]
        targets = [6 + t * 0.37 for t in range(120)]
        for slots, target, longest, q_km in itertools.product(layouts, targets, (0, 8.3, 15), (5.0, 5.69, 6.35)):
            with self.subTest(slots=slots, target=target, longest=longest, q_km=q_km):
                km, _ = split.split_week(target, slots, longest, q_km, RULES, 371)
                self.assertEqual(round(sum(km.values()), 1), round(target, 1))
                self.assertTrue(all(round(v, 1) == v for v in km.values()), km)

    def test_long_run_caps(self):
        # share cap binds at low volume: 0.45 x 20 = 9 < 10 + 2
        self.assertEqual(split.split_week(20, self.THREE, 10, 5, RULES, 360),
                         ({"tue": 6.0, "thu": 5.0, "sun": 9.0}, []))
        # longest + 2 km binds: 12 < 0.45 x 40
        self.assertEqual(split.split_week(40, self.QTEL, 10, 6, RULES, 360)[0]["sun"], 12.0)
        # 150 min at E binds: 150 x 60 / 480 = 18.75 km
        six = {"mon": "E", "tue": "F", "wed": "Q", "thu": "E", "sat": "E", "sun": "L"}
        self.assertEqual(split.split_week(80, six, 30, 6, RULES, 480)[0]["sun"], 18.8)

    def test_caps_win_over_easy_runs(self):
        # 150 min at 7:00/km = 21.4 km: L stays there, the one E run takes the rest and is longer
        km, warnings = split.split_week(50, self.THREE, 20, 6, RULES, 420)
        self.assertEqual(km, {"tue": 22.6, "thu": 6.0, "sun": 21.4})
        self.assertEqual(len(warnings), 1)
        self.assertIn("longer than L", warnings[0])
        # longest + 2 km = 5 km: L doesn't even out to 7.5 km with the easy run
        km, warnings = split.split_week(20, self.THREE, 3, 5, RULES, 360)
        self.assertEqual(km, {"tue": 10.0, "thu": 5.0, "sun": 5.0})
        self.assertIn("longer than L", warnings[0])
        # with an F slot the excess goes there instead
        self.assertEqual(split.split_week(50, self.QTEL, 20, 6, RULES, 420),
                         ({"tue": 6.0, "wed": 11.3, "thu": 11.3, "sun": 21.4}, []))

    def test_low_volume_drops_q(self):
        # 4 km can't hold a 5 km Q: Q is dropped, nothing negative, L takes the week
        km, warnings = split.split_week(4, self.THREE, 0, 5, RULES, 360)
        self.assertEqual(km, {"tue": 0.0, "thu": 0.0, "sun": 4.0})
        self.assertTrue(any("Q dropped" in w for w in warnings))
        self.assertTrue(any("under the E minimum" in w for w in warnings))
        # the floor's deload week (10 x 0.85 = 8.5 km) with a 7 km Q would leave L 1.5 km
        target = RULES["volume"]["start_floor"] * RULES["volume"]["deload"]
        km, warnings = split.split_week(target, self.THREE, 6, 7, RULES, 360)
        self.assertEqual(km, {"tue": 3.5, "thu": 0.0, "sun": 5.0})
        self.assertIn("Q dropped", warnings[0])
        # just enough for Q and an L at the E minimum: Q stays
        self.assertEqual(split.split_week(12, self.THREE, 6, 7, RULES, 360),
                         ({"tue": 0.0, "thu": 7.0, "sun": 5.0}, []))

    def test_flex_on_and_off(self):
        # E alone up to L: F stays off
        self.assertEqual(split.split_week(50, self.QTEL, 20, 6, RULES, 360),
                         ({"tue": 6.0, "wed": 0.0, "thu": 22.0, "sun": 22.0}, []))
        # E would run over L: F switches on and shares the easy km
        self.assertEqual(split.split_week(52, self.QTEL, 20, 6, RULES, 360),
                         ({"tue": 6.0, "wed": 12.0, "thu": 12.0, "sun": 22.0}, []))
        # E over L, but F would put both below 5 km: F stays off and L stays at the 5 km E minimum
        km, warnings = split.split_week(17, self.QTEL, 0, 6, RULES, 360)
        self.assertEqual(km, {"tue": 6.0, "wed": 0.0, "thu": 6.0, "sun": 5.0})
        self.assertIn("longer than L (5.0 km, at the E minimum)", warnings[0])
        # whole-number inputs still give km as floats
        km, _ = split.split_week(20, self.QTEL, 3, 5, RULES, 360)
        self.assertTrue(all(type(v) is float for v in km.values()), km)

    def test_easy_minimum(self):
        two_e = {"tue": "E", "wed": "Q", "thu": "E", "sun": "L"}
        # 20 - 9 - 6 = 5 km: one easy run of 5, the other day off
        self.assertEqual(split.split_week(20, two_e, 10, 6, RULES, 360),
                         ({"tue": 5.0, "wed": 6.0, "thu": 0.0, "sun": 9.0}, []))
        # 26 - 11.7 - 6 = 8.3 km, too little for two runs of 5 km: one run of 8.3, the other day off
        self.assertEqual(split.split_week(26, two_e, 10, 6, RULES, 360),
                         ({"tue": 8.3, "wed": 6.0, "thu": 0.0, "sun": 11.7}, []))
        # 16 - 7.2 - 5 = 3.8 km, too little for an easy run: L gives up 1.2 km so one E reaches 5 km
        self.assertEqual(split.split_week(16, two_e, 8, 5, RULES, 360),
                         ({"tue": 5.0, "wed": 5.0, "thu": 0.0, "sun": 6.0}, []))
        # 14 - 6.3 - 5 = 2.7 km: L can't give 2.3 km and stay at 5 km, and is at its cap: Q takes it
        self.assertEqual(split.split_week(14, two_e, 8, 5, RULES, 360),
                         ({"tue": 0.0, "wed": 7.7, "thu": 0.0, "sun": 6.3}, []))
        # 30 min at a slow E pace (7:30/km) is 4 km, so 8.3 km makes two runs of 4.15 km: rounded
        # to 0.1 km they still add up to 8.3, the first one taking the odd 0.1 km
        km, _ = split.split_week(26, two_e, 10, 6, RULES, 450)
        self.assertEqual((km["tue"], km["thu"]), (4.2, 4.1))
        self.assertEqual(km["sun"], 11.7)

    def test_single_run_week(self):
        km, warnings = split.split_week(12, {"sun": "L"}, 6, 5, RULES, 360)
        self.assertEqual(km, {"sun": 12.0})          # nowhere else to go: over the 5.4 km share cap
        self.assertIn("cap", warnings[0])

    def test_deload_week_is_not_the_longest_l(self):
        # the roadmap 06 example: 16 km start, longest run 8 km, a 5 km Q, E pace 6:11/km (VDOT 40)
        slots = skeleton.place_slots(["tue", "wed", "thu", "sat", "sun"], "sun", RULES)
        weeks = [split.split_week(t, slots, 8, 5, RULES, 371)[0]
                 for t in volume.block_curve(16, 4, **volume.settings(RULES))]
        longs = [w["sun"] for w in weeks]
        self.assertLess(longs[3], max(longs[:3]))
        self.assertLessEqual(longs[3], self.l_ceiling(16 * 0.85, 8, 371) + 0.05)
        self.assertGreater(weeks[3]["thu"], 5.0)      # the leftover went to Q
