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

from garmin_grab import activities, export, garmin, gpx, rhr  # noqa: E402

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

    def test_build_runs(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "gpx").mkdir()
            (out / "gpx" / "2.gpx").write_bytes(GPX)
            (out / "gpx" / "3.gpx").write_bytes(b"")          # failed download
            (out / "rhr.json").write_text('{"2024-05-02": 48, "2024-05-01": 49}')
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
            self.assertTrue((out / "cache" / "2.json").exists())


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
        for m in (activities, export, garmin, gpx, rhr):
            for name in dir(m):
                if callable(getattr(m, name)) and getattr(getattr(m, name), "__module__", "") == m.__name__:
                    self.assertTrue(hasattr(mod, name), name)
        self.assertEqual(mod.to_stream(mod.parse_gpx(GPX)), gpx.to_stream(gpx.parse_gpx(GPX)))

    def test_bundle_runs(self):
        r = subprocess.run([sys.executable, str(self.path), "--help"],
                           capture_output=True, text=True, check=True)
        self.assertIn("--rebuild", r.stdout)


if __name__ == "__main__":
    unittest.main()
