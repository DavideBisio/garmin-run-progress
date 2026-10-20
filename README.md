# garmin-run-progress

Measure how your running fitness changed over the years using your own Garmin Connect data.

It has two parts:

- **`garmin_grab.py`** is an incremental exporter. It logs into Garmin Connect, downloads the GPX of every run it hasn't seen before, and writes one compact `runs.json`.
- **`index.html`** is the analysis page. Open it in a browser, drop in `runs.json`, and get the trends. Everything runs locally, and nothing is uploaded.

## What the analysis shows

| Metric | What it tells you |
|---|---|
| **Pace at a fixed heart-rate band** | Grade-adjusted pace for the time spent in, say, 140–150 bpm, after a 10-minute warm-up. Getting faster at the same heart rate is the clearest sign of aerobic progress. The page also gives a per-year trend in s/km (Theil–Sen slope of the yearly medians). |
| **Best efforts → VDOT** | Fastest 1 km, 5 km, 10 km and half found inside any run each year, converted with Daniels' VDOT formula so different distances compare. |
| **Volume** | Kilometres and runs per year. |
| **Garmin VO2max** | The watch's own estimate, as a cross-check. |

Filters let you compare the same months across years (to remove summer heat) and exclude trail runs. Hills are corrected with Minetti's energy-cost curve over 100 m windows.

Chest-strap heart-rate data gives the most reliable results.

## Quick start

Requires Python 3.12+.

```bash
git clone https://github.com/DavideBisio/garmin-run-progress
cd garmin-run-progress
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade garminconnect curl_cffi ua-generator

python garmin_grab.py
```

The first run asks for your Garmin email, password and MFA code. Tokens are saved in `~/.garminconnect`, so later runs need nothing.

Then open `index.html` in a browser and drop in `garmin_export/runs.json`.

### Options

```text
python garmin_grab.py                    # fetch new runs, rebuild runs.json
python garmin_grab.py --since 2016-01-01 # ignore older activities
python garmin_grab.py --rebuild          # no network: rebuild runs.json from local files
python garmin_grab.py --full             # rescan the whole activity list
python garmin_grab.py --delay 2          # slower downloads (seconds between files)
python garmin_grab.py --out other_dir    # different output folder
```

The first pass over ~10 years takes about 1–2 hours because it pauses between downloads. Ctrl-C is safe; the next run picks up where it stopped. Later runs stop as soon as they reach activities they already know, so they take seconds.

### Output

```text
garmin_export/
  activities.json   summaries of every run (distance, duration, HR, VO2max, ...)
  seen_ids.json     every activity id already listed (for incremental runs)
  gpx/<id>.gpx      original GPX files
  cache/<id>.json   parsed streams, so rebuilds are fast
  runs.json         the file to load in index.html
```

`runs.json` stores each run's summary plus a time, distance, heart-rate and elevation stream sampled every 10 seconds. It is about 6 MB per 1,000 runs.

The page also accepts raw `.gpx` files directly (select many at once), but without Garmin's summaries those runs have no VO2max values.

## Privacy

- `garmin_export/` contains your GPS tracks and health data, and is listed in `.gitignore`. Don't commit it.
- `~/.garminconnect/garmin_tokens.json` grants access to your Garmin account. Treat it like a password.
- The analysis page keeps your data in your browser (IndexedDB) only if "Remember in this browser" is ticked.

## Caveats

- This uses [python-garminconnect](https://github.com/cyberjunky/python-garminconnect), an **unofficial** library. Garmin changed its login in 2026 and broke older tools; it may happen again. If login fails, first try `pip install --upgrade garminconnect curl_cffi ua-generator`.
- Best efforts are taken from any stretch of any run, so a year without races shows training efforts and understates your level.
- Garmin's VO2max can jump when you change watch model.

## License

GPL-3.0. See [LICENSE](LICENSE).
