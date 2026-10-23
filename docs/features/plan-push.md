# Planner push to Garmin Connect

`python -m garmin_plan push` (or `make push`) sends the planned sessions to your watch. It takes every session in `garmin_export/plan.json` ([format](../plan-json-format.md)) dated today or later, uploads it to Garmin Connect as a running workout and schedules it on its date, so it syncs to the watch. Module: `garmin_plan.push`; spec: [roadmap 05](../roadmap/05-garmin-workout-export.md).

## Command

```sh
make push ARGS="--weeks 2 --dry-run"     # look at the payloads first
make push ARGS="--weeks 2"               # upload and schedule
python -m garmin_plan push [--weeks N] [--dry-run] [--export DIR] [--today YYYY-MM-DD]
```

| Flag | Meaning |
|---|---|
| `--weeks N` | Push only the first N plan weeks that still have a day from today on (the current week counts as the first). Default: every future session |
| `--dry-run` | Write the payloads to `garmin_export/push/<date>-<template id>.json` and call nothing: no login, no network. Old `*.json` files in `push/` are replaced |
| `--export DIR` | Folder with `plan.json` (default `garmin_export/`) |
| `--today YYYY-MM-DD` | Pretend today is that date |

**Today** is the `--today` date, else Garmin's date in your account's timezone (`g.today()`), else the computer's local date. Never UTC. A session is future when its date is today or later, and `schedule_workout` gets `days[].date` from `plan.json` as it is, so a session never moves to the next day.

Login is `garmin_grab.garmin.login`, the grabber's: the same token store and MFA prompt. Every Garmin call goes through the grabber's `with_retry`, and there is a 1 s pause after each change, against rate limits. The `garminconnect` import happens only in a real push: `profile`, `plan` and `push --dry-run` are standard library only.

## Ownership and names

- Pushed workouts are named `[plan] <title> <date>`, for example `[plan] Cruise Tempo 2024-06-16`. At most 64 characters (`NAME_MAX`, provisional): only the title is shortened, never the date, so the names stay unique.
- The template id and variant, which are stable, go in the workout's description (`garmin_plan: template cruise_tempo, variant 2, 7.0 km`) and in `push_state.json`, not in the name.
- A push removes and recreates only **future** `[plan]` workouts in the dates it pushes. Past sessions, and any workout whose name doesn't start with `[plan] `, are never touched. Rename a pushed workout in Garmin Connect to keep it.

## Re-push and resume

A push runs in three steps:

1. **Resume.** Entries of `push_state.json` without a `scheduled_id` are workouts uploaded but not (or no longer) on the calendar, left by an interrupted push. They are deleted and dropped from the state.
2. **Remove.** `get_scheduled_workouts_by_period(today, last pushed date)` lists the calendar. Each `[plan]` workout there is unscheduled (`unschedule_workout`) and deleted (`delete_workout`).
3. **Push.** For each session: `upload_workout`, save its `workout_id`, `schedule_workout(id, date)`, save its `scheduled_id`.

`push_state.json` is saved (to a `.tmp` file, then renamed) after every change, so Ctrl-C at any point leaves a state the next push can finish: run the same command again. Pushing an unchanged plan twice gives the same set of workouts, without duplicates.

```json
{"2024-06-16": {"workout_id": 1234567, "scheduled_id": 7654321, "name": "[plan] Half-Marathon Long Run 2024-06-16"}}
```

One case can still leave a stray workout: a Ctrl-C after Garmin stored an upload but before its answer arrived. It is not on the calendar and not in the state; delete it by hand in Garmin Connect (its name starts with `[plan]`).

## Payload

`to_garmin(workout, name, description)` builds the dict that `garminconnect`'s `RunningWorkout.to_dict()` would give (sport `running`, one segment, `estimatedDurationInSecs` from the workout's total), with Garmin's ids inlined from `garminconnect.workout` 0.3.19. It is plain JSON uploaded with `upload_workout(dict)`: no `pydantic`, which `garminconnect` only has as an optional extra, and no new dependency. All steps come from one helper, `_step`; the library's `create_*_step` helpers don't cover every role, end and target combination.

| plan.json | Garmin |
|---|---|
| role `warmup`, `rep`, `recovery`, `cooldown` | `stepType` `WARMUP (1)`, `INTERVAL (3)`, `RECOVERY (4)`, `COOLDOWN (2)` |
| end `dist` | `endCondition` `DISTANCE (3)`, `endConditionValue` in metres |
| end `time` | `TIME (2)`, seconds |
| end `lap` | `LAP_BUTTON (1)`, no `endConditionValue` |
| `pace_s_per_km` `[fast, slow]` | primary `pace.zone (6)`: `targetValueOne` = slow m/s < `targetValueTwo` = fast m/s, from `PaceRange.to_speed()` |
| `hr` `[lo, hi]` with a pace | secondary `heart.rate.zone (4)`: `secondaryTargetValueOne/Two` in bpm |
| `hr` without a pace (hill reps, trail) | primary `heart.rate.zone`, bpm |
| neither | `no.target (1)` |
| repeat of 2 or more | `RepeatGroupDTO`: `numberOfIterations`, `ITERATIONS (7)` end, `skipLastRestStep` from `skip_last_rest` |
| repeat of 1 | its steps, without the last recovery (as `plan.md` and the totals) |

`stepOrder` runs 1, 2, 3 … through the whole workout, repeat children included. The step's label and note go in its `description`. The snapshots in `tests/fixtures/push/` (`cruise_tempo` 2, `hill_repeats` 1, `hm_long` 3, VDOT 40, HR 190/50) show complete payloads; regenerate them after a reviewed change with `UPDATE_SNAPSHOTS=1 python -m unittest tests.test_push`.

## Old library

If the logged-in client lacks `upload_workout`, `schedule_workout`, `unschedule_workout`, `delete_workout` or `get_scheduled_workouts_by_period`, the command stops with `error: … push needs garminconnect 0.3.19 or later. Run: make upgrade`.

## Tests

`tests/test_push.py` (TC-8) runs against `FakeGarmin`, never the real library: payload shape per role, end and target; step order; repeats; snapshots; names; future sessions and `--weeks`; re-push; resume after an interruption at every call; dry-run; the old-library message; `push --dry-run` through the CLI.

## Open: manual acceptance on a real account

Push one week, then check in Garmin Connect and on the watch:

- [ ] Whether the watch shows the secondary HR target, and which watch model was used. Older models show only the primary target.
- [ ] Garmin's real maximum workout name length (`NAME_MAX` is 64 until then).
- [ ] Whether `skipLastRestStep` skips a `RECOVERY` step, so the distance matches `plan.md`.
- [ ] The response field names: the workout id after upload (`workoutId`), the schedule id after scheduling and in the period listing (read as `workoutScheduleId`, `scheduledWorkoutId` or `id`), and the listing's date and name fields.
- [ ] Repeats, pace target and alerts while running.
