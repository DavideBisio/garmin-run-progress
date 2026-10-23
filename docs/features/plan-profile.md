# Planner profile, paces and HR zones

The planner's starting point: what you are able to run today, and when you can run. `python -m garmin_plan profile` (or `make plan-profile`) reads `garmin_export/profile.toml` and `garmin_export/runs.json` and prints every value with where it came from, then your [runner levels](#runner-levels) and why. Modules: `garmin_plan.profile`, `history`, `levels`, `physiology`, `metrics`.

## profile.toml

`garmin_export/profile.toml` is gitignored with the rest of `garmin_export/`; it holds only what the data can't tell. Every key is optional.

```toml
hr_max = 188              # bpm; also hr_rest = 48 to override the resting HR
vdot = 52.0               # from a race or time trial; wins over the derived value
days = ["tue", "thu", "sat", "sun"]   # available days (mon … sun, or full names)
long_run_day = "sun"      # must be one of days
hill_days = ["sat"]       # days with hill access
volume_level = "novice"   # beginner, novice, intermediate, advanced: wins over detection
quality_level = "intermediate"
unit = "min"              # km or min: the plan's volume unit (default: km, min for beginners)

[race]
date = 2027-04-11         # a TOML date, no quotes
distance = "hm"           # 5k, 10k, hm (half), m (marathon), or km as a number
goal = "1:35:00"          # optional, H:MM:SS or MM:SS

[week]                    # optional: pin days of the generated plan, day = "template:variant"
tue = "cruise_tempo:2"
sun = "steady_long:1"

[[override]]              # optional, repeatable: skip, reduce or lock days (plan adaptation)
from = 2027-02-02
to = 2027-02-05
action = "skip"
```

`make plan` generates the plan from these values ([plan generator](plan-generator.md)); `[week]` days override the generated ones (see [plan workouts](plan-workouts.md#manual-schedule-week)).

The derived numbers (`km_4w`, `km_12w`, `runs_per_week`, `longest_8w`) can be set too, for example after a break the data doesn't explain.

`[[override]]` tables (`parse_overrides`, `Profile.overrides`) skip, reduce or lock days from today on: see [plan adaptation](plan-adaptation.md#overrides). A missing `from`, a `to` before it or an unknown action is a `ProfileError`.

## Resolution order

For each field: the value in `profile.toml` (`set`), else derived from `runs.json` (`derived`), else a default (`default`). Each fallback to a default prints a warning on stderr. A missing `profile.toml` or `runs.json`, or an empty history, never fails. Values in the file that can't be used stop with an error: `hr_max` not above `hr_rest`, unknown day names, a `long_run_day` outside `days`, a `[race]` without a date, a file that isn't valid TOML.

| Field | Derived from `runs.json` | Default |
|---|---|---|
| `hr_max` | Second-highest run peak (99th percentile of the HR stream, else `maxHr`) within 120–230 bpm, as the page's Data tab | 190 |
| `hr_rest` | Median of the `rhr` days within 365 days of the last entry, rounded half up, as the page | 50 |
| `vdot` | Best 5 km, 10 km or half effort ([best efforts](best-efforts-and-vdot.md)) in the last 12 weeks | 30 |
| `km_4w`, `km_12w` | Average km per Monday-based week over the last 4 / 12 full weeks before this one; weeks without runs count as 0 | 0 |
| `runs_per_week` | Runs in the last 4 full weeks / 4 | 0 |
| `longest_8w` | Longest run in the last 56 days | 0 |
| `days`, `long_run_day`, `hill_days` | – | tue, thu, sat, sun; long run sun (else the last available day); no hill days |
| `volume_level`, `quality_level` | [Detected](#runner-levels) from the numbers above; with a previous `plan.json`, moved on from its levels | beginner (under 4 weeks of runs) |
| `unit` | – | The volume level's: `min` for beginners, else `km` |

Runs without a GPS stream (treadmill, indoor) count in the volume by their summary distance, as on the page. Weeks follow the date part of `date`, so a run at 23:59 on Sunday stays in that week.

With less than 4 weeks between the first run and today, the volume fields and VDOT fall back to their defaults with a warning, rather than extrapolating from a few runs.

**VDOT from training is a floor.** Efforts come from any run, so without races the value understates fitness. The output marks it `derived (training efforts)` and names the run it came from; a race or time-trial `vdot` in the profile wins.

**The VDOT across re-plans** (roadmap 09, `reestimate_vdot`). The first derived VDOT is kept in `plan.json`'s `progress.vdot` (before any layoff factor). From then on it is the derived VDOT, re-estimated every 4 weeks (`[adapt] vdot_every_weeks`): a faster race (`event` `race` in `runs.json`) raises it (`derived: race 10 km on <date>`), a break since the last estimate lowers it by the layoff table as soon as running resumes, a time trial replaces it at once. Training efforts never change it again. See [plan adaptation](plan-adaptation.md#rules).

**The time trial.** A beginner's plan has a 2 km time trial in week 3 ([plan generator](plan-generator.md#runner-levels)). When `plan.json` plans one and `runs.json` has a GPS run on that date, its best 2 km (`metrics.best_effort`) gives the derived VDOT, shown as `derived: 2 km time trial on <date>`. 2 km is not one of the page's best-effort distances, so this is separate code (`history.time_trials`). The next plan records the result in `plan.json`'s `progress` ([format](../plan-json-format.md#progress)), so it keeps giving VDOT after any number of re-plans; with several, the latest counts.

A `plan.json` that can't be read, or whose weeks and days lack their dates, is ignored with a warning: the levels are detected afresh and the block, ladder and time trials start over.

## Runner levels

A runner has two levels (roadmap 08), beginner, novice, intermediate or advanced, after Daniels' White to Gold plans: a **volume** level (how much you run: the volume curve, the long run caps, the run count) and a **quality** level (which sessions: the Q count, the templates' `min_level`, the time trial). A big aerobic base without speed work is intermediate by volume and novice by quality. `volume_level` or `quality_level` in `profile.toml` wins; the numbers each level sets are in `src/garmin_plan/data/levels.toml`.

**Detection** (`levels.detect`, `[detect]`): the highest level whose every minimum holds.

| Level | 4-week km | 12-week km | Runs/week | Weeks of 12 with 2+ runs | Longest, 8 wk | History | VDOT | Q sessions, 8 wk |
|---|---|---|---|---|---|---|---|---|
| novice | 15 | 7.5 | 2 | 4 | 5 km | 4 weeks | 30 | 0 |
| intermediate | 30 | 15 | 3 | 8 | 10 km | 8 weeks | 38 | 2 |
| advanced | 60 | 30 | 5 | 10 | 16 km | 16 weeks | 50 | 8 |

The first five columns set the volume level, the last two the quality level. A Q session is a run with 10 minutes or more in Z4 and above: from the HR stream when it has one, else the whole run when its average HR is in Z4 (`history.q_sessions`). With no VDOT (none set, no 5 km, 10 km or half effort, no time trial) the quality level is beginner; under 4 weeks of runs, so is the volume level. The output gives the reasons:

```text
Levels: volume: novice (18 km/wk over 4 wk); quality: intermediate (VDOT 39, 7 Q sessions in 8 wk)
```

and, when a level is held back, what by: `volume: novice (35 km/wk over 4 wk; not intermediate: 2 runs/wk (needs 3))`.

**After a break** (`levels.layoff`, `[layoff]`): with more than 5 days since the last run, the derived 4-week volume restarts from the weekly km of the 4 weeks before the break times the volume factor, and the derived VDOT drops by the VDOT factor; the levels are detected from what is left, so the plan restarts at the matching level. The other volume numbers come from before the break too, since the last weeks hold no runs: the runs a week of the 4 weeks before it, the weeks with 2+ runs of the 12 weeks to the last run, and the longest run of the 8 weeks to the last run times the VDOT factor (the fitness lost; the volume factor is the restart load, not what you can still cover). After 60 days off from 50 km a week that is 16.5 km a week, 5 runs, 12 of 12 weeks and a longest run of about 8 km: novice.

| Days off | VDOT factor | Volume factor |
|---|---|---|
| up to 5 | 1 | 1 |
| 6–28 | 1 down to 0.935 | 0.5 |
| 29–56 | 0.935 down to 0.86 | 0.33 |
| 57–72 | 0.86 down to 0.80 | 0.33 |
| more | 0.80 | 0.33 |

The factors follow Daniels' guidance on returning from a break as the roadmap summarises it; they are still to be checked against the book.

**Promotion** (`levels.promote`): when `plan.json` already has levels, the new plan starts from them rather than from detection. A level moves up only at a block's start (counted from the last plan's `progress.block_start`, else its first week; the week after a deload; or past the plan's end), so re-planning twice in one week doesn't promote mid-block; one level at a time: volume when each of the last 4 weeks holds the next level's km plus 10 % (`margin`, the hysteresis that stops a runner at a boundary flapping between levels) and its runs a week; quality when detection finds the next level and VDOT is 1 point over its minimum. Mid-block the reason says `novice until the next block, then intermediate (…)`. Levels never drop, except after a break, when they drop at once to what detection finds. The roadmap's third condition holds both axes back: at least 75 % (`[detect] compliance`) of the last block's planned Q sessions done. `match.q_compliance` matches the runs to the last plan's sessions (`match.match`, roadmap 09) and counts the Q days done, moved or swapped over the Q days up to today in the block that ends before the new plan (the weeks back to the one after the last deload). A block with no Q session to count skips the check with a note.

## Pace zones (Daniels)

With `VO2(v) = −4.60 + 0.182258·v + 0.000104·v²` (v in m/min) and `%max(t) = 0.8 + 0.1894393·e^(−0.012778·t) + 0.2989558·e^(−0.1932605·t)` (t in minutes), `VDOT = VO2(m/t) / %max(t)`.

| Zone | Pace |
|---|---|
| E, T, I | Solve `VO2(v) = f · VDOT` for v (the positive root of the quadratic), with `f` from `src/garmin_plan/data/rules.toml` |
| M | Predicted marathon race pace: `race_time` bisects `vdot(42195, t) = VDOT` |
| R | I pace minus 6 s per 400 m (15 s/km) |

M follows Daniels' race-equivalency table (the predicted marathon pace), not the M column of his training-pace table, which is slower at low VDOT (about 7:03/km against 6:51/km at VDOT 30).

The fractions are calibrated against Daniels' published tables for VDOT 30, 40, 50 and 60 (`tests/fixtures/daniels_paces.json`):

| `f` | Value | Fit |
|---|---|---|
| E | 0.69 | Inside the published E range at all four VDOTs |
| T | 0.88 | Within 0.5 s/km |
| I | 0.975 | Within 1.2 s/km |

At VDOT 50 that gives E 5:11, M 4:31, T 4:15, I 3:55, R 3:40 per km.

## HR zones

The same Karvonen definition as the page's `hrrZones` ([zones](training-load-zones-consistency.md)): the upper bounds of Z1–Z4 are `rest + p·(max − rest)` for p = 0.6, 0.7, 0.8, 0.9, with rest clamped to `max − 20` and rounded half up (`floor(x + 0.5)`, not Python's `round()`). A bound bpm belongs to the upper zone. Max 190 / rest 50 gives 134, 148, 162, 176.

## Parity with the page

`garmin_plan.metrics` ports the page maths the planner needs from `src/page/js/metrics.js`: `vdot`, `gap_factor`, `trimp`, `hr_zones` (`hrrZones`), `week_of`, `best_effort`, and `prepare`'s `_km`, `_hrOk` and `_hrPeak`. `tests/fixtures/metric_vectors.json` holds inputs and the JS outputs; `tests/metrics.test.mjs` checks the page still produces them and `tests/test_plan.py` checks the Python port within 1e-9 (bpm bounds exactly). If either side changes, CI fails. To change a formula, change both and regenerate the vectors from the JS.
