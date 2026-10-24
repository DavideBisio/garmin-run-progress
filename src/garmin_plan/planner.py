"""The plan generator: phases, volume, slots, sessions, the split, checks and fixes (roadmaps 06 and 07).

build_plan(prof, runs, library, rules, today) gives the plan.json dict (docs/plan-json-format.md)
from the Monday after today to the race week (or 8 weeks without a race). Each week: the phase
calendar and the volume curve set its phase, deload and km; the skeleton places L, Q, E and F;
the rotation picks Q and L; Q is sized first, the split shares the km, E and L are fitted to
them; then the checks run and the fixer shrinks Q, trims L or drops F. profile.toml's [week]
days replace the generated ones and are never changed. Warnings are {rule, detail, action}.

The runner's levels (08, levels.py) set the numbers. A plan in minutes (a beginner's) is planned in
km all the same, converted at the middle of the E pace range: its weeks show the minutes their
sessions add up to. A beginner's easy and long runs climb the run/walk ladder first, and their plan
has a time trial for a first VDOT.

A re-plan carries on from the last plan (prof.progress, progress.py): its first week keeps its place
in the block, so the deloads stay put, the ladder goes on from the stage reached, and the time trial
keeps its date, or isn't planned again once run. The plan's "progress" is what the next one reads.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from . import checks, fix, levels, select, size, skeleton
from .config import MIN_HISTORY_DAYS, WEEKDAYS
from .history import daily_load, recent_stats
from .load import projected_daily
from .model import Repeat
from .phases import PhaseError, phase_calendar
from .physiology import pace_zones, vdot
from .plan_io import VERSION, first_monday_after, manual_days, plan_profile, profile_hash, shown_km, shown_min, workout_to_dict
from .skeleton import place_slots
from .split import split_week
from .templates import instantiate, pace_range
from .terrain import workout_flat_km
from .volume import align_deloads, block_curve, settings

__all__ = ["build_plan", "PhaseError"]

TIME_KINDS = ("hill", "trail")       # long-run swaps sized to the time budget of the L they replace
WALK_MIN_S = 120                     # a run/walk session's brisk walk warm-up, at least (when it repeats)
SPLIT_ACTIONS = [                    # text in a split.py warning -> what the planner did, first match
    ("Q dropped", "made the Q day an easy run (or a rest day)"),
    ("longer than L", "kept the easy runs longer than L: the L caps come first"),
    ("run short", "planned one easy run under the minimum"),
    ("no other run", "put the whole week in L"),
    ("under the E minimum", "planned the week's km as one short long run"),
    ("leftover", "planned the week as the sum of its sessions"),
]


def warning(rule, detail, action):
    return {"rule": rule, "detail": detail, "action": action}


def _split_warning(w):
    return warning("split", w, next((a for p, a in SPLIT_ACTIONS if p in w), "kept the split as shown"))


def _cycle_start(prof, start):
    """The Monday the no-race phase cycle started: the last plan's (progress.cycle_start), else start
    (a first plan, a restart after a break, or a plan from before it was recorded)."""
    cyc = (prof.progress or {}).get("cycle_start")
    return cyc if cyc and cyc <= start and not prof.layoff else start


def _calendar(prof, rules, start, weeks):
    """(phase weeks, warnings, full weeks to the race): the whole calendar, truncated later. Without
    a race the phase cycle goes on from where the last plan's was (its deloads stay put)."""
    race = prof.race
    if race is None:
        offset = (start - _cycle_start(prof, start)).days // 7
        cal, warns = phase_calendar(start, None, None, rules, weeks or None, offset=offset)
        return cal, warns, len(cal)
    if race["date"] < start:
        raise PhaseError(f"the race on {race['date']} is before the plan's first week (Monday {start}); "
                         "update [race] in profile.toml")
    cal, warns = phase_calendar(start, race["date"], race["distance_m"], rules)
    return cal, warns, len(cal)


def _targets(prof, cal, rules, floor_km, first=1):
    """(km per week, deload week indices). The build weeks follow the block curve with deloads off
    the phase starts, from at least floor_km, the first week at place `first` in its block; taper
    weeks are [volume] taper shares of the last build week that isn't a deload."""
    every = rules["volume"]["deload_every"]
    build = [w.phase for w in cal if w.phase != "taper"]
    starts = [i for i in range(1, len(build)) if build[i] != build[i - 1]]
    deloads = align_deloads(len(build), every, starts, lead=1 - first)
    out = block_curve(prof.km_4w, len(build), **{**settings(rules), "floor": floor_km}, deloads=deloads)
    peak = next((out[i] for i in range(len(out) - 1, -1, -1) if i not in deloads), max(prof.km_4w, floor_km))
    taper = rules["volume"]["taper"]
    out += [peak * taper[min(k, len(taper) - 1)] for k in range(len(cal) - len(build))]
    return out, deloads


class _Week:
    """One week's inputs and its layout(adjust) -> (days, split warnings), the fixer's build()."""

    def __init__(self, ctx, i, pw, target, deload, bw, stage=1):
        self.ctx, self.i, self.pw, self.target, self.deload, self.bw = ctx, i, pw, target, deload, bw
        c = ctx
        # the run/walk variant of the week's E and L runs, None past the ladder or without one
        self.rw = stage if c.rw and stage <= len(c.lib[c.rw]["ladder"]) else None
        self.dates = {d: pw.start + timedelta(days=WEEKDAYS.index(d)) for d in WEEKDAYS}
        self.l_day = next((d for d, s in c.slots.items() if s == "L"), None)
        self.l_hill = self.l_day in c.prof.hill_days      # build_plan turns it off when it breaks 80/20
        # Q day -> (template id, variant, forced): the first Q day (a hill day first, for the hill
        # swap) takes the rotation's Q, the others its Q2, each sized to what the week leaves after
        # the E minimums and the Q before it
        self.q = {}
        n_e = sum(s == "E" for s in c.slots.values())
        budget = target - c.e_min * (n_e + (1 if self.l_day else 0))
        lighter = c.rules["rotation"]["deload_lighter"] if deload else 0
        q_days = sorted((d for d, s in c.slots.items() if s == "Q"), key=lambda d: d not in c.prof.hill_days)
        for k, d in enumerate(q_days):
            tid = select.rotation(pw.phase, bw, "Q2" if k else "Q", c.rules, deload=deload, library=c.lib,
                                  hill_day=d in c.prof.hill_days, level=c.level)
            if tid is None:
                continue
            v, forced = size.pick_variant(c.lib[tid], budget, target, c.caps, c.prof, c.rules, lighter=lighter)
            self.q[d] = (tid, v, self._forced(tid, budget) if forced else "")
            budget -= workout_flat_km(instantiate(c.lib[tid], v, c.prof, c.rules))
        self.tt_extra = False                   # the time trial is a hard day on top of the Q days
        if c.tt_date in self.dates.values():    # it takes the week's Q, on its day (_tt_day)
            self.q, self.tt_extra = {c.tt_day: (c.tt, 1, "")}, not q_days
        # a Q day the rotation leaves empty (Q2 in a deload) is an easy one
        self.slots = {d: "Q" if d in self.q else "E" if s == "Q" else s for d, s in c.slots.items()}

    def _forced(self, tid, budget):
        c, t = self.ctx, self.ctx.lib[tid]
        w = instantiate(t, 1, c.prof, c.rules)
        cap = size.cap_km(t["kind"], self.target, c.caps)
        if w.hard_km > cap:
            return (f"{w.title} variant 1 has {w.hard_km:.1f} hard km, over the {_cap_name(t['kind'], c.caps)} cap of "
                    f"{cap:.1f} km at {self.target:.1f} km a week")
        return f"{w.title} variant 1 is {w.km:.1f} km, over the {max(budget, 0):.1f} km the week leaves for Q"

    def _long(self, km):
        """The L workout for km: the rotation's first candidate that fits (hill and trail swaps at
        the time budget of km at E pace), else the E template fitted to km. On the run/walk ladder,
        the week's run/walk."""
        c = self.ctx
        if self.rw:
            return self._easy(km)
        ids = select.candidates(self.pw.phase, self.bw, "L", c.rules, deload=self.deload, library=c.lib,
                                hill_day=self.l_hill, level=c.level)
        for k, tid in enumerate(ids):
            t, last = c.lib[tid], k == len(ids) - 1
            if t["kind"] in TIME_KINDS:
                secs = km * c.e_mid
                v, forced = size.pick_variant(t, km, self.target, c.caps, c.prof, c.rules, slot_s=secs)
                w = size.fit(t, v, c.prof, c.rules, seconds=secs)
            else:
                v, forced = size.pick_variant(t, km, self.target, c.caps, c.prof, c.rules)
                w = size.fit(t, v, c.prof, c.rules, km=km)
            if w is not None and (not forced or last):
                return w
        return self._easy(km)

    def _run_walk(self, km):
        """The week's run/walk variant (or an earlier one when the slot is too short) for the time of
        km at E pace: the set repeated as often as the slot holds with WALK_MIN_S of brisk walk
        first, the walk taking the rest. None when not even the first variant fits."""
        c = self.ctx
        t, secs = c.lib[c.rw], km * c.e_mid
        for v in range(self.rw, 0, -1):
            rep = next((p for p in instantiate(t, v, c.prof, c.rules).parts if isinstance(p, Repeat)), None)
            ns = [None] if rep is None else range(max(rep.n, int(secs // (rep.seconds / rep.n))), 0, -1)
            for n in ns:
                w = size.fit(t, v, c.prof, c.rules, seconds=secs, values=None if n is None else {"n": n})
                if w is not None and (n in (None, 1) or w.parts[0].value >= WALK_MIN_S):
                    return w
        return None

    def _easy(self, km):
        c = self.ctx
        if self.rw:
            w = self._run_walk(km)
            if w is not None:
                return w
        t = c.lib[c.rules["rotation"]["E"]]
        v, _ = size.pick_variant(t, km, self.target, c.caps, c.prof, c.rules)
        return size.fit(t, v, c.prof, c.rules, km=km)

    def _q_extended(self, day, qw, extra):
        """qw with the split's leftover on its Q day: a longer warm-up, else a longer first easy main
        step (the progression run has no warm-up); None when the template has neither."""
        if extra <= 0.05:
            return qw
        t = self.ctx.lib[self.q[day][0]]
        return (size.fit(t, qw.variant, self.ctx.prof, self.ctx.rules, warmup_km=extra)
                or size.fit(t, qw.variant, self.ctx.prof, self.ctx.rules, km=qw.km + extra))

    def layout(self, adj):
        c, days = self.ctx, {}
        qws = {d: instantiate(c.lib[tid], max(1, v - adj.q_down), c.prof, c.rules) for d, (tid, v, _) in self.q.items()}
        q_km = {d: workout_flat_km(w) for d, w in qws.items()}
        dropped = []
        km, warns = split_week(self.target, self.slots, self.longest, q_km, c.rules, c.e_pace, dropped)
        for d, slot in self.slots.items():
            k = km[d]
            if slot == "L" and adj.trim_l_km and k:
                k = max(k - adj.trim_l_km, min(k, c.e_min))
            if k <= 0 or (slot == "F" and adj.drop_f):
                continue
            if slot == "Q" and d not in dropped:
                qw = qws[d]
                w = self._q_extended(d, qw, k - q_km[d])
                if w is None:
                    w = qw
                    warns.append(f"Q: {qw.title} has no warm-up or easy step to take the week's {k - q_km[d]:.1f} "
                                 "km leftover")
                days[d] = checks.Day(self.dates[d], "Q", w, forced=self.q[d][2])
            elif slot == "L":
                days[d] = checks.Day(self.dates[d], "L", self._long(k))
            else:
                days[d] = checks.Day(self.dates[d], "E" if slot == "Q" else slot, self._easy(k))
        for d, w in c.manual.items():
            days[d] = checks.Day(self.dates[d], None, w, manual=True)
        out = [days[d] for d in WEEKDAYS if d in days and not (c.race and self.dates[d] >= c.race)]
        return out, warns

    def check(self, days):
        c = self.ctx
        exempt = set()
        if self.i == 0 or self.deload or self.i - 1 in c.deloads:
            exempt.add("volume_rise")
        if self.deload or self.pw.phase == "taper":
            exempt.add("acwr_low")
        v, notes = checks.check_week(days, self._rules(), e_min=c.e_min, hr_max=c.prof.hr_max, hr_rest=c.prof.hr_rest,
                                     prev_km=c.prev_km, prev_days=c.prev_days, daily=c.daily,
                                     end=self.pw.start + timedelta(days=6), exempt=exempt)
        if c.daily is None:                       # said once for the whole plan
            notes = [n for n in notes if n.code != "acwr_skipped"]
        return v, notes

    def _rules(self):
        c = self.ctx
        if not self.tt_extra:
            return c.rules
        return {**c.rules, "checks": {**c.rules["checks"], "max_hard": c.rules["checks"]["max_hard"] + 1}}


def _tt_day(c):
    """(weekday, warning or None) of the time trial: a Q day off the hill days (it wants a flat
    route), else an easy day 48 h from L, one off the hill days first. Failing both, with a warning,
    a hill Q day, else an easy day next to L; (None, None) in a week of L alone."""
    l_day = next((d for d, s in c.slots.items() if s == "L"), None)
    q = [d for d, s in c.slots.items() if s == "Q"]
    easy = [d for d, s in c.slots.items() if s in ("E", "F")]
    far = [d for d in easy if l_day is None or min(skeleton.gap(l_day, d), skeleton.gap(d, l_day)) >= 2]
    hills = c.prof.hill_days
    best = [d for d in q if d not in hills] + sorted(far, key=lambda d: d in hills)
    if best:
        return best[0], None
    if not q + easy:
        return None, None
    day = (q + easy)[0]
    where = "a hill day: run it on a flat route or a track" if day in q else f"the day next to L ({l_day})"
    return day, warning("time_trial", f"no Q day off the hill days and no easy day 48 h from L ({l_day}) "
                                      "for the time trial", f"planned it on {day}, {where}")


def _tt_date(c, start, today):
    """The time trial's date: None without one at the level or once one is run (progress holds
    it); the planned one's when its week is in this plan, on c.tt_day of that week; this plan's
    first week when it was missed or falls before this plan starts (later this week: no plan would
    hold it and push removes it from the watch); else week time_trial_week."""
    car = c.prof.progress or {}
    if not c.tt or c.tt_day is None or car.get("time_trials"):
        return None
    due = car.get("time_trial")
    if due and due >= start:
        monday = due - timedelta(days=due.weekday())
    else:
        monday = start + timedelta(weeks=0 if due else c.tt_week - 1)
    return monday + timedelta(days=WEEKDAYS.index(c.tt_day))


def _block(prof, rules, start):
    """(block start, the first week's place in its block, run/walk stages reached before it) from
    the last plan's progress; (start, 1, 0) without one or after a break, which restarts the plan.
    A first week that the last plan has as a deload is the block's deload (place deload_every)."""
    car, every = prof.progress, rules["volume"]["deload_every"]
    if not car or prof.layoff:
        return start, 1, 0
    stage = car["run_walk_stage"] or 0
    if car["block_start"] == start:
        return start, 1, stage
    return car["block_start"], every if car["deload"] else min(car["block_week"], every - 1), stage


def _cap_name(kind, caps):
    c = caps.get(kind)
    return c if isinstance(c, str) else kind


def _describe(week, adj, target, actual):
    """What the fixer changed, e.g. 'Q cruise_tempo variant 5 -> 4, L 2.0 km shorter (32.4 -> 30.4 km)'."""
    parts = []
    if adj.q_down:
        parts += [f"Q {tid} variant {v} -> {max(1, v - adj.q_down)}" for tid, v, _ in week.q.values()]
    if adj.trim_l_km:
        parts.append(f"L {adj.trim_l_km:.1f} km shorter")
    if adj.drop_f:
        parts.append(f"F ({next(d for d, s in week.ctx.slots.items() if s == 'F')}) dropped")
    out = ", ".join(parts)
    if adj.trim_l_km or adj.drop_f:
        out += f" (week {target:.1f} -> {actual:.1f} km)"
    return out


def _week_warnings(week, res, before, split_warns, target, actual):
    """The week's warnings: the split's, the forced sizes, and each check that failed with what the
    fixer did about it (fixed, or not enough) or why it was left (no fix helps, max_iter reached)."""
    out = [_split_warning(w) for w in split_warns]
    for n in res.notes:
        action = {"forced_size": "used the smallest variant anyway",
                  "acwr_skipped": "skipped the load ratio check this week"}[n.code]
        out.append(warning(n.code, n.detail, action))
    did = _describe(week, res.adjust, target, actual)
    left = {v.code for v in res.violations}
    out += [warning(v.code, v.detail, f"fixed: {did}") for v in before if v.code not in left]
    for v in res.violations:
        if res.stopped:
            action = f"stopped after {week.ctx.rules['fix']['max_iter']} fixes ({did}); still failing"
        elif did and v.code in fix.FIXES:
            action = f"{did}; no further fix helps, still failing"
        else:
            action = "left as is: no fix helps (the fixer shrinks Q, trims L and drops F)"
        out.append(warning(v.code, v.detail, action))
    return out


def _hill_swap(week):
    """[warning] when the week's hill or trail long run is dropped: its climbs run at Z2-3 or under a
    Z3 cap, which isn't easy (Z1-2), and a swap that puts the week under the easy share when the
    flat long run doesn't is left out (the swaps can replace L, they don't have to)."""
    if not week.l_hill:
        return []
    days = week.layout(fix.Adjust())[0]
    swap = next((d.workout for d in days if d.slot == "L" and d.workout.kind in TIME_KINDS), None)
    if swap is None or "easy_share" not in {v.code for v in week.check(days)[0]}:
        return []
    week.l_hill = False
    if "easy_share" in {v.code for v in week.check(week.layout(fix.Adjust())[0])[0]}:
        week.l_hill = True                       # not the swap's doing: keep it
        return []
    share = checks.easy_share(days)
    return [warning("hill_swap", f"a {swap.title.lower()} on {week.l_day} would leave {share * 100:.0f} % of "
                                 f"the running time easy, under {week.ctx.rules['checks']['easy_share'] * 100:.0f} %",
                    "kept the flat long run")]


def build_plan(prof, runs, library, rules, today, weeks=None, generated=None, level_data=None):
    """The generated plan dict. weeks: with a race, only the first `weeks` of the plan to the race
    week (the plan itself doesn't change); without one, the plan's length (default 8). rules are
    rules.toml's; the runner's levels lay level_data (levels.toml by default) over them. Raises
    ProfileError ([week]), SkeletonError (days) and PhaseError (the race date)."""
    level_data = level_data or levels.load_levels()
    rules = levels.params(level_data, prof.volume_level, prof.quality_level, rules)
    start = first_monday_after(today)
    cal, phase_warns, n_full = _calendar(prof, rules, start, weeks)
    paces = pace_zones(prof.vdot, rules)
    e_mid = pace_range("E", paces, rules).mid
    floor = rules["volume"]["start_floor"]                  # in the level's own unit
    block, first, reached = _block(prof, rules, start)
    targets, deloads = _targets(prof, cal, rules, floor * 60 / e_mid if rules["volume"]["unit"] == "min" else floor,
                                first)
    c = SimpleNamespace()               # what every week shares
    c.prof, c.lib, c.rules, c.caps, c.deloads = prof, library, rules, rules["caps"], set(deloads)
    c.level, c.unit = prof.quality_level, levels.unit(prof, level_data)
    c.rw = rules["rotation"].get("run_walk")
    c.tt, c.tt_week = rules["rotation"].get("time_trial"), rules["rotation"].get("time_trial_week")
    c.slots = place_slots(prof.days, prof.long_run_day, rules)
    c.tt_day, tt_warn = _tt_day(c) if c.tt else (None, None)
    c.tt_date = _tt_date(c, start, today)
    n_q = sum(s == "Q" for s in c.slots.values())
    rules["checks"]["max_hard"] = n_q + 1                   # the Q days and L (levels.toml q_from_days)
    c.manual = manual_days(prof, library, rules)
    c.e_pace, c.e_mid = paces["E"], e_mid
    s = rules["split"]
    c.e_min = min(s["easy_min_km"], s["easy_min_min"] * 60 / c.e_pace)
    c.race = prof.race["date"] if prof.race else None
    stats = recent_stats(runs, today)
    hist_ok = stats["history_days"] >= MIN_HISTORY_DAYS
    c.daily = daily_load(runs, prof.hr_max, prof.hr_rest, until=today) if hist_ok else None   # planned from here
    c.prev_km, c.prev_days = None, []

    top = [warning("phases", w, "kept the volume ramp and shortened the phases as listed") for w in phase_warns]
    want = skeleton.q_count(len(c.slots), rules)
    if n_q < want:
        long_day = next(d for d, s in c.slots.items() if s == "L")
        top.append(warning("skeleton", f"{want} Q days don't fit {', '.join(c.slots)} with L on {long_day}: each "
                                       "Q needs 48 h from L and no two hard days may be back to back",
                           f"planned {n_q} Q day{'s' if n_q != 1 else ''} a week"))
    if prof.race and prof.race["goal_s"]:
        f = checks.feasibility(prof.vdot, vdot(prof.race["distance_m"], prof.race["goal_s"]), n_full, rules)
        if f:
            top.append(warning("feasibility", f.detail, "kept the paces at the current VDOT (set vdot after a "
                                                         "race or time trial to raise them)"))
    if c.tt_date and tt_warn:
        top.append(tt_warn)
    if not hist_ok:
        top.append(warning("acwr_skipped", f"{stats['history_days']} days of history in runs.json, under "
                                           f"{MIN_HISTORY_DAYS}", "skipped the 7:28-day load ratio check in every week"))

    every, n_build = rules["volume"]["deload_every"], sum(w.phase != "taper" for w in cal)
    longs, out = [], []
    for i, pw in enumerate(cal):
        bw = select.block_week(i, deloads, every, first) if i < n_build else i - n_build + 1
        builds = reached + sum(j not in c.deloads for j in range(i))    # a deload repeats the last stage
        week = _Week(c, i, pw, targets[i], i in c.deloads, bw, stage=max(1, builds + (i not in c.deloads)))
        week.longest = max([prof.longest_8w] + longs[max(0, i - 8):i])
        hill = _hill_swap(week)
        before = week.check(week.layout(fix.Adjust())[0])[0]
        res = fix.fix_week(lambda adj: week.layout(adj)[0], week.check, rules)
        days, split_warns = week.layout(res.adjust)
        target = round(targets[i], 1)
        actual = round(sum(shown_km(workout_to_dict(d.workout)) for d in days), 1)
        warns = hill + _week_warnings(week, res, before, split_warns, target, actual)
        race_cut = bool(c.race) and pw.start + timedelta(days=6) >= c.race
        if race_cut:
            warns.append(warning("race_week", f"the race is on {WEEKDAYS[c.race.weekday()]} {c.race}",
                                 "planned no session from race day on; the week's km are the sessions before it"))
        lost = any("leftover" in w for w in split_warns)
        if res.adjust.trim_l_km or res.adjust.drop_f or race_cut or c.manual or lost or c.unit == "min" or c.rw:
            target = actual                     # run/walk and time sessions (a beginner's) fill time, not km
        long_date = week.dates[prof.long_run_day]           # L, or the [week] day that replaces it
        longs.append(max((d.workout.km for d in days if d.slot == "L" or d.manual and d.date == long_date),
                         default=0.0))
        if c.daily is not None:
            for k, v in projected_daily([(d.date, d.workout) for d in days], prof.hr_max, prof.hr_rest).items():
                c.daily[k] = c.daily.get(k, 0) + v
        c.prev_km, c.prev_days = checks.week_km(days), days
        wk = {"start": pw.start.isoformat(), "target_km": target, "unit": c.unit}
        if c.unit == "min":
            wk["target_min"] = sum(shown_min(d.workout.seconds) for d in days)
        out.append({**wk, "phase": pw.phase, "deload": i in c.deloads, "warnings": warns,
                    "days": [{"date": d.date.isoformat(), "slot": d.slot, "workout": workout_to_dict(d.workout)}
                             for d in days]})
    if weeks:
        out = out[:weeks]
    return {"version": VERSION, "generated": generated or datetime.now().isoformat(timespec="seconds"),
            "profile_hash": profile_hash(prof, rules), "profile": plan_profile(prof),
            "levels": {"volume": prof.volume_level, "quality": prof.quality_level,
                       "reasons": {axis: prof.level_reasons.get(axis, "") for axis in ("volume", "quality")}},
            "progress": {"plan_start": start.isoformat(), "block_start": block.isoformat(),
                         "cycle_start": _cycle_start(prof, start).isoformat(),
                         "vdot": prof.vdot_estimate,
                         "run_walk_stage": min(reached, len(library[c.rw]["ladder"])) if c.rw else None,
                         "time_trials": [{**t, "vdot": round(t["vdot"], 2)}
                                         for t in (prof.progress or {}).get("time_trials", [])],
                         "time_trial": c.tt_date.isoformat() if c.tt_date else None},
            "warnings": top, "weeks": out}
