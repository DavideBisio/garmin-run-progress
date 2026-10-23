"""Split a week's km target across its slots (rules.toml [split])."""
from .config import WEEKDAYS


def split_week(target, slots, longest_km, q_km, rules, e_pace_s_per_km):
    """{weekday: km} for the place_slots week `slots`, Monday first, rounded to 0.1 km.

    L = min(long_share_cap x target, longest_km + long_over_longest_km, long_time_cap_min at E
    pace), never below the E minimum (easy_min_km or easy_min_min at E pace, whichever is shorter).
    Q gets q_km (the template size). E slots share the rest, each between the E minimum and L:
    F runs when E alone would go over L and stays off (0 km) when sharing would put the easy runs
    under the minimum; E slots the rest can't fill to the minimum are dropped (0 km, the last
    first). A remainder too small for any easy run is topped up from L when L stays at the E
    minimum, else it goes to L. When the easy runs would still be longer than L, L and the easy
    runs even out. The parts add up to target.
    """
    s = rules["split"]
    e_min = min(s["easy_min_km"], s["easy_min_min"] * 60 / e_pace_s_per_km)
    days = [d for d in WEEKDAYS if d in slots]
    of = {k: [d for d in days if slots[d] == k] for k in "LQEF"}
    q_total = q_km * len(of["Q"])
    long_km = 0.0
    if of["L"]:
        long_km = min(s["long_share_cap"] * target, longest_km + s["long_over_longest_km"],
                      s["long_time_cap_min"] * 60 / e_pace_s_per_km)
        long_km = min(max(long_km, e_min), max(target - q_total, 0.0))
    rest = target - long_km - q_total
    easy = list(of["E"])
    if of["F"] and (not easy or rest / len(easy) > long_km) and rest / (len(easy) + len(of["F"])) >= e_min:
        easy += of["F"]                                    # F on
    n = max(0, min(len(easy), int((rest + 1e-9) // e_min)))
    if easy and not n and of["L"] and long_km + rest >= 2 * e_min:
        n, long_km, rest = 1, long_km + rest - e_min, e_min      # trim L for one easy run
    easy = sorted(easy[:n], key=WEEKDAYS.index)
    easy_km = 0.0
    if easy:
        easy_km = rest / len(easy)
        if of["L"] and easy_km > long_km:                  # even out: no easy run longer than L
            long_km = easy_km = (target - q_total) / (len(easy) + 1)
    elif of["L"]:
        long_km += rest
    out = {d: 0.0 for d in days}
    for d in of["Q"]:
        out[d] = q_km
    for d in of["L"]:
        out[d] = long_km
    for d in easy:
        out[d] = easy_km
    return {d: round(km, 1) for d, km in out.items()}
