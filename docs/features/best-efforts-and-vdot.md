# Best efforts and VDOT

Finds your fastest 1 km, 5 km, 10 km and half marathon inside every run, then converts them to VDOT so different distances and years compare on one scale. Functions: `bestEffort`, `vdot`, `DISTS`.

## Fastest window

For a target distance `D`, find the shortest time over any stretch of exactly `D` metres in the run. Two pointers over the cumulative distance `d` and time `t`:

```text
i = 0
for j in 1..n-1:
    skip until d[j] - d[0] >= D
    advance i while d[j] - d[i+1] >= D        # start lies between i and i+1
    target = d[j] - D
    t_start = t[i] + (t[i+1]-t[i]) * (target - d[i]) / (d[i+1] - d[i])   # interpolate
    best = min(best, t[j] - t_start)
reject if D/best > 6.4 m/s                   # faster than 2:36/km = GPS glitch
```

Interpolating the start point matters with 10-second samples: without it a 1 km effort could be off by up to 10 s (3%). With it the error is limited to the end sample and is typically under a second.

Elapsed time is used, so a pause inside a window makes it slower, never faster.

Computed once per run in `prepare` and stored in `run._best = {"1k", "5k", "10k", "hm"}`.

## VDOT

Jack Daniels' VDOT expresses a performance as the VO2max that would produce it. For distance `m` (metres) in time `t` (minutes), with velocity `v = m/t` (m/min):

```text
VO2   = −4.60 + 0.182258·v + 0.000104·v²
%max  = 0.8 + 0.1894393·e^(−0.012778·t) + 0.2989558·e^(−0.1932605·t)
VDOT  = VO2 / %max
```

A 20:00 5 km and a 41:30 10 km both come out at about VDOT 49.8, so they count as equivalent performances.

## Aggregation

Per year (after filters), the best time for each distance is kept, then converted to VDOT. The chart shows 5 km, 10 km and half lines. The table shows the four best times and the year's maximum VDOT over 5 km, 10 km and half. 1 km is left out of the max because short efforts overstate VDOT for most endurance runners.

## Interpreting

- Efforts come from **any** run, so a year without races shows the best training stretch, which understates fitness. Years with races give the most honest points.
- A higher 10 km VDOT than 5 km VDOT in the same year usually means the 5 km was never raced, not that you're better at 10 km.
- Not grade-adjusted: a downhill course flatters the result.
