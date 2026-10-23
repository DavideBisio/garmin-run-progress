"""The adaptation loop (roadmap 09): matching runs to the plan, adapting it, re-planning (standard library only)."""
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import match, physiology, plan_io, profile, templates  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
