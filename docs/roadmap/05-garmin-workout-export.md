# 05 · Garmin workout export

## Requirements

- `python -m garmin_plan push [--weeks N] [--dry-run]` does three things for every future session in `plan.json`:
  1. converts it to a Garmin `RunningWorkout`;
  2. uploads it;
  3. schedules it on its date, so it syncs to the watch.
- Step targets:
  - **primary** is pace, as a speed range;
  - **secondary** is HR, as a custom bpm range;
  - HR-only or open targets are used where the template says so (hill, trail).
- Ownership:
  - pushed workouts are named `[plan] <title> <date>`;
  - a re-push removes and recreates only **future** `[plan]` workouts;
  - past sessions and any workout without the prefix are never touched.
- `--dry-run` writes the JSON payloads to `garmin_export/push/` and calls nothing.
- Login reuses `garmin_grab.garmin.login`, so it shares the token store and MFA flow. `with_retry` and a delay between calls avoid rate limits.
- If the installed `garminconnect` lacks `upload_running_workout` or `schedule_workout`, the command explains how to upgrade, as the resting HR step does.

## Implementation

```text
src/garmin_plan/
  push.py   to_garmin(workout) -> RunningWorkout; push(g, plan, today, dry_run)
            state in garmin_export/push_state.json: {date: {workout_id, scheduled_id}}
```

- **Step mapping:**

  | Role | `StepType` |
  |---|---|
  | warmup | `WARMUP (1)` |
  | rep | `INTERVAL (3)` |
  | recovery | `RECOVERY (4)` |
  | cooldown | `COOLDOWN (2)` |

  - Runs without a warmup or cooldown (easy, steady and progression runs) are main set only: every step is `rep`, so `INTERVAL`. `hm_long`'s steady km between the marathon-pace blocks is `recovery`, so `RECOVERY` (see [plan workouts](../features/plan-workouts.md)).

  - A distance end uses `ConditionType.DISTANCE`, a time end uses `TIME` and lap button uses `LAP_BUTTON`.
  - Repeats become `RepeatGroup(numberOfIterations=n, workoutSteps=[…])`, with `skipLastRestStep` from `skip_last_rest`. A repeat of 1 always has it `true` (a single rep has no recovery between reps), so a flattened repeat of 1 leaves its last recovery out too.
  - Steps are built as `ExecutableStep` directly, through one helper. The library's `create_*_step` helpers don't cover every role, condition and target combination.
- **Targets:**
  - `PaceTarget(lower_limit=slow m/s, upper_limit=fast m/s)`; the model validator rejects the reverse order;
  - `CustomHeartRateTarget(lower, upper)` goes into the `secondaryTarget*` fields.
- **Re-push flow:**
  1. `get_scheduled_workouts_by_period(today, last_plan_date)`;
  2. keep only the `[plan]` workouts;
  3. `unschedule_workout` and `delete_workout` on each;
  4. `upload_running_workout`, then `schedule_workout(id, date)`;
  5. save `push_state.json` after each step, so Ctrl-C leaves a consistent state.
- **Make targets:** `make plan` (render) and `make push ARGS="--weeks 2"`.

No GUI. The watch and Garmin Connect calendar are the UI.

## Testing strategy

- **Unit tests with `FakeGarmin`:** a class that records calls and returns fake ids. They cover:
  - payload shape for each step role, end condition and target combination;
  - snapshot tests of 3 workouts against `tests/fixtures/push/*.json`.
- **Replace logic:**
  - a second push with an unchanged plan only recreates the same set, with no duplicates;
  - past dates and non-`[plan]` workouts are never touched;
  - an interruption halfway through can be resumed.
- **Manual acceptance on a real account:** push one week, then check in Garmin Connect and on the watch:
  - names;
  - repeats;
  - pace target shown;
  - HR shown as secondary;
  - alerts while running.

## Completion checklist

- [ ] Find out on a real watch whether the secondary HR target is shown, and record the watch model in the feature doc. Older models show only the primary target.
- [ ] Find Garmin's maximum workout name length. Shorten the title, never the date, so the names stay unique.
- [ ] Use the local date in `schedule_workout`, not UTC. A session at 23:30 must not land on the next day.
- [ ] Verify `RepeatGroup.skipLastRestStep` against the distance shown in 04.
- [ ] Add no new dependencies. `pydantic` arrives through `garminconnect`. The upgrade message names the minimum version that has these methods (0.3.19 here).
- [ ] Hide the `push_state.json` and `push/` dry-run output from git through `garmin_export/`.
