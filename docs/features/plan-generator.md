# Planner: the plan generator

`python -m garmin_plan plan` (or `make plan`) generates the training plan from your [profile](plan-profile.md) and `runs.json`: from the Monday after today to the race week, each week's phase, volume, sessions and their sizes, checked for safety and fixed where it can be. It writes `garmin_export/plan.json` ([format](../plan-json-format.md)) and `garmin_export/plan.md`, and lists every warning with the rule that fired and what the planner did. Modules: `garmin_plan.planner`, `select`, `size`, `terrain`, `load`, `checks`, `fix`, on top of 06's `skeleton`, `volume`, `phases` and `split`. Every tunable number is in `src/garmin_plan/data/rules.toml`.

## Command

```sh
make plan                                # to the race week (8 weeks without a race)
make plan ARGS="--weeks 4"               # only the first 4 weeks
python -m garmin_plan plan [--weeks N] [--export DIR] [--today YYYY-MM-DD]
```

| Flag | Meaning |
|---|---|
| `--weeks N` | With a race, keep only the first N weeks of the plan to the race (the weeks themselves don't change). Without a race, the plan's length. Default: to the race week, else 8 weeks (`[phases] no_race_cycle` × `no_race_weeks`) |
| `--export DIR` | Folder with `profile.toml` and `runs.json` (default `garmin_export/`) |
| `--today YYYY-MM-DD` | Pretend today is that date |

Unusable available days (no day for Q at 48 h from L), a race date before the plan's first Monday or a bad `[week]` line stop with `error: …`.

## Each week

1. **Phase and volume** (06). The phase calendar counts back from the race (base, R + T, I + T, T + M, then a 2-week taper), or cycles base and R + T. The build weeks follow the 4-week block curve from your 4-week average (×1.00, ×1.08, ×1.16, deload ×0.85), the deloads moved off phase starts. The taper weeks are `[volume] taper` = 0.7 and 0.5 of the last build week that isn't a deload (Bosquet et al. 2007: a 41–60 % cut over about 2 weeks, intensity kept). The race week stops the day before the race.
2. **Slots** (06). Each available day gets L, Q, E or F, the same every week.
3. **Session choice** (`select.py`, `[rotation.<phase>]`). Each phase lists, per week of its block, the Q and L templates in order of preference. Q alternates A (the phase's first quality type) in weeks 1 and 3 and B in week 2 and the deload week; L goes steady, progression, longest (the block's biggest week), then short in the deload.

   | Phase | Q-A | Q-B | L (weeks 1–4) |
   |---|---|---|---|
   | base | `strides` (hill day: `hill_repeats`) | `strides` | steady ×4 (week 3 on a hill day: `hilly_long`) |
   | rt | `r_300`, `r_ladder` (hill day: `hill_repeats`) | `cruise_tempo` | steady, `progression_long`, steady (hill day: `hilly_long`), steady |
   | it | `vo2_intervals` | `cruise_tempo` | steady, `progression_long`, steady (hill day: `trail_long`), steady |
   | tm | `cruise_tempo` | `progression` | steady, `progression_long`, `hm_long`, steady |
   | taper | `cruise_tempo`, then `strides` | | steady, steady |

   **Levels** come in 08; until then every runner counts as `[rotation] level` = intermediate, and a template above the level falls back to the next one in the list (`r_300` → `r_220`), or the lowest-level one when none fits.
4. **Q sizing** (`size.py`, `[caps]`). Q is sized first: the last ladder variant whose **hard portion** (reps at M, T, I or R pace and hill reps; never the warm-up, cool-down or recoveries) fits under its cap and whose total fits the slot budget (the week minus L and each E slot at the E minimum). Every variant is scanned, because hard km need not grow along a ladder (`cruise_tempo` goes 6.0 then 5.0). The deload week takes one variant lighter (`[rotation] deload_lighter`).

   | Hard portion | Cap, share of the week (Daniels) |
   |---|---|
   | R (also hill reps, strides) | 5 %, at most 8 km |
   | I | 8 %, at most 10 km |
   | T | 10 % |
   | M (also L's marathon-pace blocks) | 20 % |

   When even the smallest variant is over its cap or the budget (low volume), it is used anyway with a `forced_size` note: a known exception, never a violation, so the fixer doesn't loop on it.
5. **Split** (06). The week's km go to L, Q (at its instantiated km) and the E and F runs, each rounded to 0.1 km so the days add up to the week heading. A leftover too small for an easy run becomes a longer **warm-up** on the Q day, or a longer first easy step when the template has no warm-up (the progression run), so the day's km and the workout's km agree; a Q with neither keeps its size, the week becomes the sum of its sessions and a `split` warning says so. L's cap uses the longest long run of the last 8 weeks (L, or a `[week]` day on the long-run day), never under the profile's `longest_8w`.
6. **Fitting**. E and F runs are the `easy` template, L the chosen long-run template, both stretched to the split's exact km with `instantiate` overrides (the easy part of a progression or half-marathon long run takes the difference; its marathon-pace part stays). A long run that doesn't fit (a 13 km progression run in an 11 km slot) falls back to the next candidate, `steady_long`.
7. **Checks, then fixes**, below. `[week]` days then replace their weekday's session.

## Hill and trail swaps

On a day in `hill_days`, `hill_repeats` replaces Q-A in the base and R + T phases, and `hilly_long` (base, R + T) or `trail_long` (I + T) replaces the block's longest L, never in a deload, the T + M phase or the taper. A swapped long run keeps the **time budget** of the flat one (its km at E pace); its main step stretches to fill it.

Their climbing is part of 80/20: a hilly long run spends an hour or more at Z2–3 and a trail run under a Z3 cap, and neither counts as easy (Z1–2). At ordinary volumes such a run alone takes the week under 80 % easy, so a long-run swap that would put the week under the easy share (when the flat long run doesn't) is left out, with a `hill_swap` warning: it only happens in weeks big enough to hold it.

## Volume and load

- **Flat-equivalent km** (`terrain.py`). A hill or trail session's volume is counted with Minetti's cost of running, the factor the page's grade-adjusted pace uses (`metrics.gap_factor`, clamped at ±30 %): half the distance climbs and half descends, each at `climb_m_per_km` × km over half the distance. 40 m/km of climbing (trail) counts ×1.08; 20 m/km (hilly) ×1.02.
- **Projected TRIMP** (`load.py`). Each step counts its duration at the midpoint of its HR target (else its pace zone's usual zone: E and jogs Z2, T Z4 …) through the page's Banister `trimp`, with resting HR clamped to max − 20 as the page does; repeats count n times, their last recovery once less when skipped.
- **Load ratio** (`history.daily_load`, `history.acwr`): the page's daily TRIMP of every run, then the last 7 days' load over a quarter of the last 28 days'. The planned weeks are appended to the real history up to today (runs dated after `--today` are left out, not counted twice), so the ratio of week 1 is real history plus the plan. With less than 28 days of history in `runs.json` the check is skipped for the whole plan, with one `acwr_skipped` warning.

## Checks

Every generated week (`checks.py`, `[checks]`):

| Code | Rule |
|---|---|
| `easy_share` | At least 80 % of the running time easy, Z1–2 only, the page's Easy share KPI. `Z3 cap` and `Z2-3` steps are not easy; a step with no HR target uses its pace zone |
| `hard_count` | At most 2 hard sessions. A hard session is a long run (L, hill, trail) or one with hard km |
| `hard_adjacent` | Never two hard sessions on consecutive days, across the weekend too |
| `volume_rise` | Flat-equivalent km rise at most 10 % on last week. Exempt: the first planned week, the deload week and the week after it |
| `acwr_high`, `acwr_low` | Projected 7:28-day load ratio within 0.8–1.3 on the week's Sunday. A low ratio is expected, so not checked, in the deload week and the taper |
| `long_share` | L at most `[split] long_share_cap` (45 %) of the week, or the E minimum in a small week, as in the split |

Limits allow 0.2 km for the split's rounding to 0.1 km.

## Fixes

`fix.py` changes one thing at a time and re-checks, at most `[fix] max_iter` = 12 times, in this order, using only the fixes that can help the checks that failed:

| Fix | Helps | Effect |
|---|---|---|
| Shrink Q | `easy_share`, `acwr_high` | One ladder variant down; the week is split again, so the km freed go to the easy runs |
| Trim L | `volume_rise`, `acwr_high`, `long_share` | 1 km off L (`trim_l_km`), never under the E minimum |
| Drop F | `volume_rise`, `acwr_high` | The F run becomes a rest day |

A fix that changes nothing (Q already at variant 1, L at the E minimum, a `[week]` day) is used up; nothing helps hard days or a low ratio. The result is deterministic. When L is trimmed or F dropped, the week's `target_km` becomes what is left, and the warning gives the old and new km. Whatever still fails becomes a warning saying why: no fix helps, or the fixer stopped after 12 fixes.

## Warnings

Each warning is `{rule, detail, action}` in `plan.json`: the plan-wide ones at the top level, the others in their week. `plan.md` lists the plan-wide ones under `## Warnings`, with a line per week that has its own, and repeats each week's under its heading, which also names the phase and the deload:

```text
## Week of 2024-06-24 - 34.8 km · Base

- **hill_swap**: a hilly long run on sun would leave 71 % of the running time easy, under 80 %. Planner: kept the flat long run.
```

| Rule | Where | When |
|---|---|---|
| `phases` | plan | Too few weeks to the race: the phases shortened, in a fixed order |
| `feasibility` | plan | The goal is too far for the weeks left (below) |
| `acwr_skipped` | plan | Under 28 days of history |
| `split` | week | The split dropped Q, ran an easy run short, left easy runs longer than L, or had a leftover the Q template can't take |
| `forced_size` | week | The smallest variant, over its cap, used anyway |
| `hill_swap` | week | A hilly or trail long run left out for 80/20 |
| `race_week` | week | No session from race day on |
| a check code | week | What failed and what the fixer did: `fixed: Q cruise_tempo variant 5 -> 4`, or why it is left |

## Goal feasibility

With a race goal time, the goal VDOT is `vdot(distance, goal)`. VDOT rises about 1 point per 4–6 weeks of training, so over the weeks to the race a gap of at most weeks / 6 points gets no warning, up to weeks / 4 is `ambitious`, more `unrealistic` (`[feasibility]`; the boundaries count on the lenient side). The planner only warns: the paces stay at your current VDOT until a race or time trial raises it.

## `[week]` overrides

A `[week]` table in `profile.toml` pins weekdays to `template:variant` ([plan workouts](plan-workouts.md#manual-schedule-week)). Those days replace the generated ones in every week, with `slot` `null`; the fixer never changes them, the checks still count them, and such a week's `target_km` is the sum of its sessions.

## Tests and the golden plan

`tests/test_sessions.py` covers the sizing tables at 15, 25, 40 and 60 km a week, the 12-week rotation over 3 blocks, the level fallback, the overrides, flat-equivalent km and projected load; `tests/test_checks.py` one failing week per check, the fixer and feasibility; `tests/test_planner.py` the generator and the `plan` command. The golden file `tests/fixtures/plan_golden.md` is a 16-week half-marathon plan for a generic runner (VDOT 40, HR 190 / 50, 30 km a week, longest run 12 km, five days, hills on Thursday and Sunday, a 1:43:30 goal). After a deliberate change, regenerate it and review the diff:

```sh
UPDATE_GOLDEN=1 PYTHONPATH=src python -m unittest tests.test_planner
```
