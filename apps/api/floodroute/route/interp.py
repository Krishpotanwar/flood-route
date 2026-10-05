"""P(unusable) at an arbitrary time: linear interpolation in logit space between horizons.

Inputs are {horizon_min: p}. Time is minutes after the forecast was issued. Before the first
horizon and after the last, the end value is held (clamped).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Mapping
from itertools import pairwise

# p of exactly 0 or 1 has infinite logit; clamp so the maths stays finite.
EPS = 1e-6


def _check(p: float) -> float:
    if not 0.0 <= p <= 1.0:  # also false for NaN, which would otherwise pass every comparison
        raise ValueError(f"p must be within [0, 1], got {p!r}")
    return p


def logit(p: float) -> float:
    p = min(max(_check(p), EPS), 1.0 - EPS)
    return math.log(p / (1.0 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def p_at(points: Mapping[int, float], minute: float) -> float:
    """Interpolated p at `minute`. Exact at a horizon, and between equal values."""
    if not points:
        raise ValueError("no horizons")
    hs = sorted(points)
    if minute <= hs[0]:
        return _check(points[hs[0]])
    if minute >= hs[-1]:
        return _check(points[hs[-1]])
    i = bisect_right(hs, minute) - 1
    a, b = hs[i], hs[i + 1]
    pa, pb = _check(points[a]), _check(points[b])
    if minute == a or pa == pb:
        return pa
    return sigmoid(logit(pa) + (minute - a) / (b - a) * (logit(pb) - logit(pa)))


def knots(points: Mapping[int, float], lo: float, hi: float) -> list[int]:
    """Horizons strictly inside (lo, hi): the only places a window maximum can hide."""
    return [h for h in sorted(points) if lo < h < hi]


def first_crossing(points: Mapping[int, float], threshold: float, after: float) -> float | None:
    """Earliest minute >= `after` at which p >= threshold, or None if it never gets there.

    Exact (solved per bracket, not sampled): between horizons p is monotone in logit space.
    """
    if p_at(points, after) >= threshold:
        return after
    target = logit(threshold)
    for a, b in pairwise(sorted(points)):
        if b <= after:
            continue
        la, lb = logit(points[a]), logit(points[b])
        if lb >= target:
            lo = max(a, after)
            l_lo = la + (lb - la) * (lo - a) / (b - a)
            # l_lo < target <= lb, so lb > l_lo and the division is safe
            return lo + (target - l_lo) / (lb - l_lo) * (b - lo)
    return None
