# 07 · Session selection, sizing and safety checks

## Requirements

- **Choosing workouts:**
  - Each phase has a rotation for each slot type, lined up with the 4-week block.
  - Example: Q alternates A (R work) and B (T or I), with a lighter B in the deload week. L goes steady → progression → longest → short and easy.
  - This replaces the hand-written 2-week Q cycle and 3-week L cycle, which only realigned every 6 weeks.
- **Sizing:**
  - Pick the **largest ladder variant** whose hard km fits under its cap and whose total fits the slot's km.
  - Caps on the hard portion, as a share of the week:

    | Type | Cap |
    |---|---|
    | R | 5 % (max 8 km) |
    | I | 8 % (max 10 km) |
    | T | 10 % |
    | M | 20 % |

  - If even the smallest variant is over the cap (low volume), use the smallest one anyway and record it.
- **Progression within a phase:** more reps, then longer reps, then shorter recoveries. The ladder order encodes this. Paces change only after a new VDOT estimate.
- **Hill and trail swaps:**
  - Hilly long runs and trail runs can replace L at the same time budget.
  - Short hill repeats can replace Q-A.
  - Weekly volume counts these as flat-equivalent km, using Minetti, which the page already uses.
- **Checks on every generated week:**
  - at least 80 % of time is easy (Z1–2);
  - at most 2 hard sessions, never on consecutive days;
  - week-on-week volume rises by at most 10 %, deloads excepted;
  - the projected 7:28-day load ratio stays within 0.8–1.3 (TRIMP);
  - L stays within its share cap.
- **Auto-fix order:** shrink the Q variant, then trim L, then drop F. Anything still failing becomes a warning in `plan.md`.
- **Goal feasibility:** compare goal VDOT with current VDOT against the weeks available, at about 1 point per 4–6 weeks. The planner warns; it never prescribes faster paces.

## Implementation

```text
src/garmin_plan/
  select.py   rotation(phase, block_week, slot, rules) -> template id
  size.py     pick_variant(template, slot_km, week_km, caps) -> variant index
  terrain.py  flat_equivalent_km(km, climb_m, descent_m)       # Minetti, from metrics.py
  checks.py   check_week(week, history) -> [Violation(code, detail)]
  fix.py      fix_week(week) -> week, [unfixed]   # bounded loop, deterministic
  planner.py  build_plan(profile, history, today) -> Plan   (06 + 07 wired together)
```

- **Projected TRIMP:** for each step, duration × the midpoint HR of its zone, through the ported `trimp`. The ACWR window joins the real history and the planned weeks.
- **Hill and trail templates** carry `climb_m_per_km`, and time-based reps carry an assumed pace, so their volume can be counted.
- **CLI:** `python -m garmin_plan plan` now uses the generator. The manual `[week]` table from 04 overrides it for any day it lists.

No GUI in this section.

## Testing strategy

- **Sizing tables** at 15, 25, 40 and 60 km/week for R, I, T and M. Expected variants are written out by hand in the test.
- **Rotation:** 12 weeks across 3 blocks give the expected Q and L sequence, with the lighter variants in deload weeks.
- **Checks:** one hand-built failing week per violation code, and one passing week.
- **Fixer:**
  - it converges;
  - it is deterministic;
  - it stops after N iterations with a warning when a week can't be fixed.
- **Golden plan:** 16 weeks to a half marathon for a generic profile, stored as `plan.md`. Checked by eye once, then snapshot-tested.
- **Feasibility:** goal gaps of 0, 2 and 6 VDOT points over 8 and 20 weeks give the expected warning or none.

## Completion checklist

- [ ] Caps apply to the **hard portion** only (reps), never to warmup, cooldown or recoveries.
- [ ] The low-volume "smallest variant anyway" rule doesn't make the fixer loop forever. It's a known exception, not a violation.
- [ ] With less than 28 days of history, the ACWR check is skipped with a note, not failed.
- [ ] The 80/20 easy-time check counts Z1–2 as easy, the same definition as the page's Easy share KPI (01).
- [ ] Each warning in `plan.md` says which rule fired and what the planner did about it.
