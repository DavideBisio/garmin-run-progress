# Plan adaptation

Every `make plan`, and `make replan` after each `make grab`, adapts the plan to what actually happened (roadmap 09). It matches the runs in `runs.json` to the last plan's sessions, keeps the past weeks with their result, and rewrites only the days from today on: missed sessions, fatigue and the overrides in `profile.toml`. The thresholds are settings in the `[adapt]` table of `src/garmin_plan/data/rules.toml`.

```text
plan.json (last)  ──match──▶  status of each past session        (match.py)
                                    │
profile + runs ──generate──▶ weeks from next Monday              (planner.py)
                                    │
           keep the last plan's past and current weeks           (replan.py)
                                    │
           adapt the days from today on, log the changes         (adapt.py)
                                    │
                         plan.json, plan.md "What changed"
```

## Command

```sh
make grab                                # fetch the new runs, HRV status and readiness (no planning)
make replan                              # re-plan from them, then push the future sessions again
make replan ARGS="--no-push"             # re-plan only (as make plan)
make replan ARGS="--dry-run"             # re-plan, then push --dry-run: payloads in garmin_export/push/
python -m garmin_plan replan [--weeks N] [--no-push] [--dry-run] [--export DIR] [--today YYYY-MM-DD]
```

`replan` is `plan` (generate, match, adapt; `--weeks` as for `plan`) followed by `push` of every future session ([plan push](plan-push.md#re-plans)). Whether it pushes is `auto_push` in `profile.toml` (default `true`); `--no-push` overrides it for one run. `make grab` stays as it was: it plans nothing. `runs.json` gives the runs and the wellness data (`rhr`, `hrv`, `readiness`); an older `runs.json` without `hrv` or `readiness` simply has no such signals.

```toml
auto_push = false          # profile.toml: make replan writes the plan, make push sends it
```

## Matching runs to sessions

`match.match(plan, runs, today, rules)` gives each planned session up to today a status and the `id` of its run:

| Status | Meaning |
|---|---|
| `done` | A run on its day, with at least `partial` of the planned distance or time |
| `moved` | Done, but on the day before or after (a run not matched to its own day's session) |
| `swapped` | A terrain swap: a trail run (`trail_running`) for a road session, or a road run for a trail one |
| `partial` | Under `partial` of both the planned distance and time; or a hard Q (10+ minutes of hard steps planned, not a time trial) run with under 10 minutes at Z4 and above, an easy run instead |
| `missed` | No run on its day or the day either side |

A session dated today with no run yet has no status: it is still to come. A session's own day comes first, then a free run the day before or after; L takes the longest run, a hard Q the one with 10+ minutes at Z4+, the others the run closest to the planned km. A second run on the same day joins that day's session (a session run in two parts) unless it is the moved run of the day before or after. A run without HR counts as either kind. A time trial is judged by its best 2 km (`history.time_trials`), so its warm-up is not counted.

The share of the last block's Q sessions done (done, moved or swapped) holds level promotions back under 75 % ([plan profile](plan-profile.md#runner-levels)).

## Past weeks

A re-plan keeps the last plan's weeks before its own first Monday exactly as written: the past weeks, and the current week, whose remaining days the adaptation edits in place (new plans start next Monday). Each kept day gets its `status` and `activity_id` again from `runs.json` on every re-plan; the sessions themselves never change. `plan.md` shows a settled day as one line, `- Tue 2024-06-11 · Cruise Tempo - 8.0 km: done`. See [plan.json format](../plan-json-format.md#past-weeks).

## Rules

From today on, in this order. A day already run today, a past day and a locked day are never touched.

1. **Lock** override: the day stays exactly as the last `plan.json` had it (with no session if it had none), through every re-plan.
2. **Skip** override: no session that day (`plan.md`: `skipped`). **Reduce** override: each session becomes an easy run of `reduce` (0.5) times its km. An override wins over the automatic rules: on a kept current-week day that fatigue eased or a missed L moved to, it still applies (an illness skip is never ignored). It is applied once, and the day as it was before it is kept in `change.was`: when a later re-plan finds the day no longer covered by that override (removed or narrowed in `profile.toml`), the day gets it back, a session or the change another rule made. A day changed by an override in a `plan.json` from before `was` existed stays as it is.
3. **Missed Q** is not made up: nothing changes.
4. **Missed L** (in the last `l_move_max_days`, 3, days) moves to the next free day from today: one of your `days`, with no session, and not today when `runs.json` already has a run today. It moves only when that day is at least `l_move_min_days` (2) days after the last Q (not a missed one) and before the next one, the 48 hours between hard days, and when its week, without the sessions missed, stays within `[checks] max_rise` (10 %) of the km planned that week; a second long run in a week that has its own is too much. Otherwise it is skipped, with a line in "What changed" saying why. This volume rule stands in for the generator's week checks (`checks.check_week`), which work on the planner's own week objects.
5. **Fatigue** turns the next Q into an easy run of the same km. Any one of these is fatigue:
   - the latest resting HR more than `rhr_bpm` (5) bpm above the median of the `rhr_days` (30) days before it, with at least `rhr_min_days` (10) values there;
   - an HRV status in `hrv_low` (`LOW`, `POOR`);
   - a training readiness level in `readiness_low_levels` (`POOR`, `LOW`), or, without a level, a score under `readiness_low_score` (50).

   Each value counts only when dated today or up to `fresh_days` (1) before. **Missing data never counts as fatigue**: no HRV or readiness from an older watch, a night without the watch, or too few resting HR days for a baseline leave the plan as it is. One Q is changed at a time: while a Q turned easy is still to come, fatigue changes nothing more.

A changed day records the rule in `changed_by` (`override_skip`, `override_reduce`, `l_moved`, `fatigue`) and `{from, to, reason}` in `change`; its week's `target_km` becomes the sum of its sessions. No rule applies twice, so re-planning twice in a row gives the same plan. A locked day keeps its `status` and `activity_id` from `runs.json`, as every kept day does.

**Volume.** The generator's base is already the actual 4-week average: `km_4w` in the profile is derived from `runs.json` ([plan profile](plan-profile.md)), so a week of missed runs lowers the next plan's curve with no extra rule.

**VDOT.** Once a plan carries a VDOT estimate (`progress.vdot`), the derived VDOT is that estimate, moved on every `vdot_every_weeks` (4) weeks: a race (a run whose `event` is `race` in `runs.json`) faster than it raises it, from the whole run's distance and moving time; a break since the last estimate lowers it by the layoff table ([plan profile](plan-profile.md#runner-levels)), as soon as running resumes. A race counts only when it is after the estimate's own effort (`from_date`) and after the last break that lowered it (`after`, the day running resumed), so a race from before a break never raises it straight back. A time trial replaces it at once. Training-run efforts never change it: they understate fitness, so they could only lower it by mistake. The first estimate, with no plan before, is unchanged: the best training effort of the last 12 weeks, or the time trial. A `vdot` set in `profile.toml` wins as before.

## Overrides

In `profile.toml`, for illness, travel or a day edited by hand in `plan.json`:

```toml
[[override]]
from = 2024-06-18          # a TOML date, no quotes
to = 2024-06-21            # optional: from alone is one day
action = "skip"            # skip, reduce or lock

[[override]]
from = 2024-06-23
action = "lock"
```

A missing `from`, a `to` before it or another action stops the planner with an error naming the table. An override only acts from today on; the past weeks never change.

## What changed

The re-plan's change log is `plan.json`'s `changes` and the `## What changed` section of `plan.md`, after the levels and before the warnings, one line per change:

```text
## What changed

- Tue 2024-06-18 Q → E: resting HR +7 bpm
- Mon 2024-06-17 rest → L: long run of Sun 2024-06-16 missed
```

It is read back from the changed days from today on (plus the missed long runs skipped), so a second re-plan of the day shows the same lines. `history` keeps one entry per re-plan that changed a week, with its changes ([plan.json format](../plan-json-format.md#history)).

## Settings

`[adapt]` in `src/garmin_plan/data/rules.toml`:

| Key | Default | Meaning |
|---|---|---|
| `partial` | 0.70 | A run under this share of both the planned distance and time is partial |
| `rhr_bpm` | 5 | Resting HR more than this above its baseline is fatigue |
| `rhr_days` | 30 | The baseline: the median of these days before the latest value |
| `rhr_min_days` | 10 | Values needed in the baseline, else no resting HR signal |
| `hrv_low` | `["LOW", "POOR"]` | HRV statuses that are fatigue |
| `readiness_low_levels` | `["POOR", "LOW"]` | Training readiness levels that are fatigue |
| `readiness_low_score` | 50 | Without a level, a readiness score under this is fatigue |
| `fresh_days` | 1 | A wellness value counts when dated today or up to this many days before |
| `l_move_min_days` | 2 | A missed L moves only this many days or more before the next Q |
| `l_move_max_days` | 3 | Only an L missed in the last this many days is moved or skipped |
| `reduce` | 0.5 | A reduce override's share of each session's km |
| `vdot_every_weeks` | 4 | Weeks between VDOT re-estimates |

`auto_push` (default `true`) is a `profile.toml` key, not a rule: see [Command](#command).

## Tests

`tests/test_planner.py` (`CliReplan`) runs `replan` through the CLI: `--dry-run` pushes the new plan's sessions and leaves out a day `runs.json` already has a run on, `--no-push` and `auto_push = false` push nothing, a bad `auto_push` is an error, `runs.json`'s HRV status reaches the adaptation. `tests/test_push.py` covers the day already run today. `tests/test_grabber.py` covers the wellness grab.

`tests/test_adapt.py`: matching (all done, Q missed, a Q run easy, two runs on one day, a run on the wrong day, a partial run, a trail run in place of L, today and the future, runs without HR, Q compliance), past weeks (kept, never changed, statuses, the run/walk stage and block not counted twice, no-race deloads put across weekly re-plans, history), the rules (Q missed, L missed with and without room, only on the runner's days, not onto a day already run, too soon after a Q, over the week's volume, fatigue from resting HR, HRV and readiness, missing or stale data never fatigue, thresholds as settings, a day run today left alone, skip, reduce and lock, an override over a fatigue or moved-L day, an override removed restoring the day, a locked day keeping its match), the invariants over whole re-plans (re-planning twice gives the same plan, past weeks, the current week's past days and locked days never change, "What changed"), the VDOT rules (a race before a break never raises it back) and the override parsing, with the documented `profile.toml` example.
