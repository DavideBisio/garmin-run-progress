"""The adaptation loop (roadmap 09): matching runs to the plan, adapting it, re-planning (standard library only)."""
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import match, physiology, plan_io, profile, render_md, replan, templates  # noqa: E402

RULES = physiology.load_rules()
LIB = templates.load_templates()
MON = date(2024, 6, 10)                      # the matched week's Monday
TODAY = date(2024, 6, 17)                    # the Monday after: every session of the week is past
HR = dict(hr_max=190, hr_rest=50)            # Z4 from 162 bpm


def generic_profile(**kw):
    vals = dict(hr_max=190, hr_rest=50, vdot=40.0, km_4w=30.0, km_12w=30.0, runs_per_week=4.0, longest_8w=12.0,
                volume_level="novice", quality_level="novice")
    vals.update(kw)
    return profile.Profile(**vals)


PROF = generic_profile()


def workout(tid, variant=1):
    return json.loads(json.dumps(plan_io.workout_to_dict(templates.instantiate(LIB[tid], variant, PROF, RULES))))


def day(offset):
    return (MON + timedelta(days=offset)).isoformat()


def week_plan():
    """Tue Q cruise tempo, Thu E, Sat E, Sun L: the week of MON."""
    days = [(1, "Q", "cruise_tempo"), (3, "E", "easy"), (5, "E", "easy"), (6, "L", "steady_long")]
    return {"version": 1, "weeks": [{"start": MON.isoformat(), "deload": False, "days": [
        {"date": day(k), "slot": slot, "workout": workout(tid)} for k, slot, tid in days]}]}


PLAN = week_plan()
PLANNED = {d["date"]: d["workout"] for d in PLAN["weeks"][0]["days"]}


def run(rid, offset, km=None, hr=140, secs=None, kind="running"):
    """A run without streams on MON + offset: the planned session's km and time by default."""
    w = PLANNED.get(day(offset), {"km": 6.0, "seconds": 2160})
    km = w["km"] if km is None else km
    return {"id": rid, "date": f"{day(offset)} 07:00:00", "type": kind, "dist": km * 1000,
            "dur": secs if secs is not None else w["seconds"] * km / w["km"], "avgHr": hr}


def all_runs():
    return [run(1, 1, hr=170), run(2, 3), run(3, 5), run(4, 6)]


def statuses(runs, today=TODAY, plan=PLAN):
    got = match.match(plan, runs, today, RULES, **HR)
    return {d: (v["status"], v["activity_id"]) for d, v in got.items()}


class Match(unittest.TestCase):
    def test_all_done(self):
        self.assertEqual(statuses(all_runs()), {day(1): ("done", 1), day(3): ("done", 2), day(5): ("done", 3),
                                                day(6): ("done", 4)})

    def test_q_missed(self):
        got = statuses(all_runs()[1:])
        self.assertEqual(got[day(1)], ("missed", None))
        self.assertEqual(got[day(3)], ("done", 2))

    def test_q_run_easy_is_partial(self):
        self.assertEqual(statuses([run(1, 1, hr=140)] + all_runs()[1:])[day(1)], ("partial", 1))

    def test_two_runs_one_day(self):
        # Thursday's easy run in two parts: one session, done
        runs = [run(1, 1, hr=170), run(2, 3, km=PLANNED[day(3)]["km"] / 2), run(5, 3, km=PLANNED[day(3)]["km"] / 2),
                run(3, 5), run(4, 6)]
        self.assertEqual(statuses(runs)[day(3)][0], "done")
        # Saturday's run done on Sunday next to the long run: Sat moved, Sun the longest run
        runs = [run(1, 1, hr=170), run(2, 3), run(3, 6, km=PLANNED[day(5)]["km"]), run(4, 6)]
        got = statuses(runs)
        self.assertEqual(got[day(5)], ("moved", 3))
        self.assertEqual(got[day(6)], ("done", 4))

    def test_wrong_day(self):
        runs = [run(1, 2, km=PLANNED[day(1)]["km"], hr=170, secs=PLANNED[day(1)]["seconds"])] + all_runs()[1:]
        got = statuses(runs)
        self.assertEqual(got[day(1)], ("moved", 1))
        self.assertEqual(got[day(3)], ("done", 2))
        # an easy run the day after a hard Q is no Q done
        runs = [run(1, 2, km=8, hr=140)] + all_runs()[1:]
        self.assertEqual(statuses(runs)[day(1)], ("missed", None))

    def test_partial(self):
        w = PLANNED[day(6)]
        runs = all_runs()[:3] + [run(4, 6, km=w["km"] * 0.5)]
        self.assertEqual(statuses(runs)[day(6)], ("partial", 4))
        runs = all_runs()[:3] + [run(4, 6, km=w["km"] * 0.75)]            # over 70 %: done
        self.assertEqual(statuses(runs)[day(6)], ("done", 4))
        # partial is a setting
        rules = {**RULES, "adapt": {**RULES["adapt"], "partial": 0.8}}
        self.assertEqual(match.match(PLAN, runs, TODAY, rules, **HR)[day(6)]["status"], "partial")

    def test_trail_in_place_of_long_run(self):
        w = PLANNED[day(6)]
        runs = all_runs()[:3] + [run(4, 6, km=w["km"] * 0.6, secs=w["seconds"], kind="trail_running")]
        self.assertEqual(statuses(runs)[day(6)], ("swapped", 4))

    def test_today_and_future(self):
        # Sunday's L is today: not missed yet; nothing after today is matched
        got = statuses(all_runs()[:3], today=MON + timedelta(days=6))
        self.assertNotIn(day(6), got)
        self.assertEqual(len(got), 3)
        got = statuses(all_runs(), today=MON + timedelta(days=6))
        self.assertEqual(got[day(6)], ("done", 4))
        self.assertEqual(statuses([], today=MON + timedelta(days=2)), {day(1): ("missed", None)})

    def test_no_hr_fits_any_kind(self):
        runs = [{**r, "avgHr": None} for r in all_runs()]
        self.assertEqual({s for s, _ in statuses(runs).values()}, {"done"})
        got = match.match(PLAN, [run(1, 1, hr=140)], TODAY, RULES)          # no HR bounds given
        self.assertEqual(got[day(1)]["status"], "done")

    def test_compliance(self):
        self.assertEqual(match.q_compliance(PLAN, all_runs(), TODAY, TODAY, RULES, **HR), 1.0)
        self.assertEqual(match.q_compliance(PLAN, all_runs()[1:], TODAY, TODAY, RULES, **HR), 0.0)
        self.assertIsNone(match.q_compliance(PLAN, all_runs(), MON, MON, RULES, **HR))       # nothing planned yet
        # the Q of today, not run yet, isn't counted
        self.assertIsNone(match.q_compliance(PLAN, [], MON + timedelta(days=1), TODAY, RULES, **HR))


GENERATED = "2024-06-05T08:00:00"
START_DAY = date(2024, 6, 5)                 # a Wednesday: the first plan starts on Monday 2024-06-10
NOVICE_TOML = ('hr_max = 190\nhr_rest = 50\nvdot = 40\nkm_4w = 20\nkm_12w = 20\nruns_per_week = 4\n'
               'longest_8w = 8\nvolume_level = "novice"\nquality_level = "novice"\n'
               'days = ["tue", "thu", "sat", "sun"]\nlong_run_day = "sun"\n')
BEGINNER_TOML = ('hr_max = 190\nhr_rest = 50\nvolume_level = "beginner"\nquality_level = "beginner"\n'
                 'days = ["tue", "thu", "sat"]\nlong_run_day = "sat"\n'
                 '[race]\ndate = 2024-09-29\ndistance = "10k"\n')


def make_plan(text, today, prev=None, runs=(), weeks=8, **kw):
    """plan.json as `make plan` writes it on `today` with `prev` the plan.json on disk."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "profile.toml"
        path.write_text(text, encoding="utf-8")
        prof = profile.load_profile(path, list(runs), [], today, plan=prev)
    out = replan.replan(prev, prof, list(runs), LIB, RULES, today, weeks, generated=GENERATED, **kw)
    return json.loads(json.dumps(out))


def strip_status(wk):
    return {**wk, "days": [{k: v for k, v in d.items() if k not in ("status", "activity_id", "changed_by")}
                           for d in wk["days"]]}


def easy_runs(start, end, km=6, rid=100):
    """An easy run every day from start to end (dates), ids from rid."""
    n = (end - start).days + 1
    return [{"id": rid + k, "date": f"{start + timedelta(days=k)} 07:00:00", "type": "running",
             "dist": km * 1000, "dur": km * 360, "avgHr": 140} for k in range(n)]


class PastWeeks(unittest.TestCase):
    """plan.json keeps the past weeks and the current one across re-plans (roadmap 09)."""

    def test_past_weeks_never_change(self):
        a = make_plan(NOVICE_TOML, START_DAY)
        self.assertEqual(a["history"], [])
        self.assertTrue(all(d["status"] is None for wk in a["weeks"] for d in wk["days"]))
        day = date(2024, 6, 19)
        runs = easy_runs(date(2024, 6, 10), date(2024, 6, 18))
        b = make_plan(NOVICE_TOML, day, a, runs)
        self.assertEqual([wk["start"] for wk in b["weeks"][:3]], ["2024-06-10", "2024-06-17", "2024-06-24"])
        self.assertEqual([strip_status(wk) for wk in b["weeks"][:2]], [strip_status(wk) for wk in a["weeks"][:2]])
        past = [d for wk in b["weeks"][:2] for d in wk["days"] if d["date"] < day.isoformat()]
        self.assertTrue(past)
        self.assertTrue(all(d["status"] in match.DONE + ("partial",) and d["activity_id"] for d in past), past)
        later = [d for wk in b["weeks"] for d in wk["days"] if d["date"] > day.isoformat()]
        self.assertTrue(all(d["status"] is None for d in later))
        c = make_plan(NOVICE_TOML, date(2024, 7, 3), b, runs)
        self.assertEqual(c["weeks"][0], b["weeks"][0])                        # all past at b: nothing changes
        self.assertEqual(strip_status(c["weeks"][1]), strip_status(b["weeks"][1]))
        self.assertEqual(c["weeks"][2]["days"][0]["status"], "missed")        # no run after the 18th
        md = render_md.render_plan(c)
        self.assertRegex(md, r"(?m)^- Tue 2024-06-11 · .+ - \d+\.\d km: done$")
        self.assertRegex(md, r"(?m)^- Tue 2024-06-25 · .+: missed$")
        self.assertNotRegex(md, r"(?m)^### Tue 2024-06-11")
        with tempfile.TemporaryDirectory() as d:                              # read back as written
            plan_io.write_plan(c, Path(d) / "plan.json")
            self.assertEqual(plan_io.read_plan(Path(d) / "plan.json"), c)

    def test_progress_not_counted_twice(self):
        # weekly re-plans of a beginner: the kept weeks don't add to the run/walk stage or move the block
        a = make_plan(BEGINNER_TOML, START_DAY, weeks=None)
        plan = a
        for k, today in enumerate((date(2024, 6, 12), date(2024, 6, 19), date(2024, 6, 26)), 1):
            plan = make_plan(BEGINNER_TOML, today, plan, weeks=None)
            own = [wk for wk in plan["weeks"] if wk["start"] >= plan["progress"]["plan_start"]]
            self.assertEqual(own[0]["start"], a["weeks"][k]["start"])
            self.assertEqual([wk["deload"] for wk in own[:4]], [wk["deload"] for wk in a["weeks"][k:k + 4]])
            self.assertEqual(plan["progress"]["run_walk_stage"], sum(not wk["deload"] for wk in a["weeks"][:k]))
            self.assertEqual(plan["progress"]["block_start"], a["weeks"][3]["start"] if k >= 3 else "2024-06-10")

    def test_no_race_deloads_stay_put(self):
        seen, plan = {}, None
        for k in range(10):                      # weekly re-plans for ten weeks
            plan = make_plan(NOVICE_TOML, START_DAY + timedelta(weeks=k), plan)
            for wk in plan["weeks"]:
                if wk["start"] >= plan["progress"]["plan_start"]:
                    got = (wk["deload"], wk["phase"])
                    self.assertEqual(seen.setdefault(wk["start"], got), got, wk["start"])
        deloads = sorted(s for s, (dl, _) in seen.items() if dl)
        self.assertEqual(deloads[:3], ["2024-07-01", "2024-07-29", "2024-08-26"])

    def test_history(self):
        a = make_plan(NOVICE_TOML, START_DAY)
        same = make_plan(NOVICE_TOML, START_DAY, a)
        self.assertEqual(same["history"], [])
        self.assertEqual({**same, "generated": None}, {**a, "generated": None})
        more = make_plan(NOVICE_TOML.replace("km_4w = 20", "km_4w = 30"), START_DAY, a)
        self.assertEqual(len(more["history"]), 1)
        self.assertEqual(more["history"][0]["date"], START_DAY.isoformat())
        self.assertEqual(more["history"][0]["start"], "2024-06-10")


if __name__ == "__main__":
    unittest.main()
