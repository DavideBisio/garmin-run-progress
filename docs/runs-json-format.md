# runs.json format

`runs.json` is the only interface between the grabber and the page. Format id: `garmin-runs/1`.

```json
{
  "format": "garmin-runs/1",
  "generated": "2026-10-20T11:00:00",
  "sampleEvery": 10,
  "runs": [
    {
      "id": 17345678901,
      "date": "2024-05-01 07:30:12",
      "name": "Morning Run",
      "type": "running",
      "dist": 10012.4,
      "dur": 3050.0,
      "moving": 3001.0,
      "elev": 84.0,
      "avgHr": 146.0,
      "maxHr": 171.0,
      "vo2": 52.0,
      "cad": 172.0,
      "stride": 108.4,
      "te": 3.1,
      "teAn": 0.4,
      "hrz": [120, 840, 1510, 560, 20],
      "t":  [0, 10, 20],
      "d":  [0, 31, 62],
      "hr": [118, 124, 129],
      "e":  [1203, 1204, 1206]
    }
  ],
  "rhr": [["2024-04-30", 49], ["2024-05-01", 48]]
}
```

The file is written compact (no whitespace). Runs are sorted by start time.

## Summary fields

From Garmin's activity list. Any of them can be `null`.

| Field | Unit | Garmin source |
|---|---|---|
| `id` | – | `activityId` |
| `date` | local time, `YYYY-MM-DD HH:MM:SS` | `startTimeLocal` |
| `name` | – | `activityName` |
| `type` | – | `activityType.typeKey` (`running`, `trail_running`, `treadmill_running`, …) |
| `dist` | m | `distance` |
| `dur` | s, elapsed | `duration` |
| `moving` | s | `movingDuration` |
| `elev` | m gained | `elevationGain` |
| `avgHr`, `maxHr` | bpm | `averageHR`, `maxHR` |
| `vo2` | ml/kg/min | `vO2MaxValue` |
| `cad` | steps/min | `averageRunningCadenceInStepsPerMinute` |
| `stride` | cm per step | `avgStrideLength` |
| `te`, `teAn` | 0–5 | `aerobicTrainingEffect`, `anaerobicTrainingEffect` |
| `hrz` | s in zones 1–5 (Garmin's zones) | `hrTimeInZone_1` … `hrTimeInZone_5`; `null` when Garmin has none |

Numbers are rounded to 2 decimals.

## Stream fields

Present only when the run had a usable GPX track (absent for treadmill/indoor runs). Four parallel integer arrays, one entry per sample, roughly every `sampleEvery` seconds:

| Field | Unit | Notes |
|---|---|---|
| `t` | s since first point | Includes pauses (elapsed time) |
| `d` | m, cumulative | Scaled to Garmin's summary distance when within ±15% |
| `hr` | bpm | `0` = no reading |
| `e` | decimetres | Elevation × 10; `0` = no reading |

Integers keep the file small: about 6 MB per 1,000 runs.

## Resting heart rate

Top-level `rhr`: daily resting heart rate as `[date, bpm]` pairs, sorted by date, from Garmin's wellness data (see [resting heart rate](features/resting-heart-rate.md)). Days without a value are absent. About 15 bytes per day.

## Compatibility rules for the page

- Required: a top-level `runs` array; each run needs `date`.
- Runs without streams still count for volume, VO2max, cadence, stride, Training Effect and training load (from `avgHr`).
- `rhr` and the summary fields added later (`stride`, `te`, `teAn`, `hrz`) are optional; panels without data are hidden. Run `garmin_grab.py --rebuild` to add them to an older export.
- Unknown fields are ignored, so new fields can be added without breaking older pages.
- A breaking change should bump `format` to `garmin-runs/2`.
