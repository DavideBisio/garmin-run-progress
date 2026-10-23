# 04 · Workout templates and markdown renderer

## Requirements

- A template library in `src/garmin_plan/data/workouts.toml`. Each template has:
  - `id`, `title`, `kind` (E, L, R, T, I, M, hill, trail) and `min_level`;
  - warmup, main set and cooldown, with repeat groups;
  - a **ladder** of size variants, smallest first.
- Each step has:
  - an end condition: distance, time or lap button;
  - a target: pace zone, HR zone, both, or open.
- Default targets:
  - recoveries: jog at Z2;
  - reps: their own intensity zone;
  - hill and trail steps: HR or open targets, ending on time rather than distance.
- The renderer takes a template, a variant and the profile, and produces a resolved workout: pace and HR ranges, distance, estimated duration, and hard km (the distance at quality intensity, used by the caps in 07).
- Markdown output follows the current `training_plan.md` format:
  - `### Title - 6.0 km (~35 min)`;
  - a `lap | pace range | FC range | duration | comment` table;
  - repeats grouped as `**Repeat 8x**` with `↳ **Rep**` and `↳ **Recovery**` rows.
- **Manual schedule (MVP):** a `[week]` table in `profile.toml` maps weekdays to `template:variant`. `python -m garmin_plan plan --weeks N` writes `plan.json` and `plan.md` from it.

## Implementation

```toml
# src/garmin_plan/data/workouts.toml
[[workout]]
id = "cruise_tempo"
title = "Cruise Tempo"
kind = "T"
min_level = "novice"
warmup   = { pace = "E", dist = 2000 }
main     = { repeat = "n", rep = { pace = "T", hr = "Z4", dist = "d" },
             recovery = { pace = "jog", hr = "Z2", time = 60 } }
cooldown = { pace = "E", dist = 1000 }
ladder   = [ { n = 2, d = 1200 }, { n = 3, d = 1200 }, { n = 4, d = 1200 },
             { n = 2, d = 3000 }, { n = 1, d = 5000 } ]
```

```text
src/garmin_plan/
  model.py       Step(role, end, value, pace, hr, note), Repeat(n, steps), Workout(...).km/.seconds/.hard_km
  templates.py   load + validate workouts.toml; instantiate(template, variant, zones) -> Workout
  render_md.py   Workout -> markdown section; Plan -> plan.md
  plan_io.py     read/write plan.json
```

- `pace = "jog"` is defined as the slow end of E plus 30 s/km. Duration estimates use the midpoint of each pace range.
- Totals are **computed from the parts**, never typed in. The hand-written plan had a heading of 6.0 km over parts adding up to 4.9 km.
- `plan.json` (documented in a new `docs/plan-json-format.md`):

  ```json
  { "version": 1, "generated": "…", "profile_hash": "…",
    "weeks": [ { "start": "YYYY-MM-DD", "target_km": 18,
                 "days": [ { "date": "…", "slot": "Q",
                             "workout": { "id": "…", "variant": 1, "steps": [] } } ] } ] }
  ```

  It holds resolved steps, so 05 and 10 don't need the templates.

No GUI in this section.

## Testing strategy

- **Golden file:** render every template's smallest and largest variant for a fixed generic profile (VDOT 40, HR 190/50). Compare with `tests/fixtures/workouts_golden.md`; a reviewed diff updates it.
- **Validation errors:**
  - an unknown zone;
  - a ladder missing a variable used in the steps;
  - a time-ended step with a pace target but no distance estimate;
  - a duplicate `id`.
- **Arithmetic:** distance and time sums with repeats, including a last recovery being skipped or not (it must match 05).
- **Manual schedule:** an unknown template or variant in `[week]` fails with the line it came from.

## Completion checklist

- [x] The pace-range order is handled once in `model.py`: a slower pace means a lower speed. No caller swaps bounds.
- [x] Whether the last recovery in a repeat counts is decided once, and it matches Garmin's `skipLastRestStep` in 05, so the markdown and the watch show the same distance.
- [x] Template `id`s are stable and documented as such. They end up in `plan.json` and in Garmin workout names, so renaming one orphans pushed workouts.
- [x] The rendered tables still read well on GitHub and in VS Code preview, including `|` escaping in comments.
- [x] The existing personal `training_plan.md` workouts (220 m reps, ladder, cruise tempo, VO2 intervals, progression, long runs, hill repeats, trail run) can all be expressed as templates. Add a step feature if one can't.

Shipped: `src/garmin_plan/` `model`, `templates`, `render_md` and `plan_io`, with `data/workouts.toml` (13 templates) and `[bands]` in `data/rules.toml`, a `[week]` table in `profile.toml`, `python -m garmin_plan plan --weeks N` and `make plan`, and `tests/test_workouts.py` with the golden file `tests/fixtures/workouts_golden.md`. The last recovery counts (`skip_last_rest = false`, which 05 maps to `skipLastRestStep`). The main set is a list of steps and repeats, so the ladder and progression runs need no special type, and a ladder value of 0 leaves an optional block out (the half-marathon run's marathon-pace version). Trail climbs and descents are one timed step under an HR cap, with the guidance in the comment. HR targets use whole zones and spans. See [plan workouts](../features/plan-workouts.md) and the [plan.json format](../plan-json-format.md).
