# Data loading and storage

Step 2 of the page. Code sections: `loading`, `storage (IndexedDB)`, `state`, `example data`.

## Inputs

The drop zone and hidden file input (`accept=".json,.gpx"`, `multiple`) feed `handleFiles`:

| Selection | Behaviour |
|---|---|
| contains a `.json` | Parse it; reject unless it has a `runs` array |
| only `.gpx` files | Parse each with `parseGpxText` (progress bar), wrap as `{format, runs}` |
| anything else | Error: "Choose runs.json or .gpx files." |

If both are selected, the JSON wins. The drop zone is keyboard-operable (Enter/Space opens the picker).

## setData

`setData(payload, isExample)`:

1. Shallow-copies each run and calls `prepare(run)`, which adds the derived fields below. Runs with an unparseable `date` are dropped.
2. Sorts by date.
3. Updates the status chip ("Showing example data" vs "Your data · N runs · 2016–2026").
4. Suggests a heart-rate band.
5. Calls `render()`.

`prepare` computes, once per load:

| Field | Meaning |
|---|---|
| `_x` | Decimal year (e.g. 2021.37) for time axes |
| `_y`, `_m` | Year and month for grouping and the month filter |
| `_trail` | `type` contains `trail` |
| `_km` | `dist / 1000`, or stream distance |
| `_g` | Grade per sample (see [grade-adjusted-pace](grade-adjusted-pace.md)) |
| `_hrOk` | More than 60% of samples have heart rate |
| `_best` | Best 1k/5k/10k/half times (see [best-efforts-and-vdot](best-efforts-and-vdot.md)) |

Metrics that depend on controls (heart-rate band) are computed in `render`.

## Heart-rate band suggestion

For each run with heart rate, take the median bpm. Across runs, show the 35th percentile ("easy runs typically sit around …") and the median. It's a hint only; the inputs keep their values (default 140–150).

## Remembering data

With "Remember in this browser" ticked (default), the loaded payload is stored in IndexedDB:

- database `run-progress-lab`, object store `kv`, key `data`
- IndexedDB rather than `localStorage` because a 10-year `runs.json` is 10–20 MB, beyond `localStorage` limits

On boot the page renders example data immediately, then replaces it with the stored payload if one exists. Unticking the box or pressing "Forget my data" deletes the key. Every IndexedDB call is wrapped in try/catch, so private windows or blocked storage just mean nothing is remembered.

Data never leaves the browser.

## Example data

`exampleData()` builds a deterministic synthetic 10-year dataset (seeded Park–Miller generator) so the page is useful before anything is loaded:

- a run every 3–6 days from March 2016
- fitness rising, then plateauing after year 6.5
- +4 bpm heat drift in June–August, so the month filter visibly matters
- 15% of runs at threshold heart rate
- rolling terrain (±25 m)

The status chip says "Showing example data" until real data is loaded.
