# 03 · Core metrics and runner profile

## Requirements

- `garmin_export/profile.toml` (gitignored) holds what only the runner knows:
  - HRmax, plus HRrest as an optional override;
  - an optional race: date, distance, goal time;
  - available days, preferred long-run day, days with hill access.
- Values not set in the profile are derived from `runs.json`:
  - current VDOT;
  - 4- and 12-week average weekly km;
  - runs per week;
  - longest run in the last 8 weeks;
  - resting HR, as the median of the last 365 days, the same rule the page uses.
- Pace zones E / M / T / I / R are computed from VDOT with Daniels' formulas.
- HR zones Z1–Z5 use the page's Karvonen definition from 01 (% of HRR).
- A Python port of the page maths that the planner needs (`vdot`, `gapFactor`, `trimp`, `hrrZones`, `weekOf`, `bestEffort`) gives the **same numbers** as the JS.
- `python -m garmin_plan profile` prints the resolved profile and where each value came from: `set`, `derived` or `default`.

## Implementation

```text
src/garmin_plan/
  __init__.py, __main__.py
  config.py       paths: garmin_export/profile.toml, plan.json, plan.md
  physiology.py   vo2(v), pct_max(t), vdot(m, s), race_time(vdot, m),
                  pace_zones(vdot), hr_zones(hr_max, hr_rest)
  metrics.py      gap_factor, trimp, week_of, best_effort   (ports of src/page/js/metrics.js)
  history.py      weekly_km(runs), recent_stats(runs, today)
  profile.py      load_profile(path, runs) -> Profile (dataclass) + per-field source
  cli.py          subcommands: profile (later: plan, push, replan)
```

- **VDOT:**
  - `VO2(v) = −4.60 + 0.182258·v + 0.000104·v²` (v in m/min)
  - `%max(t) = 0.8 + 0.1894393·e^(−0.012778·t) + 0.2989558·e^(−0.1932605·t)` (t in minutes)
- **Training paces:** solve `VO2(v) = f · VDOT` for v.
  - E, T and I use the fractions `f` in `rules.toml`, calibrated against Daniels' published tables.
  - M is the predicted marathon race pace. `race_time` bisects `vdot(42195, t) = VDOT`, and the goal-feasibility check in 07 reuses it.
  - R is I pace minus 6 s per 400 m.
- **HR zones:** `rest + p · (max − rest)` at the same boundaries and rounding as `hrrZones` in 01.
- **Resolution order** for each field: profile value, then derived from `runs.json`, then default. Each fallback to a default prints a warning.
- **Make targets:** `make plan-profile`. `PYTHONPATH=src` is already exported by the Makefile.

## Testing strategy

- **Physiology:** paces for VDOT 30/40/50/60 must be within ±2 s/km of Daniels' tables, which are committed as a fixture. HR zones are checked exactly for a known max/rest pair.
- **Parity with the page:** `tests/fixtures/metric_vectors.json` holds inputs and expected outputs.
  - A Node test computes them from the built page functions.
  - A Python test checks `garmin_plan.metrics` against the same file, with tolerance 1e-9.
  - If either side drifts, CI fails.
- **History:** synthetic `runs.json` fixtures check:
  - Monday-based week boundaries;
  - `startTimeLocal` dates around midnight;
  - treadmill runs counted in volume;
  - gaps of weeks with zero runs.
- **Profile:** the precedence `set > derived > default`, a missing file, an empty history, and invalid values such as max < rest.

## Completion checklist

- [x] `git check-ignore garmin_export/profile.toml` confirms the profile is never committed.
- [x] `hr_zones` gives exactly the bpm of the page's `hrrZones` (01), including rounding. The parity vectors include it.
- [x] The resting HR default uses the same median-of-365-days rule as `state.js`, so the page and the planner show the same value.
- [x] VDOT derived from training runs (not races) understates fitness. The output marks it as `derived (training efforts)`, and a race or time-trial value set in the profile wins.
- [x] A new user with fewer than 4 weeks of data gets defaults and warnings, not an exception.
- [x] `docs/architecture.md` gains a `garmin_plan` module table, and there's a new `docs/features/plan-profile.md`.

Shipped: `src/garmin_plan/` (`config`, `physiology`, `metrics`, `history`, `profile`, `cli`) with `data/rules.toml`, `make plan-profile`, and `tests/test_plan.py` plus `tests/metrics.test.mjs` on the shared `tests/fixtures/metric_vectors.json`. The parity test loads `src/page/js/metrics.js`, which the build inlines verbatim, because in `dist/` the functions sit inside the page IIFE. The Daniels fixture checks M, T, I and R within ±2 s/km and E inside the published E range, since Daniels gives E as a range. See [plan profile](../features/plan-profile.md).
