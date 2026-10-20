# Cadence, stride length and Training Effect

Three per-run values that come straight from Garmin's activity summary, so they also work for treadmill runs without a GPS stream.

| runs.json field | Garmin source | Unit |
|---|---|---|
| `cad` | `averageRunningCadenceInStepsPerMinute` | steps/min |
| `stride` | `avgStrideLength` | cm per step |
| `te` | `aerobicTrainingEffect` | 0–5 |
| `teAn` | `anaerobicTrainingEffect` | 0–5 |

The grabber reads them in `summary_fields`. Because `activities.json` keeps Garmin's full summaries, `python garmin_grab.py --rebuild` adds them to runs you downloaded before these fields existed.

## Cadence and stride length

Speed = cadence × stride length. Plotting both shows whether you got faster by taking quicker steps or longer ones.

- **Charts `#c-cad`, `#c-stride`:** one dot per run and the yearly median, side by side. They are two separate charts rather than one chart with two y axes.
- **Year table:** "Cadence" (steps/min) and "Stride" (m) yearly medians.
- Cadence values of 100 or below are ignored (a few old devices report strides per minute, half the step count).
- Both follow the month and trail filters. Faster runs have both a higher cadence and a longer stride, so years with more fast sessions show higher medians. Compare years with a similar mix.

## Training Effect

Garmin's estimate of how much each run improved your aerobic base (`te`) and your anaerobic capacity (`teAn`), on a 0–5 scale (0 = none, 2 = maintaining, 3 = improving, 4 = highly improving, 5 = overreaching).

- **Chart `#c-te`:** both scores per run, plus a yearly median line for each, on one 0–5 axis.
- A typical balanced pattern is most runs at 2–3.5 aerobic with a few anaerobic peaks above 2 from interval sessions. A year where nearly every run is aerobic 4+ suggests too much hard running.
- Garmin's algorithm uses your watch's heart-rate settings and has changed between device generations, so steps between watch models are possible.

Each panel is hidden when no run has the value.
