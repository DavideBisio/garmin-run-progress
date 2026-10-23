# 10 · Plan view in the Planning tab

## Requirements

- The **Planning** tab (from 02) shows the plan when the loaded `runs.json` has a `plan` key. `build_runs` copies `garmin_export/plan.json` into it, as it does for `rhr`. Without a plan, the tab keeps the empty state from 02.
- **This week:** one card per day with:
  - the session title;
  - km and estimated time;
  - main pace and HR targets;
  - a status: done, partial, missed, moved, next or rest.
- **Block chart:** planned against actual weekly km, with shaded phase bands and deload weeks marked.
- **Compliance KPIs** over the last 4 weeks: sessions done, km done against planned, and Q sessions done.
- **Session detail:** clicking a card opens the same step table as `plan.md`.
- **Header line:** level, current VDOT, race and weeks to go, plus any warnings from the planner.
- The view is read-only. Plans are made and changed in Python.
- The example data includes a synthetic plan, so the tab has content before you load your own data.
- **Plan vs page settings:** if the plan's max and resting HR (from `profile.toml`) differ from the Data tab's values, a note says so. The plan's own bpm targets are shown as they were pushed to the watch.

## Implementation

```text
╭─ Plan ───────────────────────────────────────────────────────────────────╮
│ Novice volume · intermediate quality · VDOT 40 · Half marathon in 14 wk  │
│ ⚠ Goal needs +3 VDOT in 14 weeks: ambitious                              │
├──────────────────────────────────────────────────────────────────────────┤
│  This week (block 2, week 3 · Phase 2: R + T)                            │
│ ┌────────┐┌──────────────┐┌────────┐┌──────────┐┌────────┐┌────────────┐ │
│ │ Mon    ││ Tue  ✓ done  ││ Wed    ││ Thu  next││ Fri    ││ Sun        │ │
│ │ rest   ││ 8×220 m R    ││ rest   ││ Easy     ││ rest   ││ Steady L   │ │
│ │        ││ 6.0 km ~35'  ││        ││ 5.5 km   ││        ││ 9.5 km     │ │
│ │        ││ 4:00–4:20/km ││        ││ Z2       ││        ││ ~1:02      │ │
│ └────────┘└──────────────┘└────────┘└──────────┘└────────┘└────────────┘ │
├──────────────────────────────────────────────────────────────────────────┤
│ [ 92% sessions ]  [ 88% km ]  [ 4/4 quality ]      ← KPI tiles (.kpis)   │
├──────────────────────────────────────────────────────────────────────────┤
│ Planned vs actual km                                                     │
│ 25┤      Base        │     Phase 2      │                                │
│ 20┤   ▒█ ▒█ ▒█       │ ▒█ ▒█ ▒█         │   ▒ planned  █ actual         │
│ 15┤▒█ ▒█ ▒█ ▒█ ▒░    │ ▒█ ▒█ ▒█ ▒░      │   ░ deload                    │
│   └──────────────────┴──────────────────┴──────▶ weeks                   │
╰──────────────────────────────────────────────────────────────────────────╯
 click a card ▶ <details> with the lap | pace | HR | duration | comment table
```

- **New file `src/page/js/plan.js`:**
  - loaded after `training.js` and before `boot.js`;
  - adds `renderPlan(c)`;
  - renders into `#tab-planning`;
  - uses the same panel, `.kpis`, `.chart-box` and legend markup as the Training group.
- **Data:**
  - `state.js` `setData` reads `payload.plan` into `PLAN`, or null;
  - `render.js` calls `renderPlan`;
  - the empty state from 02 shows when `PLAN` is null.
- **Status before 09 exists:** the page works out done and missed itself by matching runs by date, so the view is useful once 07 is done.
- `example-data.js` generates a plan relative to the example dataset's last run.
- Update `docs/runs-json-format.md` (the `plan` key) and the page code map in `docs/architecture.md`.

## Testing strategy

- **Node page tests (`tests/page.test.mjs`):**
  - example data renders the Planning tab with 7 day cards and the chart;
  - a `runs.json` without `plan` shows the empty state and still renders the other tabs;
  - a plan without `status` fields (before 09) falls back to matching by date;
  - `plan.js` is loaded exactly once, in the right order.
- **Python:** `build_runs` embeds `plan.json` when it's there, and leaves the key out when it isn't.
- **Manual:**
  - light and dark theme;
  - 360 px phone width (cards wrap into 2 columns, no horizontal scroll);
  - keyboard: cards are focusable and open the detail.

## Completion checklist

- [ ] Every new top-level name in `plan.js` is unique across all page scripts and doesn't clash with a browser global. The page files share one scope.
- [ ] Plan dates are local calendar dates. Compare them with the page's own day index (`weekOf`, Monday-based), not with `new Date()` in UTC.
- [ ] Data remembered in IndexedDB (`storage.js`) includes `plan`, and "Forget my data" clears it.
- [ ] Charts are recreated when the theme changes, which `boot.js` already does for the other charts, and they're sized correctly when the tab is first opened (02).
- [ ] Session HR targets use the zone names and bpm from 01, the same as the Analysis zones chart.
