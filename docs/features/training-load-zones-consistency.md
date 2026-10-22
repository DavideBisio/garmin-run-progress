# Training: load, heart-rate zones and consistency

The "Training" group at the bottom of the Analysis tab shows how hard and how regularly you're training. Function: `renderTraining(c)`, called at the end of `render`.

## Scope

- The **52 weeks** (Monday to Sunday) up to the week of the **last run** in the data, not today, so an old export still shows its final year.
- **Every run.** The month and trail filters don't apply: removing summer or trail runs would make load and streaks look lower than they were.
- Only runs. The grabber doesn't download other sports, so cycling or gym load isn't counted.

Weeks are indexed with `weekOf(day) = floor((day + 3) / 7)`, where `day` is days since 1970-01-01 (a Thursday), which puts week boundaries on Mondays.

## Max and resting heart rate

Two inputs (`#hr-max`, `#hr-rest`) in the Data tab's "Your heart rate" step drive the zones and the load. `suggestLimits` fills them on every load:

| Input | Default |
|---|---|
| Max HR | Second-highest per-run peak. The peak is the 99th percentile of the run's heart-rate stream (ignores optical spikes); runs without a stream use Garmin's `maxHr`. Falls back to 190. |
| Resting HR | Median of the last 365 days of [resting heart rate](resting-heart-rate.md). Falls back to 50. |

The hint under the inputs says where each value came from and that both move the zone boundaries; below it, `#zones-preview` shows the same bpm ranges as the zones chart legend. Changing either re-renders. In the Training group, `#hr-link` repeats the two values and links to the Data tab. A wrong max or resting heart rate shifts every zone, so a lab or field-test value is better than the estimate.

## Training load (TRIMP)

Banister's TRIMP, per run:

```text
HRr   = clamp((hr - rest) / (max - rest), 0, 1)
TRIMP = Σ over samples  dt/60 × HRr × 0.64 × e^(1.92 × HRr)
```

- Runs with a heart-rate stream sum over sample pairs with `0 < dt <= 30` (pauses excluded).
- Runs without a stream (treadmill) use `moving` (or `dur`) and `avgHr`.
- Runs without any heart rate add 0, which understates load.
- 1.92 is Banister's coefficient for men; the one for women is 1.67. The difference mostly scales all values and barely changes the ratio below.

**Chart `#c-load`:** total TRIMP per week.

## Load ratio (acute:chronic)

```text
acute   = load of the last 7 days
chronic = load of the last 28 days / 4          # average week
ratio   = acute / chronic                       # null in the first 28 days of data
```

Evaluated at the end of each week (or the last run day for the current week).

| Ratio | Meaning |
|---|---|
| < 0.8 | Easing off or detraining |
| 0.8–1.3 | Usual safe range |
| 1.3–1.5 | Ramping up fast |
| > 1.5 | Common injury warning sign |

After a break of several weeks the ratio jumps on the first runs back, because the chronic load is near zero. That's the intended warning: build back up gradually.

**Chart `#c-acwr`:** weekly ratio with dashed lines at 0.8 and 1.3. **KPI:** ratio at the last run, with the range named in the chip.

## Heart-rate zones

One zone model for the whole project: Karvonen, as a share of heart-rate reserve (HRR = max − rest). `HRR_ZONES = [.6, .7, .8, .9]` in `metrics.js` holds the upper bounds of Z1–Z4, and `hrrZones(max, rest)` turns them into whole bpm:

```text
rest   = min(rest, max - 20)                    # clamp, defined only here
bounds = round(rest + p × (max - rest))  for p in HRR_ZONES   # rounded half up, once
```

| Zone | % HRR | Example, max 190 / rest 50 |
|---|---|---|
| Z1 | below 60% | < 134 bpm |
| Z2 | 60–70% | 134–148 bpm |
| Z3 | 70–80% | 148–162 bpm |
| Z4 | 80–90% | 162–176 bpm |
| Z5 | 90%+ | 176+ bpm |

Ranges are half-open: the upper number of each range belongs to the next zone.

`zoneTime(run, max, rest)` returns seconds in the five zones. It compares each sample's bpm with the **rounded** bounds from `hrrZones` (`hr < b[0]` → Z1, `hr < b[1]` → Z2, …), so a bound belongs to the upper zone: 134 bpm is Z2, 148 is Z3. Because the bounds are rounded once and both the legend and the classification use them, the chart, the legend and the KPI never disagree by 1 bpm. The Python port in the planner (roadmap 03) must round the same way, half up (`floor(x + 0.5)`), not with Python's `round()`, which rounds half to even.

Runs with a stream count each sample pair with `0 < dt <= 30`. Runs without a usable stream fall back to Garmin's `hrTimeInZone_1…5` (runs.json `hrz`), which use the zones set in Garmin Connect and can't be converted.

- **Chart `#c-zones`:** stacked minutes per zone per week, one teal ramp (`--z1`…`--z5`) going from light (Z1) to dark (Z5), dim to bright in the dark theme. The tooltip names each zone's bpm range.
- **Legend `#zones-legend`:** filled on each render from `hrrZones` with the current inputs, e.g. `Z1 <134  Z2 134–148  Z3 148–162  Z4 162–176  Z5 176+ bpm` (the shared number is the bound, which belongs to the upper zone).
- **Fallback line `#zones-fallback`:** under the chart, shown when any run in the chart's 52-week window has no usable heart-rate stream (`!r._hrOk && Array.isArray(r.hrz)`): "N runs without a usable heart-rate stream use Garmin's zones: set Garmin Connect to HRR zones to match."
- **KPI "Easy share, 12 weeks":** share of time in Z1–Z2, below 70% of HRR (close to the first ventilatory threshold); the text shows the bound, e.g. "< 148 bpm". The 80/20 guideline is about 80% easy; the chip turns green at 75%.

Easy share changed with the switch from % of max HR (Z1–Z3, below 80% of max) to HRR: with a resting heart rate around 50, Z1–Z2 under HRR ends at about 77% of max, so everyone's easy share drops slightly.

### Garmin Connect zones

To make Garmin's own zone times (`hrz`) match the page, set Garmin Connect's heart-rate zones to the HRR basis with the same max and resting heart rate:

- Garmin Connect phone app: menu > Settings > User Settings > Heart Rate Zones > Based On: %HRR;
- or on the watch: User Profile > Heart Rate Zones > Zones > Based On > %HRR.

Labels vary by app version and device. Only runs synced after the change use the new zones.

## Consistency

| Output | Computation |
|---|---|
| Chart `#c-week` | Weekly km stacked as the week's longest run + all other runs |
| KPI "Runs per week, 12 weeks" | Runs in the last 12 weeks / 12, with average km |
| KPI "Weekly streak" | Consecutive weeks with at least one run, counted back from the last run's week; plus the longest streak ever |
| KPI "Long-run share, 12 weeks" | Median over weeks with a run of longest run ÷ weekly km |

**Consistency table (`#tbl2`)**, one row per calendar year, using only the days covered by the data (so a partial first or last year isn't diluted):

| Column | Computation |
|---|---|
| Runs/week | Runs ÷ (covered days / 7) |
| Weeks with a run | Weeks with at least one run ÷ weeks covered |
| Breaks of 7+ days | Gaps of 7 or more days without a run, counted in the year the break ends |
| Longest break | Longest gap in days ending that year |
| Long-run share | Median weekly long-run share |

A long-run share above 50% is normal with two runs a week; with four or more, values above about 35% mean the long run carries a lot of the week.
