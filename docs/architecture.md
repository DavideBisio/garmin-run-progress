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

Runs on your machine because Garmin's login needs TLS impersonation (`curl_cffi`), which browsers can't do from a web page, and because Garmin's API blocks cross-origin requests.

1. Log in with saved tokens, or with credentials and MFA the first time.
2. Walk the activity list newest-first and stop at the first page with nothing new.
3. Download the GPX of each new outdoor run.
4. Parse every GPX into a compact stream and write `runs.json`.

It depends on [python-garminconnect](https://github.com/cyberjunky/python-garminconnect); everything else is standard library.

### `index.html` (static page, no build step)

One self-contained file: HTML, CSS and JavaScript inline. The only external resources are Google Fonts and Chart.js 4.4.1 from cdnjs. It also embeds a copy of `garmin_grab.py` so people can get the script from the page (see [grabber-download](features/grabber-download.md)).

All computation happens in the browser. Nothing is sent to a server.

## Why the split

| Concern | Where it lives | Reason |
|---|---|---|
| Authentication, network | Python | Needs `curl_cffi`; secrets stay on disk, never in a page |
| Distance, resampling | Python | Done once per activity and cached, so the page loads fast |
| All metrics and charts | Browser | Interactive (heart-rate band, month filter) without re-running anything |

The page only needs `runs.json`, so other sources can feed it: anything that writes the [runs.json format](runs-json-format.md) works.

## Page code map

The inline script in `index.html` is one IIFE organised in sections (search for the `/* ---- name ---- */` comments):

| Section | Responsibility |
|---|---|
| copy helpers | Clipboard with `execCommand` fallback |
| zip (stored) | Minimal ZIP writer for the grabber download |
| geometry & metrics | `hav`, `minetti`, `gapFactor`, `vdot`, `decYear`, `bestEffort`, `prepare`, `bandPace` |
| stats helpers | `median`, `theilSen`, pace and time formatters |
| example data | Seeded synthetic 10-year dataset shown before you load yours |
| GPX import | `parseGpxText` for loading raw GPX files |
| storage (IndexedDB) | Remember loaded data in this browser |
| state | `setData`, heart-rate band suggestion |
| loading | Drop zone, file input, JSON/GPX dispatch |
| render | Filters → yearly aggregates → KPIs, four charts, table |
| boot | Load example data, then saved data if any |

Run objects keep the original fields from `runs.json`; derived values are stored on underscore-prefixed properties (`_x`, `_y`, `_m`, `_g`, `_best`, `_hrOk`, `_km`, `_trail`).
