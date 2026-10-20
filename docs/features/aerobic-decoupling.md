# Aerobic decoupling

How much your pace per heartbeat falls from the first half of a steady run to the second half (Friel's Pa:HR). Under 5% means your aerobic endurance holds at that duration. It complements [pace at heart rate](pace-at-heart-rate.md): that one measures fitness at a given effort, this one measures how long you can sustain it. Function: `decoupling(run)`, called once per run in `prepare`.

## Algorithm

```text
skip run if no grade data or fewer than 60% of samples have heart rate
segments = consecutive sample pairs (i-1, i) where
    t[i] >= 600                      # after a 10-minute warm-up
    0 < dt <= 30                     # no pauses
    hr[i] > 0
    1.6 <= dd/dt <= 6.5 m/s          # running, no GPS spikes
    keep (dt, dd * gapFactor(grade[i]), hr[i] * dt)
skip if total segment time < 40 min

# steady runs only
split segments into 5-minute blocks of grade-adjusted speed
skip if stdev(blocks) / mean(blocks) > 10%      # intervals, fartlek, races with surges

split segments at half the total time
EF = grade-adjusted distance / heartbeats       # for each half
decoupling = (EF1 - EF2) / EF1 * 100            # %
```

The same filters as `bandPace` are used, so both metrics see the same clean running. Grade adjustment uses the [Minetti factor](grade-adjusted-pace.md), so a hilly second half isn't mistaken for fatigue.

Result: `run._dec` (percent) and `run._decMin` (qualifying minutes), or `_dec = null`.

## Output

- **Chart `#c-dec`:** one dot per qualifying run, the yearly median, and a dashed line at 5%. The y axis is fixed to −10…25% and outliers are clamped to it.
- **KPI "Aerobic decoupling":** median of the last 12 months (up to the last run), compared with the 12 months before that. Green chip when it fell.
- **Year table "Decoupling":** yearly median, shown only with at least 3 qualifying runs.

All three follow the month and trail filters.

## Reading it

- A negative value means your efficiency improved in the second half. That's common when the first half includes an uphill start or when heart rate settles late.
- Heat and dehydration raise decoupling a lot. Use the month filter to compare the same season.
- Longer runs decouple more. A drop over the years at similar long-run durations is the signal; a drop because your runs got shorter is not.
