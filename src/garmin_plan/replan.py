"""A re-plan (roadmap 09): the new plan from the Monday after today, behind it the last plan's weeks.

Every plan starts on the Monday after today. plan.json keeps the weeks before it as the last plan
wrote them: the past weeks and the current one, whose days are still to be run. Each day of those
weeks gets its status and activity_id from the runs (match.match: done, partial, missed, moved or
swapped; null for a day still to come), and keeps its changed_by. The new weeks' days have null
status, activity_id and changed_by. history lists the re-plans that changed something: the date,
the first week of the new plan and the weeks whose sessions differ from the last plan's.
"""
import copy

from .match import match
from .planner import build_plan

DAY_FIELDS = ("status", "activity_id", "changed_by")


def _comparable(wk):
    """A week without what a re-plan always rewrites: its warnings and the days' match fields."""
    return {**{k: v for k, v in wk.items() if k != "warnings"},
            "days": [{k: v for k, v in d.items() if k not in DAY_FIELDS} for d in wk.get("days") or []]}


def changed_weeks(prev, plan):
    """The starts of plan's weeks that prev also has, with different sessions or targets."""
    old = {wk["start"]: _comparable(wk) for wk in (prev or {}).get("weeks") or []}
    return [wk["start"] for wk in plan["weeks"] if wk["start"] in old and old[wk["start"]] != _comparable(wk)]


def keep_past(prev, plan, today, statuses):
    """plan (changed in place and returned) with prev's weeks before plan's first week in front, the
    match fields on every day (statuses: match.match of prev) and the history carried on from prev's,
    plus an entry when a week both plans hold changed."""
    first = plan["weeks"][0]["start"] if plan["weeks"] else None
    kept = [copy.deepcopy(wk) for wk in (prev or {}).get("weeks") or []
            if isinstance(wk, dict) and (first is None or wk["start"] < first)]
    for wk in kept:
        for d in wk["days"]:
            got = statuses.get(d["date"]) or {}
            d["status"], d["activity_id"] = got.get("status"), got.get("activity_id")
            d.setdefault("changed_by", None)
    for wk in plan["weeks"]:
        for d in wk["days"]:
            for k in DAY_FIELDS:
                d.setdefault(k, None)
    history = [h for h in (prev or {}).get("history") or [] if isinstance(h, dict)]
    changed = changed_weeks(prev, plan) if prev else []
    if changed:
        history.append({"date": today.isoformat(), "start": first, "weeks": changed})
    plan["weeks"] = kept + plan["weeks"]
    plan["history"] = history
    return plan


def replan(prev, prof, runs, library, rules, today, weeks=None, generated=None, level_data=None):
    """The plan.json dict of a re-plan on `today` after prev (the last plan.json, or None): the
    generator's plan (planner.build_plan) behind prev's past and current weeks (keep_past)."""
    plan = build_plan(prof, runs, library, rules, today, weeks, generated=generated, level_data=level_data)
    statuses = match(prev, runs, today, rules, prof.hr_max, prof.hr_rest) if prev else {}
    return keep_past(prev, plan, today, statuses)
