# 06 · Weekly skeleton and volume curve

## Requirements

- **Slot placement:**
  - Each available day gets one slot: **L** (long), **Q** (quality), **E** (easy) or **F** (flex, the first slot dropped when volume is short). The remaining days are rest.
  - L goes on the preferred day.
  - Q goes as far from L as possible: at least 48 h away in both directions, and never on the day after L.
  - No two hard days are back to back.
- **Volume curve:**
  - The start is the 4-week average from `runs.json`.
  - Blocks have 4 weeks: ×1.00, ×1.08, ×1.16, then a deload at ×0.85.
  - The next block starts from the previous block's week 2, which is +8 % per block (week 1 of the first block is the start volume itself). The ramp, the deload and the deload period are configurable.
- **Phases:**
  - Counted back from the race date: Base (E + strides/hills), then R + T, then I + T, then T + M, then a 2-week taper.
  - With no race, the planner cycles Base and R + T.
  - If the weeks are too few, it warns and shortens phases in a fixed order rather than compressing the ramp.
- **Splitting a week's km across slots:**
  - L = min(L share cap × week, longest recent run + 2 km, time cap);
  - Q comes from the template size (sizing is in 07; until then, the smallest variant);
  - E gets the remainder, each E run between 5 km (or 30 min) and the length of L;
  - F switches on when E slots would run over L, and off when they would fall below the minimum.
  - **The caps win over E ≤ L.** L never goes over its caps, except up to the E minimum: a long run shorter than that isn't worth putting on. Excess km go to F if it's available. Otherwise the E runs end up longer than L, and the split returns a warning.
  - **Q is dropped when the week can't hold it.** If the week is too small for Q plus an L at the E minimum, Q is dropped with a warning and its day becomes an easy day (rest if nothing is left for it). No part is ever negative.
  - **Leftover km.** A remainder too small for any easy run is first taken from L, if L can give it and still stay at the E minimum. Otherwise it goes to Q as a longer warm-up and cool-down. With no Q, it becomes one short easy run, with a warning. It never goes to L, so a deload week doesn't get the block's longest L.
- The result is the week and slot structure of `plan.json`, with a km target for each slot.

## Implementation

```text
src/garmin_plan/
  skeleton.py  place_slots(available_days, long_day, rules) -> {weekday: slot}
  volume.py    block_curve(start, weeks, ramp, deload, deload_every, floor) -> [target]
               align_deloads(weeks, deload_every, phase_starts) -> [deload week index]
  phases.py    phase_calendar(today, race_date, distance_m, rules) -> ([(week_start, phase, partial)], warnings)
  split.py     split_week(target, slots, longest_km, q_km, rules, e_pace) -> ({weekday: km}, warnings)
  data/rules.toml  caps, ramp, deload, phase lengths per race distance, E minimum
```

- **Placement is brute force:** at most 4⁷ assignments. A score function adds hard constraints (infinite penalty) and soft preferences (Q–L distance, E spread). Ties break in a fixed day order, so a re-plan doesn't shuffle days.
- **Volume units** stay abstract (`km` or `min`) in `volume.py`, ready for the minute-based beginner plans in 08.
- A plan can start on any weekday. Its first week is partial and isn't counted for the ramp.

Example result for a generic profile (Tue/Wed/Thu/Sat/Sun available, long run on Sunday, 16 km starting volume, longest recent run 8 km, VDOT 40, a 5 km Q):

```text
| Mon  | Tue | Wed | Thu | Fri  | Sat | Sun |
| rest | E   | F   | Q   | rest | E   | L   |

Wk  Phase  km    Q    E (Tue)  E (Sat)  F   L
1   base   16.0  5.0  4.9      –        –   6.1
2   base   17.3  5.0  4.9      –        –   7.4
3   base   18.6  5.0  5.2      –        –   8.4
4   base   13.6  7.5  –        –        –   6.1   (deload)
```

Week 1 is the start volume, then ×1.08, ×1.16 and the ×0.85 deload. E pace at VDOT 40 is about 6:11/km, so the E minimum is 30 min (4.9 km), shorter than 5 km. At this volume only one easy run fits, and L gives up km so that run reaches the minimum (weeks 1–3). In the deload week L is at its 45 % cap (6.1 km), and the remaining 2.5 km are too few for an easy run, so they go to Q as a longer warm-up and cool-down. F stays off until the easy runs would be longer than L.

No GUI in this section.

## Testing strategy

- **Table-driven placement tests** for 2-, 3-, 4-, 5- and 6-day availabilities and a weekend-only runner. Impossible sets fail with an error that names the broken rule.
- **Property tests** over every 3–6-day subset of the week:
  - Q is never the day after L;
  - Q and L are always at least 48 h apart;
  - there are never back-to-back hard days;
  - the result is deterministic.
- **Volume curve:** exact numbers for 3 blocks; the ramp and deload settings take effect.
- **Phases:** race in 6, 12, 20 and 30 weeks; no race; race distances 5K, 10K, HM and M.
- **Split invariants:**
  - the parts add up to the target within ±0.5 km;
  - the E minimum is respected;
  - F switches on at the expected volume;
  - the L cap binds at low volume;
  - from 2 km up, no part is negative, L stays within its caps (and at the E minimum or more whenever the week allows it), and Q is dropped exactly when the week can't hold it.

## Completion checklist

- [x] The low-frequency L cap of 45 % (Daniels says 25–30 %) is a setting with a comment explaining why. Without it, a 3-runs-a-week plan gets a tiny long run.
- [x] Deloads line up with phase boundaries where possible, so a phase doesn't start with a lighter week.
- [x] A starting volume near 0, after a break, is clamped to a floor here; 08 handles detraining properly.
- [x] A "Sat/Sun" long run uses the preferred day, with the other weekend day as a fallback, and moving it doesn't break the 48 h rule.
- [x] Phase lengths per race distance are written down together with their source, in `rules.toml`.
