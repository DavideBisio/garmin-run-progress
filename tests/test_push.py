"""Garmin workout export (TC-8, standard library only): payloads, re-push, resume, dry-run.

Never imports garminconnect (CI has neither it nor pydantic); FakeGarmin stands in for the client.
Regenerate the snapshots after a reviewed change: UPDATE_SNAPSHOTS=1 python -m unittest tests.test_push
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import config, model, physiology, plan_io, profile, push, templates  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
SNAPSHOTS = FIXTURES / "push"
RULES = physiology.load_rules()
LIB = templates.load_templates()
PLAN_TODAY = date(2024, 6, 5)     # a Wednesday: plans start on Monday 2024-06-10
TODAY = date(2024, 6, 14)          # push day: 06-11 and 06-13 are past, 06-16 on are future
WEEK = {"tue": "easy:1", "thu": "cruise_tempo:2", "sun": "hm_long:3"}


def generic_profile(**kw):
    """The fixed generic runner of the golden files: VDOT 40, HR 190/50."""
    vals = dict(hr_max=190, hr_rest=50, vdot=40.0, km_4w=0.0, km_12w=0.0, runs_per_week=0.0, longest_8w=0.0)
    vals.update(kw)
    return profile.Profile(**vals)


def workout(tid, variant):
    return plan_io.workout_to_dict(templates.instantiate(LIB[tid], variant, generic_profile(), RULES))


def make_plan(weeks=2, week=WEEK):
    w = {d: {"id": e.split(":")[0], "variant": int(e.split(":")[1]), "line": f'{d} = "{e}"'}
         for d, e in week.items()}
    return plan_io.build_plan(generic_profile(week=w), LIB, RULES, PLAN_TODAY, weeks, generated="2024-06-05T08:00:00")


class FakeGarmin:
    """Records calls, returns fake ids. fail_at=N raises KeyboardInterrupt on the Nth mutating call."""

    def __init__(self, today=TODAY, fail_at=None):
        self._today = today
        self.fail_at = fail_at
        self.mutations = 0
        self.calls = []
        self.workouts = {}          # id -> payload
        self.schedules = {}         # schedule id -> (workout id, date)
        self._next = 100

    def today(self):
        return self._today

    def _new_id(self):
        self._next += 1
        return self._next

    def _mutate(self, *call):
        self.mutations += 1
        if self.fail_at == self.mutations:
            raise KeyboardInterrupt
        self.calls.append(call)

    def seed(self, name, day):
        wid = self._new_id()
        self.workouts[wid] = {"workoutName": name}
        sid = self._new_id()
        self.schedules[sid] = (wid, day)
        return wid, sid

    def upload_workout(self, payload):
        self._mutate("upload_workout", payload["workoutName"])
        wid = self._new_id()
        self.workouts[wid] = json.loads(json.dumps(payload))
        return {"workoutId": wid, "workoutName": payload["workoutName"]}

    def schedule_workout(self, workout_id, date_str):
        self._mutate("schedule_workout", workout_id, date_str)
        assert workout_id in self.workouts, workout_id
        sid = self._new_id()
        self.schedules[sid] = (workout_id, date_str)
        return {"workoutScheduleId": sid, "workout": {"workoutId": workout_id}, "calendarDate": date_str}

    def unschedule_workout(self, scheduled_id):
        self._mutate("unschedule_workout", scheduled_id)
        del self.schedules[scheduled_id]

    def delete_workout(self, workout_id):
        self._mutate("delete_workout", workout_id)
        del self.workouts[workout_id]
        for sid in [s for s, (w, _) in self.schedules.items() if w == workout_id]:
            del self.schedules[sid]

    def get_scheduled_workouts_by_period(self, start, end):
        self.calls.append(("get_scheduled_workouts_by_period", start, end))
        return [{"scheduledWorkoutId": sid, "workoutId": wid, "workoutName": self.workouts[wid]["workoutName"],
                 "date": d}
                for sid, (wid, d) in sorted(self.schedules.items()) if start <= d <= end]

    # helpers for assertions
    def by_date(self):
        out = {}
        for wid, d in self.schedules.values():
            out.setdefault(d, []).append(self.workouts[wid]["workoutName"])
        return out

    def unscheduled(self):
        used = {w for w, _ in self.schedules.values()}
        return [w for w in self.workouts if w not in used]


def run(g, plan, export, **kw):
    kw.setdefault("delay", 0)
    kw.setdefault("sleep", lambda s: None)
    with contextlib.redirect_stdout(io.StringIO()):
        return push.push(g, plan, kw.pop("today", TODAY), export, **kw)


def flat(steps):
    for s in steps:
        yield s
        if s["type"] == "RepeatGroupDTO":
            yield from flat(s["workoutSteps"])


def wd(*parts, title="Test", tid="test"):
    return plan_io.workout_to_dict(model.Workout(tid, 1, title, "R", list(parts)))


PACE = model.PaceRange(240, 250)
HR = model.HrRange(162, 176)


class Payload(unittest.TestCase):
    def steps(self, *parts):
        return push.to_garmin(wd(*parts), "[plan] Test 2024-06-16", "d")["workoutSegments"][0]["workoutSteps"]

    def test_workout_shape(self):
        p = push.to_garmin(workout("cruise_tempo", 2), "[plan] Cruise Tempo 2024-06-16", "desc")
        self.assertEqual(p["workoutName"], "[plan] Cruise Tempo 2024-06-16")
        self.assertEqual(p["description"], "desc")
        self.assertEqual(p["sportType"], {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1})
        self.assertIsInstance(p["estimatedDurationInSecs"], int)
        self.assertEqual(len(p["workoutSegments"]), 1)
        seg = p["workoutSegments"][0]
        self.assertEqual((seg["segmentOrder"], seg["sportType"]), (1, p["sportType"]))

    def test_roles(self):
        for role, (tid, key) in {"warmup": (1, "warmup"), "rep": (3, "interval"),
                                 "recovery": (4, "recovery"), "cooldown": (2, "cooldown")}.items():
            with self.subTest(role=role):
                (s,) = self.steps(model.Step(role, "X", "dist", 1000, pace=PACE))
                self.assertEqual(s["type"], "ExecutableStepDTO")
                self.assertEqual(s["stepType"], {"stepTypeId": tid, "stepTypeKey": key, "displayOrder": tid})

    def test_ends(self):
        dist, time_, lap = self.steps(model.Step("rep", "D", "dist", 1200, pace=PACE),
                                      model.Step("rep", "T", "time", 90, pace=PACE),
                                      model.Step("rep", "L", "lap", None, hr=HR, est_time=60, est_dist=200))
        self.assertEqual((dist["endCondition"]["conditionTypeId"], dist["endCondition"]["conditionTypeKey"]),
                         (3, "distance"))
        self.assertEqual(dist["endConditionValue"], 1200)
        self.assertEqual((time_["endCondition"]["conditionTypeId"], time_["endCondition"]["conditionTypeKey"]),
                         (2, "time"))
        self.assertEqual(time_["endConditionValue"], 90)
        self.assertEqual((lap["endCondition"]["conditionTypeId"], lap["endCondition"]["conditionTypeKey"]),
                         (1, "lap.button"))
        self.assertNotIn("endConditionValue", lap)

    def test_targets(self):
        both, hr_only, open_ = self.steps(model.Step("rep", "P", "dist", 1000, pace=PACE, hr=HR),
                                          model.Step("rep", "H", "time", 30, hr=HR, est_pace=300),
                                          model.Step("rep", "O", "time", 30, est_pace=300))
        self.assertEqual(both["targetType"]["workoutTargetTypeKey"], "pace.zone")
        self.assertEqual(both["targetType"]["workoutTargetTypeId"], 6)
        slow, fast = PACE.to_speed()
        self.assertAlmostEqual(both["targetValueOne"], 1000 / 250)
        self.assertEqual((both["targetValueOne"], both["targetValueTwo"]), (slow, fast))
        self.assertLess(both["targetValueOne"], both["targetValueTwo"])
        self.assertEqual(both["secondaryTargetType"]["workoutTargetTypeKey"], "heart.rate.zone")
        self.assertEqual(both["secondaryTargetType"]["workoutTargetTypeId"], 4)
        self.assertEqual((both["secondaryTargetValueOne"], both["secondaryTargetValueTwo"]), (162, 176))
        # HR only: HR is the primary target, no secondary
        self.assertEqual(hr_only["targetType"]["workoutTargetTypeKey"], "heart.rate.zone")
        self.assertEqual((hr_only["targetValueOne"], hr_only["targetValueTwo"]), (162, 176))
        self.assertNotIn("secondaryTargetType", hr_only)
        # open
        self.assertEqual(open_["targetType"], {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target",
                                               "displayOrder": 1})
        self.assertNotIn("targetValueOne", open_)
        self.assertNotIn("secondaryTargetType", open_)

    def test_repeat_group_and_step_order(self):
        rep = model.Step("rep", "Rep", "dist", 400, pace=PACE, hr=HR)
        rec = model.Step("recovery", "Jog", "time", 60, est_pace=420)
        steps = self.steps(model.Step("warmup", "W", "dist", 2000, pace=PACE),
                           model.Repeat(4, [rep, rec]), model.Repeat(3, [rep, rec], skip_last_rest=True),
                           model.Step("cooldown", "C", "dist", 1000, pace=PACE))
        orders = [s["stepOrder"] for s in flat(steps)]
        self.assertEqual(orders, list(range(1, len(orders) + 1)))
        g1, g2 = steps[1], steps[2]
        self.assertEqual(g1["type"], "RepeatGroupDTO")
        self.assertEqual(g1["stepType"], {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6})
        self.assertEqual(g1["numberOfIterations"], 4)
        self.assertEqual(g1["endCondition"]["conditionTypeKey"], "iterations")
        self.assertEqual(g1["endCondition"]["conditionTypeId"], 7)
        self.assertEqual(g1["endConditionValue"], 4)
        self.assertIs(g1["skipLastRestStep"], False)
        self.assertIs(g2["skipLastRestStep"], True)
        self.assertEqual([s["stepType"]["stepTypeKey"] for s in g1["workoutSteps"]], ["interval", "recovery"])

    def test_repeat_of_one_is_flattened(self):
        rep = model.Step("rep", "Tempo", "dist", 3000, pace=PACE)
        rec = model.Step("recovery", "Jog", "time", 60, est_pace=420)
        steps = self.steps(model.Repeat(1, [rep, rec], skip_last_rest=True), model.Step("cooldown", "C", "dist", 1000, pace=PACE))
        self.assertEqual([s["type"] for s in steps], ["ExecutableStepDTO"] * 2)
        self.assertEqual([s["stepType"]["stepTypeKey"] for s in steps], ["interval", "cooldown"])
        self.assertEqual([s["stepOrder"] for s in steps], [1, 2])
        # the library's cruise tempo top variant has one; no RepeatGroup and no trailing recovery
        t = LIB["cruise_tempo"]
        w = workout("cruise_tempo", len(t["ladder"]))
        if any(s["type"] == "repeat" and s["n"] == 1 for s in w["steps"]):
            p = push.to_garmin(w, "n", "d")["workoutSegments"][0]["workoutSteps"]
            self.assertNotIn("RepeatGroupDTO", [s["type"] for s in p])

    def test_estimated_duration(self):
        w = workout("cruise_tempo", 2)
        self.assertEqual(push.to_garmin(w, "n", "d")["estimatedDurationInSecs"], round(w["seconds"]))

    def test_snapshots(self):
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        for tid, v in [("cruise_tempo", 2), ("hill_repeats", 1), ("hm_long", 3)]:
            w = workout(tid, v)
            got = push.to_garmin(w, push.workout_name(w["title"], "2024-06-16"), push.description(w))
            path = SNAPSHOTS / f"{tid}_{v}.json"
            text = json.dumps(got, indent=1, ensure_ascii=False) + "\n"
            if os.environ.get("UPDATE_SNAPSHOTS"):
                path.write_text(text, encoding="utf-8", newline="\n")
            with self.subTest(snapshot=path.name):
                self.assertEqual(got, json.loads(path.read_text(encoding="utf-8")))


class Names(unittest.TestCase):
    def test_name(self):
        self.assertEqual(push.workout_name("Cruise Tempo", "2024-06-16"), "[plan] Cruise Tempo 2024-06-16")

    def test_long_title_shortens_only_the_title(self):
        n = push.workout_name("Very " * 40 + "Long", "2024-06-16")
        self.assertLessEqual(len(n), config.NAME_MAX)
        self.assertTrue(n.startswith(config.NAME_PREFIX))
        self.assertTrue(n.endswith(" 2024-06-16"))

    def test_description_has_template_id_and_variant(self):
        d = push.description(workout("cruise_tempo", 2))
        self.assertIn("cruise_tempo", d)
        self.assertIn("2", d)


class Sessions(unittest.TestCase):
    def test_future_is_today_and_later(self):
        plan = make_plan()
        got = [d for d, _ in push.sessions(plan, date(2024, 6, 13), None)]
        self.assertEqual(got[0], "2024-06-13")
        self.assertTrue(all(d >= "2024-06-13" for d in got))
        self.assertEqual(len(got), 5)

    def test_weeks_limit(self):
        plan = make_plan(weeks=3)
        self.assertEqual(len(list(push.sessions(plan, TODAY, None))), 1 + 3 + 3)
        # the first plan week from today is the current one (06-10..06-16, one session left)
        self.assertEqual([d for d, _ in push.sessions(plan, TODAY, 1)], ["2024-06-16"])
        self.assertEqual(len(list(push.sessions(plan, TODAY, 2))), 4)
        self.assertEqual(len(list(push.sessions(plan, date(2024, 6, 1), 1))), 3)

    def test_local_today(self):
        g = FakeGarmin(today=date(2024, 6, 20))
        self.assertEqual(push.local_today(g, date(2024, 6, 1)), date(2024, 6, 1))
        self.assertEqual(push.local_today(g, None), date(2024, 6, 20))
        self.assertEqual(push.local_today(object(), None), date.today())

        class Broken:
            def today(self):
                raise RuntimeError("no timezone")
        self.assertEqual(push.local_today(Broken(), None), date.today())


class Push(unittest.TestCase):
    def setUp(self):
        self.export = Path(tempfile.mkdtemp())
        self.plan = make_plan()
        self.g = FakeGarmin()
        self.past_plan = self.g.seed("[plan] Easy Run 2024-06-11", "2024-06-11")
        self.club = self.g.seed("Club run", "2024-06-18")
        self.future = [d for d, _ in push.sessions(self.plan, TODAY, None)]

    def state(self):
        return json.loads((self.export / config.PUSH_STATE).read_text(encoding="utf-8"))

    def assert_consistent(self):
        g = self.g
        by = g.by_date()
        for d in self.future:
            names = [n for n in by.get(d, []) if n.startswith("[plan] ")]
            self.assertEqual(len(names), 1, (d, by.get(d)))
            self.assertTrue(names[0].endswith(" " + d))
        self.assertEqual(g.unscheduled(), [])
        st = self.state()
        self.assertEqual(sorted(st), self.future)
        for d, e in st.items():
            self.assertEqual(g.schedules[e["scheduled_id"]], (e["workout_id"], d))
            self.assertEqual(g.workouts[e["workout_id"]]["workoutName"], e["name"])
        # untouched: past [plan] and non-[plan]
        for wid, sid in (self.past_plan, self.club):
            self.assertIn(wid, g.workouts)
            self.assertIn(sid, g.schedules)

    def test_first_push(self):
        run(self.g, self.plan, self.export)
        self.assert_consistent()
        scheduled = [c for c in self.g.calls if c[0] == "schedule_workout"]
        # local date: days[].date verbatim
        self.assertEqual([c[2] for c in scheduled], self.future)
        self.assertEqual(self.g.calls[0], ("get_scheduled_workouts_by_period", "2024-06-14", self.future[-1]))

    def test_repush_unchanged_plan(self):
        run(self.g, self.plan, self.export)
        first = self.state()
        before = {d: sorted(n) for d, n in self.g.by_date().items()}
        self.g.calls.clear()
        run(self.g, self.plan, self.export)
        self.assert_consistent()
        self.assertEqual({d: sorted(n) for d, n in self.g.by_date().items()}, before)
        removed = {c[1] for c in self.g.calls if c[0] == "delete_workout"}
        self.assertEqual(removed, {e["workout_id"] for e in first.values()})
        unscheduled = {c[1] for c in self.g.calls if c[0] == "unschedule_workout"}
        self.assertEqual(unscheduled, {e["scheduled_id"] for e in first.values()})

    def test_resume_after_interrupt(self):
        for fail_at in range(1, 2 * len(self.future) + 1):
            with self.subTest(fail_at=fail_at):
                self.setUp()
                self.g.fail_at = fail_at
                with self.assertRaises(KeyboardInterrupt):
                    run(self.g, self.plan, self.export)
                self.g.fail_at = None
                run(self.g, self.plan, self.export)
                self.assert_consistent()

    def test_resume_during_repush(self):
        run(self.g, self.plan, self.export)
        self.g.fail_at = self.g.mutations + 3     # mid-way through removing the old set
        with self.assertRaises(KeyboardInterrupt):
            run(self.g, self.plan, self.export)
        self.g.fail_at = None
        run(self.g, self.plan, self.export)
        self.assert_consistent()

    def test_with_retry_and_delay(self):
        from garmin_grab import garmin
        sleeps = []
        flaky = {"n": 0}
        real = self.g.upload_workout

        def upload(payload):
            flaky["n"] += 1
            if flaky["n"] == 1:
                raise RuntimeError("500 server error")
            return real(payload)
        self.g.upload_workout = upload
        with mock.patch("time.sleep") as slept, contextlib.redirect_stdout(io.StringIO()):
            push.push(self.g, self.plan, TODAY, self.export, delay=0.5, sleep=sleeps.append, retry=garmin.with_retry)
        slept.assert_called()
        self.assertTrue(sleeps and all(s == 0.5 for s in sleeps))
        self.assert_consistent()

    def test_dry_run(self):
        g = mock.Mock()
        run(g, self.plan, self.export, dry_run=True)
        self.assertEqual(g.mock_calls, [])
        files = sorted(p.name for p in (self.export / config.PUSH_DIR).glob("*.json"))
        self.assertEqual(files, [f"{d}-{w['id']}.json" for d, w in push.sessions(self.plan, TODAY, None)])
        p = json.loads((self.export / config.PUSH_DIR / files[0]).read_text(encoding="utf-8"))
        self.assertEqual(p["workoutName"], f"[plan] Half-Marathon Long Run {self.future[0]}")
        self.assertFalse((self.export / config.PUSH_STATE).exists())

    def test_nothing_to_push(self):
        run(self.g, self.plan, self.export, today=date(2025, 1, 1))
        self.assertEqual(self.g.calls, [])


class Library(unittest.TestCase):
    def test_old_library(self):
        with self.assertRaises(SystemExit) as cm:
            push.check_library(object())
        msg = str(cm.exception.code)
        self.assertTrue(msg.startswith("error:"))
        self.assertIn("0.3.19", msg)
        self.assertIn("make upgrade", msg)

    def test_new_library(self):
        push.check_library(FakeGarmin())


class Cli(unittest.TestCase):
    def test_push_dry_run(self):
        export = Path(tempfile.mkdtemp())
        plan_io.write_plan(make_plan(), export / config.PLAN_JSON)
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        r = subprocess.run([sys.executable, "-m", "garmin_plan", "push", "--dry-run", "--weeks", "1",
                            "--export", str(export), "--today", TODAY.isoformat()],
                           capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(export))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Logged in", r.stdout)
        self.assertEqual(sorted(p.name for p in (export / config.PUSH_DIR).glob("*.json")),
                         ["2024-06-16-hm_long.json"])
        self.assertFalse((export / config.PUSH_STATE).exists())

    def test_push_without_plan(self):
        export = Path(tempfile.mkdtemp())
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        r = subprocess.run([sys.executable, "-m", "garmin_plan", "push", "--dry-run", "--export", str(export)],
                           capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(export))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error:", r.stderr)


if __name__ == "__main__":
    unittest.main()
