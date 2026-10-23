# Roadmap: training plan generator

A scriptable alternative to Garmin Coach. It turns your own data (VDOT, heart rate, recent volume) and a target (race date, distance, goal time) into a week-by-week plan. It renders the plan as markdown, pushes the workouts to the Garmin calendar so they sync to the watch, and re-plans after each `make grab`. Everything shows up in Run Progress Lab, which becomes one app with three tabs (**Data**, **Analysis**, **Planning**). The app sits inside a project site built with the shared [site-kit](https://github.com/DavideBisio/site-kit).

Paces come from Daniels' VDOT formulas and HR zones from Karvonen's heart-rate reserve. Workouts come from a **template library plus volume rules**. Every tunable number (caps, ramp, rotations, level parameters) lives in data files, not in code.

## Sections

| # | Section | Depends on | Milestone | Issue |
|---|---|---|---|---|
| 00 | [Project site and shared look with site-kit](00-site-kit-adoption.md) | – | Page foundation | [#3](https://github.com/DavideBisio/garmin-run-progress/issues/3) |
| 01 | [Heart-rate reserve zones everywhere](01-hrr-zones-everywhere.md) | – | Page foundation | [#4](https://github.com/DavideBisio/garmin-run-progress/issues/4) |
| 02 | [Three-tab page layout](02-three-tab-layout.md) | 00, 01 | Page foundation | [#5](https://github.com/DavideBisio/garmin-run-progress/issues/5) |
| 03 | [Core metrics and runner profile](03-core-metrics-and-profile.md) | 01 | MVP | [#6](https://github.com/DavideBisio/garmin-run-progress/issues/6) |
| 04 | [Workout templates and markdown renderer](04-workout-templates-and-renderer.md) | 03 | MVP | [#7](https://github.com/DavideBisio/garmin-run-progress/issues/7) |
| 05 | [Garmin workout export](05-garmin-workout-export.md) | 04 | MVP | [#8](https://github.com/DavideBisio/garmin-run-progress/issues/8) |
| 06 | [Weekly skeleton and volume curve](06-weekly-skeleton-and-volume.md) | 03 | Planner | [#9](https://github.com/DavideBisio/garmin-run-progress/issues/9) |
| 07 | [Session selection, sizing and safety checks](07-session-selection-and-checks.md) | 04, 06 | Planner | [#10](https://github.com/DavideBisio/garmin-run-progress/issues/10) |
| 08 | [Runner levels, beginner to advanced](08-runner-levels.md) | 07 | Planner | [#11](https://github.com/DavideBisio/garmin-run-progress/issues/11) |
| 09 | [Adaptation loop after each grab](09-adaptation-loop.md) | 05, 07 | Closed loop | [#12](https://github.com/DavideBisio/garmin-run-progress/issues/12) |
| 10 | [Plan view in the Planning tab](10-page-plan-view.md) | 02, 07 (09 for status) | Closed loop | [#13](https://github.com/DavideBisio/garmin-run-progress/issues/13) |

```text
00 ─┐
01 ─┴▶ 02 ──────────────────────────────────────────┐
 │                                                   ▼
 └─▶ 03 ──▶ 04 ──▶ 05 ─────────────────┐             10 ◀── 09 (status)
      │       │                        ▼             ▲
      └─▶ 06 ─┴─▶ 07 ──▶ 08            09            │
                   └─────────────────────────────────┘ (plan only)
```

- **Page foundation (00–02):** the site-kit project site with the app at `/app/`, one zone model across the project, and the Data / Analysis / Planning tabs. All three are useful on their own and don't need the planner.
- **MVP (03–05):** a hand-picked weekly schedule in `profile.toml`, rendered to markdown and pushed to the Garmin calendar. On its own this already replaces Garmin Coach with workouts you control.
- **Planner (06–08):** the plan is generated from the race date, the goal and your current volume, and works at any level.
- **Closed loop (09–10):** completed runs feed back into the plan, and the Planning tab shows planned against actual.

## Decisions that apply to every section

- **Site and app.** `davidebisio.github.io/garmin-run-progress/` is the site-kit landing page and docs (including this roadmap). The app is at `/app/`, still one self-contained file with no third-party requests, under the shared `<site-bar>` and tokens. The app gets three tabs. The plan reaches the page inside `runs.json` (a `plan` key, copied in like `rhr`), so you still drop a single file. The page only displays the plan: making and pushing it needs Python, because a browser can't log into Garmin.
- **One zone model: Karvonen heart-rate reserve.** The zone bounds are 50/60/70/80/90 % of (max − rest), and "easy" means Z1–2. Section 01 defines it once in `metrics.js`. The Python planner matches it exactly, with parity tests.
- **New package `src/garmin_plan/`**, next to `garmin_grab`. It reuses `garmin_grab.garmin.login` and `with_retry`, so both share one token store. It runs from a clone (`make plan`, `make push`) and is **not** part of the single-file release bundle on this roadmap.
- **Dependencies:** standard library plus `garminconnect`, which already brings in `pydantic`. Config files are **TOML**, read with the standard library's `tomllib`. YAML would need a new dependency.
- **Where files live:**
  - Personal files stay in the gitignored `garmin_export/`: `profile.toml`, `plan.json`, `plan.md` and push state.
  - Generic data is committed under `src/garmin_plan/data/`: `workouts.toml`, `rules.toml` and `levels.toml`.
- **Docs:** each section adds or updates a `docs/features/*.md` page and the module tables in `docs/architecture.md`, as the existing features do.
