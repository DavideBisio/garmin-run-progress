"""Split a week's km target across its slots (rules.toml [split])."""
from .config import WEEKDAYS


def split_week(target, slots, longest_km, q_km, rules, e_pace_s_per_km):
    """({weekday: km}, warnings) for the place_slots week `slots`, Monday first, km rounded to 0.1.

    L = min(long_share_cap x target, longest_km + long_over_longest_km, long_time_cap_min at E
    pace), or the E minimum (easy_min_km or easy_min_min at E pace, whichever is shorter) when that
    is longer, and never more: the caps win over keeping the easy runs shorter than L. Q gets
    q_km (the template size), unless the week can't hold Q and an L at the E minimum: then Q is
    dropped and its day is an easy one. E slots share the rest, each at least the E minimum: F runs
    when E alone would go over L and stays off (0 km) when sharing would put the easy runs under
    the minimum; E slots the rest can't fill to the minimum are dropped (0 km, the last first).
    When the easy runs are still longer than L, they stay so (warning). A remainder too small for
    any easy run is taken from L when L stays at the E minimum, else it goes to Q (a longer warm-up
    and cool-down), else to one short easy run (warning). The parts add up to target, none negative.
    """
    s = rules["split"]
    e_min = min(s["easy_min_km"], s["easy_min_min"] * 60 / e_pace_s_per_km)
    days = [d for d in WEEKDAYS if d in slots]
    of = {k: [d for d in days if slots[d] == k] for k in "LQEF"}
    warnings = []
    if of["Q"] and target - q_km * len(of["Q"]) < (e_min if of["L"] else 0):
        warnings.append(f"Q dropped ({', '.join(of['Q'])}): {target:.1f} km can't hold a {q_km:.1f} km Q "
                        f"and a long run of {e_min:.1f} km (the E minimum), so the day is easy")
        of["E"], of["Q"] = sorted(of["E"] + of["Q"], key=WEEKDAYS.index), []
    q_total = q_km * len(of["Q"])
    long_km = 0.0
    if of["L"]:
        cap = min(s["long_share_cap"] * target, longest_km + s["long_over_longest_km"],
                  s["long_time_cap_min"] * 60 / e_pace_s_per_km)
        long_km = min(max(cap, e_min), max(target - q_total, 0.0))
        if long_km < e_min:
            warnings.append(f"L: the week's {target:.1f} km is under the E minimum of {e_min:.1f} km")
    rest = max(target - long_km - q_total, 0.0)
    easy = list(of["E"])
    if of["F"] and (not easy or rest / len(easy) > long_km) and rest / (len(easy) + len(of["F"])) >= e_min:
        easy += of["F"]                                    # F on
    n = max(0, min(len(easy), int((rest + 1e-9) // e_min)))
    if easy and not n and of["L"] and long_km + rest >= 2 * e_min:
        n, long_km, rest = 1, long_km + rest - e_min, e_min      # trim L for one easy run
    easy = sorted(easy[:n], key=WEEKDAYS.index)
    easy_km, q_extra = 0.0, 0.0
    if easy:
        easy_km = rest / len(easy)
        if of["L"] and easy_km > long_km:                  # L at its cap and no F left to share
            warnings.append(f"E: {easy_km:.1f} km runs are longer than L ({long_km:.1f} km, at its cap)")
    elif rest > 1e-9:                                      # too little for an easy run of the minimum
        if of["Q"]:
            q_extra = rest / len(of["Q"])
        elif of["E"] or of["F"]:
            easy, easy_km = [(of["E"] or of["F"])[0]], rest
            warnings.append(f"E: {rest:.1f} km is under the E minimum of {e_min:.1f} km, run short")
        elif of["L"]:
            long_km += rest
            warnings.append(f"L: {long_km:.1f} km is over its cap of {max(cap, e_min):.1f} km, "
                            "the week has no other run")
    out = {d: 0.0 for d in days}
    for d in of["Q"]:
        out[d] = q_km + q_extra
    for d in of["L"]:
        out[d] = long_km
    for d in easy:
        out[d] = easy_km
    return {d: round(km, 1) for d, km in out.items()}, warnings
