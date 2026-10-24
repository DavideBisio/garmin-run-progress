"""A re-plan (roadmap 09): the new plan from the Monday after today, behind it the last plan's weeks,
adapted to what happened.

Every plan starts on the Monday after today. plan.json keeps the weeks before it as the last plan
wrote them: the past weeks and the current one, whose days are still to be run. Each day of those
weeks gets its status and activity_id from the runs (match.match: done, partial, missed, moved or
swapped; null for a day still to come), and keeps its changed_by. The new weeks' days have null
status, activity_id and changed_by. Then adapt.adapt edits the days from today on (missed
sessions, fatigue, overrides); its change log is the plan's "changes". history lists the re-plans
that changed something: the date, the first week of the new plan, the weeks whose sessions differ
from the last plan's and the changes.
"""
import copy
import json

from . import levels, size
from .adapt import adapt
from .match import match
from .planner import build_plan
from .plan_io import workout_to_dict
from .templates import instantiate

DAY_FIELDS = ("status", "activity_id", "changed_by")
MATCH_FIELDS = ("status", "activity_id")         # filled in again on every re-plan


def _comparable(wk):
    """A week without what a re-plan always rewrites: its warnings and the days' match fields."""
    return {**{k: v for k, v in wk.items() if k != "warnings"},
            "days": [{k: v for k, v in d.items() if k not in MATCH_FIELDS} for d in wk.get("days") or []]}


def changed_weeks(prev, plan):
    """The starts of plan's weeks that prev also has, with different sessions or targets."""
    old = {wk["start"]: _comparable(wk) for wk in (prev or {}).get("weeks") or []}
    return [wk["start"] for wk in plan["weeks"] if wk["start"] in old and old[wk["start"]] != _comparable(wk)]


def keep_past(prev, plan, statuses):
    """plan (changed in place and returned) with prev's weeks before plan's first week in front and
    the match fields on every day (statuses: match.match of prev)."""
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
    plan["weeks"] = kept + plan["weeks"]
    return plan


def record_history(prev, plan, today):
    """plan's history: prev's, plus an entry when a week both plans hold changed."""
    history = [h for h in (prev or {}).get("history") or [] if isinstance(h, dict)]
    changed = changed_weeks(prev, plan) if prev else []
    if changed:
        history.append({"date": today.isoformat(), "start": plan["progress"].get("plan_start"), "weeks": changed,
                        "changes": plan.get("changes", [])})
    plan["history"] = history
    return plan


def easy_maker(prof, library, rules, level_data=None):
    """easy(km) -> the workout dict of the runner's easy run (the level's E template) fitted to km."""
    r = levels.params(level_data or levels.load_levels(), prof.volume_level, prof.quality_level, rules)
    t = library[r["rotation"]["E"]]

    def easy(km):
        v, _ = size.pick_variant(t, km, km, r["caps"], prof, r)
        w = size.fit(t, v, prof, r, km=km) or instantiate(t, v, prof, r)
        return json.loads(json.dumps(workout_to_dict(w)))
    return easy


def replan(prev, prof, runs, library, rules, today, weeks=None, generated=None, level_data=None, wellness=None):
    """The plan.json dict of a re-plan on `today` after prev (the last plan.json, or None): the
    generator's plan (planner.build_plan) behind prev's past and current weeks (keep_past), adapted
    (adapt.adapt; wellness: {"rhr", "hrv", "readiness"} as in runs.json), with its history."""
    plan = build_plan(prof, runs, library, rules, today, weeks, generated=generated, level_data=level_data)
    statuses = match(prev, runs, today, rules, prof.hr_max, prof.hr_rest) if prev else {}
    keep_past(prev, plan, statuses)
    ran = any(str(r.get("date") or "")[:10] == today.isoformat() for r in runs or ())
    plan["changes"] = adapt(plan, statuses, wellness, prof.overrides, today, rules,
                            easy_maker(prof, library, rules, level_data), prev=prev, days=prof.days, ran_today=ran)
    return record_history(prev, plan, today)
