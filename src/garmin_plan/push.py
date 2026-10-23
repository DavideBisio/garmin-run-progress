"""Garmin export (05): upload plan.json's future sessions and schedule them on their dates.

Payloads are plain dicts in the shape of garminconnect's RunningWorkout.to_dict(), uploaded with
g.upload_workout(dict), so neither pydantic nor garminconnect is imported here: the caller passes
a logged-in client (garmin_grab.garmin.login) or, in the tests, a fake.

Ownership: pushed workouts are named "[plan] <title> <date>". A push first deletes the workouts an
interrupted push left off the calendar, then removes the future "[plan]" workouts in its date range
(unschedule, then delete), then uploads and schedules each session. push_state.json ({date:
{workout_id, scheduled_id, name}}) is saved after every mutating call, so an interrupted push is
resumed by running it again.
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from .config import NAME_MAX, NAME_PREFIX, PUSH_DIR, PUSH_STATE
from .model import Repeat
from .plan_io import workout_from_dict

# Garmin ids and keys, as in garminconnect.workout 0.3.19 (SportType, StepType, ConditionType,
# TargetType and the create_* helpers' dicts). Inlined so this module needs no garminconnect.
SPORT_RUNNING = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}
STEP_TYPES = {"warmup": (1, "warmup"), "cooldown": (2, "cooldown"), "rep": (3, "interval"),
              "recovery": (4, "recovery")}
REPEAT_TYPE = (6, "repeat")
CONDITIONS = {"lap": (1, "lap.button"), "time": (2, "time"), "dist": (3, "distance")}
ITERATIONS = (7, "iterations")
NO_TARGET = (1, "no.target")
HR_TARGET = (4, "heart.rate.zone")
PACE_TARGET = (6, "pace.zone")

MIN_VERSION = "0.3.19"
NEEDED = ("upload_workout", "schedule_workout", "unschedule_workout", "delete_workout",
          "get_workout_by_id", "get_scheduled_workouts_by_period")

# response field names: the documented ones first, then the alternatives seen in Garmin's API
WORKOUT_ID_KEYS = ("workoutId",)
SCHEDULE_ID_KEYS = ("workoutScheduleId", "scheduledWorkoutId")
DATE_KEYS = ("date", "scheduledDate", "calendarDate")
NAME_KEYS = ("workoutName", "title")


class PushError(RuntimeError):
    """Garmin answered something push can't use."""


def response_value(resp, keys, nested=False):
    """The first non-null of keys in a response dict (with nested, also in its "workout" dict)."""
    for d in (resp, resp.get("workout") if nested and isinstance(resp, dict) else None):
        if isinstance(d, dict):
            for k in keys:
                if d.get(k) is not None:
                    return d[k]
    return None


def _type(ids, prefix, order):
    return {f"{prefix}Id": ids[0], f"{prefix}Key": ids[1], "displayOrder": order}


def _condition(ids, displayable=True):
    return {"conditionTypeId": ids[0], "conditionTypeKey": ids[1], "displayOrder": ids[0],
            "displayable": displayable}


def _step(s, order):
    """One ExecutableStepDTO. Pace is the primary target (as a speed range, slow to fast m/s) and
    HR the secondary; without pace, HR is the primary; with neither, no.target."""
    out = {"type": "ExecutableStepDTO", "stepOrder": order,
           "stepType": _type(STEP_TYPES[s.role], "stepType", STEP_TYPES[s.role][0]),
           "endCondition": _condition(CONDITIONS[s.end])}
    if s.end != "lap":
        out["endConditionValue"] = float(s.value)
    targets = []
    if s.pace:
        targets.append((PACE_TARGET, *s.pace.to_speed()))
    if s.hr:
        targets.append((HR_TARGET, float(s.hr.lo), float(s.hr.hi)))
    if not targets:
        out["targetType"] = _type(NO_TARGET, "workoutTargetType", 1)
    for i, (ids, lo, hi) in enumerate(targets[:2]):
        pre = ("target", "secondaryTarget")[i]
        out[f"{pre}Type"] = _type(ids, "workoutTargetType", i + 1)
        out[f"{pre}ValueOne"], out[f"{pre}ValueTwo"] = lo, hi
    desc = "; ".join(x for x in (s.label, s.note) if x)
    if desc:
        out["description"] = desc
    return out


def _add_note(steps, note):
    """Prepend a repeat's note to the description of the first executable step in steps."""
    for s in steps:
        if s["type"] == "RepeatGroupDTO":
            if _add_note(s["workoutSteps"], note):
                return True
            continue
        s["description"] = "; ".join(x for x in (note, s.get("description")) if x)
        return True
    return False


def _steps(parts, order):
    """(Garmin steps, next stepOrder). stepOrder runs 1, 2, ... through repeat children too. A
    repeat of 1 is its steps, without the last recovery when skip_last_rest (as in plan.md). A
    repeat's note goes first in its first step's description."""
    out = []
    for p in parts:
        if not isinstance(p, Repeat):
            out.append(_step(p, order))
            order += 1
        elif p.n == 1:
            steps = p.steps[:-1] if p.skip_last_rest and p.steps and p.steps[-1].role == "recovery" else p.steps
            flat, order = _steps(steps, order)
            if p.note:
                _add_note(flat, p.note)
            out += flat
        else:
            group = {"type": "RepeatGroupDTO", "stepOrder": order, "stepType": _type(REPEAT_TYPE, "stepType", 6),
                     "numberOfIterations": p.n}
            children, order = _steps(p.steps, order + 1)
            if p.note:
                _add_note(children, p.note)
            group.update(workoutSteps=children, endCondition=_condition(ITERATIONS, displayable=False),
                         endConditionValue=float(p.n), smartRepeat=False, skipLastRestStep=bool(p.skip_last_rest))
            out.append(group)
    return out, order


def to_garmin(workout, name, description):
    """A plan.json workout dict as a RunningWorkout payload (the dict upload_workout posts)."""
    w = workout_from_dict(workout)
    steps, _ = _steps(w.parts, 1)
    return {"workoutName": name, "description": description, "sportType": dict(SPORT_RUNNING),
            "estimatedDurationInSecs": int(round(w.seconds)), "author": {},
            "workoutSegments": [{"segmentOrder": 1, "sportType": dict(SPORT_RUNNING), "workoutSteps": steps}]}


def workout_name(title, day):
    """'[plan] <title> <date>', at most NAME_MAX characters: only the title is shortened."""
    suffix = f" {day}"
    room = max(NAME_MAX - len(NAME_PREFIX) - len(suffix), 1)
    return f"{NAME_PREFIX}{title[:room].rstrip()}{suffix}"


def description(workout):
    return f"garmin_plan: template {workout['id']}, variant {workout['variant']}, {workout['km']:.1f} km"


def sessions(plan, today, weeks=None):
    """(date, workout dict) of every session dated today or later. weeks=N keeps the first N plan
    weeks that still have a day from today on (the current week counts as the first)."""
    ws = [w for w in plan["weeks"]
          if (date.fromisoformat(w["start"]) + timedelta(days=6)) >= today]
    if weeks is not None:
        ws = ws[:weeks]
    for w in ws:
        for d in w["days"]:
            if d.get("workout") and d["date"] >= today.isoformat():
                yield d["date"], d["workout"]


def local_today(g, today=None):
    """--today, else Garmin's date in the user's timezone (g.today()), else the machine's local date."""
    if today:
        return today
    try:
        return g.today()
    except Exception:  # noqa: BLE001  (an old library, or no timezone in the profile)
        return date.today()


def check_library(g):
    missing = [m for m in NEEDED if not hasattr(g, m)]
    if missing:
        sys.exit(f"error: the installed garminconnect lacks {', '.join(missing)}; push needs garminconnect "
                 f"{MIN_VERSION} or later. Run:  make upgrade  (or pip install --upgrade garminconnect)")


def _items(resp):
    """The scheduled-workout list, whether Garmin returns a list or wraps it in a dict."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for v in resp.values():
            if isinstance(v, list):
                return v
    return []


def _is_not_found(e):
    """A 404 from garminconnect (GarminConnectNotFoundError) or anything that says so."""
    msg = str(e).lower()
    return "notfound" in type(e).__name__.lower() or "404" in msg or "not found" in msg


def _get_workout(g, workout_id):
    """The library workout, or None when Garmin no longer has it (a 404 is not retried)."""
    try:
        return g.get_workout_by_id(workout_id) or None
    except Exception as e:  # noqa: BLE001  (the library's error classes aren't imported here)
        if _is_not_found(e):
            return None
        raise


def _plan_name(name):
    return isinstance(name, str) and name.startswith(NAME_PREFIX)


def _iso_day(v):
    try:
        return date.fromisoformat(str(v)[:10]).isoformat() if v is not None else None
    except ValueError:
        return None


def _keys_seen(items):
    keys = set()
    for it in items:
        if isinstance(it, dict):
            keys.update(it)
            if isinstance(it.get("workout"), dict):
                keys.update(f"workout.{k}" for k in it["workout"])
    return ", ".join(sorted(keys)) or "none"


def _warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def load_state(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise PushError(f"{path}: can't read push state ({e})") from e


def save_state(state, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(sorted(state.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def dry_run_files(todo, export):
    out = Path(export) / PUSH_DIR
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    for day, wd, payload in todo:
        (out / f"{day}-{wd['id']}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                                    encoding="utf-8")
    print(f"Dry run: wrote {len(todo)} workout(s) to {out}, called nothing")
    return {"pushed": 0, "removed": 0, "written": len(todo)}


def push(g, plan, today, export, dry_run=False, weeks=None, delay=1.0, sleep=time.sleep, retry=None):
    """Replace the future [plan] workouts in the pushed range with plan.json's sessions.

    retry(fn, *args) wraps every Garmin call (garmin_grab.garmin.with_retry); sleep(delay) follows
    every mutating call. Returns {"pushed", "removed"} counts.
    """
    todo = [(day, wd, to_garmin(wd, workout_name(wd["title"], day), description(wd)))
            for day, wd in sessions(plan, today, weeks)]
    if dry_run:
        return dry_run_files(todo, export)

    call = retry or (lambda fn, *a: fn(*a))
    path = Path(export) / PUSH_STATE
    state = load_state(path)
    removed = 0

    def mutate(fn, *args):
        r = call(fn, *args)
        sleep(delay)
        return r

    # 1. resume: a workout uploaded but never scheduled (or being removed) is not on the calendar,
    #    so the listing below can't find it. Delete it only if Garmin still has it as a [plan] workout.
    for day in sorted(state):
        e = state[day]
        if e.get("scheduled_id") is not None:
            continue
        wid = e.get("workout_id")
        if wid is not None:
            w = call(_get_workout, g, wid)
            name = response_value(w, NAME_KEYS, nested=True) if isinstance(w, dict) else None
            if w and _plan_name(name):
                mutate(g.delete_workout, wid)
                removed += 1
            elif w:
                _warn(f"kept workout {wid} ({name!r}): its name no longer starts with {NAME_PREFIX!r}")
        del state[day]
        save_state(state, path)

    if not todo:
        print("Nothing to push: plan.json has no session from today on")
        return {"pushed": 0, "removed": removed}
    first, last = today.isoformat(), todo[-1][0]

    # 2. remove the future [plan] workouts in range; past ones and other names are never touched.
    #    An item is ours if its name starts with [plan], or (name unreadable) its ids match the state.
    items = _items(call(g.get_scheduled_workouts_by_period, first, last))
    readable, found, gone, targets = False, set(), [], []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = response_value(it, NAME_KEYS, nested=True)
        day = _iso_day(response_value(it, DATE_KEYS))
        sid, wid = response_value(it, SCHEDULE_ID_KEYS), response_value(it, WORKOUT_ID_KEYS, nested=True)
        matched = [d for d, e in sorted(state.items()) if _plan_name(e.get("name"))
                   and ((sid is not None and e.get("scheduled_id") == sid)
                        or (wid is not None and e.get("workout_id") == wid))]
        readable = readable or isinstance(name, str) or day is not None or bool(matched)
        found.update(matched)
        if isinstance(name, str) and not _plan_name(name):
            if matched:           # renamed in Garmin Connect: the user keeps it
                _warn(f"kept {name!r}: its name no longer starts with {NAME_PREFIX!r}")
                gone += matched
            continue
        if name is None and not matched:
            continue
        day = day or (matched[0] if matched else None)
        if day is None or not first <= day <= last:
            continue
        if wid is None and matched:
            wid = state[matched[0]].get("workout_id")
        targets.append((sid, wid, matched, day, name))
    if items and not readable:
        raise PushError(f"can't read Garmin's scheduled-workout listing: no name, date or known id in "
                        f"{len(items)} item(s) (keys seen: {_keys_seen(items)})")
    for d in sorted(state):
        e = state[d]
        if first <= d <= last and e.get("scheduled_id") is not None and d not in found:
            if e.get("workout_id") is None or call(_get_workout, g, e["workout_id"]):
                raise PushError(f"{d}: workout {e.get('workout_id')} (schedule {e['scheduled_id']}) of "
                                f"{path.name} is not in Garmin's scheduled-workout listing "
                                f"(keys seen: {_keys_seen(items)})")
            gone.append(d)     # deleted by hand in Garmin Connect
    for d in set(gone):
        del state[d]

    # mark first (a stop from here on leaves entries that step 1 deletes), unschedule all, then
    # delete each workout once
    for sid, wid, matched, day, name in targets:
        for d in matched:
            state[d]["scheduled_id"] = None
        if not matched and wid is not None and day not in state:
            state[day] = {"workout_id": wid, "scheduled_id": None, "name": name}
            matched.append(day)
    save_state(state, path)
    for sid, *_ in targets:
        if sid is not None:
            mutate(g.unschedule_workout, sid)
    deleted = set()
    for _, wid, matched, *_ in targets:
        if wid is not None and wid not in deleted:
            mutate(g.delete_workout, wid)
            deleted.add(wid)
            removed += 1
        for d in matched:
            state.pop(d, None)
        save_state(state, path)

    # 3. upload, then schedule on the session's local date
    for day, _, payload in todo:
        wid = response_value(mutate(g.upload_workout, payload), WORKOUT_ID_KEYS)
        if wid is None:
            raise PushError(f"upload of {payload['workoutName']!r} returned no workoutId")
        state[day] = {"workout_id": wid, "scheduled_id": None, "name": payload["workoutName"]}
        save_state(state, path)
        resp = mutate(g.schedule_workout, wid, day)
        sid = response_value(resp, SCHEDULE_ID_KEYS)
        if sid is None:
            keys = ", ".join(resp) if isinstance(resp, dict) else type(resp).__name__
            raise PushError(f"scheduling {payload['workoutName']!r} returned no schedule id (got: {keys})")
        state[day]["scheduled_id"] = sid
        save_state(state, path)
        print(f"  {day}  {payload['workoutName']}")
    print(f"Pushed {len(todo)} workout(s) from {first} to {last}; removed {removed} old [plan] workout(s)")
    return {"pushed": len(todo), "removed": removed}
