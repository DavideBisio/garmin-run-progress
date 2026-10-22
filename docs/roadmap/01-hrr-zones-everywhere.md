# 01 · Heart-rate reserve zones everywhere

## Requirements

- **One zone model** for the whole project: Karvonen, as a share of heart-rate reserve (HRR = max − rest).

  | Zone | % HRR | Example, max 190 / rest 50 |
  |---|---|---|
  | Z1 | 50–60 % (and anything below 50 %) | < 134 bpm |
  | Z2 | 60–70 % | 134–148 bpm |
  | Z3 | 70–80 % | 148–162 bpm |
  | Z4 | 80–90 % | 162–176 bpm |
  | Z5 | 90 %+ | ≥ 176 bpm |

  Ranges are half-open: a bound bpm belongs to the upper zone (148 bpm is Z3).

- The page's **zones chart** switches from % of max HR to % of HRR. Load (TRIMP) already uses HRR, so the page becomes consistent with itself.
- **"Easy" means Z1–Z2**, below 70 % of HRR, which is close to the first ventilatory threshold. The KPI "Easy share, 12 weeks" and its text change to match. Today it says "below 80% of max HR".
- The zones legend shows **live bpm ranges** from the current max and resting HR, such as `Z2 134–148`, not only percentages.
- **Runs without an HR stream** fall back to Garmin's own zone times (`hrz`), which can't be converted. The page:
  - says how many runs in the window use the fallback;
  - recommends setting Garmin Connect's HR zones to the HRR basis with the same max and resting HR, so all three sources agree.
- The planner (03), the planner's checks (07) and the Planning view (10) use the same definition, from this section.

## Implementation

- **`src/page/js/metrics.js`:**
  - add `const HRR_ZONES = [.6, .7, .8, .9];` (upper bounds of Z1–Z4) and `hrrZones(max, rest)`, which returns rounded bpm boundaries;
  - `zoneTime(r, max, rest)` classifies each sample's bpm against the rounded bounds from `hrrZones` (`hr < b[0]` → Z1, `hr < b[1]` → Z2, …), so it agrees with the legend to the bpm;
  - this is the single definition. The Python `hr_zones` in 03 must match it, rounding half up (`floor(x + 0.5)`, not Python's `round()`), and the parity vectors in 03 cover it.
- **`training.js`:**
  - pass `rest` to `zoneTime`; the clamp `rest ≤ max − 20` moves into `hrrZones`;
  - easy share becomes `(zt[0] + zt[1]) / zSum`;
  - the KPI text reads `of running time below 70% of heart-rate reserve (< 148 bpm)`;
  - the fallback count goes under the chart.
- **`index.html`:** the static `%max` legend becomes `<div class="legend" id="zones-legend">`, filled by `training.js` on each render.
- **Docs:**
  - `docs/features/training-load-zones-consistency.md`: the zone table, the easy definition and a "Garmin Connect zones" note;
  - the "How to read this" panel;
  - the `metrics.js` row in `docs/architecture.md`.

No layout change. The legend contents change:

```text
Heart-rate zones per week
Minutes in each zone, as a share of your heart-rate reserve (max − resting). Zones 1–2 count as easy.
■ Z1 <134  ■ Z2 134–148  ■ Z3 148–162  ■ Z4 162–176  ■ Z5 176+ bpm
12 runs without a usable heart-rate stream use Garmin's zones: set Garmin Connect to HRR zones to match.
```

## Testing strategy

- **Node unit tests on `zoneTime`:** with max 190 and rest 50, samples at 133, 134, 147, 148, 175, 176 and 200 bpm, and one below rest, land in the expected zones. Tolerance is to the bpm.
- **Legend:** `hrrZones(190, 50)` returns `[134, 148, 162, 176]`. The legend text follows a change of the max or resting input.
- **Existing page tests still pass:**
  - the example data renders the zones chart and an easy-share KPI between 0 and 100;
  - an old `runs.json` without `rhr` falls back to the 50 bpm placeholder.
- **Fallback:** a dataset with `hrz` only shows the "use Garmin's zones" count line.

## Completion checklist

- [x] Write down that everyone's easy-share number changes, in the release notes and the feature doc. For a resting HR around 50, Z1–2 under HRR is about 77 % of max, versus 80 % before, so easy share drops slightly.
- [x] Boundaries are rounded to whole bpm **once**, in `hrrZones`. The classification compares against the same rounded values, so the legend, the chart and the planner never disagree by 1 bpm.
- [x] Resting HR now moves the zone boundaries. The hint under the max and resting HR inputs says so.
- [ ] Find the Garmin Connect setting that switches zones to HRR (Heart Rate Zones → "Based on: %HRR") in the current app, and put the exact path in the doc.
- [x] Search for "of max" and "max HR" across `src/page` and `docs` to leave no stale %max wording.
