# Training: load, heart-rate zones and consistency

The "Training" group at the bottom of the analysis shows how hard and how regularly you're training. Function: `renderTraining(c)`, called at the end of `render`.

## Scope

- The **52 weeks** (Monday to Sunday) up to the week of the **last run** in the data, not today, so an old export still shows its final year.
- **Every run.** The month and trail filters don't apply: removing summer or trail runs would make load and streaks look lower than they were.
- Only runs. The grabber doesn't download other sports, so cycling or gym load isn't counted.

Weeks are indexed with `weekOf(day) = floor((day + 3) / 7)`, where `day` is days since 1970-01-01 (a Thursday), which puts week boundaries on Mondays.

## Max and resting heart rate

Two inputs (`#hr-max`, `#hr-rest`) drive the zones and the load. `suggestLimits` fills them on every load:

| Input | Default |
|---|---|
| Max HR | Second-highest per-run peak. The peak is the 99th percentile of the run's heart-rate stream (ignores optical spikes); runs without a stream use Garmin's `maxHr`. Falls back to 190. |
| Resting HR | Median of the last 365 days of [resting heart rate](resting-heart-rate.md). Falls back to 50. |

The hint under the inputs says where each value came from. Changing either re-renders. A wrong max shifts every zone, so a lab or field-test value is better than the estimate.

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

`zoneTime(run, max)` returns seconds in five zones, by share of max HR:

| Zone | Share of max HR |
|---|---|
| Z1 | < 60% |
| Z2 | 60–70% |
| Z3 | 70–80% |
| Z4 | 80–90% |
| Z5 | ≥ 90% |

Runs with a stream count each sample pair with `0 < dt <= 30`. Runs without one fall back to Garmin's `hrTimeInZone_1…5` (runs.json `hrz`), which use the zones set in Garmin Connect, not the max HR above.

- **Chart `#c-zones`:** stacked minutes per zone per week, one teal ramp (`--z1`…`--z5`) going from light (Z1) to dark (Z5), dim to bright in the dark theme.
- **KPI "Easy share, 12 weeks":** share of time in Z1–Z3 (below 80% of max, roughly the first ventilatory threshold). The 80/20 guideline is about 80% easy; the chip turns green at 75%.

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
