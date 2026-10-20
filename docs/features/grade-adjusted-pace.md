# Grade-adjusted pace

Running uphill costs more energy than the same speed on the flat; gentle downhill costs less. Without correcting for that, a hilly year looks like a fitness drop. Functions: `prepare` (grade), `minetti`, `gapFactor`.

## Grade per sample

For each sample `i`, find the furthest-back sample `k` that is still at least 100 m behind:

```text
while r.d[i] - r.d[k+1] >= 100: k++      # two pointers, O(n)
grade[i] = (e[i] - e[k]) / 10 / (d[i] - d[k])    if d[i]-d[k] >= 60 and both elevations exist
         = 0                                     otherwise
```

The 100 m window smooths GPS/barometric noise; a sample-to-sample grade over 30 m would swing wildly. Grades are stored as a `Float32Array` on `run._g`.

## Energy cost (Minetti 2002)

Minetti et al. measured the metabolic cost of running on gradients from −45% to +45%, fitted as a 5th-order polynomial in grade `i` (a fraction):

```text
C(i) = 155.4 i⁵ − 30.4 i⁴ − 43.3 i³ + 46.3 i² + 19.5 i + 3.6     [J / kg / m]
```

`C(0) = 3.6`. The grade is clamped to ±0.30 before evaluating.

```text
gapFactor(i) = C(i) / 3.6
```

| Grade | Factor | Meaning |
|---|---|---|
| −10% | ~0.60 | 1 km here costs like 0.60 km on the flat |
| 0% | 1.00 | |
| +5% | ~1.30 | |
| +10% | ~1.66 | |

## Applying it

The page converts distance to "equivalent flat distance": each segment's distance is multiplied by `gapFactor(grade)`. Grade-adjusted pace is then `time / equivalent distance`. Used by [pace-at-heart-rate](pace-at-heart-rate.md).

Best efforts are **not** grade-adjusted: a 5 km time is reported as run.

## Limits

- Very steep or technical trails aren't well described by a treadmill-derived curve; that's one reason trail runs are excluded by default.
- Without elevation data (`e = 0`) the grade is 0, so pace is unadjusted.
