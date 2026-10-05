import math
import random

import pytest

from floodroute.route.interp import first_crossing, knots, logit, p_at, sigmoid

H = {0: 0.05, 30: 0.10, 60: 0.75, 120: 0.75}


def test_exact_at_horizons():
    for h, p in H.items():
        assert p_at(H, h) == p


def test_midpoint_is_linear_in_logit_space():
    want = sigmoid((logit(0.10) + logit(0.75)) / 2)
    assert p_at(H, 45) == pytest.approx(want)
    assert want != pytest.approx((0.10 + 0.75) / 2)  # not a plain average of p


def test_clamped_beyond_both_ends():
    assert p_at(H, -10) == 0.05
    assert p_at(H, 0) == 0.05
    assert p_at(H, 500) == 0.75


@pytest.mark.parametrize("pa,pb", [(0.0, 1.0), (1.0, 0.0), (0.0, 0.0), (1.0, 1.0), (0.0, 0.3)])
def test_exact_zero_and_one_are_safe(pa, pb):
    pts = {0: pa, 30: pb}
    for m in (0, 1, 15, 29.999, 30):
        p = p_at(pts, m)
        assert math.isfinite(p) and 0.0 <= p <= 1.0
    assert p_at(pts, 0) == pa and p_at(pts, 30) == pb  # exact at the horizons, no 0.999999


def test_zero_to_one_crosses_half_in_the_middle():
    assert p_at({0: 0.0, 30: 1.0}, 15) == pytest.approx(0.5)


@pytest.mark.parametrize("bad", [float("nan"), -0.1, 1.1, float("inf")])
def test_bad_p_raises_instead_of_passing_comparisons(bad):
    with pytest.raises(ValueError):
        p_at({0: bad, 30: 0.1}, 10)
    with pytest.raises(ValueError):
        p_at({0: 0.1, 30: bad}, 100)  # also when only a clamped end holds it
    with pytest.raises(ValueError):
        logit(bad)


def test_empty_and_single_horizon():
    with pytest.raises(ValueError):
        p_at({}, 5)
    assert p_at({60: 0.3}, 0) == 0.3 == p_at({60: 0.3}, 999)


def test_result_stays_between_neighbours_and_is_monotone():
    rng = random.Random(7)
    for _ in range(300):
        pa, pb = rng.random(), rng.random()
        pts = {0: pa, 30: pb}
        lo, hi = min(pa, pb), max(pa, pb)
        vals = [p_at(pts, m / 2) for m in range(61)]
        assert all(lo - 1e-12 <= v <= hi + 1e-12 for v in vals)
        assert vals == sorted(vals) or vals == sorted(vals, reverse=True)


def test_insertion_order_does_not_matter():
    shuffled = {120: 0.75, 30: 0.10, 0: 0.05, 60: 0.75}
    for m in (0, 12.5, 40, 45, 90, 200):
        assert p_at(shuffled, m) == p_at(H, m)


def test_first_crossing_fr_rt2_is_minute_40():
    assert first_crossing(H, 0.25, 0) == pytest.approx(40.0, abs=1e-9)
    assert p_at(H, 40.0) == pytest.approx(0.25, abs=1e-9)
    assert first_crossing(H, 0.25, 25) == pytest.approx(40.0, abs=1e-9)
    assert first_crossing(H, 0.25, 45) == 45  # already over the limit: returns the start


def test_first_crossing_none_when_it_never_gets_there():
    assert first_crossing({0: 0.05, 30: 0.1, 60: 0.2, 120: 0.2}, 0.25, 0) is None
    assert first_crossing({0: 0.9, 30: 0.1}, 0.5, 31) is None  # falling forecast, past the peak


def test_first_crossing_in_the_clamped_tail():
    # rises above the limit only at the last horizon, which then holds
    assert first_crossing({0: 0.05, 60: 0.05, 120: 0.9}, 0.5, 0) == pytest.approx(
        60 + (logit(0.5) - logit(0.05)) / (logit(0.9) - logit(0.05)) * 60
    )


def test_first_crossing_agrees_with_dense_sampling():
    rng = random.Random(11)
    step = 0.1
    for _ in range(100):
        pts = {h: rng.random() for h in (0, 30, 60, 120)}
        thr, after = rng.uniform(0.05, 0.5), rng.uniform(0, 100)
        got = first_crossing(pts, thr, after)
        sampled = next(
            (m for m in (after + i * step for i in range(2001)) if p_at(pts, m) >= thr), None
        )
        if got is None:
            assert sampled is None
        else:
            assert sampled is not None and 0 <= sampled - got <= step + 1e-9


def test_knots_are_strictly_inside():
    assert knots(H, 0, 120) == [30, 60]
    assert knots(H, 30, 60) == []
    assert knots(H, 29, 61) == [30, 60]
