# Documentation

| Document | Contents |
|---|---|
| [Architecture](architecture.md) | The two components, how data flows between them, design choices |
| [runs.json format](runs-json-format.md) | The file contract between the grabber and the page |
| [plan.json format](plan-json-format.md) | The planner's output: resolved workouts for the Garmin export and the page |
| [Deploy](deploy.md) | Running locally, GitHub Pages, scheduling the grabber, releasing changes |
| [Source layout and build](architecture.md#source-layout-and-build) | `src/`, `tools/build.py`, tests, Makefile |
| [Roadmap](roadmap/README.md) | The training plan generator, section by section (00–10) |

## Features

**Grabber (`garmin_grab.py`)**

| Feature | Document |
|---|---|
| Login, incremental listing, GPX download, retries | [features/incremental-grabber.md](features/incremental-grabber.md) |
| GPX parsing and 10-second streams | [features/gpx-to-stream.md](features/gpx-to-stream.md) |
| Daily resting heart rate | [features/resting-heart-rate.md](features/resting-heart-rate.md) |
| Daily HRV status and training readiness | [features/wellness.md](features/wellness.md) |

**Analysis page (`index.html`)**

| Feature | Document |
|---|---|
| Grabber download (zip) and copy buttons | [features/grabber-download.md](features/grabber-download.md) |
| Loading runs.json / GPX, browser storage, example data | [features/data-loading-and-storage.md](features/data-loading-and-storage.md) |
| Grade-adjusted pace (Minetti) | [features/grade-adjusted-pace.md](features/grade-adjusted-pace.md) |
| Pace at a fixed heart-rate band | [features/pace-at-heart-rate.md](features/pace-at-heart-rate.md) |
| Best efforts and VDOT | [features/best-efforts-and-vdot.md](features/best-efforts-and-vdot.md) |
| Yearly aggregates, trend, filters, charts, table | [features/yearly-trends.md](features/yearly-trends.md) |
| Resting heart rate chart and KPI | [features/resting-heart-rate.md](features/resting-heart-rate.md#page) |
| Aerobic decoupling | [features/aerobic-decoupling.md](features/aerobic-decoupling.md) |
| Cadence, stride length, Training Effect | [features/form-and-training-effect.md](features/form-and-training-effect.md) |
| Training load, load ratio, zones, consistency | [features/training-load-zones-consistency.md](features/training-load-zones-consistency.md) |

**Planner (`garmin_plan`)**

| Feature | Document |
|---|---|
| Runner profile, Daniels paces, HR zones | [features/plan-profile.md](features/plan-profile.md) |
| Workout templates, markdown renderer, manual `[week]` schedule | [features/plan-workouts.md](features/plan-workouts.md) |
| Plan generator: phases, volume, session choice and sizing, checks, fixes, warnings | [features/plan-generator.md](features/plan-generator.md) |
| Push to Garmin Connect: upload, schedule, re-push, dry-run | [features/plan-push.md](features/plan-push.md) |
| Plan adaptation: matching runs, missed sessions, fatigue, overrides, VDOT re-estimates, "What changed" | [features/plan-adaptation.md](features/plan-adaptation.md) |
