# Architecture

```text
 Garmin Connect                     your computer                          browser
┌──────────────┐  activity list  ┌──────────────────┐   runs.json    ┌─────────────────┐
│  web API     │ ──────────────▶ │  garmin_grab.py  │ ─────────────▶ │   index.html    │
│ (unofficial) │  GPX per run    │  garmin_export/  │  (drag & drop) │  analysis, all  │
└──────────────┘ ──────────────▶ └──────────────────┘                │  client-side    │
                                                                     └─────────────────┘
```

## Components

### `garmin_grab.py` (Python 3.12+)

Source: the `src/garmin_grab/` package. `tools/build.py` bundles it into a single-file `garmin_grab.py`, which is what people download (from a release or the page) and run (see [Source layout and build](#source-layout-and-build)).

Runs on your machine because Garmin's login needs TLS impersonation (`curl_cffi`), which browsers can't do from a web page, and because Garmin's API blocks cross-origin requests.

1. Log in with saved tokens, or with credentials and MFA the first time.
2. Walk the activity list newest-first and stop at the first page with nothing new.
3. Download the GPX of each new outdoor run.
4. Fetch daily resting heart rate since the first run (or the last known day).
5. Parse every GPX into a compact stream and write `runs.json`.

It depends on [python-garminconnect](https://github.com/cyberjunky/python-garminconnect); everything else is standard library.

### `index.html` (static page)

Source: `src/page/`. The built `index.html` is one self-contained file: HTML, CSS and JavaScript inline, including the vendored Chart.js (version in `CHART_VERSION` in `tools/build.py`) and site-kit's `tokens.css`. It makes no third-party requests, so it works offline. The shared `<site-bar>` from site-kit sits on top, and the theme (`data-theme`, `localStorage.theme`) is shared with every `*.github.io` project site. It also embeds a copy of `garmin_grab.py` so people can get the script from the page (see [grabber-download](features/grabber-download.md)).

All computation happens in the browser. Nothing is sent to a server.

## Why the split

| Concern | Where it lives | Reason |
|---|---|---|
| Authentication, network | Python | Needs `curl_cffi`; secrets stay on disk, never in a page |
| Distance, resampling | Python | Done once per activity and cached, so the page loads fast |
| All metrics and charts | Browser | Interactive (heart-rate band, month filter) without re-running anything |

The page only needs `runs.json`, so other sources can feed it: anything that writes the [runs.json format](runs-json-format.md) works.

## Source layout and build

```text
src/garmin_grab/        grabber package (python -m garmin_grab from src/)
src/garmin_plan/        training planner package (python -m garmin_plan from src/; not bundled)
src/garmin_plan/data/   generic planner data: rules.toml (pace fractions, bands), workouts.toml (workout templates)
src/page/index.html     page markup; loads vendor/tokens.css, styles.css, vendor/chart.umd.min.js and js/*.js
src/page/styles.css     the app's CSS; its tokens alias site-kit's --sk-* tokens, plus the data-viz colors
src/page/vendor/        tokens.css (copied from site-kit) and chart.umd.min.js (Chart.js, MIT header kept)
src/page/js/*.js        page script, one file per section; site-bar.js is copied from site-kit
tools/build.py          src/ → dist/garmin_grab.py + dist/index.html (not committed)
site/                   project site (Astro + site-kit): landing page, docs/ as pages, the app copied to /app/
project.json            listing for the hub (davidebisio.github.io)
.github/workflows/      ci.yml: test, build the site; pages.yml: deploy the site; release.yml: publish releases
tests/                  grabber, planner and build unit tests, page smoke tests, metric parity vectors
                        (fixtures/metric_vectors.json, metrics.test.mjs), site checks (site.test.mjs)
Makefile                dev, test, site and deploy tasks
```

`tools/build.py` writes the two shipped files into `dist/`:

- **`garmin_grab.py`:** the `__init__.py` docstring, then every module's imports merged at the top, then each module's body in dependency order (`MODULES` in the build script). Package-internal imports (`from .x import y`) are dropped. Because the bundle has a single namespace, the build fails in four cases:
  - a module imports from one listed after it
  - a relative import sits inside a function
  - two modules define the same top-level name
  - one module defines a name that another module imports, or two modules import the same name from different places
- **`index.html`:** `src/page/index.html` with `vendor/tokens.css` and `styles.css` inlined into `<style>` (in that order), `vendor/chart.umd.min.js` inlined as its own `<script>`, the block of `<script src="js/…">` tags replaced by one inline IIFE holding the files in tag order, and the bundled grabber in `#grabber-src`. The build then checks that the page is self-contained: it fails on any remote `<script src>`, any remote `<link>` (stylesheet, font, preconnect), any CSS `@import` or remote `url()`, and any local `.js`/`.css` file left un-inlined. Plain links (`<a href>`) are fine.

`dist/` is gitignored. GitHub Actions builds it on every push: on `main`, `pages.yml` copies `dist/index.html` into the project site at `/app/` and deploys the site to GitHub Pages, and a `v*` tag publishes both files as release assets, so people still get a single script to run without installing a package (see [Deploy → Releasing a change](deploy.md#releasing-a-change)).

## Page code map

The page script is split into `src/page/js/`, one file per section, loaded in this order. The files share one scope: the built page wraps them in a single IIFE, and the unbuilt page loads them as classic scripts, whose top-level declarations are visible to the scripts after them. So a top-level name must be unique across files and must not clash with a browser global.

| File | Responsibility |
|---|---|
| `site-bar.js` | site-kit's `<site-bar>` element (verbatim copy, loaded first): owner and project links, Docs and Source, theme switch shared through `localStorage.theme` |
| `dom.js` | `$` helper; shows the embedded grabber source |
| `copy.js` | Clipboard with `execCommand` fallback |
| `zip.js` | Minimal ZIP writer for the grabber download |
| `metrics.js` | `hav`, `minetti`, `gapFactor`, `vdot`, `decYear`, `weekOf`, `bestEffort`, `prepare`, `bandPace`, `decoupling`, `HRR_ZONES`, `hrrZones`, `zoneTime`, `trimp` |
| `stats.js` | `median`, `theilSen`, pace and time formatters |
| `example-data.js` | Seeded synthetic 10-year dataset shown before you load yours |
| `gpx-import.js` | `parseGpxText` for loading raw GPX files |
| `storage.js` | Remember loaded data in this browser (IndexedDB) |
| `state.js` | `setData(payload, isExample, fromUser)` (runs, resting HR and the plan (`PLAN`, or null), status chip; a user load opens Analysis), heart-rate band and max/resting HR suggestions |
| `loading.js` | Drop zone, file input, JSON/GPX dispatch |
| `render.js` | Filters → yearly aggregates → KPIs, fitness charts, year table; then `renderTraining` and `renderPlan` |
| `training.js` | `renderTraining`: last 52 weeks of all runs → load, load ratio, zones, weekly distance, consistency table |
| `plan.js` | `renderPlan`: the Planning tab from `runs.json`'s `plan` (read-only): header line and warnings, the HR note, this week's 7 day cards with their status (stored, else matched to the runs by date), the step table of a picked day; the empty state without a plan. Its top-level names start with `plan`/`PLAN_` |
| `tabs.js` | Data, Analysis and Planning tabs: WAI-ARIA tabs (arrow keys, Home/End), `showTab` follows the URL hash (`#data`, `#analysis`, `#planning`; old `#s1`–`#s3` too) and resizes the Analysis charts on show |
| `boot.js` | Re-render on theme change; load example data, then saved data if any (which opens Analysis unless the hash picked a tab) |

## Grabber modules

| Module | Responsibility |
|---|---|
| `config.py` | Token folder, page size, sample interval, resting HR, HRV and readiness chunking and refresh |
| `storage.py` | `load_json`, `save_json` (atomic write) |
| `activities.py` | `is_run`, `type_key`, `has_gps` |
| `garmin.py` | `login`, `with_retry`, `list_new_activities`, `download_gpx` |
| `rhr.py` | `update_rhr` |
| `wellness.py` | `update_wellness` (`update_hrv`, `update_readiness`; optional, skipped per source without the library method; `wellness_fetched.json` records how far each got), `wellness_start`, `hrv_statuses`, `readiness_entry` |
| `gpx.py` | `parse_gpx`, `to_stream`, `haversine` |
| `export.py` | `summary_fields`, `build_runs` |
| `cli.py` | `main`: arguments and the overall flow |

## Planner modules (`garmin_plan`)

Runs from a clone (`make plan-profile`, `make plan`, `make push`, `make replan`) and is not part of the release bundle. It is standard library only, except a real `push`: that logs in through `garmin_grab.garmin.login` and so uses `garminconnect`, imported only then (`push --dry-run` needs neither). Personal files (`profile.toml`, `plan.json`, `plan.md`, `push_state.json`, `push/`) stay in `garmin_export/`; generic data is committed in `src/garmin_plan/data/`. See [plan profile](features/plan-profile.md), [plan workouts](features/plan-workouts.md), [plan generator](features/plan-generator.md), [plan push](features/plan-push.md) and the [plan.json format](plan-json-format.md).

| Module | Responsibility |
|---|---|
| `config.py` | Paths (`garmin_export/`, `profile.toml`, `runs.json`, `plan.json`, `plan.md`, `push_state.json`, `push/`, `data/`), defaults, weekday names, the `[plan] ` name prefix and `NAME_MAX` |
| `physiology.py` | `vo2`, `pct_max`, `vdot`, `race_time`, `pace_zones` (Daniels, fractions in `data/rules.toml`), `hr_zones` (Karvonen, as `hrrZones`) |
| `metrics.py` | Ports of `metrics.js`: `gap_factor`, `day_index`, `week_of`, `week_start`, `best_effort`, `trimp`, and `prepare`'s `run_km`, `hr_ok`, `hr_peak` |
| `history.py` | `weekly_km`, `recent_stats` (4/12-week volume, runs per week, longest run, recent VDOT, consistency, days since the last run and the volume, consistency and longest run before it), `q_sessions` (runs with 10 min in Z4+, `z4_seconds`), `time_trials` (the planned time trials' best 2 km, with the recorded ones), `resting_hr`, `hr_max` (the page's suggestions), `daily_load` and `acwr` (the page's daily TRIMP and 7:28-day load ratio) |
| `profile.py` | `load_profile` → `Profile` with a `set` / `derived` / `default` source per field, the levels and their reasons, the layoff, the unit, the `[week]` schedule, the `[[override]]` days (`parse_overrides`), the VDOT estimate across re-plans (`reestimate_vdot`, `race_vdot`), warnings, `ProfileError` |
| `levels.py` | `load_levels`, `params` (`levels.toml` laid over `rules.toml` for a volume and a quality level), `detect` (both levels from the history, with reasons), `describe`, `promote` (from the last plan's levels: at a block's start, with hysteresis; down only after a break), `block_start`, `layoff` (VDOT and volume factors after a break), `unit` |
| `match.py` | `match` (each planned session up to today → done, partial, missed, moved or swapped, with the run's id: same day first, then ±1 day, by kind), `q_compliance` (the last block's Q sessions done, for `levels.promote`), `last_block`, `hard_seconds` |
| `progress.py` | `carry` (what the last `plan.json`'s `progress` carries to a plan from a Monday: its block, the no-race cycle's start, the run/walk stage reached in the plan's own weeks, the time trials run and planned), `trial_days` |
| `adapt.py` | `adapt` (from today on: lock, skip and reduce overrides, a missed L moved or skipped, fatigue turning the next Q easy; the change log), `fatigue` (resting HR, HRV status, readiness) |
| `replan.py` | `replan` (the generator's plan behind the last plan's past and current weeks, adapted), `keep_past` (the kept weeks, each day's `status` and `activity_id`), `record_history`, `changed_weeks`, `easy_maker` |
| `model.py` | `PaceRange` (the only place pace order is handled; `to_speed`), `HrRange`, `Step`, `Repeat`, `Workout` with `km` / `seconds` / `hard_km` summed from the parts |
| `templates.py` | `load_templates` (validates `workouts.toml`, `TemplateError`), `instantiate(template, variant, profile, rules, overrides)` (overrides: ladder values, warm-up and cool-down lengths), `pace_range`, `jog_pace`, `hr_range`, `zone_span` |
| `render_md.py` | `render_workout`, `render_plan` (markdown in the hand-written plan's format; "What changed", the warnings, each week's phase and deload, the kept days' status), `fmt_pace`, `fmt_time`, `fmt_est`, `fmt_warning` |
| `plan_io.py` | `manual_days` (the `[week]` schedule's workouts), `build_plan` (the `[week]` schedule alone over N weeks), `profile_hash`, `write_plan` / `read_plan` (rejects weeks and days without their dates), workout ↔ dict |
| `skeleton.py` | `place_slots` (each available day → L / Q / E / F or rest: the run cap, one or more Q days, the 48 h rule, the Sat/Sun fallback), `q_count`, `gap`, `SkeletonError` |
| `volume.py` | `block_curve` (4-week ramp and deload blocks, the start floor, unit-agnostic), `align_deloads` (deloads off phase starts), `settings` |
| `phases.py` | `phase_calendar` (Monday-based weeks counted back from the race, shortened phases with warnings; without a race the cycle from an offset), `race_key`, `PhaseWeek`, `PhaseError` |
| `split.py` | `split_week` (a week's km across its slots: the L caps, the E minimum, F on/off, Q dropped when the week can't hold it, with warnings) |
| `select.py` | `block_week` (a week's place in its block, from a mid-block start too), `rotation` / `candidates` (the Q and L templates of a phase and block week: hill swaps, level fallback) |
| `size.py` | `cap_km` (hard-portion caps), `pick_variant` (the largest ladder variant under the cap that fits the slot; the smallest, forced, when none does), `fit` (an easy or long run stretched to its km or time budget, a longer warm-up) |
| `terrain.py` | `flat_equivalent_km`, `workout_flat_km` (hill and trail volume through Minetti's cost of running, as the page's grade-adjusted pace) |
| `load.py` | `flat_steps`, `hr_mid`, `step_trimp`, `workout_trimp`, `projected_daily` (planned TRIMP at each step's HR-zone midpoint) |
| `checks.py` | `Day`, `check_week` (easy share, hard days, volume rise, load ratio, L share → `Violation`s and notes), `easy_share`, `week_km`, `feasibility` |
| `fix.py` | `fix_week` (shrink Q, trim L, drop F; bounded and deterministic), `Adjust`, `FixResult` |
| `planner.py` | `build_plan` (the generator: phases, volume, slots, sessions, the split, checks and fixes, `[week]` overrides, warnings, the `progress` the next plan carries on) |
| `push.py` | `to_garmin` (plan.json workout → `RunningWorkout`-shaped dict, Garmin ids inlined), `workout_name`, `sessions`, `local_today`, `check_library`, `push` (re-push, resume, `push_state.json`, dry-run; a day already run left alone) |
| `cli.py` | `main`: the `profile`, `plan` (the generator, through `replan`), `push` and `replan` (plan, then push unless `--no-push` or `auto_push = false`) subcommands (shared `--export`, `--today`); `load_runs` (runs and wellness), `ran_today` |
| `data/rules.toml` | What is the same at every level: Daniels pace fractions, the R-pace offset, pace bands and the jog offset; the F slot (`[skeleton]`), the deload, the next block's start and the taper (`[volume]`), L's growth (`[split]`), the phase calendar (`[phases]`, lengths per race distance in `[phases.*]`), the hard-portion caps (`[caps]`), the session rotations (`[rotation]`, per phase in `[rotation.*]`, with `Q2` rows), the week checks (`[checks]`), the fixer (`[fix]`), goal feasibility (`[feasibility]`) and the adaptation loop (`[adapt]`) |
| `data/levels.toml` | What depends on the runner's level, each key a `level = value` table: the ramp, block length, start floor and unit (`[volume]`), the long run caps and the E minimum (`[split]`), the run cap and Q days (`[skeleton]`), the E template, run/walk ladder, time trial and the beginner's rotation (`[rotation]`); level detection and promotion (`[detect]`) and the layoff table (`[layoff]`) |
| `data/workouts.toml` | The workout template library (stable ids) |

Run objects keep the original fields from `runs.json`; derived values are stored on underscore-prefixed properties (`_x`, `_y`, `_m`, `_day`, `_g`, `_best`, `_hrOk`, `_hrPeak`, `_dec`, `_decMin`, `_km`, `_trail`).
