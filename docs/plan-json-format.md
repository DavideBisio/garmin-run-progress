# plan.json format

`garmin_export/plan.json` is the planner's output and the contract with what comes after it: the Garmin export (roadmap 05) and the Planning tab (10). `python -m garmin_plan plan` (or `make plan`) writes it next to `plan.md`, its markdown rendering. Both are personal and gitignored with the rest of `garmin_export/`. Format version: `1`.

The file holds **resolved** workouts: every step carries its pace and HR ranges in numbers, so readers need neither the templates (`src/garmin_plan/data/workouts.toml`) nor the profile.

```json
{
  "version": 1,
  "generated": "2026-10-23T11:00:00",
  "profile_hash": "b924fafb9b64…",
  "weeks": [
    {
      "start": "2024-06-10",
      "target_km": 28.0,
      "days": [
        {
          "date": "2024-06-11",
          "slot": null,
          "workout": {
            "id": "cruise_tempo", "variant": 2, "title": "Cruise Tempo", "kind": "T",
            "km": 7.03, "seconds": 2427.0, "hard_km": 3.6, "climb_m_per_km": null,
            "steps": [
              { "type": "step", "role": "warmup", "label": "Warmup", "end": "dist", "value": 2000,
                "zone": "E", "pace_s_per_km": [368.96, 390.96], "hr_zone": "Z2", "hr": [134, 148],
                "est_pace_s_per_km": null, "est_dist": null, "est_time": null,
                "effort": null, "note": "", "hard": false, "meters": 2000, "seconds": 759.9 },
              { "type": "repeat", "n": 3, "skip_last_rest": false, "note": "",
                "meters": 4027.6, "seconds": 1287.2,
                "steps": [ { "type": "step", "role": "rep", "label": "Tempo", "…": "…" },
                           { "type": "step", "role": "recovery", "label": "Recovery", "…": "…" } ] }
            ]
          }
        }
      ]
    }
  ]
}
```

The file is UTF-8, indented by one space. Numbers are rounded to 2 decimals (step and repeat totals to 1, workout seconds to whole seconds).

## Top level

| Field | Contents |
|---|---|
| `version` | `1`. A breaking change bumps it; readers reject versions they don't know |
| `generated` | Local time the plan was written, `YYYY-MM-DDTHH:MM:SS` |
| `profile_hash` | sha256 (hex) of what the resolved steps depend on: VDOT, HR max and rest, and the resolved zones (each pace zone's range to 0.01 s/km, the jog pace, the bpm of Z1–Z5). A different hash for today's profile means the steps are stale |
| `weeks` | Monday-based weeks, oldest first |

## Weeks and days

| Field | Contents |
|---|---|
| `start` | The week's Monday, `YYYY-MM-DD` |
| `target_km` | The week's planned volume. With the manual `[week]` schedule it is the sum of the sessions' km as `plan.md` shows them (each rounded to 0.1 km first), so the week heading adds up its day headings; the weekly skeleton (06) sets it from the volume progression |
| `days` | One entry per session, by date |
| `days[].date` | `YYYY-MM-DD`, local date |
| `days[].slot` | The session's role in the week (06: quality, long, easy …); `null` with the manual schedule |
| `days[].workout` | The resolved workout |

## Workout

| Field | Contents |
|---|---|
| `id` | Template id. **Stable**: it is stored in `push_state.json` and in the description of the workouts pushed to Garmin, which are named `[plan] <title> <date>` ([plan push](features/plan-push.md)) |
| `variant` | Ladder variant, 1-based |
| `title`, `kind` | Display title; kind `E`, `L`, `R`, `T`, `I`, `M`, `hill` or `trail` |
| `km`, `seconds` | Totals, summed from the steps (estimates at the middle of each pace range) |
| `hard_km` | Distance at quality intensity: steps at M, T, I or R pace and hill reps (the caps in 07) |
| `climb_m_per_km` | Climbing the session expects (hill and trail templates), else `null` |
| `steps` | Steps and repeats, in order |

## Steps

A step is `{"type": "step", …}`; a repeat is `{"type": "repeat", "n", "skip_last_rest", "note", "meters", "seconds", "steps": [steps]}`. Repeats are flat: they hold steps, never other repeats, as Garmin's `RepeatGroup`. `skip_last_rest` is `false` in every template's repeats of 2 or more: the last recovery is run and counts in the totals. A repeat of 1 has no recovery between reps, so it is always `true` there and the totals leave the last recovery out. The Garmin export sets `skipLastRestStep` from the same flag.

| Field | Contents |
|---|---|
| `role` | `warmup`, `rep`, `recovery` or `cooldown`: Garmin's step type (WARMUP, INTERVAL, RECOVERY, COOLDOWN) |
| `label` | Lap name (`Warmup`, `Tempo`, `Uphill` …) |
| `end`, `value` | `dist` (m), `time` (s) or `lap` (lap button, `value` null) |
| `zone` | Pace zone the step came from: `E`, `M`, `T`, `I`, `R`, `jog`, or `null` for HR-only and open targets |
| `pace_s_per_km` | Primary target `[fast, slow]` in s/km (fast is the smaller number), or `null`. As a Garmin speed range: lower limit `1000 / slow`, upper `1000 / fast` m/s |
| `hr_zone`, `hr` | HR target: `"Z2"`, `"Z4-5"` or `"Z3 cap"`, and its `[lo, hi]` bpm; `null` for none. Secondary when there is a pace target |
| `est_pace_s_per_km` | Pace used to estimate the missing dimension (distance of a time end, time of a step without a pace target); `null` when the pace range's middle is used |
| `est_dist`, `est_time` | Estimates for lap-button steps (m, s) |
| `effort` | Pace-column text for open targets (`"Hard effort"`), else `null` |
| `note` | Comment |
| `hard` | Counts in `hard_km` |
| `meters`, `seconds` | The step's resolved distance and duration (one iteration) |

Recovery jogs (`zone: "jog"`) have no pace target, only an HR target; their estimate is the slow end of E plus 30 s/km.
