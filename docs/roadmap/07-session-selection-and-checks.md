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

- [x] Caps apply to the **hard portion** only (reps), never to warmup, cooldown or recoveries.
- [x] The low-volume "smallest variant anyway" rule doesn't make the fixer loop forever. It's a known exception, not a violation.
- [x] With less than 28 days of history, the ACWR check is skipped with a note, not failed.
- [x] The 80/20 easy-time check counts Z1–2 as easy, the same definition as the page's Easy share KPI (01).
- [x] Each warning in `plan.md` says which rule fired and what the planner did about it.

## Shipped

`python -m garmin_plan plan` generates the plan (#10): `select.py`, `size.py`, `terrain.py`, `load.py`, `checks.py`, `fix.py` and `planner.py`, with `[caps]`, `[rotation.*]`, `[checks]`, `[fix]`, `[feasibility]` and `[volume] taper` in `rules.toml` and a new `strides` template. Documented in [plan generator](../features/plan-generator.md); tested by `tests/test_sessions.py`, `tests/test_checks.py` and `tests/test_planner.py` with the golden plan `tests/fixtures/plan_golden.md`. Differences from the plan above:

- Signatures: `rotation(phase, block_week, slot, rules, *, deload, hill_day, level, library)`; `pick_variant(template, slot_km, week_km, caps, profile, rules, *, lighter, slot_s) -> (variant, forced)`; `check_week(days, rules, *, e_min, hr_max, hr_rest, prev_km, prev_days, daily, end, exempt) -> (violations, notes)`; `fix_week(build, check, rules)`, where `build(adjust)` lays the week out again (so shrinking Q re-splits the week) and the fixer only sees `Adjust(q_down, trim_l_km, drop_f)`; `build_plan(profile, runs, library, rules, today, weeks)`.
- Q comes first: it is sized from its cap and the slot budget (the week minus L and each E slot at the E minimum), and its km go into the split; the split's leftover becomes a longer warm-up, or a longer first easy step without one (the progression run). E and L are fitted to the split's km with `instantiate` overrides; hill and trail swaps keep the long run's time budget.
- The ACWR check is skipped for the whole plan, with one warning, when `runs.json` holds under 28 days; otherwise the planned weeks extend the real history up to today.
- Each fix applies only to the checks it can help: shrinking Q keeps the week's km, so it fixes the easy share and the load ratio but not a volume rise; nothing fixes hard days or a low ratio, which stays a warning. A trimmed week's `target_km` is what is left.
- Hilly and trail long runs are Z2–3 or under a Z3 cap, so not easy by the Z1–2 definition: a long-run swap that would take the week under 80 % easy is left out with a `hill_swap` warning. At ordinary volumes that is every time; the swap stands only in weeks big enough to hold it.
- The plan starts on the Monday after today (no partial week); the 2 taper weeks are 0.7 and 0.5 of the last build week, and the race week has no session from race day on. `--weeks` only shortens a plan to a race; without one the default is 8 weeks.
- Levels: until 08 everyone is intermediate, falling back down a rotation list to lower `min_level` templates.
