# GPX parsing and streams

File: `garmin_grab.py` — `parse_gpx`, `to_stream`, `haversine`, `summary_fields`, `build_runs`. The page has a JavaScript twin, `parseGpxText`, for loading raw GPX files.

## Parsing

`parse_gpx` uses `xml.etree.ElementTree` and matches on local tag names, so namespaces (GPX 1.1, Garmin `TrackPointExtension` v1/v2) don't matter:

| Tag | Use |
|---|---|
| `trkpt@lat`, `@lon` | position |
| `time` | ISO 8601 → epoch seconds (`Z` → UTC; naive times treated as UTC) |
| `ele` | metres |
| `hr` | bpm, from Garmin's extension |

Points without a time are dropped; the rest are sorted by time.

## Distance

Cumulative haversine distance (Earth radius 6,371,008.8 m) is computed over **all** points before resampling, so no distance is lost by skipping points.

GPS distance usually differs a little from Garmin's own (which may use a foot pod or smoothing). If the summary distance is within ±15% of the GPS total, every cumulative value is scaled by `summary / gps`. Outside that range the GPS distance is kept, since the summary is probably wrong (e.g. a manually edited activity).

## Resampling

A point is kept when at least `SAMPLE_EVERY_S` (10) seconds have passed since the last kept point; the last point is always kept. Recording at 1 Hz, that shrinks a run by ~10× while keeping enough resolution for:

- heart-rate band filtering (10 s is far below HR response time)
- best efforts, which interpolate between samples (see [best-efforts-and-vdot](best-efforts-and-vdot.md))

Pauses remain as larger gaps in `t`; the page treats gaps over 30 s as stops.

## Encoding

`t` seconds from start, `d` metres, `hr` bpm (`0` if missing), `e` elevation in decimetres (`0` if missing). All integers. See [runs.json format](../runs-json-format.md).

## Cache

`build_runs` stores each parsed stream in `garmin_export/cache/<id>.json` and reuses it while it is newer than the GPX file. Rebuilding `runs.json` for 2,500 runs then takes seconds instead of a minute or so. Delete `cache/` to force a full re-parse (needed after changing `SAMPLE_EVERY_S` or the parsing code).

## The browser version

`parseGpxText` in `index.html` does the same with `DOMParser` and `getElementsByTagNameNS("*", "trkpt")`, with two differences:

- no summary is available, so distance is not scaled and VO2max is missing;
- `type` is `trail_running` if the word "trail" appears in the first 3,000 characters of the file (Garmin puts the activity type and name near the top), else `running`.

Files are parsed sequentially with a yield to the event loop every 20 files, so the progress bar updates.
