"""plan.json "progress": what one plan carries to the next (roadmap 08, docs/plan-json-format.md).

Every plan starts on the Monday after today, so a re-plan restarts its weeks. progress keeps what
that must not reset: the block the first week is in (levels move at a block's start only, and the
deloads stay where they were), the run/walk stage reached, the time trials run and the one still
to come. carry(plan, monday) reads it from the last plan.json for a plan from `monday`;
planner.build_plan writes the new plan's. A plan without it (from before, or none) carries what
its weeks say: its first week starts a block, the ladder starts over, no time trial is recorded.
"""
from datetime import date


def _date(v):
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def _stage(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def carry(plan, monday):
    """Where a plan from `monday` stands after `plan` (the last plan.json dict), or None without a
    generated plan (none, or one of the [week] schedule alone, which has no levels):

    block_start: the Monday its block started, monday itself when it starts one (the plan's
    progress.block_start, else its first week; the week after a deload; a week the plan doesn't
    reach); block_week: monday's week in that block, 1-based; deload: plan has a deload that week;
    run_walk_stage: the stage reached before monday (None when plan had no ladder); time_trials:
    the ones recorded; time_trial: the date of the one planned and not run yet, or None.
    A progress value of the wrong type counts as missing.
    """
    weeks = (plan or {}).get("weeks") or []
    if not isinstance((plan or {}).get("levels"), dict) or not weeks:
        return None
    p = plan.get("progress") if isinstance(plan.get("progress"), dict) else {}
    starts = [date.fromisoformat(wk["start"]) for wk in weeks]
    first = _date(p.get("block_start"))
    if first is None or first > starts[0]:
        first = starts[0]
    trials = p.get("time_trials") if isinstance(p.get("time_trials"), list) else []
    out = {"time_trials": [t for t in trials if isinstance(t, dict) and _date(t.get("date"))
                           and isinstance(t.get("vdot"), (int, float))],
           "time_trial": _date(p.get("time_trial"))}
    if monday in starts:
        i = starts.index(monday)
        block = max([first] + [starts[j] for j in range(1, i + 1) if weeks[j - 1].get("deload")])
        out.update(block_start=block, block_week=(monday - block).days // 7 + 1,
                   deload=bool(weeks[i].get("deload")))
        done = weeks[:i]
    else:
        out.update(block_start=monday, block_week=1, deload=False)
        done = weeks if monday > starts[-1] else []
    stage = _stage(p.get("run_walk_stage"))
    out["run_walk_stage"] = None if stage is None else stage + sum(not wk.get("deload") for wk in done)
    return out


def trial_days(plan, carried):
    """The days a run is a time trial: plan's tt days, its pending time trial and the recorded ones."""
    days = {d["date"] for wk in (plan or {}).get("weeks") or [] for d in wk.get("days", [])
            if (d.get("workout") or {}).get("kind") == "tt"}
    if carried:
        days |= {t["date"] for t in carried["time_trials"]}
        if carried["time_trial"]:
            days.add(carried["time_trial"].isoformat())
    return days
