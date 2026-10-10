"""State bands, hysteresis (FR-R3), staleness (FR-R4) and coverage honesty (FR-R5)."""

from __future__ import annotations

import itertools
import random
from datetime import timedelta

import pytest
from score_helpers import CFG, T0, at, row, seg, step

from floodroute.score import Evidence, RunInput, SegmentInput, score_run
from floodroute.score.state import state_from_p

CLOSED = "impassable"


def drive(ps, step_s: int = 60, **kw):
    """One car row at horizon 0, one run per p value, `step_s` seconds apart."""
    prev, out = {}, []
    for i, p in enumerate(ps):
        now = T0 + timedelta(seconds=step_s * i)
        _, prev = step(now, [seg(1, p=min(max(p, 1e-6), 1 - 1e-6))], prev, **kw)
        out.append(row(prev))
    return out


def states(rows):
    return [r.state for r in rows]


# ---- bands -------------------------------------------------------------------------------


def test_state_from_p_bands_at_the_boundaries():
    want = [
        (0.0, "clear"), (0.0999, "clear"), (0.10, "watch"), (0.2999, "watch"),
        (0.30, "risky"), (0.4999, "risky"), (0.50, "impassable"), (1.0, "impassable"),
    ]  # fmt: skip
    for p, state in want:
        assert state_from_p(p, CFG) == state, p


# ---- FR-R3 hysteresis ------------------------------------------------------------------------


def test_close_is_immediate_and_a_closed_segment_stays_closed_between_the_thresholds():
    rows = drive([0.2, 0.55, 0.4, 0.3, 0.26, 0.5])
    assert states(rows) == ["watch", CLOSED, CLOSED, CLOSED, CLOSED, CLOSED]
    assert rows[0].closed_since is None
    assert {r.closed_since for r in rows[1:]} == {rows[1].updated_at}  # kept from the first close
    assert rows[1].reason == "closed" and rows[2].reason == "closed_hold"


def test_reopen_only_after_p_stays_below_025_for_10_minutes():
    rows = drive([0.6] + [0.2] * 12)  # one run a minute: timer starts at minute 1
    assert states(rows[:11]) == [CLOSED] * 11  # minutes 0 to 10: only 9 min below so far
    assert rows[11].state == "watch" and rows[11].reason == "reopened"  # minute 11: 10 min below
    assert (rows[11].closed_since, rows[11].reopen_ok_since) == (None, None)
    assert rows[10].reopen_ok_since == rows[1].updated_at  # timer started at the first low sample


def test_a_sample_at_025_or_above_restarts_the_reopen_timer():
    rows = drive([0.6] + [0.2] * 9 + [0.25] + [0.2] * 11)  # minute 10 is exactly 0.25
    assert rows[10].reopen_ok_since is None  # 0.25 is not below 0.25
    assert states(rows[:21]) == [CLOSED] * 21  # new timer starts at minute 11, due at minute 21
    assert rows[21].state == "watch"


def test_reopen_needs_fresh_evidence_under_15_minutes():
    low = [0.6] + [0.05] * 40
    assert set(states(drive(low, obs_age_s=900))) == {CLOSED}  # exactly 900 s is not under 900
    assert drive(low, obs_age_s=899)[-1].state == "clear"
    assert set(states(drive(low, obs=()))) == {CLOSED}  # no rain data at all


def test_a_gap_longer_than_the_hold_between_runs_restarts_the_timer():
    prev = {}
    for minute, p in [(0, 0.6), (1, 0.2), (20, 0.2), (30, 0.2)]:  # 19 min gap, then 10 min
        _, prev = step(at(minute), [seg(1, p=p)], prev)
        if minute == 20:
            assert row(prev).state == CLOSED and row(prev).reopen_ok_since == at(20)
    assert row(prev).state == "watch"  # reopened 10 min after the restarted timer
    prev = {}
    for minute, p in [(0, 0.6), (1, 0.2), (11, 0.2)]:  # a gap of exactly the hold is continuous
        _, prev = step(at(minute), [seg(1, p=p)], prev)
    assert row(prev).state == "watch"


def test_reopened_state_is_rebanded_from_p():
    assert drive([0.6] + [0.05] * 12)[-1].state == "clear"
    assert drive([0.6] + [0.2] * 12)[-1].state == "watch"


def test_a_closed_segment_stays_closed_through_a_feed_outage():
    # closes on fresh data, then the rain feed goes stale while p is low: it must not reopen
    prev = {}
    _, prev = step(at(0), [seg(1, p=0.6)], prev)
    for minute in range(5, 120, 5):
        _, prev = step(at(minute), [seg(1, p=0.05)], prev, obs_age_s=1200)
        assert row(prev).state == CLOSED


def noisy_series(seed: int) -> list[float]:
    """Three hours at one sample a minute: a noisy rise through 0.3 and 0.5, a noisy plateau
    around the close threshold, then a noisy fall through 0.25."""
    rng = random.Random(seed)
    out = []
    for m in range(180):
        if m < 60:
            mean, sd = 0.15 + 0.5 * m / 60, 0.12
        elif m < 120:
            mean, sd = 0.45, 0.15
        else:
            mean, sd = 0.45 - 0.4 * (m - 120) / 60, 0.08
        out.append(min(1.0, max(0.0, rng.gauss(mean, sd))))
    return out


def test_fr_r3_noisy_series_flips_closure_at_most_once_per_10_minutes():
    ps = noisy_series(seed=20260518)
    rows = drive(ps)
    closed = [r.state == CLOSED for r in rows]
    flips = [i for i in range(1, len(closed)) if closed[i] != closed[i - 1]]
    naive = sum(
        (state_from_p(a, CFG) == CLOSED) != (state_from_p(b, CFG) == CLOSED)
        for a, b in itertools.pairwise(ps)
    )
    assert naive >= 10  # the series is noisy enough that banding alone would flap
    assert len(flips) == 2  # one close on the way up, one reopen on the way down
    assert all(b - a >= 10 for a, b in itertools.pairwise(flips))  # never two flips within 10 min


@pytest.mark.parametrize("seed", range(40))
def test_reopen_invariants_hold_on_random_series(seed):
    """Whatever the input: p >= 0.5 is always closed; a reopen is always preceded by 10 minutes
    of p below 0.25; and a close is never followed by a reopen within 10 minutes."""
    rng = random.Random(seed)
    ps = []
    while len(ps) < 300:
        lo, hi = rng.choice([(0, 0.2), (0.2, 0.5), (0.5, 1.0), (0.0, 1.0)])
        ps += [rng.uniform(lo, hi) for _ in range(rng.randint(3, 25))]
    ps = ps[:300]
    rows = drive(ps)
    for i, (p, r) in enumerate(zip(ps, rows, strict=True)):
        if p >= 0.5:
            assert r.state == CLOSED
        if i and rows[i - 1].state == CLOSED and r.state != CLOSED:  # a reopen at minute i
            assert all(q < 0.25 for q in ps[i - 10 : i + 1])
            assert r.p == pytest.approx(p)
    closes = [i for i in range(1, 300) if rows[i].state == CLOSED and rows[i - 1].state != CLOSED]
    reopens = [i for i in range(1, 300) if rows[i].state != CLOSED and rows[i - 1].state == CLOSED]
    for c in closes:
        later = [i for i in reopens if i > c]
        assert not later or later[0] - c >= 10


# ---- FR-R4 staleness -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("age_s", "state"), [(0, "clear"), (899, "clear"), (900, "clear"), (901, "unknown")]
)
def test_clear_degrades_to_unknown_only_over_15_minutes(age_s, state):
    _, rows = step(at(), [seg(1, p=0.01)], obs_age_s=age_s)
    r = row(rows)
    assert r.state == state and r.evidence_age_s == age_s
    assert r.reason == ("stale_data" if state == "unknown" else "band")
    assert r.p == pytest.approx(0.01)  # the estimate is still reported


def test_stale_data_never_lowers_watch_risky_or_impassable():
    for p, state in [(0.2, "watch"), (0.4, "risky"), (0.6, "impassable")]:
        _, rows = step(at(), [seg(1, p=p)], obs_age_s=1200)
        assert row(rows).state == state and row(rows).confidence == "low"


def test_cutting_a_feed_flips_clear_to_unknown_within_one_scoring_cycle():
    from floodroute.score import RainObs

    last_obs = (RainObs("gauge", at(0), 0.0, 0.0),)
    prev, timeline = {}, {}
    for minute in range(0, 31, 5):
        _, prev = step(at(minute), [seg(1, p=0.01)], prev, obs=last_obs)
        timeline[minute] = row(prev).state
    assert timeline == {0: "clear", 5: "clear", 10: "clear", 15: "clear", 20: "unknown",
                        25: "unknown", 30: "unknown"}  # fmt: skip


def test_no_evidence_at_all_is_unknown_never_clear():
    _, rows = step(at(), [seg(1, p=0.01)], obs=())
    r = row(rows)
    assert (r.state, r.evidence_age_s, r.confidence) == ("unknown", None, "low")


def test_unknown_wetness_withholds_one_confidence_level():
    from floodroute.score import RainObs

    reps = (
        Evidence("report", at(minutes=-1), at(minutes=14), "u1", trust=0.9),
        Evidence("report", at(minutes=-1), at(minutes=14), "u2", trust=0.9),
    )
    wet = (RainObs("gauge", at(), 0.0, 80.0),)
    _, rows = step(at(), [seg(1, p=0.01, evidence=reps)], obs=wet)
    assert row(rows).confidence == "high"
    dry_unknown = (RainObs("gauge", at(), 0.0, None),)
    _, rows = step(at(), [seg(1, p=0.01, evidence=reps)], obs=dry_unknown)
    assert row(rows).confidence == "medium"


# ---- TRD 5: no rain source in an active alert ------------------------------------------------


def test_alert_with_no_rain_source_newer_than_30_minutes_marks_clear_and_watch_unknown():
    for p in (0.01, 0.2):
        _, rows = step(at(), [seg(1, p=p)], obs_age_s=1800, alert=True)
        r = row(rows)
        assert (r.state, r.reason) == ("unknown", "no_rain_source")
    _, rows = step(at(), [seg(1, p=0.2)], obs_age_s=1799, alert=True)
    assert row(rows).state == "watch"  # 29 min 59 s is newer than 30 min
    _, rows = step(at(), [seg(1, p=0.2)], obs_age_s=1800, alert=False)
    assert row(rows).state == "watch"  # no alert: the rule does not apply


def test_missing_rain_data_never_lowers_risky_or_impassable():
    for p, state in [(0.4, "risky"), (0.6, "impassable")]:
        _, rows = step(at(), [seg(1, p=p)], obs=(), alert=True)
        assert row(rows).state == state


# ---- FR-R5 coverage honesty ------------------------------------------------------------------


def test_unassessed_segment_has_no_state_p_or_confidence_at_any_class_or_horizon():
    closure = Evidence("official", at(-5), at(30), "police")
    s = seg(1, assessed=False, evidence=(closure,))
    _, rows = step(at(), [s], rate=80.0)  # heavy rain and an official closure change nothing
    assert len(rows) == len(CFG.vclasses) * len(CFG.horizons_min)
    for r in rows.values():
        assert r.assessed is False
        assert (r.state, r.p, r.confidence, r.evidence_age_s, r.override) == (None,) * 5


def test_unassessed_segment_needs_no_zone():
    s = SegmentInput(7, 999, False)
    res = score_run(RunInput(at(), (), (s,)), {}, CFG)
    assert all(r.state is None for r in res.rows) and not res.changes


def test_assessed_segment_without_rain_data_for_its_zone_is_an_error():
    with pytest.raises(ValueError, match="zone has no rain data"):
        score_run(RunInput(at(), (), (seg(1),)), {}, CFG)


def test_coverage_changes_are_logged():
    prev = {}
    res, prev = step(at(0), [seg(1, p=0.01)], prev)
    assert row(prev).state == "clear"
    res, prev = step(at(5), [seg(1, p=0.01, assessed=False)], prev)
    ch = [c for c in res.changes if (c.vclass, c.horizon_min) == ("car", 0)]
    assert [(c.before["state"], c.after["state"], c.reason) for c in ch] == [
        ("clear", None, "not_assessed")
    ]
    res, prev = step(at(10), [seg(1, p=0.01)], prev)
    ch = [c for c in res.changes if (c.vclass, c.horizon_min) == ("car", 0)]
    assert [(c.before["state"], c.after["state"]) for c in ch] == [(None, "clear")]
