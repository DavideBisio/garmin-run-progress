# Pace at a fixed heart rate

The page's main fitness signal: how fast you run, adjusted for hills, while your heart rate is inside a chosen band. As aerobic fitness improves, the same heart rate produces a faster pace. Function: `bandPace(run, lo, hi)`.

## Algorithm

```text
skip run if no grade data or fewer than 60% of samples have heart rate
for each consecutive pair of samples (i-1, i):
    skip if t[i] < 600                 # first 10 minutes: HR still rising
    dt = t[i]-t[i-1]; dd = d[i]-d[i-1]
    skip if dt <= 0 or dt > 30         # pause / auto-pause gap
    v = dd/dt
    skip if v < 1.6 or v > 6.5 m/s     # walking/standing or GPS glitch
    skip if hr[i] outside [lo, hi]
    time     += dt
    adjDist  += dd * gapFactor(grade[i])
return time/adjDist*1000  (s/km)    if time >= 600 s, else null
```

### Why these thresholds

| Rule | Reason |
|---|---|
| Skip first 10 min | Heart rate lags effort at the start (cardiac drift goes the other way later, but that is part of fitness) |
| Gaps > 30 s | Traffic lights and auto-pause would otherwise add zero-distance time |
| 1.6–6.5 m/s | 10:25/km to 2:34/km: excludes walking breaks and GPS spikes |
| ≥ 10 min in band | Fewer qualifying minutes give a noisy number |

Each qualifying run yields one point. Intervals and races mostly sit above an easy band, so they contribute little or nothing automatically; no workout classification is needed.

## Choosing the band

Pick a 10 bpm band you spend a lot of time in on easy runs. The page suggests one from your data ([data loading](data-loading-and-storage.md#heart-rate-band-suggestion)). Changing the band re-runs `bandPace` for every run, which is fast (a few milliseconds per 1,000 runs).

If your max or resting heart rate changed a lot over the decade, an absolute band compares slightly different intensities across years. A narrower band near your aerobic threshold is the most stable choice.

## Output

- **Chart:** one dot per run (decimal-year x, pace y, axis reversed so faster is higher), plus the yearly median line at mid-year.
- **Year table:** "Pace @ lo–hi" column = yearly median, only for years with at least 5 qualifying runs. Best year highlighted.
- **KPIs:** first vs last year median, and the trend (see [yearly-trends](yearly-trends.md)).

## Confounders

- **Heat** raises heart rate at the same pace. Use the month filter to compare the same season.
- **Sensor:** chest-strap data is reliable; optical wrist data can lock onto cadence and produce false readings.
- **Fatigue and altitude** also shift heart rate; yearly medians absorb most of this.
