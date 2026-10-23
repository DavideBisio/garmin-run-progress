"""Workout templates, resolved model, markdown renderer and plan.json (TC-7, standard library only).

Regenerate the golden file after a reviewed change: UPDATE_GOLDEN=1 python -m unittest tests.test_workouts
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import model, physiology, plan_io, profile, render_md, templates  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "workouts_golden.md"
DANIELS = json.loads((FIXTURES / "daniels_paces.json").read_text(encoding="utf-8"))
RULES = physiology.load_rules()
TODAY = date(2024, 6, 5)   # a Wednesday: plans start on Monday 2024-06-10


def generic_profile(**kw):
    """The fixed generic runner of the golden file: VDOT 40, HR 190/50."""
    vals = dict(hr_max=190, hr_rest=50, vdot=40.0, km_4w=0.0, km_12w=0.0, runs_per_week=0.0, longest_8w=0.0)
    vals.update(kw)
    return profile.Profile(**vals)


def write(text, name="profile.toml"):
    d = tempfile.mkdtemp()
    p = Path(d) / name
    p.write_text(text, encoding="utf-8")
    return p


R = model.PaceRange(240, 250)       # mid 245 s/km
E = model.PaceRange(360, 380)       # mid 370 s/km


def rep(m=400):
    return model.Step("rep", "Rep", "dist", m, zone="R", pace=R, hr=model.HrRange(162, 190), hr_zone="Z4-5",
                      hard=True)


def rec(m=200):
    return model.Step("recovery", "Recovery", "dist", m, zone="jog", est_pace=420, hr=model.HrRange(134, 148),
                      hr_zone="Z2")


def easy(role, m=1000):
    return model.Step(role, role.title(), "dist", m, zone="E", pace=E, hr=model.HrRange(134, 148), hr_zone="Z2")


class Model(unittest.TestCase):
    def test_totals_are_summed_from_parts(self):
        w = model.Workout("x", 1, "X", "R", [easy("warmup"), model.Repeat(4, [rep(), rec()]), easy("cooldown")])
        self.assertAlmostEqual(w.km, 1 + 4 * 0.6 + 1)
        self.assertAlmostEqual(w.seconds, 370 + 4 * (0.4 * 245 + 0.2 * 420) + 370)
        self.assertAlmostEqual(w.hard_km, 1.6)

    def test_last_recovery(self):
        counted = model.Repeat(4, [rep(), rec()])
        skipped = model.Repeat(4, [rep(), rec()], skip_last_rest=True)
        self.assertFalse(counted.skip_last_rest)        # the default: the last recovery counts
        self.assertAlmostEqual(counted.meters, 2400)
        self.assertAlmostEqual(skipped.meters, 2200)
        self.assertAlmostEqual(counted.seconds - skipped.seconds, 0.2 * 420)
        self.assertAlmostEqual(skipped.hard_meters, 1600)

    def test_time_and_lap_ends(self):
        t = model.Step("recovery", "Recovery", "time", 60, zone="jog", est_pace=300)
        self.assertAlmostEqual((t.meters, t.seconds), (200, 60))
        lap = model.Step("recovery", "Back", "lap", None, est_time=90, est_dist=150)
        self.assertEqual((lap.meters, lap.seconds), (150, 90))

    def test_pace_range_order(self):
        with self.assertRaises(ValueError):
            model.PaceRange(250, 240)
        slow_mps, fast_mps = R.to_speed()
        self.assertAlmostEqual(slow_mps, 1000 / 250)
        self.assertAlmostEqual(fast_mps, 1000 / 240)
        self.assertLess(slow_mps, fast_mps)
        self.assertEqual(R.mid, 245)
        with self.assertRaises(ValueError):
            model.HrRange(150, 140)

    def test_repeat_of_one_renders_as_plain_steps(self):
        md = render_md.render_workout(model.Workout("x", 1, "X", "R", [model.Repeat(1, [rep(), rec()])]))
        self.assertNotIn("Repeat 1x", md)
        self.assertNotIn("↳", md)
        self.assertIn("| **Rep** |", md)
        self.assertIn("| **Recovery** | Jog |", md)


BASE = """
[[workout]]
id = "t1"
title = "Test"
kind = "T"
min_level = "novice"
warmup = { pace = "E", dist = 1000 }
main = [ { repeat = "n", rep = { pace = "T", dist = "d" }, recovery = { time = 60 } } ]
cooldown = { pace = "E", dist = 1000 }
ladder = [ { n = 2, d = 1000 }, { n = 3, d = 1000 } ]
"""


class Templates(unittest.TestCase):
    def load(self, text):
        return templates.load_templates(write(text, "workouts.toml"))

    def test_base_template_and_defaults(self):
        t = self.load(BASE)["t1"]
        w = templates.instantiate(t, 2, generic_profile(), RULES)
        rpt = w.parts[1]
        self.assertEqual(rpt.n, 3)
        r, rc = rpt.steps
        self.assertEqual((r.role, r.zone, r.hr), ("rep", "T", model.HrRange(162, 176)))   # T defaults to Z4
        self.assertEqual((rc.role, rc.zone, rc.pace, rc.hr), ("recovery", "jog", None, model.HrRange(134, 148)))
        for v in (0, 3):
            with self.assertRaises(templates.TemplateError):
                templates.instantiate(t, v, generic_profile(), RULES)

    def test_validation_errors(self):
        bad = {
            "unknown pace zone": BASE.replace('pace = "T"', 'pace = "X"'),
            "unknown hr zone": BASE.replace('pace = "T"', 'pace = "T", hr = "Z7"'),
            "ladder missing a variable": BASE.replace("{ n = 3, d = 1000 }", "{ n = 3 }"),
            "time end, pace target, no estimate": BASE.replace('pace = "T", dist = "d"', 'pace = "T", time = 300'),
            "duplicate id": BASE + BASE,
            "unknown kind": BASE.replace('kind = "T"', 'kind = "Q"'),
            "unknown min_level": BASE.replace('min_level = "novice"', 'min_level = "elite"'),
            "no end": BASE.replace('cooldown = { pace = "E", dist = 1000 }', 'cooldown = { pace = "E" }'),
            "two ends": BASE.replace('cooldown = { pace = "E", dist = 1000 }',
                                     'cooldown = { pace = "E", dist = 1000, time = 60 }'),
            "unknown key": BASE.replace('cooldown = { pace = "E", dist = 1000 }',
                                        'cooldown = { pace = "E", distance = 1000 }'),
            "empty ladder": BASE.replace("ladder = [ { n = 2, d = 1000 }, { n = 3, d = 1000 } ]", "ladder = []"),
        }
        for why, text in bad.items():
            with self.assertRaises(templates.TemplateError, msg=why):
                self.load(text)
        # an estimate makes the time-ended pace step valid
        self.load(BASE.replace('pace = "T", dist = "d"', 'pace = "T", time = 300, est_pace = "T"'))

    def test_library_loads(self):
        lib = templates.load_templates()
        self.assertGreaterEqual(len(lib), 13)
        for t in lib.values():
            for v in range(1, len(t["ladder"]) + 1):
                w = templates.instantiate(t, v, generic_profile(), RULES)
                self.assertGreater(w.km, 0, (t["id"], v))
                self.assertGreater(w.seconds, 0, (t["id"], v))
            if len(t["ladder"]) > 1:
                first = templates.instantiate(t, 1, generic_profile(), RULES)
                last = templates.instantiate(t, len(t["ladder"]), generic_profile(), RULES)
                self.assertLess(first.km, last.km + 1e-9, f"{t['id']}: ladder must be smallest first")

    def test_bands(self):
        # E ranges sit inside Daniels' published E ranges
        for v, want in DANIELS["paces"].items():
            got = templates.pace_range("E", physiology.pace_zones(float(v)), RULES)
            fast, slow = want["E"]
            self.assertTrue(fast <= got.fast_s and got.slow_s <= slow, f"VDOT {v}: {got}")
        paces = physiology.pace_zones(40.0)
        for z in "EMTIR":
            got = templates.pace_range(z, paces, RULES)
            self.assertTrue(got.fast_s <= paces[z] <= got.slow_s, z)
        self.assertEqual(templates.jog_pace(paces, RULES), templates.pace_range("E", paces, RULES).slow_s + 30)

    def test_hr_ranges(self):
        # 190/50: Z1-Z4 tops 134, 148, 162, 176; Z1 starts at 50% HRR, Z5 ends at max
        self.assertEqual(templates.hr_range("Z1", 190, 50), model.HrRange(120, 134))
        self.assertEqual(templates.hr_range("Z2", 190, 50), model.HrRange(134, 148))
        self.assertEqual(templates.hr_range("Z4-5", 190, 50), model.HrRange(162, 190))
        self.assertEqual(templates.hr_range("Z3 cap", 190, 50), model.HrRange(120, 162))
        for spec in ("Z0", "Z6", "Z5-4", "Z2-6", "zone 2", "Z2 max"):
            with self.assertRaises(templates.TemplateError, msg=spec):
                templates.hr_range(spec, 190, 50)


class Render(unittest.TestCase):
    def test_golden(self):
        lib = templates.load_templates()
        sections = []
        for t in lib.values():
            for v in sorted({1, len(t["ladder"])}):
                sections.append(render_md.render_workout(templates.instantiate(t, v, generic_profile(), RULES)))
        got = "\n".join(sections)
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.write_text(got, encoding="utf-8", newline="\n")
        self.assertEqual(got, GOLDEN.read_text(encoding="utf-8"))

    def test_format(self):
        t = templates.load_templates()["r_220"]
        md = render_md.render_workout(templates.instantiate(t, 1, generic_profile(), RULES))
        lines = md.splitlines()
        self.assertRegex(lines[0], r"^### .+ - \d+\.\d km \(~[^)]+\)$")
        self.assertIn("| Lap | Pace range | FC range | Duration | Comment |", lines)
        self.assertTrue(any(ln.startswith("| **Repeat ") and "x** |" in ln for ln in lines), md)
        self.assertTrue(any(ln.startswith("| ↳ **Rep** |") for ln in lines), md)
        self.assertTrue(any(ln.startswith("| ↳ **Recovery** | Jog |") for ln in lines), md)
        # every table row has the same number of cells
        rows = [ln for ln in lines if ln.startswith("|")]
        self.assertEqual({ln.replace("\\|", "").count("|") for ln in rows}, {6})

    def test_pipe_escaping(self):
        s = model.Step("rep", "A|B", "dist", 1000, zone="E", pace=E, note="hills | flats")
        md = render_md.render_workout(model.Workout("x", 1, "Up|Down", "E", [s]))
        self.assertIn("Up\\|Down", md)
        self.assertIn("A\\|B", md)
        self.assertIn("hills \\| flats", md)

    def test_duration_format(self):
        f = render_md.fmt_est
        self.assertEqual([f(45), f(59.4), f(59.6), f(390), f(599), f(1860), f(3599), f(5460)],
                         ["~45 s", "~59 s", "~1:00", "~6:30", "~9:59", "~31 min", "~1:00", "~1:31"])


WEEK = '[week]\ntue = "r_220:1"\n"Thu" = "easy:2"   # a comment\nsun = "steady_long:1"\n'


class Schedule(unittest.TestCase):
    def build(self, text, weeks=2):
        prof = profile.load_profile(write("vdot = 40\nhr_max = 190\nhr_rest = 50\n" + text), [], [], TODAY)
        return plan_io.build_plan(prof, templates.load_templates(), RULES, TODAY, weeks)

    def test_week_table(self):
        prof = profile.load_profile(write(WEEK), [], [], TODAY)
        self.assertEqual(list(prof.week), ["tue", "thu", "sun"])
        self.assertEqual(prof.week["thu"]["id"], "easy")
        self.assertEqual(prof.week["thu"]["variant"], 2)
        self.assertEqual(prof.week["thu"]["line"], '"Thu" = "easy:2"   # a comment')

    def test_unknown_template_or_variant(self):
        for line in ('tue = "nope:1"', 'tue = "r_220:99"', 'tue = "r_220:0"'):
            with self.assertRaises(profile.ProfileError, msg=line) as cm:
                self.build(f"[week]\n{line}\n")
            self.assertIn(line, str(cm.exception))
        for line in ('tue = "r_220"', "tue = 3", 'funday = "easy:1"'):
            with self.assertRaises(profile.ProfileError, msg=line) as cm:
                self.build(f"[week]\n{line}\n")
            if "funday" not in line:
                self.assertIn(line, str(cm.exception))
        with self.assertRaises(profile.ProfileError):
            self.build("")      # no [week] table

    def test_plan(self):
        plan = self.build(WEEK)
        self.assertEqual(plan["version"], 1)
        self.assertEqual([w["start"] for w in plan["weeks"]], ["2024-06-10", "2024-06-17"])
        days = plan["weeks"][0]["days"]
        self.assertEqual([d["date"] for d in days], ["2024-06-11", "2024-06-13", "2024-06-16"])
        self.assertTrue(all(d["slot"] is None for d in days))
        self.assertAlmostEqual(plan["weeks"][0]["target_km"], sum(d["workout"]["km"] for d in days), places=1)
        rep = next(s for s in days[0]["workout"]["steps"] if s["type"] == "repeat")
        self.assertFalse(rep["skip_last_rest"])
        r = rep["steps"][0]
        self.assertLess(r["pace_s_per_km"][0], r["pace_s_per_km"][1])     # [fast, slow]
        # JSON round trip renders the same markdown as the in-memory plan
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.json"
            plan_io.write_plan(plan, p)
            back = plan_io.read_plan(p)
        self.assertEqual(back, json.loads(json.dumps(plan)))
        md = render_md.render_plan(back)
        self.assertIn("## Week of 2024-06-10", md)
        self.assertIn("### Tue 2024-06-11", md)

    def test_profile_hash(self):
        h = plan_io.profile_hash(generic_profile(), RULES)
        self.assertEqual(h, plan_io.profile_hash(generic_profile(km_4w=30.0), RULES))   # volume isn't hashed
        self.assertNotEqual(h, plan_io.profile_hash(generic_profile(vdot=41.0), RULES))
        self.assertNotEqual(h, plan_io.profile_hash(generic_profile(hr_rest=48), RULES))
        self.assertRegex(h, r"^[0-9a-f]{64}$")


class CliPlan(unittest.TestCase):
    def plan(self, d, check=True):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        return subprocess.run([sys.executable, "-m", "garmin_plan", "plan", "--weeks", "2", "--export", d,
                               "--today", TODAY.isoformat()],
                              capture_output=True, text=True, encoding="utf-8", env=env, check=check)

    def test_plan_command(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text("vdot = 40\n" + WEEK, encoding="utf-8")
            self.plan(d)
            plan = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))
            md = (Path(d) / "plan.md").read_text(encoding="utf-8")
        self.assertEqual(plan["version"], 1)
        self.assertEqual(len(plan["weeks"]), 2)
        self.assertIn("↳ **Rep**", md)

    def test_errors_quote_the_line(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.toml").write_text('[week]\nsat = "tempo_run:1"\n', encoding="utf-8")
            res = self.plan(d, check=False)
            self.assertFalse((Path(d) / "plan.json").exists())
        self.assertNotEqual(res.returncode, 0)
        last = res.stderr.strip().splitlines()[-1]     # after the profile's default warnings
        self.assertTrue(last.startswith("error: "), res.stderr)
        self.assertIn('sat = "tempo_run:1"', last)
        self.assertNotIn("Traceback", res.stderr)


# The workout shapes of the hand-written personal plan (garmin_export/training_plan.md, gitignored and
# never read here), each with the template that expresses it.
SHAPES = {
    "220 m reps": "r_220",
    "300 m reps": "r_300",
    "ladder": "r_ladder",
    "cruise tempo": "cruise_tempo",
    "VO2 intervals": "vo2_intervals",
    "easy run": "easy",
    "progression run": "progression",
    "steady long run": "steady_long",
    "progression long run": "progression_long",
    "half-marathon long run": "hm_long",
    "hill repeats": "hill_repeats",
    "hilly long run": "hilly_long",
    "trail long run": "trail_long",
}


class Coverage(unittest.TestCase):
    def test_every_shape_has_a_template(self):
        lib = templates.load_templates()
        for shape, tid in SHAPES.items():
            self.assertIn(tid, lib, shape)

    def test_hill_and_trail_use_hr_or_open_targets_on_time(self):
        lib = templates.load_templates()
        for tid in ("hill_repeats", "hilly_long", "trail_long"):
            w = templates.instantiate(lib[tid], 1, generic_profile(), RULES)
            main = [s for p in w.parts for s in (p.steps if isinstance(p, model.Repeat) else [p])
                    if s.role in ("rep", "recovery")]
            self.assertTrue(main, tid)
            self.assertTrue(all(s.pace is None for s in main), tid)
            self.assertTrue(any(s.end in ("time", "lap") for s in main), tid)
        hill = templates.instantiate(lib["hill_repeats"], 1, generic_profile(), RULES)
        self.assertGreater(hill.hard_km, 0)
        self.assertTrue(any(s.end == "lap" for p in hill.parts if isinstance(p, model.Repeat) for s in p.steps))


if __name__ == "__main__":
    unittest.main()
