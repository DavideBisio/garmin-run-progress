# Planner workouts, renderer and manual schedule

The planner's sessions come from a template library, `src/garmin_plan/data/workouts.toml`. A template plus a size variant plus your [profile](plan-profile.md) gives a resolved workout: concrete pace and HR ranges, distance, estimated duration and hard km. `python -m garmin_plan plan --weeks N` (or `make plan ARGS="--weeks 4"`) writes those workouts to `garmin_export/plan.json` ([format](../plan-json-format.md)) and `garmin_export/plan.md` from a `[week]` table in `profile.toml`. Modules: `garmin_plan.model`, `templates`, `render_md`, `plan_io`.

## Templates

| Id | Kind | Min level | Ladder (smallest first) |
|---|---|---|---|
| `r_220` | R | novice | 6, 8, 10, 12 × 220 m, 180 m jog |
| `r_300` | R | intermediate | 6, 8, 10 × 300 m, 200 m jog |
| `r_ladder` | R | intermediate | 200-300-400-300-200, 300-400-500-400-300, 2 × 200-300-400-300-200; jogs as long as the rep |
| `cruise_tempo` | T | novice | 2, 3, 4 × 1200 m, 2 × 3000 m, 1 × 5000 m; 60 s jog between reps |
| `vo2_intervals` | I | intermediate | 5 × 600 m, 6 × 800 m, 5 and 6 × 1000 m |
| `easy` | E | beginner | 4, 5, 6, 7, 8, 10 km |
| `progression` | M | novice | E then M: 3 + 2, 3.5 + 3.5, 4 + 5 km |
| `steady_long` | L | novice | 10, 12, 14, 16, 18 km |
| `progression_long` | L | intermediate | E, M, E: 8 + 3 + 2, 10.5 + 3.5 + 3.5, 12 + 5 + 3 km |
| `hm_long` | L | intermediate | 16, 18, 21 km; 21 km with 3 × 2 km at M |
| `hill_repeats` | hill | intermediate | 5 × 30 s, 6 and 8 × 45 s, 10 × 60 s uphill, lap-button recovery |
| `hilly_long` | hill | intermediate | 40, 60, 80 min rolling terrain plus 4–6 downhill reps |
| `trail_long` | trail | intermediate | 80, 100, 120 min on trail, Z3 cap |

**Ids are stable.** They go into `plan.json`, and into `push_state.json` and the description of workouts pushed to Garmin ([plan push](plan-push.md)); the pushed workouts themselves are named `[plan] <title> <date>`. Renaming an id breaks that link for workouts already on the calendar. Add a new template instead. Variants are 1-based everywhere.

## Template schema

```toml
[[workout]]
id = "cruise_tempo"            # lower case, digits, _
title = "Cruise Tempo"
kind = "T"                     # E, L, R, T, I, M, hill, trail
min_level = "novice"           # beginner, novice, intermediate, advanced
warmup = { pace = "E", dist = 2000 }
cooldown = { pace = "E", dist = 1000 }
ladder = [ { n = 2, d = 1200 }, { n = 3, d = 1200 }, { n = 1, d = 5000 } ]
[[workout.main]]               # one table per block, in order (or main = [ ... ] inline)
repeat = "n"
rep = { label = "Tempo", pace = "T", dist = "d" }
recovery = { time = 60 }
```

- **Main set:** a list of blocks, run in order. A block is a step or a repeat. A repeat has `rep` (and optionally `recovery`), or a `steps` list for anything longer, such as a ladder. Repeats hold steps only, as Garmin's flat `RepeatGroup`. A progression is just consecutive steps.
- **Ladder variables:** a string value (`dist = "d"`, `repeat = "n"`) is looked up in the variant. Every variant must define every variable the steps use. A value of 0 leaves the step or repeat out, which is how `hm_long` carries its optional marathon-pace blocks. A variant may also set `title`.
- **Step end:** exactly one of `dist` (m), `time` (s) or `lap = true` (lap button).
- **Step target:** `pace` (`E`, `M`, `T`, `I`, `R` or `jog`), `hr` (`Z1` … `Z5`, a span such as `Z4-5`, a cap such as `Z3 cap`, or `open`), both, or an `effort` text shown instead of a pace (`"Hard effort"`). `pace` and `effort` are exclusive.
- **Roles:** `role` is the Garmin step type: `warmup`, `rep`, `recovery`, `cooldown`. It defaults from the position: `warmup` and `cooldown` for those steps, `recovery` for a repeat's `recovery`, otherwise `rep`. `label` is the lap name, separate from the role.
- **Role mapping:** 05 sends `warmup` as `WARMUP`, `rep` as `INTERVAL`, `recovery` as `RECOVERY` and `cooldown` as `COOLDOWN`. Runs without a warmup or cooldown (`easy`, `progression`, `steady_long`, `progression_long`, `hm_long`) are all main set, so every step is `rep` and goes to Garmin as `INTERVAL`, whatever its pace. `hm_long`'s `Steady` km between the marathon-pace blocks sets `role = "recovery"` and goes as `RECOVERY`: it is the easy float between the work blocks, so the watch shows the MP blocks as the intervals. It stays a recovery on purpose (an E-pace `rep` there would make the whole 21 km read as intervals); it still has its E pace target and counts in the totals.
- **Defaults:** a recovery without `pace` or `effort` is a jog at Z2. A pace zone without `hr` gets its usual HR zone: E Z2, M Z3, T Z4, I and R Z4-5.
- **Estimates:** a time-ended step needs `est_pace` for its distance (a jog uses the jog pace). A distance-ended step without a pace target needs `est_pace` for its duration. A lap-button step needs `est_time` and `est_dist`. `est_pace` is a zone (`E`, `jog`), a zone plus or minus seconds per km (`I+30`), or an absolute `M:SS`.
- **Hard km:** steps at M, T, I or R pace, plus steps marked `hard = true` (the hill reps).
- `climb_m_per_km` (hill and trail templates) is the climbing the session expects, for the terrain checks in 07.

Hill and trail sessions use HR or open targets and end on time or the lap button, because terrain sets the pace. A trail run's climbs and descents are one timed step under an HR cap, with the guidance in the comment.

`load_templates` rejects, with a `TemplateError` naming the template and step: unknown keys, zones, kinds or levels, a ladder missing a variable, a ladder value used as a repeat count that is not a whole number (`n = 2.5`, also `n = 3.0`), a step without exactly one end, a time-ended step without an estimate, a lap step without `est_time` and `est_dist`, and a duplicate id.

## Pace and HR ranges

Each zone's point pace comes from Daniels ([plan profile](plan-profile.md#pace-zones-daniels)). The `[bands]` table in `rules.toml` widens it to a range, in seconds per km faster and slower:

| Zone | Faster | Slower | At VDOT 40 |
|---|---|---|---|
| E | 2 | 20 | 6:09 – 6:31 /km |
| M | 5 | 10 | 5:22 – 5:37 /km |
| T | 3 | 7 | 5:03 – 5:13 /km |
| I | 3 | 5 | 4:38 – 4:46 /km |
| R | 5 | 5 | 4:21 – 4:31 /km |

Daniels gives E as a range and the point pace sits near its fast end, so the E band reaches mostly slower. It stays inside the published E range at VDOT 30, 40, 50 and 60 (`tests/fixtures/daniels_paces.json`). The others are points in Daniels' tables; the band leaves room for GPS noise.

**Jog** is the slow end of E plus `jog_offset_s` (30 s/km). It is a duration estimate only: a jog step has an HR target (Z2) and no pace target, and renders as `Jog`.

HR ranges use whole zones from the same Karvonen bounds as the page: Z1 starts at 50 % of the heart-rate reserve, Z5 ends at HR max. `Z4-5` runs from the bottom of Z4 to HR max; `Z3 cap` runs from the bottom of Z1 to the top of Z3. At 190 / 50: Z2 134 – 148, Z4-5 162 – 190, Z3 cap 120 – 162 bpm.

`PaceRange` in `model.py` is the only place pace order is handled: `fast_s <= slow_s` in s/km, and `to_speed()` returns `(slow m/s, fast m/s)`, Garmin's lower and upper speed limits.

## Totals and the last recovery

Distance, duration and hard km are always **summed from the steps**, never typed in. Durations use the middle of each pace range; time-ended and lap steps use their estimates.

**The last recovery of a repeat counts.** Templates leave `skip_last_rest` at `false`, so 8 × (220 m + 180 m jog) is 3.2 km on paper, and the Garmin export (05) maps the same flag to `skipLastRestStep`, so the watch shows the same distance. When a template sets it to `true`, the totals drop the final recovery and the markdown says so.

**A repeat of 1 has no last recovery.** The recovery is the rest between reps, and a single rep has none, so a repeat of 1 always gets `skip_last_rest = true`: `cruise_tempo` 1 × 5000 m goes from the tempo straight into the cooldown (8.0 km, not 8.1 km), and `r_ladder`'s single ladders end on their last rep. The heading, the `plan.json` totals and the export's `skipLastRestStep` all follow the same flag.

## Markdown

`render_md.render_workout` produces the hand-written plan's format: a `### Title - 6.0 km (~35 min)` heading and a `Lap | Pace range | FC range | Duration | Comment` table. A repeat is a `**Repeat 8x**` row with its total, followed by `↳ **Rep**` and `↳ **Recovery**` rows; a repeat of 1 renders as plain rows, its note in front of the first row's comment. `|` in titles, labels and comments is escaped as `\|`.

| Duration | Format |
|---|---|
| Under 1 min | `~45 s` |
| Under 10 min | `~6:30` |
| Under 1 h | `~31 min` |
| From 1 h | `~1 h 05`, `~1 h 31` (hours and zero-padded minutes; on the hour `~1 h 00`) |

Exact durations of time-ended steps use the same format without the `~`: the trail run's main step is `1 h 20 (~10.2 km)`.

Numbers are rounded only when rendering. Write the output as UTF-8: `↳` is not ASCII.

## Manual schedule (`[week]`)

Until the weekly skeleton (06) chooses sessions, `profile.toml` maps weekdays to `template:variant`:

```toml
[week]
tue = "cruise_tempo:2"
thu = "easy:3"
sun = "steady_long:1"
```

`make plan ARGS="--weeks 4"` (or `python -m garmin_plan plan --weeks 4`) plans 4 weeks starting on the Monday after today (`--today YYYY-MM-DD` to pretend otherwise). Every week repeats `[week]`, `target_km` is the sum of the week's sessions as `plan.md` shows them (each workout's km rounded to 0.1 first, so the week heading equals the sum of its day headings) and `slot` stays `null`. It writes `garmin_export/plan.json` and `garmin_export/plan.md`.

An unknown template, a variant outside the ladder or a value not shaped `template:variant` stops with `error: …` and quotes the line as written in `profile.toml`. `tomllib` has no line numbers, so the profile keeps the raw line of each `[week]` key. Any line starting with `[` (another `[table]`, a dotted `[week.x]` or an `[[array]]` table) ends the `[week]` section.

## Tests and the golden file

`tests/test_workouts.py` covers the arithmetic (repeats, the last recovery, time and lap ends), validation errors, the `[week]` errors, `plan.json` round trips and the `plan` command. The golden file `tests/fixtures/workouts_golden.md` renders every template's smallest and largest variant for a generic runner (VDOT 40, HR 190 / 50). After a deliberate change, regenerate it and review the diff:

```sh
UPDATE_GOLDEN=1 PYTHONPATH=src python -m unittest tests.test_workouts
```
