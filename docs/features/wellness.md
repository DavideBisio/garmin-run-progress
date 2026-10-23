# HRV status and training readiness

Daily HRV status and training readiness from Garmin's wellness data. The planner's adaptation loop ([plan adaptation](plan-adaptation.md#rules)) reads them as fatigue signals, next to resting heart rate. Both are optional: older watches don't record them, and nights without the watch have no value. A missing value never counts as fatigue.

## Grabber: `update_wellness`

Runs after `update_rhr`, skipped with `--rebuild`. Each source is skipped on its own, with a hint to upgrade, when the installed `garminconnect` lacks its method.

```text
hrv = garmin_export/hrv.json                    # {"YYYY-MM-DD": "BALANCED" | "UNBALANCED" | "LOW" | ...}
start = (latest known day − 7 days)  if hrv exists
        else --since, else the first run's date
for each chunk of 28 days from start to today:
    get_hrv_data_range(chunk_start, chunk_end)  # one request per chunk
    store each summary's {calendarDate: status}

ready = garmin_export/readiness.json            # {"YYYY-MM-DD": {"level": "LOW", "score": 22}}
start = as above, but never more than 60 days back
for each day from start to today:
    get_training_readiness(day)                 # one request per day
    store {level, score} (the morning reading when the day has several)
```

- Constants are in `config.py`: `HRV_CHUNK_DAYS` (28), `WELLNESS_REFRESH_DAYS` (7, the last week is fetched again because today's value settles later) and `READINESS_FIRST_DAYS` (60: readiness costs one request a day, so the first fetch and a long gap stop there).
- Parsing is defensive (`hrv_statuses`, `readiness_entry`): an HRV response may be `{"hrvSummaries": [...]}`, `{"hrvSummary": {...}}` or a list; a summary without a date or a status is skipped; a readiness reading without a level keeps `level: null`, one without a score `score: null`, and one with neither is skipped.
- The response shapes are not yet confirmed on a real account. If a field name differs, the day is simply missing.
- A failed request is logged and skipped. Ctrl-C keeps what was already saved by the step before.

`build_runs` copies both files into `runs.json` as sorted `hrv` and `readiness` arrays (see [runs.json format](../runs-json-format.md)). `--rebuild` uses the local files, so it needs no network.
