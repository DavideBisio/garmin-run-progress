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

- [ ] Missing HRV or readiness data, from older watches or nights without the watch, never counts as fatigue.
- [ ] Bundler rules hold for `wellness.py`: unique top-level names and module order. `tools/build.py` fails otherwise.
- [ ] Re-planning only touches `[plan]` workouts in Garmin. A session already started on the watch today is left alone.
- [ ] Training-run efforts are never used to raise VDOT. Per the page's own notes, they understate fitness, so they could only lower it by mistake.
- [ ] The partial-run threshold and the fatigue thresholds are settings, documented in `docs/features/plan-adaptation.md`.
