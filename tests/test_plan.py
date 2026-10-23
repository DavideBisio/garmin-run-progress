"""Planner unit tests (standard library only): python -m unittest discover -s tests"""
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import history, metrics, physiology, profile  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
VECTORS = json.loads((FIXTURES / "metric_vectors.json").read_text(encoding="utf-8"))
DANIELS = json.loads((FIXTURES / "daniels_paces.json").read_text(encoding="utf-8"))

TODAY = date(2024, 6, 5)   # a Wednesday


def run(day, km, hour="07:00:00", **kw):
    """A summary-only run (no streams), like a treadmill run in runs.json."""
    return {"date": f"{day} {hour}", "type": "running", "dist": km * 1000, "dur": km * 330, **kw}


def stream_run(day, km, secs, max_hr=None):
    """A GPS run with a steady 10-second stream covering km in secs."""
    n = int(secs // 10) + 1
    t = [i * 10 for i in range(n)]
    d = [round(km * 1000 * i / (n - 1)) for i in range(n)]
    hr = [150] * n
    if max_hr:
        hr[n // 2:] = [max_hr] * (n - n // 2)
    return {"date": f"{day} 07:00:00", "type": "running", "dist": km * 1000, "dur": secs,
            "t": t, "d": d, "hr": hr, "e": [2000] * n}


def weekly(days_back, every=2, km=8.0):
    """One run every `every` days for the last `days_back` days before TODAY."""
    return [run(TODAY - timedelta(days=k), km) for k in range(1, days_back + 1, every)]


class MetricParity(unittest.TestCase):
    """Same numbers as src/page/js/metrics.js (tests/metrics.test.mjs checks the JS side)."""

    def test_vdot(self):
        for m, s, want in VECTORS["vdot"]:
            self.assertAlmostEqual(physiology.vdot(m, s), want, delta=1e-9)
            self.assertAlmostEqual(metrics.vdot(m, s), want, delta=1e-9)

    def test_gap_factor(self):
        for g, want in VECTORS["gapFactor"]:
            self.assertAlmostEqual(metrics.gap_factor(g), want, delta=1e-9, msg=g)

    def test_hrr_zones_exact(self):
        for hr_max, rest, want in VECTORS["hrrZones"]:
            self.assertEqual(physiology.hr_zones(hr_max, rest), want, (hr_max, rest))

    def test_week_of_and_day_index(self):
        for day, want in VECTORS["weekOf"]:
            self.assertEqual(metrics.week_of(day), want, day)
        for s, want in VECTORS["day"]:
            self.assertEqual(metrics.day_index(s), want, s)

    def test_best_effort(self):
        for v in VECTORS["bestEffort"]:
            got = metrics.best_effort(v["t"], v["d"], v["D"])
            if v["expected"] is None:
                self.assertIsNone(got, v["D"])
            else:
                self.assertAlmostEqual(got, v["expected"], delta=1e-9, msg=v["D"])

    def test_trimp(self):
        for v in VECTORS["trimp"]:
            got = metrics.trimp(v["run"], v["max"], v["rest"])
            self.assertTrue(math.isclose(got, v["expected"], rel_tol=1e-12, abs_tol=1e-9),
                            (v["run"]["date"], got, v["expected"]))


class Physiology(unittest.TestCase):
    def test_paces_match_daniels(self):
        tol = DANIELS["tolerance_s_per_km"]
        for v, want in DANIELS["paces"].items():
            got = physiology.pace_zones(float(v))
            for zone in "MTIR":
                self.assertLessEqual(abs(got[zone] - want[zone]), tol, f"VDOT {v} {zone}: {got[zone]:.1f}")
            fast, slow = want["E"]
            self.assertTrue(fast - tol <= got["E"] <= slow + tol, f"VDOT {v} E: {got['E']:.1f}")

    def test_race_time_inverts_vdot(self):
        for v in (30.0, 45.5, 60.0):
            for m in (5000, 10000, 21097.5, 42195):
                self.assertAlmostEqual(physiology.vdot(m, physiology.race_time(v, m)), v, places=6)
        # Daniels' table: VDOT 50 runs 5 km in 19:57
        self.assertLess(abs(physiology.race_time(50, 5000) - (19 * 60 + 57)), 3)

    def test_r_is_i_minus_6_s_per_400(self):
        z = physiology.pace_zones(50)
        self.assertAlmostEqual(z["I"] - z["R"], 15.0)

    def test_hr_zones_known_pair(self):
        self.assertEqual(physiology.hr_zones(190, 50), [134, 148, 162, 176])
        # .5 cases round half up, not to even
        self.assertEqual(physiology.hr_zones(185, 50), [131, 145, 158, 172])
        # rest is clamped to max - 20
        self.assertEqual(physiology.hr_zones(150, 140), [142, 144, 146, 148])


class History(unittest.TestCase):
    def test_monday_weeks(self):
        mon, sun, prev_sun = (metrics.day_index(s) for s in ("2024-01-01", "2024-01-07", "2023-12-31"))
        self.assertEqual(metrics.week_of(mon), metrics.week_of(sun))
        self.assertEqual(metrics.week_of(prev_sun), metrics.week_of(mon) - 1)
        self.assertEqual(metrics.week_start(metrics.week_of(sun)), mon)

    def test_dates_around_midnight(self):
        w = history.weekly_km([run("2024-01-07", 5, "23:59:59"), run("2024-01-08", 7, "00:00:01")])
        sunday_week = metrics.week_of(metrics.day_index("2024-01-07"))
        self.assertEqual(w[sunday_week]["km"], 5)
        self.assertEqual(w[sunday_week + 1]["km"], 7)

    def test_treadmill_runs_count(self):
        runs = [run("2024-01-02", 6, type="treadmill_running"),
                stream_run("2024-01-03", 10, 3000)]
        w = history.weekly_km(runs)[metrics.week_of(metrics.day_index("2024-01-02"))]
        self.assertEqual((w["runs"], w["km"], w["longest"]), (2, 16, 10))

    def test_zero_run_weeks_count_in_averages(self):
        # TODAY is in the week of Mon 2024-06-03; the last 4 full weeks start 2024-05-06
        runs = [run("2024-05-27", 20), run("2024-05-07", 12)] + weekly(200, every=7)[8:]
        s = history.recent_stats(runs, TODAY)
        self.assertEqual(s["km_4w"], (20 + 12) / 4)
        self.assertEqual(s["runs_per_week"], 2 / 4)

    def test_recent_stats(self):
        runs = weekly(120) + [stream_run((TODAY - timedelta(days=10)).isoformat(), 10, 2490)]
        s = history.recent_stats(runs, TODAY)
        self.assertEqual(s["longest_8w"], 10)
        self.assertGreater(s["km_12w"], 0)
        self.assertAlmostEqual(s["vdot"], physiology.vdot(10000, 2490), places=6)
        self.assertEqual(s["vdot_from"], ("10k", (TODAY - timedelta(days=10)).isoformat()))

    def test_resting_hr_median_of_last_365_days(self):
        rhr = [["2022-01-01", 70]] * 10 + [["2023-06-01", 50], ["2023-12-01", 47], ["2024-01-01", 0],
                                          ["bad", 40], ["2024-05-31", 48]]
        # anchored on the last entry: 2022 is outside the window, 0 and bad dates are skipped
        self.assertEqual(history.resting_hr(rhr), 48)
        # even count: the two middle values are averaged, then rounded half up (48.5 -> 49)
        self.assertEqual(history.resting_hr([["2024-01-01", 48], ["2024-01-02", 49]]), 49)
        self.assertEqual(history.resting_hr([["2024-01-01", 46], ["2024-01-02", 47]]), 47)
        self.assertIsNone(history.resting_hr([]))

    def test_hr_max_suggestion(self):
        runs = [stream_run("2024-01-01", 5, 1500, 181), stream_run("2024-01-02", 5, 1500, 186),
                run("2024-01-03", 5, maxHr=240), run("2024-01-04", 5, maxHr=183)]
        self.assertEqual(history.hr_max(runs), 183)   # second highest within 120-230
        self.assertIsNone(history.hr_max([run("2024-01-03", 5)]))


class Profile(unittest.TestCase):
    def write(self, text):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "profile.toml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_precedence(self):
        runs = weekly(120) + [stream_run((TODAY - timedelta(days=3)).isoformat(), 10, 2490, 181)]
        rhr = [["2024-05-01", 51], ["2024-06-01", 53]]
        p = self.write('hr_max = 192\n[race]\ndate = 2024-10-13\ndistance = "hm"\ngoal = "1:35:00"\n')
        prof = profile.load_profile(p, runs, rhr, TODAY)
        self.assertEqual((prof.hr_max, prof.sources["hr_max"]), (192, "set"))
        self.assertEqual((prof.hr_rest, prof.sources["hr_rest"]), (52, "derived"))
        self.assertEqual(prof.sources["vdot"], "derived")
        self.assertEqual(prof.sources["days"], "default")
        self.assertEqual(prof.race, {"date": date(2024, 10, 13), "distance_m": 21097.5, "goal_s": 5700})
        prof = profile.load_profile(self.write("vdot = 55.5\nhr_rest = 45\n"), runs, rhr, TODAY)
        self.assertEqual((prof.vdot, prof.sources["vdot"]), (55.5, "set"))
        self.assertEqual((prof.hr_rest, prof.sources["hr_rest"]), (45, "set"))

    def test_missing_file_and_empty_history(self):
        prof = profile.load_profile(Path(tempfile.gettempdir()) / "no-such-profile.toml", [], [], TODAY)
        self.assertEqual((prof.hr_max, prof.hr_rest), (190, 50))
        self.assertTrue(all(s == "default" for s in prof.sources.values()), prof.sources)
        self.assertTrue(any("hr_max" in w for w in prof.warnings))
        self.assertTrue(any("vdot" in w for w in prof.warnings))

    def test_short_history_gets_defaults(self):
        runs = weekly(20, every=1) + [stream_run((TODAY - timedelta(days=2)).isoformat(), 5, 1200)]
        prof = profile.load_profile(self.write(""), runs, [], TODAY)
        for key in ("vdot", "km_4w", "km_12w", "runs_per_week", "longest_8w"):
            self.assertEqual(prof.sources[key], "default", key)
        self.assertTrue(any("4 weeks" in w for w in prof.warnings))

    def test_invalid_values(self):
        for text in ("hr_max = 150\nhr_rest = 150\n", "hr_max = 140\nhr_rest = 160\n",
                     'days = ["mon", "funday"]\n', 'long_run_day = "sun"\ndays = ["mon", "wed"]\n',
                     'hr_max = "fast"\n', "hr_max = 190\n[race]\ndistance = \"hm\"\n", "not toml ["):
            with self.assertRaises(profile.ProfileError, msg=text):
                profile.load_profile(self.write(text), [], [], TODAY)

    def test_days(self):
        prof = profile.load_profile(self.write('days = ["Tue", "thu", "sat"]\nhill_days = ["thu"]\n'),
                                    [], [], TODAY)
        self.assertEqual(prof.days, ["tue", "thu", "sat"])
        self.assertEqual(prof.long_run_day, "sat")   # default sun is not available: the last day is used
        self.assertEqual(prof.hill_days, ["thu"])


class Cli(unittest.TestCase):
    def test_profile_command(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            runs = weekly(120) + [stream_run((TODAY - timedelta(days=3)).isoformat(), 10, 2490, 181)]
            (out / "runs.json").write_text(json.dumps({"format": "garmin-runs/1", "runs": runs,
                                                       "rhr": [["2024-06-01", 48]]}), encoding="utf-8")
            (out / "profile.toml").write_text("hr_max = 191\n", encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
            res = subprocess.run([sys.executable, "-m", "garmin_plan", "profile", "--export", d,
                                  "--today", TODAY.isoformat()],
                                 capture_output=True, text=True, env=env, check=True)
        self.assertIn("191 bpm", res.stdout)
        self.assertIn("set", res.stdout)
        self.assertIn("derived (training efforts)", res.stdout)
        self.assertIn("default", res.stdout)
        self.assertIn("Z1", res.stdout)
        self.assertIn("warning", res.stderr)


if __name__ == "__main__":
    unittest.main()
