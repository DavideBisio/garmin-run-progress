"""Adapt a re-plan to what happened (roadmap 09): missed sessions, fatigue and profile.toml overrides.

adapt(plan, history, wellness, overrides, today, rules, easy, prev) edits plan's days from today on
in place: the current week's remaining days (kept from the last plan, replan.keep_past) and the new
weeks. Past days are never touched, nor a day already run today (one in history). The rules, in
order ([adapt] in rules.toml holds the numbers):

1. lock override: the day stays exactly as the last plan.json had it (or without a session), and no
   other rule touches it;
2. skip override: no session that day; reduce override: an easy run of `reduce` times the session's km;
3. a missed Q is not made up (nothing to do);
4. a missed L (in the last l_move_max_days days) moves to the next free day from today, a day
   without a session, when the next Q is at least l_move_min_days after it; else it is skipped;
5. fatigue turns the next Q into an easy run of the same km: resting HR more than rhr_bpm above the
   median of the rhr_days before it, a low HRV status, or low training readiness, each from the
   last fresh_days days. Missing or stale data never counts as fatigue.

A changed day records the rule in changed_by and {from, to, reason} in change. A rule never applies
twice: a day once changed is left alone, a missed L already moved isn't moved again, and fatigue
changes one Q while a changed one is still to come; so adapting a plan twice gives the same plan.
The change log is read back from the days: {date, from, to, rule, reason} of each changed day from
today on, plus each missed L skipped. Volume needs no rule here: the generator's base is already the
actual 4-week average (profile km_4w).
"""
import copy
from datetime import date, timedelta

from .config import WEEKDAYS
from .history import median
from .plan_io import shown_km, shown_min

ACTIONS = ("skip", "reduce", "lock")


def _date(v):
    try:
        return date.fromisoformat(v) if isinstance(v, str) else None
    except ValueError:
        return None


def _latest(pairs, today, fresh_days, ok):
    """The last (date, value) of [[date, value]] dated today or up to fresh_days before, value ok."""
    pts = [(d, v) for d, v in ((_date(p[0]), p[1]) for p in pairs or [] if isinstance(p, (list, tuple)) and len(p) == 2)
           if d is not None and d <= today and ok(v)]
    if not pts:
        return None
    d, v = max(pts, key=lambda p: p[0])
    return (d, v) if (today - d).days <= fresh_days else None


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def fatigue(wellness, today, rules):
    """The reasons today counts as a fatigue day ("resting HR +7 bpm", "HRV status low", "training
    readiness low (30)"), joined with ', '; None when no signal says so or the data is missing."""
    a, w, out = rules["adapt"], wellness or {}, []
    last = _latest(w.get("rhr"), today, a["fresh_days"], _number)
    if last:
        d0, v = last
        base = [v1 for d1, v1 in ((_date(p[0]), p[1]) for p in w["rhr"] if isinstance(p, (list, tuple)) and len(p) == 2)
                if d1 is not None and d0 - timedelta(days=a["rhr_days"]) <= d1 < d0 and _number(v1)]
        if len(base) >= a["rhr_min_days"] and v - median(base) > a["rhr_bpm"]:
            out.append(f"resting HR +{v - median(base):.0f} bpm")
    hrv = _latest(w.get("hrv"), today, a["fresh_days"], lambda v: isinstance(v, str))
    if hrv and hrv[1].upper() in a["hrv_low"]:
        out.append("HRV status low")
    ready = _latest(w.get("readiness"), today, a["fresh_days"],
                    lambda v: isinstance(v, dict) and (isinstance(v.get("level"), str) or _number(v.get("score"))))
    if ready:
        lv, score = ready[1].get("level"), ready[1].get("score")
        low = lv.upper() in a["readiness_low_levels"] if isinstance(lv, str) else score < a["readiness_low_score"]
        if low:
            out.append(f"training readiness low ({score})" if _number(score) else "training readiness low")
    return ", ".join(out) or None


def _day_name(iso):
    return WEEKDAYS[date.fromisoformat(iso).weekday()].capitalize()


def _week_of(plan, iso):
    d = date.fromisoformat(iso)
    return next((wk for wk in plan["weeks"]
                 if date.fromisoformat(wk["start"]) <= d <= date.fromisoformat(wk["start"]) + timedelta(days=6)), None)


def _change(d, rule, frm, to, reason, **extra):
    d["changed_by"] = rule
    d["change"] = {"from": frm, "to": to, "reason": reason, **extra}


def _is_q(d):
    """A Q day, or one fatigue made easy (it still counts as the Q for the L move's 48 hours)."""
    return d.get("workout") and (d.get("slot") == "Q" or (d.get("change") or {}).get("from") == "Q")


def _dates(ranges, action):
    """The ISO dates the overrides with `action` cover."""
    return {(date.fromisoformat(f) + timedelta(days=k)).isoformat() for f, e, act in ranges if act == action
            for k in range((date.fromisoformat(e) - date.fromisoformat(f)).days + 1)}


def _lock(plan, prev, locked):
    """Each locked date as the last plan had it: its day, or none when it had none that week."""
    for iso in sorted(locked):
        old_wk = _week_of(prev or {"weeks": []}, iso)
        wk = _week_of(plan, iso)
        if old_wk is None or wk is None:
            continue
        old = next((d for d in old_wk["days"] if d["date"] == iso), None)
        days = [d for d in wk["days"] if d["date"] != iso]
        if old is not None:
            days.append(copy.deepcopy(old))
        wk["days"] = sorted(days, key=lambda d: d["date"])


def _retarget(wk):
    """A changed week's target: the sum of its sessions as plan.md shows them."""
    ws = [d["workout"] for d in wk["days"] if d.get("workout")]
    wk["target_km"] = round(sum(shown_km(w) for w in ws), 1)
    if wk.get("unit") == "min":
        wk["target_min"] = sum(shown_min(w["seconds"]) for w in ws)


def adapt(plan, history, wellness, overrides, today, rules, easy, prev=None):
    """Edit plan (a plan.json dict with the kept weeks in front) from today on and return the change
    log (module docstring). history: match.match of the last plan ({date: {status, activity_id}});
    wellness: {"rhr", "hrv", "readiness"} as in runs.json; overrides: profile.toml's [[override]]
    ({from, to, action}); easy(km): an easy run's workout dict; prev: the last plan.json (lock)."""
    a, t = rules["adapt"], today.isoformat()
    in_range = [(o["from"].isoformat(), o["to"].isoformat(), o["action"]) for o in overrides or []]
    locked = {d for d in _dates(in_range, "lock") if d >= t}
    _lock(plan, prev, locked)
    skipped = _dates(in_range, "skip")

    def days():
        return [d for wk in plan["weeks"] for d in wk["days"]]

    def open_(d):
        return d["date"] >= t and d["date"] not in history and d["date"] not in locked and not d.get("changed_by")

    touched = set(locked)
    for f, e, act in in_range:                                    # skip and reduce overrides
        for d in days():
            if act not in ("skip", "reduce") or not f <= d["date"] <= e or not open_(d) or not d.get("workout"):
                continue
            slot = d.get("slot") or "session"
            if act == "skip":
                d["workout"] = None
                _change(d, "override_skip", slot, "rest", f"skip override {f} to {e}")
            else:
                d["workout"], d["slot"] = easy(d["workout"]["km"] * a["reduce"]), "E"
                _change(d, "override_reduce", slot, "E", f"reduce override {f} to {e}: x{a['reduce']:g} km, easy")
            touched.add(d["date"])

    notes = []
    for d in sorted((d for d in days() if d.get("slot") == "L" and d.get("workout")
                     and (history.get(d["date"]) or {}).get("status") == "missed"
                     and 0 < (today - date.fromisoformat(d["date"])).days <= a["l_move_max_days"]),
                    key=lambda d: d["date"]):
        if any(x.get("changed_by") == "l_moved" and x["change"].get("from_date") == d["date"] for x in days()):
            continue
        taken = {x["date"] for x in days()} | locked | skipped
        free = next((d1 for d1 in (today + timedelta(days=k) for k in range(14)) if d1.isoformat() not in taken),
                    None)
        wk = _week_of(plan, free.isoformat()) if free else None
        nxt = min((date.fromisoformat(x["date"]) for x in days() if _is_q(x) and free and x["date"] > free.isoformat()),
                  default=None)
        gap = (nxt - free).days if nxt and free else None
        if wk is None or (gap is not None and gap < a["l_move_min_days"]):
            why = (f"{gap} day{'s' if gap != 1 else ''} from the next free day to the next Q, under "
                   f"{a['l_move_min_days']}" if wk is not None else "no free day in the plan")
            notes.append({"date": d["date"], "from": "L", "to": "skipped", "rule": "l_skipped",
                          "reason": f"long run missed; {why}"})
            continue
        new = {"date": free.isoformat(), "slot": "L", "workout": copy.deepcopy(d["workout"]), "status": None,
               "activity_id": None}
        _change(new, "l_moved", "rest", "L", f"long run of {_day_name(d['date'])} {d['date']} missed",
                from_date=d["date"])
        wk["days"] = sorted(wk["days"] + [new], key=lambda x: x["date"])
        touched.add(new["date"])

    reason = fatigue(wellness, today, rules)
    if reason and not any(d.get("changed_by") == "fatigue" and d["date"] >= t for d in days()):
        q = next((d for d in sorted(days(), key=lambda d: d["date"]) if d.get("slot") == "Q" and d.get("workout")
                  and open_(d)), None)
        if q is not None:
            q["workout"], q["slot"] = easy(q["workout"]["km"]), "E"
            _change(q, "fatigue", "Q", "E", reason)
            touched.add(q["date"])

    for wk in plan["weeks"]:
        if any(d["date"] in touched for d in wk["days"]):
            _retarget(wk)
    log = [{"date": d["date"], "from": d["change"]["from"], "to": d["change"]["to"], "rule": d["changed_by"],
            "reason": d["change"]["reason"]} for d in days() if d["date"] >= t and d.get("changed_by")
           and isinstance(d.get("change"), dict)]
    return sorted(log + notes, key=lambda c: (c["date"], c["rule"]))
