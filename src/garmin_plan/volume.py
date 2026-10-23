"""Weekly volume curve: 4-week blocks of ramp and deload. Unit-agnostic (km or minutes, see 08)."""


def settings(rules):
    """block_curve keyword arguments from rules.toml [volume]."""
    v = rules["volume"]
    return {"ramp": v["ramp"], "deload": v["deload"], "deload_every": v["deload_every"],
            "floor": v["start_floor"], "next_from": v["next_block_from_week"]}


def _check(deload_every):
    if deload_every < 2:
        raise ValueError(f"deload_every must be 2 or more, got {deload_every}")


def align_deloads(weeks, deload_every, phase_starts=(), lead=0):
    """Deload week indices (0-based) over `weeks` weeks: every deload_every-th week after `lead`
    (the partial first week), moved one week earlier, else one later, when it would fall on a
    phase's first week, so a phase doesn't start with a lighter week. A deload stays put when both
    neighbours are phase starts or would leave no build week since the last deload. The blocks
    after a moved deload keep their length. Pass the weeks before the taper only: it has no deloads.
    """
    _check(deload_every)
    starts, out = set(phase_starts), []
    prev, i = lead - 1, lead + deload_every - 1
    while i < weeks:
        if i in starts:
            i = next((j for j in (i - 1, i + 1) if j < weeks and j not in starts and j - prev >= 2), i)
        out.append(i)
        prev, i = i, i + deload_every
    return out


def block_curve(start, weeks, ramp=0.08, deload=0.85, deload_every=4, floor=10.0, next_from=2,
                deloads=None, partial_first=False):
    """Target volume for each of `weeks` weeks.

    Build weeks run x1.00, x1 + ramp, x1 + 2 ramp ... of the block's base, and a deload week is
    x deload of it. The next block's base is the previous block's week `next_from` (week 2: + ramp,
    +8 % by default). start is clamped up to floor (a restart after a break; 08 handles detraining).
    Deloads fall every deload_every-th week unless `deloads` lists the indices (align_deloads).
    With partial_first, week 0 is a partial week held at the start volume and not ramped.
    """
    _check(deload_every)
    base = max(start, floor)
    lead = 1 if partial_first and weeks else 0
    if deloads is None:
        deloads = align_deloads(weeks, deload_every, lead=lead)
    deloads = set(deloads)
    out, k = [base] * lead, 0
    for i in range(lead, weeks):
        if i in deloads:
            out.append(base * deload)
            base *= 1 + ramp * (next_from - 1)
            k = 0
        else:
            out.append(base * (1 + ramp * k))
            k += 1
    return out
