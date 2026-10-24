# plan.json format

`garmin_export/plan.json` is the planner's output and the contract with what comes after it: the Garmin export (roadmap 05) and the Planning tab (10), which reads it from `runs.json`'s `plan` key ([runs.json format](runs-json-format.md#training-plan)). `python -m garmin_plan plan` (or `make plan`) writes it next to `plan.md`, its markdown rendering. Both are personal and gitignored with the rest of `garmin_export/`. Format version: `1`. The generator (07) added `warnings` and each week's `phase`, `deload` and `warnings`, the runner levels (08) `levels`, `progress` and each week's `unit` and `target_min`, the adaptation loop (09) the kept past weeks, `history` and each day's `status`, `activity_id` and `changed_by`, and the plan view (10) `profile`; readers that don't know them ignore them, so the version stays `1`.

The file holds **resolved** workouts: every step carries its pace and HR ranges in numbers, so readers need neither the templates (`src/garmin_plan/data/workouts.toml`) nor the profile.

```json
{
  "version": 1,
  "generated": "2026-10-23T11:00:00",
  "profile_hash": "b924fafb9b64…",
  "profile": { "vdot": 40.0, "hr_max": 190, "hr_rest": 50,
               "race": { "date": "2024-09-29", "distance_m": 21097.5, "goal_s": 6210 } },
  "levels": { "volume": "novice", "quality": "intermediate",
              "reasons": { "volume": "18 km/wk over 4 wk", "quality": "VDOT 39, 7 Q sessions in 8 wk" } },
  "progress": { "plan_start": "2024-06-10", "block_start": "2024-06-03", "cycle_start": "2024-06-03",
                "run_walk_stage": null,
                "vdot": { "value": 39.2, "date": "2024-06-05", "from": "10k", "from_date": "2024-05-26" },
                "time_trials": [ { "date": "2024-05-21", "dist_m": 2000, "time_s": 662.4, "vdot": 31.81 } ],
                "time_trial": null },
  "changes": [ { "date": "2024-06-06", "from": "Q", "to": "E", "rule": "fatigue", "reason": "resting HR +7 bpm" } ],
  "history": [ { "date": "2024-06-05", "start": "2024-06-10", "weeks": ["2024-06-10", "2024-06-17"],
                 "changes": [] } ],
  "warnings": [
    { "rule": "feasibility", "detail": "the goal needs VDOT 43.4, 3.4 above the current 40.0, in 16 weeks: ambitious …",
      "action": "kept the paces at the current VDOT …" }
  ],
  "weeks": [
    {
      "start": "2024-06-10",
      "target_km": 28.0,
      "unit": "km",
      "phase": "base",
      "deload": false,
      "warnings": [],
      "days": [
        {
          "date": "2024-06-11",
          "slot": null,
          "status": null, "activity_id": null, "changed_by": null,
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
| `profile_hash` | sha256 (hex) of what the resolved steps depend on: VDOT, HR max and rest, the resolved zones (each pace zone's range to 0.01 s/km, the jog pace, the bpm of Z1–Z5), the runner's two levels and the volume unit. A different hash for today's profile means the steps are stale |
| `profile` | What the plan was made for, for the page's Planning tab: `vdot` (the VDOT its paces come from, to 0.1), `hr_max` and `hr_rest` (the bpm its HR targets come from) and `race`, `{date, distance_m, goal_s}` (`goal_s` `null` without a goal) or `null` without a race. Plans written before it have none |
| `levels` | The runner's levels (roadmap 08, [plan profile](features/plan-profile.md#runner-levels)): `volume` and `quality`, each `"beginner"`, `"novice"`, `"intermediate"` or `"advanced"`, and `reasons`, why each axis is at its level (`""` when not known). The next plan starts from them (promotion); a beginner level on either axis makes the push send HR as guidance only. Absent in a plan of the `[week]` schedule alone |
| `progress` | What the next plan carries on from this one ([Progress](#progress)). Absent in a plan of the `[week]` schedule alone and in plans written before it: the next plan then starts afresh |
| `warnings` | Plan-wide warnings: phases shortened for a near race, goal feasibility, no load-ratio check for want of history, the time trial's day. Absent in a plan of the `[week]` schedule alone |
| `changes` | This re-plan's change log, from today on ([plan adaptation](features/plan-adaptation.md#what-changed)): `date`, `from` and `to` (a slot, `rest` or `skipped`), `rule` and `reason`. `plan.md` shows it under "What changed" |
| `history` | The re-plans that changed something, oldest first ([History](#history)). `[]` in a first plan |
| `weeks` | Monday-based weeks, oldest first: the weeks a re-plan kept from the plans before it, then the plan's own from `progress.plan_start` ([Past weeks](#past-weeks)) |

## Progress

Every plan starts on the Monday after today, so a re-plan restarts its weeks; `progress` keeps what that must not reset. The next `make plan` reads it from the `plan.json` on disk before writing the new one (`progress.carry`), so it carries across any number of re-plans. A value of the wrong type counts as missing.

| Field | Contents |
|---|---|
| `plan_start` | The plan's first own week (the Monday after the day it was made). The weeks before it are the kept past weeks |
| `block_start` | The Monday the block holding the plan's first week started (`YYYY-MM-DD`). With the weeks' `deload` flags it says where the blocks of this plan start: here, and on each week after a deload. A new plan whose first week starts a block (or that this plan doesn't reach) can promote the levels; otherwise it keeps its place in the block, so its deloads fall where this plan's did and the promotion waits. Without it the plan's first week counts as a block start |
| `run_walk_stage` | The run/walk ladder variants climbed before the plan's first week (`0` at the ladder's start); the plan's week `i` takes the next one in each build week, the same in a deload. The next plan adds this plan's own build weeks (from `plan_start`) before its own start, never the kept past weeks, which the stage already counts. `null` in a plan without the ladder |
| `vdot` | The derived VDOT estimate the next plan starts from (roadmap 09): `value` (before any layoff factor), `date` of the last re-estimate, `from` (`10k`, `2 km time trial`, `race 10 km`, …) and `from_date`, the day of that effort; `after`, once a break lowered it, the day running resumed (only races after it can raise it again). Training efforts set only the first one; races and time trials raise it, a break lowers it ([plan adaptation](features/plan-adaptation.md#rules)). `null` when the VDOT is set in `profile.toml` or a default |
| `cycle_start` | The Monday the no-race phase cycle (`[phases] no_race_cycle`) started: the next plan without a race goes on with the cycle from there, so its phases and deloads fall where this plan's did. A restart after a break, or a plan without it, starts the cycle afresh |
| `time_trials` | The 2 km time trials run, oldest first: `date`, `dist_m` (2000), `time_s` (the best 2 km of the run that day) and `vdot`. The latest gives the derived VDOT ([plan profile](features/plan-profile.md)); once there is one, no time trial is planned again |
| `time_trial` | The date of the time trial planned and not run yet, else `null`. A re-plan keeps it, in the same week; one that has passed without a run, or falls before the new plan starts, is planned again in the new plan's first week |

A break of more than 5 days restarts the plan ([plan profile](features/plan-profile.md#runner-levels)): its first week starts a block and the ladder starts over; the time trials stay.

## Past weeks

Every plan starts on the Monday after today; a re-plan keeps the weeks of the last `plan.json` before that Monday as they were written: the past weeks, and the current week, whose days from today on are still to run (and stay pushed to the watch). Their sessions never change; only each day's `status` and `activity_id` are filled in again from `runs.json` on every re-plan (`match.match`). A day still to come has `null` there; so do the days of the plan's own weeks.

| Field | Contents |
|---|---|
| `days[].status` | `"done"`, `"partial"` (under `[adapt] partial`, 70 %, of both the planned distance and time, or a hard Q run easy), `"missed"`, `"moved"` (run the day before or after) or `"swapped"` (a trail run for a road session, or the other way round); `null` for a day still to come ([plan generator](features/plan-generator.md#re-plans)) |
| `days[].activity_id` | The Garmin activity id of the run that matched the day (`runs.json`'s `id`), else `null` |
| `days[].changed_by` | The rule that changed the day after it was planned (`override_skip`, `override_reduce`, `l_moved`, `fatigue`), else `null` |
| `days[].change` | With `changed_by` only: `{from, to, reason}` (`from_date` too for a moved long run, kept through an override on it), the line "What changed" shows. An override's change also has `was`: the day's `slot`, `workout`, `changed_by` and `change` before it, given back when the override no longer covers the day |
| `days[].workout` | `null` for a day an override skipped |

## History

One entry per re-plan whose weeks differ from the last plan's (a re-plan that changes nothing adds none):

| Field | Contents |
|---|---|
| `date` | The day of the re-plan |
| `start` | Its first own week |
| `weeks` | The weeks both plans hold whose sessions or targets changed (warnings and match fields left out of the comparison) |
| `changes` | The re-plan's change log (top-level `changes`) |

## Weeks and days

| Field | Contents |
|---|---|
| `start` | The week's Monday, `YYYY-MM-DD` |
| `target_km` | The week's planned volume, in flat-equivalent km: the volume curve's target (06; the taper's share of the last build week), to 0.1 km; the split rounds the days so they add up to it. It becomes the sum of the sessions' km as `plan.md` shows them (each rounded to 0.1 km first, so the week heading adds up its day headings) when the week has `[week]` days, when the fixer trimmed L or dropped F, when the Q template can't take the split's leftover (a `split` warning), and in the race week, which stops before race day |
| `unit` | The plan's volume unit, `"km"` or `"min"` (a beginner's plan). `target_km` is there either way. Absent in a plan of the `[week]` schedule alone |
| `target_min` | In a plan in minutes only: the week's sessions in whole minutes, each rounded half up as `plan.md` shows it, then added up. Such a week's `target_km` is the sum of its sessions' km, as is a beginner's in km (run/walk and time sessions fill time, not km) |
| `phase` | `"base"`, `"rt"` (R + T), `"it"` (I + T), `"tm"` (T + M) or `"taper"` (06's phase calendar). Absent in a plan of the `[week]` schedule alone |
| `deload` | `true` for the block's lighter week (×0.85 of the block, the deload Q one variant lighter). Absent as `phase` |
| `warnings` | The week's warnings (see [Warnings](#warnings)), `[]` when it passes every check. Absent as `phase` |
| `days` | One entry per session, by date |
| `days[].date` | `YYYY-MM-DD`, local date |
| `days[].slot` | The session's role in the week from the weekly skeleton (06): `"L"` long run, `"Q"` quality, `"E"` easy or `"F"` flex (an easy run that is the first dropped when the volume is short; an F day with no run has no entry). `null` for a `[week]` day (the manual schedule overrides the generated day) |
| `days[].workout` | The resolved workout |

## Warnings

Each warning says which rule fired and what the planner did about it; `plan.md` lists them under `## Warnings` and under their week.

| Field | Contents |
|---|---|
| `rule` | The rule: a check (`easy_share`, `hard_count`, `hard_adjacent`, `volume_rise`, `acwr_high`, `acwr_low`, `long_share`), a note (`acwr_skipped`, `forced_size`), or a planning step (`split`, `phases`, `feasibility`, `hill_swap`, `race_week`, `skeleton`, `time_trial`) |
| `detail` | What happened, with the numbers |
| `action` | What the planner did: the fix it applied (`fixed: Q cruise_tempo variant 5 -> 4`), or why it left it |

## Workout

| Field | Contents |
|---|---|
| `id` | Template id. **Stable**: it is stored in `push_state.json` and in the description of the workouts pushed to Garmin, which are named `[plan] <title> <date>` ([plan push](features/plan-push.md)) |
| `variant` | Ladder variant, 1-based |
| `title`, `kind` | Display title; kind `E`, `L`, `R`, `T`, `I`, `M`, `hill`, `trail` or `tt` (time trial; its day is the one whose run gives the first VDOT) |
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
| `effort` | Pace-column text for steps without a pace target (`"Hard effort"`, `"Easy, conversational (RPE 3-4)"`), else `null` |
| `note` | Comment |
| `hard` | Counts in `hard_km` |
| `meters`, `seconds` | The step's resolved distance and duration (one iteration) |

Recovery jogs (`zone: "jog"`) have no pace target, only an HR target; their estimate is the slow end of E plus 30 s/km.
