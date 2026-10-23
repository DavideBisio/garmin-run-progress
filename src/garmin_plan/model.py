"""A resolved workout: steps with concrete pace and HR ranges, and totals computed from the parts.

Paces are seconds per km, so the fast end of a range is the smaller number. PaceRange is the only
place that order is handled: to_speed() gives Garmin's (slow, fast) m/s pair, and nothing else
swaps bounds. Totals are never typed in; km, seconds and hard_km add up the steps.
"""
from dataclasses import dataclass, field

ROLES = ("warmup", "rep", "recovery", "cooldown")      # Garmin step types (05)
ENDS = ("dist", "time", "lap")                         # DISTANCE, TIME, LAP_BUTTON


@dataclass(frozen=True)
class PaceRange:
    """A pace target in s/km: fast_s <= slow_s."""
    fast_s: float
    slow_s: float

    def __post_init__(self):
        if not 0 < self.fast_s <= self.slow_s:
            raise ValueError(f"pace range must be 0 < fast <= slow s/km, got {self.fast_s}..{self.slow_s}")

    @property
    def mid(self):
        return (self.fast_s + self.slow_s) / 2

    def to_speed(self):
        """(slow m/s, fast m/s): Garmin's lower and upper speed limits."""
        return 1000 / self.slow_s, 1000 / self.fast_s


@dataclass(frozen=True)
class HrRange:
    lo: int
    hi: int

    def __post_init__(self):
        if not 0 < self.lo <= self.hi:
            raise ValueError(f"HR range must be 0 < lo <= hi bpm, got {self.lo}-{self.hi}")


@dataclass
class Step:
    """One step. value is metres (dist), seconds (time) or None (lap button).

    zone is the pace zone it was resolved from (E, M, T, I, R, jog or None for open targets);
    pace is None for jog and open targets. est_pace (s/km) estimates the missing dimension of time
    ends and of steps without a pace target; lap ends carry est_time and est_dist instead.
    """
    role: str
    label: str
    end: str
    value: float | None
    zone: str | None = None
    pace: PaceRange | None = None
    hr_zone: str | None = None          # "Z2", "Z4-5", "Z3 cap"
    hr: HrRange | None = None
    est_pace: float | None = None
    est_dist: float | None = None
    est_time: float | None = None
    effort: str | None = None           # pace column text for open targets ("By effort")
    note: str = ""
    hard: bool = False                  # counts in hard_km (M/T/I/R pace, hill reps)

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"unknown step role {self.role!r}")
        if self.end not in ENDS:
            raise ValueError(f"unknown step end {self.end!r}")

    def _est_pace(self):
        p = self.est_pace if self.est_pace is not None else self.pace.mid if self.pace else None
        if not p:
            raise ValueError(f"step {self.label!r} has no pace to estimate with")
        return p

    @property
    def meters(self):
        if self.end == "dist":
            return self.value
        if self.end == "time":
            return self.value * 1000 / self._est_pace()
        return self.est_dist

    @property
    def seconds(self):
        if self.end == "dist":
            return self.value * self._est_pace() / 1000
        if self.end == "time":
            return self.value
        return self.est_time

    @property
    def hard_meters(self):
        return self.meters if self.hard else 0


@dataclass
class Repeat:
    """n times the steps. skip_last_rest drops the final recovery (Garmin's skipLastRestStep);
    the default is False: the last recovery counts, on paper and on the watch."""
    n: int
    steps: list
    skip_last_rest: bool = False
    note: str = ""

    def _sum(self, attr):
        one = sum(getattr(s, attr) for s in self.steps)
        total = self.n * one
        if self.skip_last_rest and self.n > 0 and self.steps and self.steps[-1].role == "recovery":
            total -= getattr(self.steps[-1], attr)
        return total

    @property
    def meters(self):
        return self._sum("meters")

    @property
    def seconds(self):
        return self._sum("seconds")

    @property
    def hard_meters(self):
        return self._sum("hard_meters")


@dataclass
class Workout:
    """parts: warmup, the main set's blocks (steps and repeats in sequence), cooldown."""
    id: str
    variant: int
    title: str
    kind: str
    parts: list = field(default_factory=list)
    climb_m_per_km: float | None = None

    @property
    def km(self):
        return sum(p.meters for p in self.parts) / 1000

    @property
    def seconds(self):
        return sum(p.seconds for p in self.parts)

    @property
    def hard_km(self):
        return sum(p.hard_meters for p in self.parts) / 1000
