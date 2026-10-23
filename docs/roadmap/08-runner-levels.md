# 08 · Runner levels, beginner to advanced

## Requirements

- `src/garmin_plan/data/levels.toml` holds the four levels, after Daniels' White to Gold plans:

  | Parameter | Beginner | Novice | Intermediate | Advanced |
  |---|---|---|---|---|
  | Typical km/week | 0–15 | 15–30 | 30–60 | 60+ |
  | Runs/week | 3 | 3–4 | 4–5 | 6–10 |
  | Q per week | 0 (strides) | 1 | 1–2 | 2–3 |
  | Intensities | E, strides, hills by effort | + R, T | + I, M | all + race-specific |
  | L cap | 50 % / 60 min | 45 % / 90 min | 30–35 % / 120 min | 25 % / 150 min |
  | Ramp per block | +5–8 % | +10 % | +10 % | +5 % |
  | Deload | every 3rd week | every 4th | every 4th | every 4th or on fatigue |
  | Watch targets | time + RPE / HR cap | pace + HR | pace + HR | pace (HR as a check) |
  | Volume unit | minutes | km | km | km or minutes |

- **Two separate axes:** a volume level and a quality level. A runner with a big aerobic base and no speed work gets intermediate volume with novice-level sessions.
- **Detection** from `runs.json`: 4- and 12-week volume, frequency, consistency (share of the last 12 weeks with 2 or more runs), longest recent run, VDOT, and length of history. A level set in `profile.toml` overrides it.
- Templates are filtered by `min_level`. New beginner templates:
  - run/walk ladders, from 8×(2 min run + 1 min walk) to 30 min continuous;
  - a 2 km or 20-minute **time trial** at the end of the first 2–4 weeks, to get a first VDOT.
- **Promotion:** the next level's volume and frequency for 4 or more weeks, and at least 75 % of planned Q sessions done. It takes effect at the next block.
- **Detraining:** after a break, VDOT and volume drop by a layoff table that lives in config. The plan restarts from the matching level.

## Implementation

```text
src/garmin_plan/
  levels.py   detect(history) -> (volume_level, quality_level, reasons)
              params(levels, volume_level, quality_level) -> rules used by 06/07
              layoff(days_off) -> (vdot_factor, volume_factor)
```

- The fixed numbers in `rules.toml` from 06 and 07 move into `levels.toml`. `rules.toml` keeps only what is the same at every level.
- **Beginner plans** run in minutes:
  - `volume.py` already takes a unit;
  - templates use `time` ends and HR-cap targets;
  - `push.py` sends them as a time end with an HR target and a note for RPE.
- Detection prints its reasons. For example: `volume: novice (16 km/wk over 4 wk); quality: intermediate (VDOT 40, 3 Q sessions in 8 wk)`.

No GUI in this section. The level appears in the `plan.md` header and, from 10, on the page.

## Testing strategy

- **Detection fixtures:** a synthetic history for each level, plus edge cases:
  - a split-axis runner;
  - a runner coming back after 6 weeks off;
  - a new runner with no history.
- **Transitions:**
  - promotion only at a block boundary;
  - no flapping between levels across consecutive weeks (hysteresis);
  - demotion after a layoff.
- **Beginner plans:** no pace targets, minute-based volume, and a time trial in weeks 2–4, which then fills in VDOT.
- **Golden plans:** one 12-week plan per level for the same race, with snapshots.

## Completion checklist

- [ ] Check the layoff table and the level boundaries against the Daniels source before coding. They're cited in `levels.toml`. Still open: the values come from the table above and the roadmap's summary, flagged "verify against the book" in `levels.toml`.
- [x] Beginners without a chest strap get HR caps as guidance only: secondary target or note, never the primary target that would beep all run long.
- [x] Advanced plans say in `plan.md` that they're a starting point to edit. Manual edits that last through re-plans are handled in 09.
- [x] The current personal profile is classified, and the result is a sanity check: it should come out as novice by volume and intermediate by fitness.

## Shipped

Runner levels (#11): `levels.py` and `data/levels.toml`, level detection in the profile, beginner plans in minutes and promotion between plans. Documented in [plan profile](../features/plan-profile.md#runner-levels), [plan generator](../features/plan-generator.md#runner-levels), [plan workouts](../features/plan-workouts.md), [plan push](../features/plan-push.md) and the [plan.json format](../plan-json-format.md); tested by `tests/test_levels.py` (TC-11) with four golden plans, `tests/fixtures/plan_golden_<level>.md`. Differences from the plan above:

- Signatures: `params(levels, volume_level, quality_level, rules=None)` lays `levels.toml` (each key a `level = value` table) over a copy of `rules.toml`; `detect(stats, levels)` takes the resolved profile numbers plus consistency, history length, VDOT and the Q sessions of 8 weeks; `layoff(days_off, levels=None)`; `promote(current, stats, levels, *, block_start, compliance=None)`.
- Volume is the 4-week average, with the 12-week average as a gate at half the level's km; consistency is counted as weeks out of 12 with 2+ runs (4, 8, 10). A Q session is a run with 10 minutes or more in Z4 and up.
- Novice and intermediate keep 06's +8 % blocks rather than the table's +10 %. Beginners ramp +6 %, advanced runners +5 %.
- Q per week: beginner 1 Q day from 3 runs that only holds strides by feel, hills by effort or the time trial; novice 1; intermediate 1, 2 from 5 runs; advanced 2 from 4 runs. Daniels' third advanced Q is the long run's quality: a third Q day can't be placed with L and no back-to-back hard days. The checks allow Q days + 1 hard sessions. The rotation got `Q2` rows; a hill day takes the first Q.
- Runs a week are capped at the level's maximum (3, 4, 5, 7): extra profile days rest.
- Beginner plans are planned in km inside and shown in minutes (`weeks[].unit`, `target_min`); the run/walk ladder repeats its set to fill each slot. The time trial is 2 km in week 3; its result is read from the run on that date with `metrics.best_effort` (the 20-minute variant exists, its result isn't read yet).
- The push sends a beginner's HR caps as a note in the step description, with no target, rather than as an HR target.
- Promotion starts from the last `plan.json`'s levels and checks volume and frequency over 4 weeks with a 10 % margin; the 75 % Q compliance clause takes an optional input that 09 will provide and is skipped with a note until then. Levels drop only after a break, at once.
- `strides` is now beginner-level and `progression` intermediate-level, so below intermediate the T + M phase's M session falls back to `cruise_tempo`.
