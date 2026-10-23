"""Session selection and sizing, terrain and projected load (TC-10, standard library only)."""
import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import history, load, metrics, model, physiology, profile, select, size, templates, terrain  # noqa: E402,E501
from garmin_plan import levels, volume  # noqa: E402

RULES = levels.params(levels.load_levels(), "intermediate", "intermediate")   # the golden runner's levels
LIB = templates.load_templates()
CAPS = RULES["caps"]
BIG = 99.0          # a slot so long that only the hard-portion cap binds


def generic_profile(**kw):
    """The fixed generic runner of the golden files: VDOT 40, HR 190/50."""
    vals = dict(hr_max=190, hr_rest=50, vdot=40.0, km_4w=0.0, km_12w=0.0, runs_per_week=0.0, longest_8w=0.0)
    vals.update(kw)
    return profile.Profile(**vals)


PROF = generic_profile()


def pick(tid, week_km, slot_km=BIG, **kw):
    return size.pick_variant(LIB[tid], slot_km, week_km, CAPS, PROF, RULES, **kw)


def work(tid, variant, **kw):
    return templates.instantiate(LIB[tid], variant, PROF, RULES, **kw)


class Caps(unittest.TestCase):
    def test_cap_km(self):
        self.assertAlmostEqual(size.cap_km("R", 40, CAPS), 2.0)
        self.assertEqual(size.cap_km("R", 200, CAPS), 8)              # 5 %, at most 8 km
        self.assertAlmostEqual(size.cap_km("I", 50, CAPS), 4.0)
        self.assertEqual(size.cap_km("I", 200, CAPS), 10)             # 8 %, at most 10 km
        self.assertAlmostEqual(size.cap_km("T", 200, CAPS), 20.0)     # 10 %, no km limit
        self.assertAlmostEqual(size.cap_km("M", 50, CAPS), 10.0)
        self.assertAlmostEqual(size.cap_km("L", 50, CAPS), 10.0)      # marathon-pace blocks: the M cap
        self.assertAlmostEqual(size.cap_km("hill", 40, CAPS), 2.0)    # hill reps: the R cap
        self.assertAlmostEqual(size.cap_km("E", 40, CAPS), 2.0)       # strides: the R cap
        self.assertEqual(size.cap_km("trail", 40, CAPS), math.inf)    # no hard steps, no cap

    def test_caps_count_the_hard_portion_only(self):
        # 8 x 220 m at R: 1.76 hard km of a 5.7 km session (warm-up, cool-down and jogs excluded)
        w = work("r_220", 2)
        self.assertAlmostEqual(w.hard_km, 8 * 0.22)
        self.assertAlmostEqual(w.km, 5.7)
        reps = sum(s.meters * p.n for p in w.parts if isinstance(p, model.Repeat) for s in p.steps if s.role == "rep")
        self.assertAlmostEqual(w.hard_km, reps / 1000)
        # at 40 km a week the R cap is 2.0 km: the 5.7 km session fits, its total is never compared to the cap
        self.assertEqual(pick("r_220", 40), (2, False))
        # warm-up, cool-down and recoveries are never hard, whatever the template
        for t in LIB.values():
            for v in range(1, len(t["ladder"]) + 1):
                for p in templates.instantiate(t, v, PROF, RULES).parts:
                    for s in (p.steps if isinstance(p, model.Repeat) else [p]):
                        if s.role in ("warmup", "cooldown", "recovery"):
                            self.assertFalse(s.hard, (t["id"], v, s.label))


class SizingTables(unittest.TestCase):
    # (variant, forced) at 15, 25, 40 and 60 km a week, written out by hand from the ladders' hard km:
    #   r_220 1.32 1.76 2.2 2.64 | vo2_intervals 3.0 4.8 5.0 6.0 | cruise_tempo 2.4 3.6 4.8 6.0 5.0 |
    #   progression 2.0 3.5 5.0
    TABLE = {
        "r_220": [(1, True), (1, True), (2, False), (4, False)],              # caps 0.75 1.25 2.0 3.0
        "vo2_intervals": [(1, True), (1, True), (1, False), (2, False)],     # caps 1.2 2.0 3.2 4.8
        "cruise_tempo": [(1, True), (1, False), (2, False), (5, False)],     # caps 1.5 2.5 4.0 6.0
        "progression": [(1, False), (3, False), (3, False), (3, False)],     # caps 3 5 8 12
    }

    def test_table(self):
        for tid, want in self.TABLE.items():
            for week_km, w in zip((15, 25, 40, 60), want):
                with self.subTest(tid=tid, week_km=week_km):
                    self.assertEqual(pick(tid, week_km), w)

    def test_scans_every_variant(self):
        # cruise_tempo's hard km go down from variant 4 (6.0) to 5 (5.0): at 55 km (cap 5.5) the
        # ladder's last variant fits although the one before it doesn't
        self.assertEqual(pick("cruise_tempo", 55), (5, False))
        self.assertEqual(pick("cruise_tempo", 45), (2, False))         # 4.8 and 5.0 are over 4.5

    def test_slot_km_binds(self):
        self.assertEqual(pick("progression", 60, slot_km=8), (2, False))     # 9 km doesn't fit 8
        self.assertEqual(pick("cruise_tempo", 60, slot_km=3), (1, True))     # nothing fits: smallest
        self.assertEqual(pick("steady_long", 40, slot_km=15), (3, False))    # 14 km
        # time slot (hill and trail swaps keep the time budget)
        self.assertEqual(pick("trail_long", 40, slot_s=130 * 60), (2, False))

    def test_lighter(self):
        self.assertEqual(pick("cruise_tempo", 60, lighter=1), (4, False))
        self.assertEqual(pick("cruise_tempo", 25, lighter=1), (1, False))    # never below 1
        self.assertEqual(pick("r_220", 15, lighter=1), (1, True))


class Overrides(unittest.TestCase):
    def test_ladder_variables(self):
        self.assertAlmostEqual(work("easy", 1, overrides={"d": 7300}).km, 7.3)
        w = work("trail_long", 1, overrides={"t": 3000})
        self.assertEqual(next(p for p in w.parts if p.label == "Trail").value, 3000)
        # every other value stays the variant's
        self.assertEqual(work("progression_long", 2, overrides={"e": 5000}).hard_km, 3.5)

    def test_warmup_and_cooldown(self):
        base = work("cruise_tempo", 2)
        w = work("cruise_tempo", 2, overrides={"warmup": 3500})
        self.assertAlmostEqual(w.km - base.km, 1.5)
        self.assertEqual(w.hard_km, base.hard_km)
        self.assertEqual(w.parts[0].value, 3500)
        self.assertAlmostEqual(work("cruise_tempo", 2, overrides={"cooldown": 0}).km, base.km - 1.0)

    def test_errors(self):
        for bad in ({"x": 1}, {"warmup": -1}, {"n": 2.5}, {"d": "long"}):
            with self.assertRaises(templates.TemplateError, msg=bad):
                work("cruise_tempo", 2, overrides=bad)
        with self.assertRaises(templates.TemplateError):
            work("easy", 1, overrides={"warmup": 1000})                 # easy has no warm-up

    def test_fit(self):
        w = size.fit(LIB["steady_long"], 1, PROF, RULES, km=13.7)
        self.assertAlmostEqual(w.km, 13.7)
        self.assertEqual(w.variant, 1)
        w = size.fit(LIB["progression_long"], 1, PROF, RULES, km=15)
        self.assertAlmostEqual(w.km, 15)
        self.assertEqual(w.hard_km, 3.0)                                # the easy part takes the change
        w = size.fit(LIB["easy"], 2, PROF, RULES, km=4.6)
        self.assertAlmostEqual(w.km, 4.6)
        w = size.fit(LIB["trail_long"], 1, PROF, RULES, seconds=5400)
        self.assertAlmostEqual(w.seconds, 5400, delta=1)
        self.assertIsNone(size.fit(LIB["progression_long"], 1, PROF, RULES, km=4))   # E part under 0
        w = size.fit(LIB["cruise_tempo"], 2, PROF, RULES, warmup_km=1.2)
        self.assertAlmostEqual(w.km, work("cruise_tempo", 2).km + 1.2)


class Strides(unittest.TestCase):
    def test_template(self):
        t = LIB["strides"]
        self.assertEqual((t["kind"], t["min_level"]), ("E", "novice"))
        w = work("strides", 1)
        self.assertGreater(w.hard_km, 0)
        self.assertLess(w.hard_km, 0.1 * w.km)                          # mostly an easy run
        kms = [work("strides", v).km for v in range(1, len(t["ladder"]) + 1)]
        self.assertEqual(kms, sorted(kms))


class Rotation(unittest.TestCase):
    def test_block_week(self):
        self.assertEqual([select.block_week(i, [3, 7, 11], 4) for i in range(12)],
                         [1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4])
        self.assertEqual([select.block_week(i, [2, 6], 4) for i in range(8)],    # a deload moved earlier
                         [1, 2, 4, 1, 2, 3, 4, 1])
        self.assertEqual([select.block_week(i, [4, 8], 4) for i in range(9)],    # and one moved later
                         [1, 2, 3, 3, 4, 1, 2, 3, 4])

    def test_twelve_weeks_three_blocks(self):
        # rt phase: Q alternates A (R) and B (T), the deload B one variant lighter; L goes steady,
        # progression, longest (steady, the block's biggest week), short (steady, the deload)
        targets = volume.block_curve(50, 12, **volume.settings(RULES))
        deloads = volume.align_deloads(12, 4)
        self.assertEqual(deloads, [3, 7, 11])
        q, long = [], []
        for i, target in enumerate(targets):
            bw, dl = select.block_week(i, deloads, 4), i in deloads
            tid = select.rotation("rt", bw, "Q", RULES, deload=dl, library=LIB)
            v, _ = pick(tid, target, lighter=RULES["rotation"]["deload_lighter"] if dl else 0)
            q.append((tid, v))
            long.append(select.rotation("rt", bw, "L", RULES, deload=dl, library=LIB))
        # caps by week (km): R 2.5 2.7 2.9 | 2.7 2.92 3.13 | 2.92 3.15 3.38; T 5.4 4.25 | 5.83 4.59 | 6.3 4.96
        # deloads: variant 2 (3.6 hard km), 2, then 3 (4.8 km), each one lighter
        self.assertEqual(q, [("r_300", 2), ("cruise_tempo", 5), ("r_ladder", 3), ("cruise_tempo", 1),
                             ("r_300", 2), ("cruise_tempo", 5), ("r_ladder", 3), ("cruise_tempo", 1),
                             ("r_300", 2), ("cruise_tempo", 5), ("r_ladder", 3), ("cruise_tempo", 2)])
        self.assertEqual(long, ["steady_long", "progression_long", "steady_long", "steady_long"] * 3)

    def test_phases(self):
        def q(phase, bw=1, **kw):
            return select.rotation(phase, bw, "Q", RULES, library=LIB, **kw)
        self.assertEqual([q("base"), q("rt"), q("it"), q("tm"), q("taper")],
                         ["strides", "r_300", "vo2_intervals", "cruise_tempo", "cruise_tempo"])
        self.assertEqual([q("base", 2), q("rt", 2), q("it", 2), q("tm", 2), q("taper", 2)],
                         ["strides", "cruise_tempo", "cruise_tempo", "progression", "strides"])
        self.assertEqual(select.rotation("tm", 3, "L", RULES, library=LIB), "hm_long")

    def test_hill_swaps(self):
        def pick_id(phase, bw, slot, **kw):
            return select.rotation(phase, bw, slot, RULES, hill_day=True, library=LIB, **kw)
        self.assertEqual(pick_id("base", 1, "Q"), "hill_repeats")      # Q-A
        self.assertEqual(pick_id("rt", 1, "Q"), "hill_repeats")
        self.assertEqual(pick_id("rt", 2, "Q"), "cruise_tempo")        # Q-B stays
        self.assertEqual(pick_id("tm", 1, "Q"), "cruise_tempo")        # race-specific phase: no swap
        self.assertEqual(pick_id("rt", 3, "L"), "hilly_long")
        self.assertEqual(pick_id("it", 3, "L"), "trail_long")
        self.assertEqual(pick_id("rt", 1, "L"), "steady_long")
        self.assertEqual(pick_id("rt", 3, "Q", deload=True), "cruise_tempo")    # deload: the B session
        self.assertEqual(pick_id("rt", 3, "L", deload=True), "steady_long")

    def test_level_fallback(self):
        def q(phase, bw, slot="Q", **kw):
            return select.rotation(phase, bw, slot, RULES, library=LIB, **kw)
        self.assertEqual(RULES["rotation"]["level"], "intermediate")   # the quality level (levels.params)
        self.assertEqual(q("rt", 1, level="novice"), "r_220")
        self.assertEqual(q("it", 1, level="novice"), "cruise_tempo")
        self.assertEqual(q("rt", 2, "L", level="novice"), "steady_long")
        self.assertEqual(q("rt", 1, hill_day=True, level="novice"), "r_220")    # hills are intermediate
        self.assertEqual(q("rt", 1, level="beginner"), "r_220")        # nothing fits: the lowest level
        self.assertEqual(select.candidates("rt", 2, "L", RULES, library=LIB),
                         ["progression_long", "steady_long"])


def minetti(i):
    """Minetti's cost of running (J/kg/m) at grade i, written out again for the expected numbers."""
    i = max(-0.3, min(0.3, i))
    return 155.4 * i ** 5 - 30.4 * i ** 4 - 43.3 * i ** 3 + 46.3 * i ** 2 + 19.5 * i + 3.6


class Terrain(unittest.TestCase):
    def test_flat_equivalent(self):
        # half the distance climbs and half descends, each at climb / (half the distance)
        self.assertEqual(terrain.flat_equivalent_km(10, 0, 0), 10)
        self.assertAlmostEqual(terrain.flat_equivalent_km(10, 200, 200), 10.2056, places=4)     # 4 % grades
        self.assertAlmostEqual(terrain.flat_equivalent_km(10, 400, 400), 10.8197, places=4)     # 8 %
        self.assertAlmostEqual(terrain.flat_equivalent_km(10, 200, 200),
                               5 * (minetti(0.04) + minetti(-0.04)) / 3.6, places=9)
        self.assertAlmostEqual(terrain.flat_equivalent_km(1, 1000, 1000), 2.0891, places=4)   # clamped at 30 %
        self.assertAlmostEqual(terrain.flat_equivalent_km(10, 400, 0),
                               5 * (minetti(0.08) + minetti(0)) / 3.6, places=9)              # climb only
        self.assertEqual(terrain.flat_equivalent_km(0, 100, 100), 0)

    def test_workouts(self):
        w = work("trail_long", 1)                                       # 40 m/km of climbing
        self.assertAlmostEqual(terrain.workout_flat_km(w),
                               terrain.flat_equivalent_km(w.km, 40 * w.km, 40 * w.km))
        self.assertAlmostEqual(terrain.workout_flat_km(w) / w.km, 1.0820, places=3)
        self.assertAlmostEqual(terrain.workout_flat_km(work("hilly_long", 1)) / work("hilly_long", 1).km,
                               1.0206, places=3)
        self.assertEqual(terrain.workout_flat_km(work("easy", 2)), 5.0)   # flat: unchanged


def summary_run(day, minutes, hr):
    return {"date": f"{day} 07:00:00", "type": "running", "dist": 5000, "dur": minutes * 60, "avgHr": hr}


class Load(unittest.TestCase):
    def test_step_trimp_through_metrics(self):
        w = work("cruise_tempo", 2)
        warm = w.parts[0]                                               # E, Z2 134-148
        want = metrics.trimp({"moving": warm.seconds, "avgHr": 141}, 190, 50)
        self.assertAlmostEqual(load.step_trimp(warm, 190, 50), want)
        rep = w.parts[1]
        tempo, jog = rep.steps                                          # T Z4 162-176, jog Z2
        self.assertAlmostEqual(load.step_trimp(tempo, 190, 50),
                               metrics.trimp({"moving": tempo.seconds, "avgHr": 169}, 190, 50))
        total = (load.step_trimp(warm, 190, 50) + 3 * (load.step_trimp(tempo, 190, 50) + load.step_trimp(jog, 190, 50))
                 + load.step_trimp(w.parts[2], 190, 50))
        self.assertAlmostEqual(load.workout_trimp(w, 190, 50), total)

    def test_repeat_counts_and_last_rest(self):
        w = work("cruise_tempo", 5)                                     # 1 x 5000 m: no recovery
        steps = load.flat_steps(w)
        self.assertEqual([(s.role, n) for s, n in steps], [("warmup", 1), ("rep", 1), ("recovery", 0),
                                                            ("cooldown", 1)])
        self.assertAlmostEqual(sum(s.seconds * n for s, n in steps), w.seconds)
        w = work("r_220", 3)
        self.assertAlmostEqual(sum(s.seconds * n for s, n in load.flat_steps(w)), w.seconds)

    def test_hr_from_the_zone(self):
        # no HR target (open): the pace zone's usual HR zone; no zone either: no load
        s = model.Step("rep", "Run", "dist", 1000, zone="E", pace=model.PaceRange(360, 380))
        self.assertEqual(load.hr_mid(s, 190, 50), 141)
        self.assertEqual(load.hr_mid(model.Step("rep", "Run", "time", 600, est_pace=400), 190, 50), None)
        self.assertEqual(load.step_trimp(model.Step("rep", "Run", "time", 600, est_pace=400), 190, 50), 0)
        trail = work("trail_long", 1)
        self.assertEqual(load.hr_mid(trail.parts[1], 190, 50), (120 + 162) / 2)    # Z3 cap: Z1 low to Z3 high

    def test_projected_daily(self):
        d = date(2024, 6, 11)
        days = [(d, work("easy", 2)), (d, work("easy", 1)), (d + timedelta(days=2), work("r_220", 1))]
        got = load.projected_daily(days, 190, 50)
        i = metrics.day_index(d.isoformat())
        self.assertEqual(sorted(got), [i, i + 2])
        self.assertAlmostEqual(got[i], load.workout_trimp(work("easy", 2), 190, 50)
                               + load.workout_trimp(work("easy", 1), 190, 50))


class Acwr(unittest.TestCase):
    def test_daily_load(self):
        runs = [summary_run("2024-05-01", 40, 140), summary_run("2024-05-01", 20, 150),
                summary_run("2024-05-03", 30, 0), {"date": "bad", "dur": 600, "avgHr": 150}]
        daily = history.daily_load(runs, 190, 50)
        i = metrics.day_index("2024-05-01")
        self.assertEqual(sorted(daily), [i, i + 2])                      # every dated run, even at 0 load
        self.assertAlmostEqual(daily[i], metrics.trimp(runs[0], 190, 50) + metrics.trimp(runs[1], 190, 50))
        self.assertEqual(daily[i + 2], 0)
        # the page clamps resting HR to max - 20 before computing TRIMP
        self.assertAlmostEqual(history.daily_load(runs[:1], 150, 140)[i], metrics.trimp(runs[0], 150, 130))

    def test_matches_the_page_formula(self):
        # training.js: acwr(day) = sum(day-6 .. day) / (sum(day-27 .. day) / 4), null before 28 days
        start = metrics.day_index("2024-04-01")
        daily = {start + k: float(10 + k % 7 * 3 + k // 5) for k in range(0, 40) if k % 3}
        day = start + 39
        week = sum(daily.get(d, 0) for d in range(day - 6, day + 1))
        month = sum(daily.get(d, 0) for d in range(day - 27, day + 1))
        self.assertAlmostEqual(history.acwr(daily, day), week / (month / 4))
        self.assertGreater(min(daily), start)                           # the first run is on day 1
        first = min(daily)
        self.assertIsNotNone(history.acwr(daily, first + 27))          # exactly 28 days
        self.assertIsNone(history.acwr(daily, first + 26))             # short history: None
        self.assertIsNone(history.acwr({}, day))
        self.assertIsNone(history.acwr({first: 0.0, first + 30: 0.0}, first + 30))    # no chronic load


if __name__ == "__main__":
    unittest.main()
