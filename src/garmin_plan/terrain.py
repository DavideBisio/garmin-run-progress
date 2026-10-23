"""Hill and trail volume as flat-equivalent km: Minetti's cost of running (metrics.gap_factor, as the page)."""
from .metrics import gap_factor


def flat_equivalent_km(km, climb_m, descent_m):
    """The flat km that cost as much as km with climb_m up and descent_m down.

    Half the distance climbs and half descends, each at a steady grade (climb_m, or descent_m, over
    half the distance), and each half counts gap_factor(grade) times its length: the page's
    grade-adjusted pace factor, clamped at +-30 % as there. No climbing gives km back.
    """
    if km <= 0:
        return 0
    half = km * 1000 / 2
    return km / 2 * gap_factor(climb_m / half) + km / 2 * gap_factor(-descent_m / half)


def workout_flat_km(w):
    """A workout's flat-equivalent km: climb_m_per_km over its whole distance, as much up as down
    (a loop). Flat workouts (no climb_m_per_km) count their km."""
    climb = (w.climb_m_per_km or 0) * w.km
    return flat_equivalent_km(w.km, climb, climb) if climb else w.km
