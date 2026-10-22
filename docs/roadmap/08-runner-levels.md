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

- [ ] Check the layoff table and the level boundaries against the Daniels source before coding. They're cited in `levels.toml`.
- [ ] Beginners without a chest strap get HR caps as guidance only: secondary target or note, never the primary target that would beep all run long.
- [ ] Advanced plans say in `plan.md` that they're a starting point to edit. Manual edits that last through re-plans are handled in 09.
- [ ] The current personal profile is classified, and the result is a sanity check: it should come out as novice by volume and intermediate by fitness.
