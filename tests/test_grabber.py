"""Grabber unit tests (standard library only): python -m unittest discover -s tests"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_grab import activities, export, garmin, gpx, rhr, wellness  # noqa: E402

GPX = b"""<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:ns3="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
<trk><trkseg>
<trkpt lat="45.0010" lon="7.0"><ele>210.5</ele><time>2024-05-01T07:00:20Z</time></trkpt>
<trkpt lat="45.0000" lon="7.0"><ele>210.0</ele><time>2024-05-01T07:00:00Z</time>
  <extensions><ns3:TrackPointExtension><ns3:hr>140</ns3:hr></ns3:TrackPointExtension></extensions></trkpt>
<trkpt lat="45.0005" lon="7.0"><time>2024-05-01T07:00:05Z</time></trkpt>
<trkpt lat="45.0020" lon="7.0"><ele>211</ele><time>2024-05-01T07:00:31Z</time></trkpt>
<trkpt lat="45.0030" lon="7.0"><ele>212</ele></trkpt>
</trkseg></trk></gpx>"""


def act(aid, day, key="running", **kw):
    return {"activityId": aid, "startTimeLocal": f"{day} 07:00:00",
            "activityType": {"typeKey": key}, **kw}


class Activities(unittest.TestCase):
    def test_is_run(self):
        self.assertTrue(activities.is_run(act(1, "2024-01-01", "trail_running")))
        self.assertTrue(activities.is_run(act(1, "2024-01-01", "treadmill_running")))
        self.assertFalse(activities.is_run(act(1, "2024-01-01", "cycling")))
        self.assertFalse(activities.is_run({}))

    def test_has_gps(self):
        self.assertTrue(activities.has_gps(act(1, "2024-01-01")))
        self.assertFalse(activities.has_gps(act(1, "2024-01-01", "treadmill_running")))
        self.assertFalse(activities.has_gps(act(1, "2024-01-01", "indoor_running")))
        self.assertFalse(activities.has_gps(act(1, "2024-01-01", hasPolyline=False)))


class Gpx(unittest.TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(gpx.haversine(45, 7, 46, 7), 111195, delta=5)

    def test_parse_sorts_and_skips_points_without_time(self):
        pts = gpx.parse_gpx(GPX)
        self.assertEqual([p[0] - pts[0][0] for p in pts], [0, 5, 20, 31])
        self.assertEqual(pts[0][3:], (210.0, 140))
        self.assertEqual(pts[1][3:], (None, None))

    def test_stream_samples_every_10_s_and_keeps_last_point(self):
        s = gpx.to_stream(gpx.parse_gpx(GPX))
        self.assertEqual(s["t"], [0, 20, 31])
        self.assertEqual(s["hr"], [140, 0, 0])
        self.assertEqual(s["e"], [2100, 2105, 2110])
        self.assertAlmostEqual(s["d"][-1], 222, delta=1)

    def test_stream_scales_to_garmin_distance_only_when_close(self):
        pts = gpx.parse_gpx(GPX)
        self.assertEqual(gpx.to_stream(pts, 233)["d"][-1], 233)
        self.assertEqual(gpx.to_stream(pts, 400)["d"][-1], 222)

    def test_too_short(self):
        self.assertIsNone(gpx.to_stream(gpx.parse_gpx(GPX)[:1]))


class Export(unittest.TestCase):
    def test_summary_fields(self):
        rec = export.summary_fields(act(5, "2024-05-01", distance=10012.346, averageHR=141.27,
                                        hrTimeInZone_2=600.4, aerobicTrainingEffect=3.1))
        self.assertEqual((rec["id"], rec["type"], rec["dist"], rec["avgHr"], rec["te"]),
                         (5, "running", 10012.35, 141.27, 3.1))
        self.assertEqual(rec["hrz"], [0, 600, 0, 0, 0])
        self.assertIsNone(export.summary_fields(act(6, "2024-05-02"))["hrz"])

    def test_event_type(self):
        self.assertEqual(export.summary_fields(act(5, "2024-05-01", eventType={"typeKey": "race"}))["event"], "race")
        self.assertIsNone(export.summary_fields(act(6, "2024-05-02"))["event"])
        self.assertIsNone(export.summary_fields(act(7, "2024-05-02", eventType="race"))["event"])

    def test_build_runs(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "gpx").mkdir()
            (out / "gpx" / "2.gpx").write_bytes(GPX)
            (out / "gpx" / "3.gpx").write_bytes(b"")          # failed download
            (out / "rhr.json").write_text('{"2024-05-02": 48, "2024-05-01": 49}')
            (out / "hrv.json").write_text('{"2024-05-02": "LOW", "2024-05-01": "BALANCED"}')
            (out / "readiness.json").write_text('{"2024-05-02": {"level": "LOW", "score": 20}}')
            acts = {"2": act(2, "2024-05-01"), "1": act(1, "2023-01-01", "treadmill_running"),
                    "3": act(3, "2024-06-01")}
            with mock.patch("builtins.print"):
                export.build_runs(out, acts)
            data = json.loads((out / "runs.json").read_text())
            self.assertEqual(data["format"], "garmin-runs/1")
            self.assertEqual([r["id"] for r in data["runs"]], [1, 2, 3])
            self.assertEqual(data["runs"][1]["t"], [0, 20, 31])
            self.assertNotIn("t", data["runs"][0])
            self.assertNotIn("t", data["runs"][2])
            self.assertEqual(data["rhr"], [["2024-05-01", 49], ["2024-05-02", 48]])
            self.assertEqual(data["hrv"], [["2024-05-01", "BALANCED"], ["2024-05-02", "LOW"]])
            self.assertEqual(data["readiness"], [["2024-05-02", {"level": "LOW", "score": 20}]])
            self.assertIn("event", data["runs"][0])
            self.assertTrue((out / "cache" / "2.json").exists())

    def test_build_runs_without_wellness(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "gpx").mkdir()
            with mock.patch("builtins.print"):
                export.build_runs(out, {"1": act(1, "2024-05-01")})
            data = json.loads((out / "runs.json").read_text())
            self.assertEqual((data["rhr"], data["hrv"], data["readiness"]), ([], [], []))


class FakeGarmin:
    def __init__(self, pages=(), rhr_rows=None):
        self.pages, self.rhr_rows, self.calls = list(pages), rhr_rows or {}, []

    def get_activities(self, start, limit):
        i = start // limit
        return self.pages[i] if i < len(self.pages) else []

    def get_rhr_daily(self, start, end):
        self.calls.append((start, end))
        return [{"calendarDate": k, "value": v} for k, v in self.rhr_rows.items() if start <= k <= end]


@mock.patch("time.sleep")
@mock.patch("builtins.print")
class Listing(unittest.TestCase):
    def test_stops_at_first_page_all_known(self, *_):
        pages = [[act(3, "2024-03-01"), act(9, "2024-02-15", "cycling")],
                 [act(2, "2024-02-01")], [act(1, "2024-01-01")]]
        with mock.patch.object(garmin, "PAGE", 2):
            found, seen = garmin.list_new_activities(FakeGarmin(pages), {"2"}, None, False)
        self.assertEqual(set(found), {"3", "2"})        # runs on the stop page are kept
        self.assertEqual(seen, {"3", "9", "2"})         # page 3 was never fetched

    def test_full_scan_and_since(self, *_):
        pages = [[act(3, "2024-03-01"), act(2, "2024-02-01")], [act(1, "2023-12-31")]]
        with mock.patch.object(garmin, "PAGE", 2):
            found, _ = garmin.list_new_activities(FakeGarmin(pages), {"3", "2"}, "2024-01-01", True)
        self.assertEqual(set(found), {"3", "2"})

    def test_with_retry(self, *_):
        fn = mock.Mock(side_effect=[RuntimeError("boom"), "ok"])
        self.assertEqual(garmin.with_retry(fn, 1), "ok")
        with self.assertRaises(RuntimeError):
            garmin.with_retry(mock.Mock(side_effect=RuntimeError("x")), tries=2)


@mock.patch("time.sleep")
@mock.patch("builtins.print")
class RestingHr(unittest.TestCase):
    def test_first_fetch_in_chunks(self, *_):
        first = (date.today() - timedelta(days=500)).isoformat()
        g = FakeGarmin(rhr_rows={first: 50.4, "1999-01-01": 70})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rhr.json"
            rhr.update_rhr(g, path, first)
            self.assertEqual(json.loads(path.read_text()), {first: 50})
        self.assertEqual(len(g.calls), 2)
        self.assertEqual(g.calls[0][0], first)
        self.assertEqual(g.calls[-1][1], date.today().isoformat())

    def test_refreshes_last_week(self, *_):
        last = date.today() - timedelta(days=3)
        g = FakeGarmin()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rhr.json"
            path.write_text(json.dumps({last.isoformat(): 47}))
            rhr.update_rhr(g, path, "2010-01-01")
        self.assertEqual(g.calls, [((last - timedelta(days=7)).isoformat(), date.today().isoformat())])

    def test_old_library_is_skipped(self, *_):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rhr.json"
            rhr.update_rhr(object(), path, "2024-01-01")
            self.assertFalse(path.exists())


class FakeWellness:
    """A client with the HRV range and the per-day readiness calls (shapes as parsed by wellness.py)."""

    def __init__(self, hrv=None, ready=None):
        self.hrv, self.ready, self.hrv_calls, self.ready_calls = hrv or {}, ready or {}, [], []

    def get_hrv_data_range(self, start, end):
        self.hrv_calls.append((start, end))
        return {"hrvSummaries": [{"calendarDate": k, "status": v} for k, v in self.hrv.items() if start <= k <= end]}

    def get_training_readiness(self, cdate):
        self.ready_calls.append(cdate)
        v = self.ready.get(cdate)
        return [] if v is None else [{"calendarDate": cdate, "level": v[0], "score": v[1]}]


class HrvOnly:
    def __init__(self):
        self.calls = []

    def get_hrv_data_range(self, start, end):
        self.calls.append((start, end))
        return [{"calendarDate": start, "status": "UNBALANCED"}, {"calendarDate": end}, "junk"]


@mock.patch("time.sleep")
@mock.patch("builtins.print")
class Wellness(unittest.TestCase):
    def run_in(self, g, first, hrv=None, ready=None):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            if hrv is not None:
                (out / "hrv.json").write_text(json.dumps(hrv))
            if ready is not None:
                (out / "readiness.json").write_text(json.dumps(ready))
            wellness.update_wellness(g, out, first)
            return {name: json.loads((out / name).read_text()) if (out / name).exists() else None
                    for name in ("hrv.json", "readiness.json")}

    def test_first_fetch(self, *_):
        today = date.today()
        first = (today - timedelta(days=100)).isoformat()
        y = (today - timedelta(days=1)).isoformat()
        g = FakeWellness(hrv={first: "BALANCED", y: "LOW"}, ready={y: ("LOW", 22)})
        got = self.run_in(g, first)
        self.assertEqual(got["hrv.json"], {first: "BALANCED", y: "LOW"})
        self.assertEqual(got["readiness.json"], {y: {"level": "LOW", "score": 22}})
        # HRV in chunks from the first day to today
        self.assertEqual(g.hrv_calls[0][0], first)
        self.assertEqual(g.hrv_calls[-1][1], today.isoformat())
        self.assertGreater(len(g.hrv_calls), 1)
        self.assertTrue(all(date.fromisoformat(b) - date.fromisoformat(a) < timedelta(days=wellness.HRV_CHUNK_DAYS)
                            for a, b in g.hrv_calls))
        # readiness: one request a day, at most the last READINESS_FIRST_DAYS days
        self.assertEqual(len(g.ready_calls), wellness.READINESS_FIRST_DAYS)
        self.assertEqual(g.ready_calls[-1], today.isoformat())

    def test_refreshes_last_week(self, *_):
        today = date.today()
        last = today - timedelta(days=3)
        g = FakeWellness()
        self.run_in(g, "2010-01-01", hrv={last.isoformat(): "BALANCED"},
                    ready={last.isoformat(): {"level": "HIGH", "score": 80}})
        start = (last - timedelta(days=wellness.WELLNESS_REFRESH_DAYS)).isoformat()
        self.assertEqual(g.hrv_calls, [(start, today.isoformat())])
        self.assertEqual(g.ready_calls[0], start)
        self.assertEqual(len(g.ready_calls), 11)

    def test_long_gap_capped(self, *_):
        old = (date.today() - timedelta(days=400)).isoformat()
        g = FakeWellness()
        self.run_in(g, "2010-01-01", ready={old: {"level": "HIGH", "score": 80}})
        self.assertEqual(len(g.ready_calls), wellness.READINESS_FIRST_DAYS)

    def test_missing_methods(self, *_):
        got = self.run_in(object(), "2024-01-01")
        self.assertEqual(got, {"hrv.json": None, "readiness.json": None})
        g = HrvOnly()                                  # no readiness method: HRV still fetched
        got = self.run_in(g, date.today().isoformat())
        self.assertEqual(got["hrv.json"], {date.today().isoformat(): "UNBALANCED"})
        self.assertIsNone(got["readiness.json"])

    def test_no_first_day(self, *_):
        g = FakeWellness()
        self.assertEqual(self.run_in(g, None), {"hrv.json": None, "readiness.json": None})
        self.assertEqual((g.hrv_calls, g.ready_calls), ([], []))

    def test_errors_and_odd_shapes(self, *_):
        class Broken(FakeWellness):
            def get_hrv_data_range(self, start, end):
                raise RuntimeError("boom")

            def get_training_readiness(self, cdate):
                return {"level": "MODERATE"}
        today = date.today().isoformat()
        got = self.run_in(Broken(), today)
        self.assertEqual(got["hrv.json"], {})
        self.assertEqual(got["readiness.json"], {today: {"level": "MODERATE", "score": None}})

    def test_parsers(self, *_):
        self.assertEqual(wellness.hrv_statuses({"hrvSummaries": [{"calendarDate": "2024-01-01", "status": "LOW"}]}),
                         {"2024-01-01": "LOW"})
        self.assertEqual(wellness.hrv_statuses({"hrvSummary": {"calendarDate": "2024-01-02", "status": "BALANCED"}}),
                         {"2024-01-02": "BALANCED"})
        self.assertEqual(wellness.hrv_statuses(None), {})
        self.assertEqual(wellness.readiness_entry([{"level": "HIGH", "score": 81.4}]), {"level": "HIGH", "score": 81})
        self.assertEqual(wellness.readiness_entry({"score": 40}), {"level": None, "score": 40})
        self.assertIsNone(wellness.readiness_entry([]))
        self.assertIsNone(wellness.readiness_entry("x"))
        self.assertIsNone(wellness.readiness_entry({"unexpected": True}))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Bundle(unittest.TestCase):
    """The single-file garmin_grab.py built by tools/build.py behaves like the package."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "garmin_grab.py"
        cls.path.write_text(load("build", ROOT / "tools" / "build.py").bundle_grabber(), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_bundle_has_the_package_functions(self):
        mod = load("bundled", self.path)
        for m in (activities, export, garmin, gpx, rhr, wellness):
            for name in dir(m):
                if callable(getattr(m, name)) and getattr(getattr(m, name), "__module__", "") == m.__name__:
                    self.assertTrue(hasattr(mod, name), name)
        self.assertEqual(mod.to_stream(mod.parse_gpx(GPX)), gpx.to_stream(gpx.parse_gpx(GPX)))

    def test_module_order(self):
        build = load("build", ROOT / "tools" / "build.py")
        self.assertLess(build.MODULES.index("rhr"), build.MODULES.index("wellness"))
        self.assertLess(build.MODULES.index("wellness"), build.MODULES.index("export"))

    def test_bundle_runs(self):
        r = subprocess.run([sys.executable, str(self.path), "--help"],
                           capture_output=True, text=True, check=True)
        self.assertIn("--rebuild", r.stdout)


class BuildChecks(unittest.TestCase):
    """tools/build.py refuses packages that would break once flattened into one namespace."""

    def bundle(self, **modules):
        build = load("build", ROOT / "tools" / "build.py")
        with tempfile.TemporaryDirectory() as d:
            build.PKG, build.MODULES = Path(d), list(modules)
            (build.PKG / "__init__.py").write_text('"""doc"""\n')
            for name, src in modules.items():
                (build.PKG / f"{name}.py").write_text(src)
            return build.bundle_grabber()

    def assertFails(self, **modules):
        with self.assertRaises(SystemExit):
            self.bundle(**modules)

    def test_keeps_aliases(self):
        out = self.bundle(a="from datetime import date as d\nX = d.today\n")
        self.assertIn("from datetime import date as d\n", out)

    def test_nested_relative_import(self):
        self.assertFails(a="X = 1\n", b="def f():\n    from .a import X\n    return X\n")

    def test_import_from_a_later_module(self):
        self.assertFails(a="from .b import X\n", b="X = 1\n")

    def test_duplicate_definitions(self):
        self.assertFails(a="X: int = 1\n", b="X, Y = 1, 2\n")

    def test_definition_shadows_an_import(self):
        self.assertFails(a="import time\n", b="def time():\n    pass\n")

    def test_same_name_imported_from_two_places(self):
        self.assertFails(a="import time\n", b="from datetime import time\n")
        self.bundle(a="import time\n", b="import time\n")


if __name__ == "__main__":
    unittest.main()
