"""The adaptation loop (roadmap 09): matching runs to the plan, adapting it, re-planning (standard library only)."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import adapt, levels, match, physiology, plan_io, profile, render_md, replan, templates  # noqa: E402,E501

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
    return {**wk, "days": [{k: v for k, v in d.items() if k not in ("status", "activity_id", "changed_by", "change")}
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


EASY = replan.easy_maker(PROF, LIB, RULES)


def plan_of(*days):
    """A plan of (offset from MON, slot, template id) sessions, in Monday weeks."""
    weeks = {}
    for k, slot, tid in days:
        d = MON + timedelta(days=k)
        mon = d - timedelta(days=d.weekday())
        weeks.setdefault(mon.isoformat(), []).append(
            {"date": d.isoformat(), "slot": slot, "workout": workout(tid), "status": None, "activity_id": None,
             "changed_by": None})
    return {"version": 1, "generated": GENERATED, "profile_hash": "0" * 64,
            "weeks": [{"start": m, "deload": False, "target_km": 0, "days": ds}
                      for m, ds in sorted(weeks.items())]}


def two_weeks(q2=9):
    """Tue Q, Thu E, Sat E, Sun L; then Tue E, the Q on MON + q2 (Wed by default), Sat E, Sun L."""
    return plan_of((1, "Q", "cruise_tempo"), (3, "E", "easy"), (5, "E", "easy"), (6, "L", "steady_long"),
                   (8, "E", "easy"), (q2, "Q", "cruise_tempo"), (12, "E", "easy"), (13, "L", "steady_long"))


def day_of(plan, iso):
    return next((d for wk in plan["weeks"] for d in wk["days"] if d["date"] == iso), None)


def rhr_rising(today, last=57, base=50, days=30):
    return [[(today - timedelta(days=k)).isoformat(), base] for k in range(days, 0, -1)] + [[today.isoformat(), last]]


def run_adapt(plan, today, history=None, wellness=None, overrides=(), prev=None):
    return adapt.adapt(plan, history or {}, wellness or {}, list(overrides), today, RULES, easy=EASY, prev=prev)


class Adapt(unittest.TestCase):
    """adapt.adapt: missed sessions, fatigue and overrides, from today on only."""

    def test_q_missed_not_made_up(self):
        plan = two_weeks()
        before = copy.deepcopy(plan)
        changes = run_adapt(plan, MON + timedelta(days=2), {day(1): {"status": "missed", "activity_id": None}})
        self.assertEqual((changes, plan), ([], before))

    def test_l_missed_moved(self):
        # Sunday's L missed; Monday is free and the next Q is Wednesday, 2 days after: L moves to Monday
        plan = two_weeks(q2=9)
        today = MON + timedelta(days=7)
        changes = run_adapt(plan, today, {day(6): {"status": "missed", "activity_id": None}})
        moved = day_of(plan, day(7))
        self.assertEqual((moved["slot"], moved["changed_by"], moved["workout"]["id"]), ("L", "l_moved", "steady_long"))
        self.assertEqual([(c["date"], c["from"], c["to"], c["rule"]) for c in changes],
                         [(day(7), "rest", "L", "l_moved")])
        dates = [d["date"] for d in plan["weeks"][1]["days"]]
        self.assertEqual(dates, sorted(dates))
        # applied again (the next re-plan of the day): not moved twice
        again = run_adapt(plan, today, {day(6): {"status": "missed", "activity_id": None}})
        self.assertEqual(again, changes)
        self.assertEqual(sum(d["slot"] == "L" for d in plan["weeks"][1]["days"]), 2)

    def test_l_missed_no_room(self):
        plan = two_weeks(q2=8)                       # the next Q on Tuesday, one day after Monday
        plan["weeks"][1]["days"] = [d for d in plan["weeks"][1]["days"] if d["date"] != day(8) or d["slot"] == "Q"]
        before = copy.deepcopy(plan)
        changes = run_adapt(plan, MON + timedelta(days=7), {day(6): {"status": "missed", "activity_id": None}})
        self.assertEqual(plan, before)
        self.assertEqual([(c["date"], c["from"], c["to"], c["rule"]) for c in changes],
                         [(day(6), "L", "skipped", "l_skipped")])

    def assert_fatigue(self, wellness, reason):
        plan = two_weeks()
        today = MON
        changes = run_adapt(plan, today, wellness=wellness)
        q = day_of(plan, day(1))
        self.assertEqual((q["slot"], q["changed_by"], q["workout"]["kind"]), ("E", "fatigue", "E"))
        self.assertAlmostEqual(q["workout"]["km"], workout("cruise_tempo")["km"], delta=0.2)
        self.assertEqual(day_of(plan, day(9))["slot"], "Q")                 # only the next Q
        self.assertEqual([(c["date"], c["from"], c["to"], c["rule"]) for c in changes], [(day(1), "Q", "E", "fatigue")])
        self.assertIn(reason, changes[0]["reason"])
        self.assertEqual(run_adapt(plan, today, wellness=wellness), changes)     # once, not a Q a re-plan
        self.assertEqual(day_of(plan, day(9))["slot"], "Q")

    def test_fatigue_from_resting_hr(self):
        self.assert_fatigue({"rhr": rhr_rising(MON)}, "resting HR +7 bpm")

    def test_fatigue_from_hrv(self):
        self.assert_fatigue({"hrv": [[MON.isoformat(), "LOW"]]}, "HRV status low")

    def test_fatigue_from_readiness(self):
        self.assert_fatigue({"readiness": [[MON.isoformat(), {"level": "LOW", "score": 30}]]}, "training readiness low")
        self.assert_fatigue({"readiness": [[MON.isoformat(), {"level": None, "score": 10}]]}, "training readiness low")

    def test_missing_wellness_is_never_fatigue(self):
        old = (MON - timedelta(days=5)).isoformat()
        for wellness in ({}, {"rhr": [], "hrv": [], "readiness": []},
                         {"rhr": [[MON.isoformat(), 80]]},                      # no 30-day baseline
                         {"rhr": rhr_rising(MON, last=54)},                      # +4 bpm: under the threshold
                         {"rhr": rhr_rising(MON - timedelta(days=5))},           # stale: 5 days old
                         {"hrv": [[old, "LOW"]]}, {"hrv": [[MON.isoformat(), "BALANCED"]]},
                         {"hrv": [[MON.isoformat(), None]]},
                         {"readiness": [[MON.isoformat(), {"level": None, "score": None}]]},
                         {"readiness": [[MON.isoformat(), {"level": "HIGH", "score": 80}]], "hrv": [["x", "LOW"]]}):
            with self.subTest(wellness=wellness):
                plan = two_weeks()
                before = copy.deepcopy(plan)
                self.assertEqual(run_adapt(plan, MON, wellness=wellness), [])
                self.assertEqual(plan, before)

    def test_thresholds_are_settings(self):
        rules = {**RULES, "adapt": {**RULES["adapt"], "rhr_bpm": 8}}
        plan = two_weeks()
        self.assertEqual(adapt.adapt(plan, {}, {"rhr": rhr_rising(MON)}, [], MON, rules, easy=EASY), [])

    def test_done_today_is_left_alone(self):
        plan = two_weeks()
        changes = run_adapt(plan, MON + timedelta(days=1), {day(1): {"status": "done", "activity_id": 7}},
                            wellness={"hrv": [[day(1), "LOW"]]})
        self.assertEqual(day_of(plan, day(1))["slot"], "Q")
        self.assertEqual([c["date"] for c in changes], [day(9)])                # the next Q not run yet

    def test_override_skip_and_reduce(self):
        plan = two_weeks()
        ov = [{"from": MON + timedelta(days=8), "to": MON + timedelta(days=9), "action": "skip"},
              {"from": MON + timedelta(days=12), "to": MON + timedelta(days=13), "action": "reduce"},
              {"from": MON, "to": MON + timedelta(days=1), "action": "skip"}]          # partly past: today on only
        today = MON + timedelta(days=1)
        changes = run_adapt(plan, today, {}, overrides=ov)
        self.assertEqual(day_of(plan, day(1))["changed_by"], "override_skip")
        for k in (8, 9):
            d = day_of(plan, day(k))
            self.assertEqual((d["workout"], d["changed_by"]), (None, "override_skip"))
        sat, sun = day_of(plan, day(12)), day_of(plan, day(13))
        self.assertEqual((sun["slot"], sun["changed_by"], sun["workout"]["kind"]), ("E", "override_reduce", "E"))
        self.assertAlmostEqual(sun["workout"]["km"], workout("steady_long")["km"] * RULES["adapt"]["reduce"], delta=0.2)
        self.assertEqual(sat["changed_by"], "override_reduce")
        self.assertEqual([(c["date"], c["to"]) for c in changes],
                         [(day(1), "rest"), (day(8), "rest"), (day(9), "rest"), (day(12), "E"), (day(13), "E")])
        # adapted again: nothing is reduced twice
        sun_km = sun["workout"]["km"]
        self.assertEqual(run_adapt(plan, today, {}, overrides=ov), changes)
        self.assertEqual(day_of(plan, day(13))["workout"]["km"], sun_km)
        md = render_md.render_plan(plan)
        self.assertRegex(md, rf"(?m)^- Tue {day(8)} · skipped$")

    def test_override_lock(self):
        prev = two_weeks()
        day_of(prev, day(9))["workout"] = workout("vo2_intervals")               # edited by hand in plan.json
        plan = two_weeks()
        ov = [{"from": MON + timedelta(days=9), "to": MON + timedelta(days=9), "action": "lock"},
              {"from": MON + timedelta(days=9), "to": MON + timedelta(days=9), "action": "skip"}]
        changes = run_adapt(plan, MON, {}, {"hrv": [[MON.isoformat(), "LOW"]]}, ov, prev=prev)
        self.assertEqual(day_of(plan, day(9)), day_of(prev, day(9)))           # locked: neither skipped nor E
        self.assertEqual([c["date"] for c in changes], [day(1)])


class ProfileOverrides(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.toml"
            path.write_text(text, encoding="utf-8")
            return profile.load_profile(path, [], [], START_DAY)

    def test_parsed(self):
        p = self.load('[[override]]\nfrom = 2024-06-11\nto = 2024-06-13\naction = "skip"\n'
                      '[[override]]\nfrom = 2024-06-20\naction = "Lock"\n')
        self.assertEqual(p.overrides, [{"from": date(2024, 6, 11), "to": date(2024, 6, 13), "action": "skip"},
                                       {"from": date(2024, 6, 20), "to": date(2024, 6, 20), "action": "lock"}])
        self.assertEqual(self.load("").overrides, [])

    def test_rejected(self):
        for text, msg in (('[[override]]\nfrom = 2024-06-11\naction = "rest"\n', "skip, reduce or lock"),
                          ('[[override]]\nfrom = "2024-06-11"\naction = "skip"\n', "from = YYYY-MM-DD"),
                          ('[[override]]\naction = "skip"\n', "from = YYYY-MM-DD"),
                          ('[[override]]\nfrom = 2024-06-11\nto = 2024-06-10\naction = "skip"\n', "before"),
                          ('[[override]]\nfrom = 2024-06-11\nto = 5\naction = "skip"\n', "to = YYYY-MM-DD"),
                          ('override = 3\n', "override")):
            with self.subTest(text=text), self.assertRaisesRegex(profile.ProfileError, msg):
                self.load(text)


def wellness_days(today):
    return {"rhr": rhr_rising(today)}


class Invariants(unittest.TestCase):
    """Across whole re-plans (replan.replan): past weeks, locked days, and a re-plan run twice."""

    def test_replan_twice_is_the_same(self):
        runs = easy_runs(date(2024, 6, 10), date(2024, 6, 15))
        a = make_plan(NOVICE_TOML, START_DAY)
        today = date(2024, 6, 17)
        b = make_plan(NOVICE_TOML, today, a, runs, wellness=wellness_days(today))
        self.assertTrue(b["changes"])
        c = make_plan(NOVICE_TOML, today, b, runs, wellness=wellness_days(today))
        self.assertEqual({**c, "generated": None}, {**b, "generated": None})
        self.assertEqual(len(c["history"]), len(b["history"]))

    def test_past_weeks_and_locked_days_never_change(self):
        lock = "[[override]]\nfrom = 2024-07-02\nto = 2024-07-04\naction = \"lock\"\n"
        a = make_plan(NOVICE_TOML + lock, START_DAY)
        locked = [d for wk in a["weeks"] for d in wk["days"] if "2024-07-02" <= d["date"] <= "2024-07-04"]
        self.assertTrue(locked)
        plan, runs = a, []
        for k, km in enumerate((30, 40, 25), 1):
            today = START_DAY + timedelta(weeks=k)
            runs = easy_runs(date(2024, 6, 10), today - timedelta(days=1))
            text = NOVICE_TOML.replace("km_4w = 20", f"km_4w = {km}") + lock
            new = make_plan(text, today, plan, runs, wellness=wellness_days(today))
            for wk in plan["weeks"]:
                ended = date.fromisoformat(wk["start"]) + timedelta(days=6) < today
                if wk["start"] < new["progress"]["plan_start"] and ended:
                    self.assertEqual(strip_status(next(w for w in new["weeks"] if w["start"] == wk["start"])),
                                     strip_status(wk))
            got = [d for wk in new["weeks"] for d in wk["days"] if "2024-07-02" <= d["date"] <= "2024-07-04"]
            self.assertEqual([strip_status({"days": [d]}) for d in got], [strip_status({"days": [d]}) for d in locked])
            plan = new

    def test_what_changed_in_plan_md(self):
        a = make_plan(NOVICE_TOML, START_DAY)
        today = date(2024, 6, 17)
        b = make_plan(NOVICE_TOML, today, a, easy_runs(date(2024, 6, 10), date(2024, 6, 16)),
                      wellness=wellness_days(today))
        md = render_md.render_plan(b)
        self.assertRegex(md, r"(?m)^## What changed\n\n- \w{3} \d{4}-\d{2}-\d{2} Q → E: resting HR \+7 bpm$")
        self.assertLess(md.index("## What changed"), md.index("## Week of"))
        self.assertEqual(b["history"][-1]["changes"], b["changes"])


def race_run(day_, km, secs, rid=900):
    return {"id": rid, "date": f"{day_} 09:00:00", "type": "running", "dist": km * 1000, "dur": secs,
            "moving": secs, "avgHr": 170, "event": "race"}


def stream_effort(day_, km, secs, rid=800):
    n = int(secs // 10) + 1
    return {"id": rid, "date": f"{day_} 07:00:00", "type": "running", "dist": km * 1000, "dur": secs,
            "t": [i * 10 for i in range(n)], "d": [round(km * 1000 * i / (n - 1)) for i in range(n)],
            "hr": [150] * n}


VDOT_TOML = 'hr_max = 190\nhr_rest = 50\nvolume_level = "novice"\nquality_level = "novice"\n'


class Vdot(unittest.TestCase):
    """The VDOT across re-plans: race and time-trial efforts raise it, detraining lowers it."""

    def setUp(self):
        self.d0 = date(2024, 6, 5)
        self.base = [r for r in easy_runs(self.d0 - timedelta(days=60), self.d0 - timedelta(days=1))]
        self.first = stream_effort(self.d0 - timedelta(days=3), 10, 3000)           # a 10 km training effort

    def load(self, runs, today, plan=None):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.toml"
            path.write_text(VDOT_TOML, encoding="utf-8")
            return profile.load_profile(path, sorted(runs, key=lambda r: r["date"]), [], today, plan=plan)

    def plan_at(self, runs, today, prev=None):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.toml"
            path.write_text(VDOT_TOML, encoding="utf-8")
            prof = profile.load_profile(path, sorted(runs, key=lambda r: r["date"]), [], today, plan=prev)
        return prof, json.loads(json.dumps(replan.replan(prev, prof, runs, LIB, RULES, today, 8, generated=GENERATED)))

    def test_first_estimate_unchanged(self):
        runs = self.base + [self.first]
        prof, plan = self.plan_at(runs, self.d0)
        self.assertAlmostEqual(prof.vdot, physiology.vdot(10000, 3000), places=6)
        self.assertAlmostEqual(plan["progress"]["vdot"]["value"], physiology.vdot(10000, 3000), places=6)

    def test_training_efforts_never_raise_it(self):
        runs = self.base + [self.first]
        _, plan = self.plan_at(runs, self.d0)
        later = self.d0 + timedelta(weeks=5)
        faster = runs + easy_runs(self.d0, later - timedelta(days=1), rid=300) + \
            [stream_effort(later - timedelta(days=2), 10, 2700, rid=801)]
        prof = self.load(faster, later, plan)
        self.assertAlmostEqual(prof.vdot, physiology.vdot(10000, 3000), places=1)

    def test_race_raises_it_at_the_re_estimate(self):
        runs = self.base + [self.first]
        _, plan = self.plan_at(runs, self.d0)
        race = race_run(self.d0 + timedelta(days=10), 10, 2760)
        fill = easy_runs(self.d0, self.d0 + timedelta(weeks=6), rid=300)
        early = self.load(runs + fill + [race], self.d0 + timedelta(weeks=2), plan)       # not 4 weeks yet
        self.assertAlmostEqual(early.vdot, physiology.vdot(10000, 3000), places=1)
        prof = self.load(runs + fill + [race], self.d0 + timedelta(weeks=4), plan)
        self.assertAlmostEqual(prof.vdot, physiology.vdot(10000, 2760), places=1)
        self.assertIn("race", prof.vdot_from[0])
        slow = self.load(runs + fill + [race_run(self.d0 + timedelta(days=10), 10, 3300)], self.d0 + timedelta(weeks=4),
                         plan)
        self.assertAlmostEqual(slow.vdot, physiology.vdot(10000, 3000), places=1)        # a slow race: kept

    def test_detraining_lowers_it(self):
        runs = self.base + [self.first]
        _, plan = self.plan_at(runs, self.d0)
        gap_end = self.d0 + timedelta(days=40)
        back = runs + easy_runs(gap_end, gap_end + timedelta(days=2), rid=300)        # 40 days off, then back
        prof = self.load(back, gap_end + timedelta(days=3), plan)
        factor = levels.layoff(40)[0]
        self.assertLess(factor, 1)
        self.assertAlmostEqual(prof.vdot, physiology.vdot(10000, 3000) * factor, places=1)


if __name__ == "__main__":
    unittest.main()
