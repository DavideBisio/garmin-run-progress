# Resting heart rate

Daily resting heart rate from Garmin's wellness data, not from activities. A falling resting heart rate over months is one of the clearest signs of rising aerobic fitness; a sudden rise of 5 bpm or more usually means fatigue, illness or poor sleep.

## Grabber: `update_rhr`

```text
rhr = garmin_export/rhr.json                    # {"YYYY-MM-DD": bpm}
start = (latest known day − 7 days)  if rhr exists
        else --since, else the first run's date
for each chunk of 364 days from start to today:
    get_rhr_daily(chunk_start, chunk_end)       # one request per chunk
    store every {calendarDate, value} row (rounded to whole bpm)
save rhr.json
```

- `get_rhr_daily` was added in python-garminconnect 0.3.x and queries `/userstats-service/wellness/daily/{displayName}` with `metricId=60` for a whole date range. If the installed library doesn't have it, the step prints a message telling you to upgrade and is skipped.
- The last 7 days are fetched again on every run because today's value is still provisional until Garmin finishes the day.
- Ten years of history take about 10 requests. A failed chunk is logged and skipped; it is retried next time only if it falls inside the refresh window, so after a failure on the first run, delete `rhr.json` to start again.
- Ctrl-C during this step keeps everything already downloaded.
- Days without a watch-worn night have no value and are simply missing.

`build_runs` copies `rhr.json` into `runs.json` as a sorted `rhr` array of `[date, bpm]` pairs (see [runs.json format](../runs-json-format.md)). `--rebuild` uses the local file, so it needs no network.

## Page

`setData` turns `payload.rhr` into `RHR`: `{x: decimal year, y: year, day: day index, v: bpm}`, sorted by day. Missing or malformed entries are dropped.

| Output | Computation |
|---|---|
| Chart `#c-rhr` | Daily dots, plus a 30-day rolling median (drawn once at least 10 days are in the window) |
| KPI "Resting heart rate" | Median of the last 30 days of data vs the 30 days one year earlier; green chip when lower |
| Year table "Resting HR" | Median of all days in that calendar year |
| "Your heart rate" (Data tab) resting HR default | Median of the last 365 days (see [training](training-load-zones-consistency.md)) |

The month and trail filters don't apply to resting heart rate. The panel and KPI are hidden when the file has no `rhr` array (older runs.json files or GPX imports).
