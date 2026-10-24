# 09 · Adaptation loop after each grab

## Requirements

- `make replan` (also run after `make grab`) re-plans from the actual runs:
  1. **Match** each run to a planned session by date (±1 day) and kind. Each session becomes done, partial (under 70 % of the planned distance or time), missed, moved or swapped (a terrain swap).
  2. **Missed Q** is not made up.
  3. **Missed L** moves to the next free day if there are at least 2 days before the next Q. Otherwise it's skipped.
  4. **Fatigue:** any of these turns the next Q into an E run:
     - resting HR more than 5 bpm above its 30-day median;
     - low HRV status;
     - low training readiness.
  5. **Volume:** the actual 4-week average replaces the planned one as the base of the curve.
  6. **VDOT:** re-estimated every 4–6 weeks from best efforts. Paces are re-rendered.
- Only weeks from today on are rewritten. Past weeks keep their plan and their actual result, for compliance.
- **Manual overrides** in `profile.toml`:
  - `[[override]] from/to/action = "skip" | "reduce" | "lock"`, for illness, travel or a day edited by hand;
  - `lock` keeps a day exactly as written through every re-plan.
- After a re-plan, the changed future sessions are pushed again through the replace logic in 05. An option controls whether this happens automatically.
- **New grabber step:** daily HRV status and training readiness. They are optional, and skipped if the watch or the library doesn't provide them.

## Implementation

```text
src/garmin_grab/wellness.py   update_wellness(g, path, first_day) -> hrv.json, readiness.json
                              (same pattern as rhr.py; added to tools/build.py MODULES before export)
src/garmin_plan/
  match.py   match(plan, runs) -> per-session status + activity id
  adapt.py   adapt(plan, history, wellness, overrides, today) -> new future weeks + change log
```

- `build_runs` copies the wellness data into `runs.json` as `hrv` and `readiness` arrays, like `rhr`. Update `docs/runs-json-format.md`.
- `plan.json` gains, for each session, `status`, `activity_id` and `changed_by` (a rule code), and a top-level `history` of re-plans.
- `plan.md` gets a "What changed" section at the top, such as `Tue Q → E: resting HR +7 bpm`.
- **Make targets:** `replan` runs plan and push. `grab` stays unchanged and runs no planning.

No GUI in this section. Status shows up on the page in 10.

## Testing strategy

- **Scenario tests:** fixture timelines with a plan, runs and wellness data, each with an expected result:
  - all done;
  - Q missed;
  - L missed, with room to move it and without;
  - fatigue from resting HR;
  - fatigue from HRV;
  - two runs on one day;
  - a run on the wrong day;
  - a partial run;
  - a trail run done in place of L.
- **Invariants:**
  - past weeks never change;
  - locked days never change;
  - re-planning twice in a row gives the same plan.
- **VDOT update:** only race or time-trial efforts raise it; detraining evidence lowers it.
- **Grabber:** `update_wellness` with a fake client, chunking and the refresh window as in `rhr.py`, and a missing library method.

## Completion checklist

- [x] Missing HRV or readiness data, from older watches or nights without the watch, never counts as fatigue.
- [x] Bundler rules hold for `wellness.py`: unique top-level names and module order. `tools/build.py` fails otherwise.
- [x] Re-planning only touches `[plan]` workouts in Garmin. A session already started on the watch today is left alone. "Started" is read as a run of today already in `runs.json` (after `make grab`); a session in progress that isn't synced yet can't be seen.
- [x] Training-run efforts are never used to raise VDOT. Per the page's own notes, they understate fitness, so they could only lower it by mistake.
- [x] The partial-run threshold and the fatigue thresholds are settings, documented in `docs/features/plan-adaptation.md`.

## Shipped

Adaptation loop (#12): `garmin_grab/wellness.py` (HRV status and training readiness), `garmin_plan/match.py`, `adapt.py` and `replan.py`, the kept past weeks and `history` in `plan.json`, `make replan` and the re-push that leaves a day already run alone. Documented in [plan adaptation](../features/plan-adaptation.md), [HRV status and training readiness](../features/wellness.md), [plan push](../features/plan-push.md#re-plans), [plan profile](../features/plan-profile.md), [plan generator](../features/plan-generator.md#re-plans), the [plan.json format](../plan-json-format.md) and the [runs.json format](../runs-json-format.md); tested by `tests/test_adapt.py`, `tests/test_grabber.py` (`Wellness`), `tests/test_push.py`, `tests/test_planner.py` (`CliReplan`) and `tests/test_levels.py` (Q compliance). Differences from the plan above:

- Signatures: `update_wellness(g, out, first_day)` writes both files (and `wellness_fetched.json`) into the export folder; `match(plan, runs, today, rules, hr_max=None, hr_rest=None)` (the HR bounds tell a Q run); `adapt(plan, history, wellness, overrides, today, rules, easy, prev=None, days=None, ran_today=False)` edits the plan in place and returns the change log; `replan.replan` ties the generator, `keep_past`, `match` and `adapt` together for `plan` and `replan`.
- Partial means under 70 % of both the planned distance and time (a slow run that went the time isn't partial); a hard Q run with under 10 minutes at Z4+ is partial too. A time trial is judged by its best 2 km, not its planned total.
- A missed L is only moved or skipped within 3 days (`l_move_max_days`), so a weekly re-plan doesn't move last week's long run into this one. Fatigue changes one Q at a time; each wellness value counts only when fresh (today or yesterday).
- Two runs on one day count as one session unless the second is the moved run of the day before or after.
- The VDOT across re-plans is `progress.vdot`: training efforts give the first estimate only; races (`event` = `race` in `runs.json`) raise it every 4 weeks, a time trial replaces it at once, and a break lowers it by the layoff table once running resumes (during the break the layoff factor applies on top, as before).
- Q compliance for the level promotion is the last block's Q sessions done, moved or swapped over those planned.
- Without a race the phase cycle is carried (`progress.cycle_start`), so its deloads stay put across re-plans; `progress.plan_start` marks the plan's own weeks so the kept ones don't count twice.
- "What changed" goes after the levels line and before the warnings in `plan.md`.
- Review fixes: an override wins over fatigue and a moved L on a kept day and is undone (`change.was`) when removed; a missed L moves only to one of the runner's days, not onto a day already run, 2+ days from the Qs on both sides and within the week's planned km + 10 %; a locked day keeps its match fields; a race from before a break can't raise the lowered VDOT back (`progress.vdot.after`); the grabber records how far HRV and readiness were fetched (`wellness_fetched.json`) so an account without them isn't re-fetched from the first run on every grab.

Open, to check on a real account: the shapes of `get_hrv_data_range` and `get_training_readiness` responses (parsed defensively, field names unconfirmed), Garmin's day limit for an HRV range request (28 days assumed), and readiness levels and score bands (`LOW`/`POOR`, under 50).
