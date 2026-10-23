"""Session selection and sizing, terrain and projected load (TC-10, standard library only)."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import model, physiology, profile, select, size, templates, volume  # noqa: E402

RULES = physiology.load_rules()
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
        self.assertEqual(RULES["rotation"]["level"], "intermediate")   # stopgap until 08
        self.assertEqual(q("rt", 1, level="novice"), "r_220")
        self.assertEqual(q("it", 1, level="novice"), "cruise_tempo")
        self.assertEqual(q("rt", 2, "L", level="novice"), "steady_long")
        self.assertEqual(q("rt", 1, hill_day=True, level="novice"), "r_220")    # hills are intermediate
        self.assertEqual(q("rt", 1, level="beginner"), "r_220")        # nothing fits: the lowest level
        self.assertEqual(select.candidates("rt", 2, "L", RULES, library=LIB),
                         ["progression_long", "steady_long"])


if __name__ == "__main__":
    unittest.main()
