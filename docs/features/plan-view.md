# Plan view

The page's Planning tab shows the training plan (roadmap 10): this week's sessions, how the last weeks went, and planned against actual km over the whole plan. It is read-only: plans are made and changed in Python (`make plan`, `make replan`, [plan generator](plan-generator.md), [plan adaptation](plan-adaptation.md)). Code: `src/page/js/plan.js` (`renderPlan(c)`, called at the end of `render` after `renderTraining`); data: `state.js`.

## Where the plan comes from

`runs.json` carries a copy of `garmin_export/plan.json` under its `plan` key ([runs.json format](../runs-json-format.md#training-plan), [plan.json format](../plan-json-format.md)). Every rebuild of `runs.json` copies the `plan.json` on disk (`make grab`, `make rebuild`), and `make plan` and `make replan` rebuild it afterwards, offline, so the page sees the fresh plan:

```bash
make plan            # or make grab, then make replan
# then load garmin_export/runs.json in the Data tab
```

`setData` reads `payload.plan` into `PLAN` when it is an object with a `weeks` array, else `null`. Without a plan the tab shows the empty state, which says how to get one; the other tabs don't depend on it. The plan is part of the payload, so "Remember in this browser" keeps it and "Forget my data" clears it ([data loading and storage](data-loading-and-storage.md#remembering-data)). The example data comes with a synthetic plan.

## Today

Plan dates are local calendar dates (`YYYY-MM-DD`). The page turns them into its own day index (`decYear(date).day`, days since 1970-01-01) and weeks with `weekOf` (Monday-based), as the Training charts do. Today is the local calendar day (`Date.UTC(getFullYear(), getMonth(), getDate())`), never a UTC parse of the current time. For the example data, today is the day after its last run, so its plan stays current.

## Header

One line: the runner's levels (`levels`), the VDOT (`profile.vdot`, else `progress.vdot.value`), the race (`profile.race`: distance, weeks to go between this week and the race week, goal time), then every planner warning, plan-wide and this week's (`rule`: detail. Planner: action).

**Plan vs page settings.** The plan's HR targets come from `profile.toml`'s max and resting HR (`profile.hr_max`, `hr_rest`). When they differ from the Data tab's inputs, a note says so; the cards and the step tables still show the plan's own bpm, as they were pushed to the watch. A plan without `profile` (written before roadmap 10) has no note.

## This week

The week holding today; else the first week to come; else the plan's last week. Its heading gives the block, the week in the block and the phase: blocks start at `progress.block_start` and on the week after each deload (`deload: true`); taper weeks count on their own. A week without a phase (a `[week]` schedule alone) has no block.

Seven cards, Monday to Sunday, one per day (days without a session are rest days). Each card is a button: the day, its status, the session title, km and estimated time (whole minutes first in a plan in minutes), the main step's pace and HR target. The main step is the first rep, else the longest step that isn't a warmup or cooldown. The HR target uses the page's zone names and colours (`--z1`…`--z5`).

| Status | When |
|---|---|
| done, partial, missed, moved, swapped | The day's stored `status` (roadmap 09's match), when there is one |
| skipped | `workout` is null and `changed_by` is set (an override) |
| done / partial | No stored status, a run that day (today included): partial under 70 % of both the planned km and time |
| moved | No stored status, a past day without a run, but a run the day before or after on a day without a session of its own (each such run moves one session) |
| missed | No stored status, a past day with no run that could be it |
| next | The first session still to come |
| rest | A day without a session |

So a plan from before 09, whose days have no status, still shows done and missed. Picking a card (click, or Enter/Space on the focused button) opens the session detail below the cards: the date, the size, the status, a change made by a re-plan, and the step table of `plan.md` (Lap, Pace range, HR, Duration, Comment; a repeat as a "Repeat Nx" row over its "↳" steps, a repeat of 1 as its steps; numbers rounded as `render_md` does).

## Compliance

Three KPI tiles over the last 4 complete weeks before this one (the plan weeks among them):

| KPI | Meaning |
|---|---|
| Sessions done | Days with a session that are done, moved or swapped, over those days (partial doesn't count) |
| Km done | The km run in those weeks against their `target_km` |
| Quality done | The Q days (`slot` `"Q"`) done, moved or swapped, over the Q days |

## Block chart

Planned against actual km per plan week, past and future: the planned bar is the week's `target_km` (lighter for a deload week, whose label also has ↓), the actual bar the km run that week (none for weeks to come). Shaded bands behind the bars mark the phases (an inline Chart.js plugin, no annotation plugin). Like the other charts it is recreated on theme changes and resized when the Planning tab is first shown.

## Layout

The cards sit in a grid that wraps; at phone width (under 560 px) it is two columns, with no horizontal scroll. The step table scrolls inside its panel when it is wider.
