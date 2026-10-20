# Yearly aggregates, trend and display

Everything below happens in `render()`, which runs on load and whenever a control or the colour theme changes.

## Filters

| Control | Effect |
|---|---|
| Heart-rate band (`#hr-lo`, `#hr-hi`) | Passed to `bandPace`; swapped if entered in the wrong order |
| Months (`#season`) | Keep runs whose month is in the set: spring, summer, autumn, winter, or "all but summer heat" (Jun–Aug excluded) |
| Exclude trail runs (`#no-trail`) | Drop runs whose `type` contains `trail` (default on) |

Filters apply to every metric, chart and table above the Training group, except resting heart rate. The [Training group](training-load-zones-consistency.md) always uses every run.

## Per-year aggregation

For each filtered run, grouped by calendar year:

| Field | Computation |
|---|---|
| `n`, `km` | Count, sum of `_km` |
| `eff` | All `bandPace` results; `effMed` = median if at least 5 values, else null |
| `best[k]` | Minimum `_best[k]` for 1k, 5k, 10k, hm |
| `vdot[k]` | `vdot(distance, best[k])` |
| `vdotMax` | Max of 5k/10k/hm VDOT |
| `vo2Med` | Median of Garmin `vo2` values |
| `decMed` | Median of [`_dec`](aerobic-decoupling.md) if at least 3 values |
| `cadMed`, `strideMed` | Medians of `cad` (> 100) and `stride` (in m) |
| `rhrMed` | Median [resting heart rate](resting-heart-rate.md) of the calendar year (not filtered) |

## Trend (Theil–Sen)

The headline "Trend at lo–hi bpm" is the Theil–Sen slope of `(year, effMed)` over years that have an `effMed`:

```text
slopes = [(y_j - y_i) / (x_j - x_i) for every pair i < j]
trend  = median(slopes)          # s/km per year; negative = faster
```

Theil–Sen is used instead of least squares because it ignores outlier years (an injury year, a year of mostly hill running). It tolerates about 29% outliers. With 10 years there are only 45 pairs, so it's instant.

## KPI cards

1. **Trend at band:** Theil–Sen slope with "getting faster/slower".
2. **Pace at same HR:** first year → last year median, with the difference in seconds (green chip when faster).
3. **Best-effort VDOT:** first year → last year `vdotMax`, plus the peak year.
4. **Volume:** total km, runs, years.
5. **Aerobic decoupling:** median of the last 12 months vs the 12 months before.
6. **Resting heart rate:** last 30 days vs a year earlier (only with resting HR data).

## Charts

Chart.js 4.4.1 (UMD build from cdnjs). Each chart is destroyed and recreated on render; with `animation: false` this is cheap.

| Canvas | Type | Data |
|---|---|---|
| `#c-eff` | scatter + line | Per-run band pace at decimal year; yearly median at `year + 0.5`; y reversed, `m:ss` ticks |
| `#c-vdot` | line | Yearly VDOT for 5 km, 10 km, half; `spanGaps` bridges missing years; tooltip shows the time |
| `#c-vol` | bar | km per year |
| `#c-vo2` | scatter + line | Garmin VO2max per run and yearly median; panel hidden if there is no VO2max data |
| `#c-rhr` | scatter + line | [Resting heart rate](resting-heart-rate.md) per day and 30-day median |
| `#c-dec` | scatter + line | [Aerobic decoupling](aerobic-decoupling.md) per run, yearly median, 5% line |
| `#c-cad`, `#c-stride`, `#c-te` | scatter + line | [Cadence, stride, Training Effect](form-and-training-effect.md) |

Time axes use a linear scale on decimal years with integer ticks, which avoids loading a date adapter.

### Theming

Colours are CSS custom properties (`--accent`, `--accent-2`, `--accent-3`, `--ink`, `--muted`, `--line`, `--surface`, and `--z1`…`--z5` for heart-rate zones) with light and dark values. `render` reads them with `getComputedStyle` each time, so charts match the theme. A `matchMedia("(prefers-color-scheme: dark)")` listener and a `MutationObserver` on the root `data-theme` attribute trigger a re-render when the theme changes.

## Year table

Newest year first. Columns: year, runs, km, pace at band, best 1 km / 5 km / 10 km / half, VDOT, Garmin VO2max, decoupling, cadence, stride, resting HR. The best value in the pace, 5 km, 10 km and VDOT columns is highlighted. The table scrolls horizontally on narrow screens.
