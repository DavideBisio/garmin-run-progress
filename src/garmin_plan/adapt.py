"""Adapt a re-plan to what happened (roadmap 09): missed sessions, fatigue and profile.toml overrides.

adapt(plan, history, wellness, overrides, today, rules, easy, prev, days, ran_today) edits plan's
days from today on in place: the current week's remaining days (kept from the last plan,
replan.keep_past) and the new weeks. Past days are never touched, nor a day already run today (one
in history). The rules, in order ([adapt] in rules.toml holds the numbers):

1. lock override: the day stays exactly as the last plan.json had it (or without a session), with
   its match fields from history, and no other rule touches it;
2. skip override: no session that day; reduce override: an easy run of `reduce` times the session's
   km. An override wins over the automatic rules: it applies to a day fatigue or a moved L changed
   too (on a kept current-week day), and keeps the day as it was before it in change["was"]; a day
   an override no longer covers (it was removed or narrowed) gets that back;
3. a missed Q is not made up (nothing to do);
4. a missed L (in the last l_move_max_days days) moves to the next free day from today: one of the
   runner's days (days), without a session, and not today when runs.json already has a run today
   (ran_today; on a free day it matched no session). It moves when that day is at least l_move_min_days after the last Q and before the
   next one, and when its week's km, the missed sessions left out, stay within [checks] max_rise of
   the week's planned km (a second long run in a week is too much); else it is skipped;
5. fatigue turns the next Q into an easy run of the same km: resting HR more than rhr_bpm above the
   median of the rhr_days before it, a low HRV status, or low training readiness, each from the
   last fresh_days days. Missing or stale data never counts as fatigue.

A changed day records the rule in changed_by and {from, to, reason} in change. A rule never applies
twice: a day once changed is left alone by the automatic rules, an override isn't applied again
over itself, a missed L already moved isn't moved again (its from_date stays on the day through an
override), and fatigue changes one Q while a changed one is still to come; so adapting a plan twice
gives the same plan.
The change log is read back from the days: {date, from, to, rule, reason} of each changed day from
today on, plus each missed L skipped. Volume needs no rule here: the generator's base is already the
actual 4-week average (profile km_4w).
"""
import copy
from datetime import date, timedelta

from .checks import SLACK_KM
from .config import WEEKDAYS
from .history import median
from .plan_io import shown_km, shown_min

ACTIONS = ("skip", "reduce", "lock")
OVERRIDE_RULES = {"override_skip": "skip", "override_reduce": "reduce"}
SESSION_FIELDS = ("slot", "workout", "changed_by", "change")     # what an override saves and gives back


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


def _lock(plan, prev, locked, history):
    """Each locked date as the last plan had it: its day, or none when it had none that week. The
    day's match fields come from history again, as keep_past gives every kept day."""
    for iso in sorted(locked):
        old_wk = _week_of(prev or {"weeks": []}, iso)
        wk = _week_of(plan, iso)
        if old_wk is None or wk is None:
            continue
        old = next((d for d in old_wk["days"] if d["date"] == iso), None)
        days = [d for d in wk["days"] if d["date"] != iso]
        if old is not None:
            got = history.get(iso) or {}
            days.append({**copy.deepcopy(old), "status": got.get("status"), "activity_id": got.get("activity_id")})
        wk["days"] = sorted(days, key=lambda d: d["date"])


def _restore(d):
    """The day as it was before the override that changed it (change["was"])."""
    was = d["change"]["was"]
    for k in SESSION_FIELDS:
        d[k] = copy.deepcopy(was.get(k))
    if d["change"] is None:
        del d["change"]


def _plural(n, word):
    return f"{n} {word}{'s' if n != 1 else ''}"


def _retarget(wk):
    """A changed week's target: the sum of its sessions as plan.md shows them."""
    ws = [d["workout"] for d in wk["days"] if d.get("workout")]
    wk["target_km"] = round(sum(shown_km(w) for w in ws), 1)
    if wk.get("unit") == "min":
        wk["target_min"] = sum(shown_min(w["seconds"]) for w in ws)


def _l_move_block(plan, wk, free, l_workout, history, rules):
    """Why the missed L can't move to `free` in week wk (rule 4), else None."""
    n = rules["adapt"]["l_move_min_days"]

    def missed(x):
        return (history.get(x["date"]) or {}).get("status") == "missed"

    hard = [date.fromisoformat(x["date"]) for w in plan["weeks"] for x in w["days"] if _is_q(x) and not missed(x)]
    last = max((q for q in hard if q < free), default=None)
    nxt = min((q for q in hard if q > free), default=None)
    if last and (free - last).days < n:
        return f"the next free day is {_plural((free - last).days, 'day')} after the last Q, under {n}"
    if nxt and (nxt - free).days < n:
        return f"{_plural((nxt - free).days, 'day')} from the next free day to the next Q, under {n}"
    ws = [x for x in wk["days"] if x.get("workout")]
    planned = sum(shown_km(x["workout"]) for x in ws)
    km = sum(shown_km(x["workout"]) for x in ws if not missed(x)) + shown_km(l_workout)
    rise = rules["checks"]["max_rise"]
    if km > planned * (1 + rise) + SLACK_KM:
        return (f"{km:.1f} km in the week of {wk['start']} with it, over the week's {planned:.1f} km planned "
                f"by more than {rise * 100:.0f} %")
    return None


def adapt(plan, history, wellness, overrides, today, rules, easy, prev=None, days=None, ran_today=False):
    """Edit plan (a plan.json dict with the kept weeks in front) from today on and return the change
    log (module docstring). history: match.match of the last plan ({date: {status, activity_id}});
    wellness: {"rhr", "hrv", "readiness"} as in runs.json; overrides: profile.toml's [[override]]
    ({from, to, action}); easy(km): an easy run's workout dict; prev: the last plan.json (lock);
    days: the runner's days ("tue", ...; None: any day) and ran_today: a run is dated today (the
    missed L's move)."""
    a, t = rules["adapt"], today.isoformat()
    in_range = [(o["from"].isoformat(), o["to"].isoformat(), o["action"]) for o in overrides or []]
    locked = {d for d in _dates(in_range, "lock") if d >= t}
    _lock(plan, prev, locked, history)
    covered = {act: _dates(in_range, act) for act in ("skip", "reduce")}
    allowed = {WEEKDAYS.index(x) for x in days} if days else set(range(7))

    def all_days():
        return [d for wk in plan["weeks"] for d in wk["days"]]

    def open_(d):
        """From today on, not run today, not locked: the overrides may change it."""
        return d["date"] >= t and d["date"] not in history and d["date"] not in locked

    def free_(d):
        """Open and not changed yet: the automatic rules may change it."""
        return open_(d) and not d.get("changed_by")

    touched = set(locked)
    for d in all_days():                     # an override no longer covering a day: the day back as before it
        while (open_(d) and d.get("changed_by") in OVERRIDE_RULES
               and d["date"] not in covered[OVERRIDE_RULES[d["changed_by"]]]
               and isinstance((d.get("change") or {}).get("was"), dict)):
            _restore(d)
            touched.add(d["date"])

    for f, e, act in in_range:                                    # skip and reduce overrides
        for d in all_days():
            if (act not in ("skip", "reduce") or not f <= d["date"] <= e or not open_(d) or not d.get("workout")
                    or d.get("changed_by") == f"override_{act}"):
                continue
            slot = d.get("slot") or "session"
            was = {k: copy.deepcopy(d.get(k)) for k in SESSION_FIELDS}
            extra = {"was": was}
            if (d.get("change") or {}).get("from_date"):
                extra["from_date"] = d["change"]["from_date"]           # a moved L stays moved
            if act == "skip":
                d["workout"] = None
                _change(d, "override_skip", slot, "rest", f"skip override {f} to {e}", **extra)
            else:
                d["workout"], d["slot"] = easy(d["workout"]["km"] * a["reduce"]), "E"
                _change(d, "override_reduce", slot, "E", f"reduce override {f} to {e}: x{a['reduce']:g} km, easy",
                        **extra)
            touched.add(d["date"])

    notes = []
    for d in sorted((d for d in all_days() if d.get("slot") == "L" and d.get("workout")
                     and (history.get(d["date"]) or {}).get("status") == "missed"
                     and 0 < (today - date.fromisoformat(d["date"])).days <= a["l_move_max_days"]),
                    key=lambda d: d["date"]):
        if any((x.get("change") or {}).get("from_date") == d["date"] for x in all_days()):
            continue
        taken = {x["date"] for x in all_days()} | locked | covered["skip"] | ({t} if ran_today else set())
        free = next((d1 for d1 in (today + timedelta(days=k) for k in range(14))
                     if d1.isoformat() not in taken and d1.weekday() in allowed), None)
        wk = _week_of(plan, free.isoformat()) if free else None
        why = _l_move_block(plan, wk, free, d["workout"], history, rules) if wk else "no free day in the plan"
        if why:
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
    if reason and not any(d.get("changed_by") == "fatigue" and d["date"] >= t for d in all_days()):
        q = next((d for d in sorted(all_days(), key=lambda d: d["date"]) if d.get("slot") == "Q" and d.get("workout")
                  and free_(d)), None)
        if q is not None:
            q["workout"], q["slot"] = easy(q["workout"]["km"]), "E"
            _change(q, "fatigue", "Q", "E", reason)
            touched.add(q["date"])

    for wk in plan["weeks"]:
        if any(d["date"] in touched for d in wk["days"]):
            _retarget(wk)
    log = [{"date": d["date"], "from": d["change"]["from"], "to": d["change"]["to"], "rule": d["changed_by"],
            "reason": d["change"]["reason"]} for d in all_days() if d["date"] >= t and d.get("changed_by")
           and isinstance(d.get("change"), dict)]
    return sorted(log + notes, key=lambda c: (c["date"], c["rule"]))
