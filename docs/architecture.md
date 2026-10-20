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

Source: `src/page/`. The built `index.html` is one self-contained file: HTML, CSS and JavaScript inline. The only external resources are Google Fonts and Chart.js 4.4.1 from cdnjs. It also embeds a copy of `garmin_grab.py` so people can get the script from the page (see [grabber-download](features/grabber-download.md)).

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
src/page/index.html     page markup; loads styles.css and js/*.js
src/page/styles.css     all CSS
src/page/js/*.js        page script, one file per section
tools/build.py          src/ → dist/garmin_grab.py + dist/index.html (not committed)
.github/workflows/      ci.yml: test, deploy Pages; release.yml: publish releases
tests/                  grabber unit tests, page smoke tests
Makefile                dev, test and deploy tasks
```

`tools/build.py` writes the two shipped files into `dist/`:

- **`garmin_grab.py`:** the `__init__.py` docstring, then every module's imports merged at the top, then each module's body in dependency order (`MODULES` in the build script). Package-internal imports (`from .x import y`) are dropped. Because the bundle has a single namespace, the build fails in four cases:
  - a module imports from one listed after it
  - a relative import sits inside a function
  - two modules define the same top-level name
  - one module defines a name that another module imports, or two modules import the same name from different places
- **`index.html`:** `src/page/index.html` with `styles.css` inlined into `<style>`, the block of `<script src="js/…">` tags replaced by one inline IIFE holding the files in tag order, and the bundled grabber in `#grabber-src`.

`dist/` is gitignored. GitHub Actions builds it on every push: `main` is deployed to GitHub Pages, and a `v*` tag publishes both files as release assets, so people still get a single script to run without installing a package (see [Deploy → Releasing a change](deploy.md#releasing-a-change)).

## Page code map

The page script is split into `src/page/js/`, one file per section, loaded in this order. The files share one scope: the built page wraps them in a single IIFE, and the unbuilt page loads them as classic scripts, whose top-level declarations are visible to the scripts after them. So a top-level name must be unique across files and must not clash with a browser global.

| File | Responsibility |
|---|---|
| `dom.js` | `$` helper; shows the embedded grabber source |
| `copy.js` | Clipboard with `execCommand` fallback |
| `zip.js` | Minimal ZIP writer for the grabber download |
| `metrics.js` | `hav`, `minetti`, `gapFactor`, `vdot`, `decYear`, `weekOf`, `bestEffort`, `prepare`, `bandPace`, `decoupling`, `zoneTime`, `trimp` |
| `stats.js` | `median`, `theilSen`, pace and time formatters |
| `example-data.js` | Seeded synthetic 10-year dataset shown before you load yours |
| `gpx-import.js` | `parseGpxText` for loading raw GPX files |
| `storage.js` | Remember loaded data in this browser (IndexedDB) |
| `state.js` | `setData` (runs and resting HR), heart-rate band and max/resting HR suggestions |
| `loading.js` | Drop zone, file input, JSON/GPX dispatch |
| `render.js` | Filters → yearly aggregates → KPIs, fitness charts, year table |
| `training.js` | `renderTraining`: last 52 weeks of all runs → load, load ratio, zones, weekly distance, consistency table |
| `boot.js` | Re-render on theme change; load example data, then saved data if any |

## Grabber modules

| Module | Responsibility |
|---|---|
| `config.py` | Token folder, page size, sample interval, resting HR chunking |
| `storage.py` | `load_json`, `save_json` (atomic write) |
| `activities.py` | `is_run`, `type_key`, `has_gps` |
| `garmin.py` | `login`, `with_retry`, `list_new_activities`, `download_gpx` |
| `rhr.py` | `update_rhr` |
| `gpx.py` | `parse_gpx`, `to_stream`, `haversine` |
| `export.py` | `summary_fields`, `build_runs` |
| `cli.py` | `main`: arguments and the overall flow |

Run objects keep the original fields from `runs.json`; derived values are stored on underscore-prefixed properties (`_x`, `_y`, `_m`, `_day`, `_g`, `_best`, `_hrOk`, `_hrPeak`, `_dec`, `_decMin`, `_km`, `_trail`).
