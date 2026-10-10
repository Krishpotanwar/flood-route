"""Evidence rules (TRD 6.3), corroboration (FR-R8), decay, and human overrides."""

from __future__ import annotations

import itertools
import math

import pytest
from score_helpers import CFG, at, fcst, logit, row, seg, step

from floodroute.score import Evidence, Override

BASE = 0.05  # model p for a car at horizon 0 in these tests


def report(source: str, age_s: int = 0, trust: float = 0.9, **kw) -> Evidence:
    return Evidence("report", at(seconds=-age_s), at(60), source, trust=trust, **kw)


def car(evidence=(), overrides=(), p=BASE, h=0, **kw):
    """The car row at horizon h for a segment whose model p is `p`."""
    s = seg(1, p=p, evidence=tuple(evidence), overrides=tuple(overrides))
    _, rows = step(kw.pop("now", at()), [s], **kw)
    return row(rows, h=h)


def same_as_without_evidence(evidence) -> bool:
    """True if the evidence changes no row at all (every class and horizon)."""
    now = at()
    _, a = step(now, [seg(1, p=BASE, evidence=tuple(evidence))])
    _, b = step(now, [seg(1, p=BASE)])
    return all(a[k].p == b[k].p and a[k].state == b[k].state for k in a)


def test_contributors_must_be_an_integer_count():
    with pytest.raises((TypeError, ValueError)):
        Evidence("probe", at(), at(60), "p1", speed_ratio=0.2, contributors=5.5)
    with pytest.raises((TypeError, ValueError)):
        Evidence("probe", at(), at(60), "p1", speed_ratio=0.2, contributors=-1)
    Evidence("probe", at(), at(60), "p1", speed_ratio=0.2, contributors=5)  # floor holds


def test_replay_accepts_zulu_utc_suffix():
    import json

    from floodroute.score.replay import replay

    lines = [
        json.dumps(
            {
                "type": "segment",
                "ts": "2027-05-18T11:00:00Z",
                "segment_id": 1,
                "zone_id": 10,
                "assessed": False,
            }
        ),
        json.dumps({"type": "tick", "ts": "2027-05-18T11:00:00Z"}),
    ]
    ticks = list(replay(lines, CFG))
    assert len(ticks) == 1 and ticks[0]["ts"] == "2027-05-18T11:00:00+00:00"


# ---- FR-R8 corroboration ----------------------------------------------------------------


def test_single_report_never_closes_and_has_no_effect():
    assert same_as_without_evidence([report("u1")])
    r = car([report("u1")])
    assert r.state == "clear" and r.evidence_rules == ()


def test_two_independent_reports_close():
    r = car([report("u1", 5), report("u2", 120)])
    assert r.p == pytest.approx(0.6)
    assert (r.state, r.reason, r.evidence_rules) == (
        "impassable",
        "closed",
        ("reports_corroborated",),
    )
    assert r.closed_since == at()


def test_same_source_twice_does_not_count():
    assert same_as_without_evidence([report("u1", 10), report("u1", 200)])
    assert same_as_without_evidence(
        [report("u1", 10), report("u1", 200), report("u2", 5, trust=0.3)]
    )


def test_corroboration_window_is_15_minutes_inclusive():
    assert car([report("u1", 0), report("u2", 900)]).state == "impassable"
    assert same_as_without_evidence([report("u1", 0), report("u2", 901)])


def test_only_trusted_reports_count():
    assert same_as_without_evidence([report("u1", trust=0.49), report("u2", trust=0.49)])
    assert same_as_without_evidence([report("u1"), report("u2", trust=0.49)])
    assert car([report("u1", trust=0.5), report("u2", trust=0.5)]).state == "impassable"


def test_other_evidence_kinds_do_not_corroborate_a_report():
    probe = Evidence("probe", at(), at(60), "p1", speed_ratio=0.9, contributors=9)
    sensor = Evidence("sensor", at(), at(60), "s1", depth_cm=1.0)
    assert same_as_without_evidence([report("u1"), probe, sensor])


def test_expired_evidence_is_ignored_and_expiry_is_exclusive():
    gone = [
        Evidence("report", at(-5), at(), "u1", trust=0.9),
        Evidence("report", at(-5), at(), "u2", trust=0.9),
    ]
    assert same_as_without_evidence(gone)
    live = [Evidence("report", at(-5), at(seconds=1), s, trust=0.9) for s in ("u1", "u2")]
    assert not same_as_without_evidence(live)


def test_ineffective_evidence_does_not_refresh_staleness():
    # a lone report is fresh, but it changed nothing, so the row still rests on the 10 min old rain
    r = car([report("u1", 5)], obs_age_s=600)
    assert r.evidence_age_s == 600
    r = car([report("u1", 5), report("u2", 60)], obs_age_s=600)
    assert r.evidence_age_s == 5  # corroborated: the newest report is evidence the row uses


# ---- verified depth ------------------------------------------------------------------------


def sensor(depth: float, age_s: int = 0, verified: bool = True, source: str = "s1", kind="sensor"):
    return Evidence(kind, at(seconds=-age_s), at(60), source, depth_cm=depth, verified=verified)


def test_verified_depth_at_unusable_sets_p_to_090_for_classes_it_exceeds():
    ev = [sensor(30.0)]  # car unusable is 30 cm, so equal counts
    assert car(ev).p == pytest.approx(0.9)
    rows = step(at(), [seg(1, p=BASE, evidence=tuple(ev))])[1]
    assert row(rows, vclass="two_wheeler").p == pytest.approx(0.9)  # unusable 15 cm
    assert row(rows, vclass="heavy").evidence_rules == ()  # unusable 50 cm
    assert row(rows, vclass="suv").evidence_rules == ()  # unusable 40 cm
    assert car([sensor(29.9)]).evidence_rules == ()


def test_unverified_depth_is_ignored():
    assert same_as_without_evidence([sensor(80.0, verified=False)])


def test_verified_photo_report_counts_but_probe_depth_does_not():
    photo = report("u1", depth_cm=35.0, verified=True)
    assert car([photo]).p == pytest.approx(0.9)
    ghost = Evidence("probe", at(), at(60), "p1", depth_cm=80.0, verified=True)
    assert same_as_without_evidence([ghost])


def test_evidence_weight_decays_with_age_by_tau():
    tau_s = CFG.evidence.tau_min * 60
    for age_s in (0, 600, 1200, 3000):
        w = math.exp(-age_s / tau_s)
        assert car([sensor(40.0, age_s)]).p == pytest.approx(BASE + w * (0.9 - BASE))


def test_evidence_effect_decays_toward_zero_at_later_horizons():
    ev = [sensor(40.0), report("u1"), report("u2")]
    _, rows = step(at(), [seg(1, p=BASE, evidence=tuple(ev))])
    gains = [row(rows, h=h).p - BASE for h in CFG.horizons_min]
    assert gains[0] == pytest.approx(0.9 - BASE)  # full effect at horizon 0
    assert all(a > b > 0 for a, b in itertools.pairwise(gains))  # strictly fading
    assert gains[-1] < 0.2 * gains[0]
    # the fade matches exp(-h / horizon_tau) for the floor that dominates here
    for h, gain in zip(CFG.horizons_min, gains, strict=True):
        assert gain == pytest.approx(math.exp(-h / CFG.evidence.horizon_tau_min) * (0.9 - BASE))


def test_latest_reading_from_a_source_replaces_its_earlier_one():
    deep_then_shallow = [sensor(40.0, 600), sensor(2.0, 60)]
    shallow_only = [sensor(2.0, 60)]
    assert car(deep_then_shallow, p=0.4).p == car(shallow_only, p=0.4).p
    shallow_then_deep = [sensor(2.0, 600), sensor(40.0, 60)]
    r = car(shallow_then_deep, p=0.4)
    assert r.evidence_rules == ("depth_unusable",)


def test_shallow_reading_with_rain_below_trigger_caps_p_at_020():
    r = car([sensor(5.0)], p=0.4)  # car caution is 15 cm, underpass trigger is 10 mm/h
    assert r.p == pytest.approx(0.2) and r.evidence_rules == ("depth_below_caution",)
    camera = car([sensor(5.0, kind="camera")], p=0.4)
    assert camera.p == pytest.approx(0.2)
    assert car([sensor(5.0)], p=0.4, rate=9.9).p == pytest.approx(0.2)  # just below r_low = 10
    assert car([sensor(5.0)], p=0.4, rate=10.0).evidence_rules == ()  # at the trigger: not below
    assert car([sensor(5.0)], p=0.4, rate=25.0).evidence_rules == ()  # raining above trigger


def test_cap_needs_known_rain_and_a_forecast_at_later_horizons():
    ev = [sensor(5.0)]
    s = seg(1, p=0.4, evidence=tuple(ev))
    _, rows = step(at(), [s], obs=())  # no rain observation at all: rain unknown
    assert row(rows).evidence_rules == ()
    _, rows = step(at(), [s])  # observation but no forecast: only horizon 0 is known
    assert row(rows, h=0).evidence_rules == ("depth_below_caution",)
    assert row(rows, h=60).evidence_rules == ()
    _, rows = step(at(), [s], fcst=[fcst(at(60), 2.0)])
    assert row(rows, h=60).evidence_rules == ("depth_below_caution",)
    _, rows = step(at(), [s], fcst=[fcst(at(60), 30.0)])  # heavy rain forecast: no cap
    assert row(rows, h=60).evidence_rules == ()


def test_a_cap_never_hides_a_hazard_signal():
    r = car([sensor(5.0, source="s1"), report("u1"), report("u2")], p=0.4)
    assert r.p == pytest.approx(0.6) and r.state == "impassable"
    deep_and_shallow = car([sensor(5.0, source="s1"), sensor(60.0, source="s2")], p=0.4)
    assert deep_and_shallow.p == pytest.approx(0.9)


# ---- probe -------------------------------------------------------------------------------


def probe(ratio=0.3, n=9, age_s=0):
    return Evidence("probe", at(seconds=-age_s), at(60), "p1", speed_ratio=ratio, contributors=n)


def test_probe_adds_one_logit_during_rain_only():
    p0 = BASE
    want = 1 / (1 + math.exp(-(logit(p0) + 1.0)))
    assert car([probe()], rate=1.0).p == pytest.approx(want)
    assert car([probe()], rate=1.0).evidence_rules == ("probe_slow",)
    assert car([probe(ratio=0.4)], rate=1.0).evidence_rules == ()  # needs below 0.4
    assert car([probe(n=4)], rate=1.0).evidence_rules == ()  # k-anonymity floor of 5
    assert car([probe(n=5)], rate=1.0).evidence_rules == ("probe_slow",)
    assert car([probe()], rate=0.0).evidence_rules == ()  # not raining
    assert car([probe()], rate=1.0, obs=()).evidence_rules == ()  # rain unknown


def test_probe_logit_decays_with_age():
    w = math.exp(-1)  # 20 min at tau 20 min
    want = 1 / (1 + math.exp(-(logit(BASE) + w)))
    assert car([probe(age_s=1200)], rate=1.0).p == pytest.approx(want)


# ---- official closure and other overrides ----------------------------------------------------


def official(start_min: float, end_min: float) -> Evidence:
    return Evidence("official", at(start_min), at(end_min), "traffic-police")


def test_official_closure_beats_the_model_and_sets_p_to_one():
    r = car([official(-5, 25)], p=0.001)
    assert (r.state, r.p, r.override, r.reason) == ("impassable", 1.0, "close", "override_close")
    # even over a verified shallow reading that would otherwise cap p
    r = car([official(-5, 25), sensor(2.0)], p=0.001)
    assert r.state == "impassable" and r.p == 1.0
    assert r.closed_since is None  # an overlay: the model's own latch is untouched


def test_closure_window_start_inclusive_end_exclusive():
    scheduled = [Override("close", at(10), at(40))]
    assert car(overrides=scheduled, now=at(9, 59)).state == "clear"
    assert car(overrides=scheduled, now=at(10)).state == "impassable"
    assert car(overrides=scheduled, now=at(39, 59)).state == "impassable"
    assert car(overrides=scheduled, now=at(40)).state == "clear"
    assert car([official(-30, 25)], now=at(24, 59)).state == "impassable"
    assert car([official(-30, 25)], now=at(25)).state == "clear"  # expired: back to the model


def test_future_dated_official_evidence_is_rejected_not_scheduled():
    with pytest.raises(ValueError, match="future"):
        car([official(10, 40)])  # a scheduled closure belongs in an Override, not in evidence


def test_closure_applies_at_a_horizon_only_while_it_is_in_force_then():
    # FR-RT2 shape: a closure that ends 40 min from now covers h = 0 and 30, not 60 or 120
    _, rows = step(at(), [seg(1, p=0.001, evidence=(official(-5, 40),))])
    states = {h: row(rows, h=h).state for h in CFG.horizons_min}
    assert states == {0: "impassable", 30: "impassable", 60: "clear", 120: "clear"}
    # one that starts in 45 min covers only 60 and 120
    _, rows = step(at(), [seg(1, p=0.001, overrides=(Override("close", at(45), at(300)),))])
    states = {h: row(rows, h=h).state for h in CFG.horizons_min}
    assert states == {0: "clear", 30: "clear", 60: "impassable", 120: "impassable"}


def test_override_from_the_console_acts_like_an_official_closure():
    r = car(overrides=[Override("close", at(-1), at(120))], p=0.001)
    assert (r.state, r.override) == ("impassable", "close")


def test_closure_expiry_reverts_to_the_model_and_logs_the_reason():
    s = [seg(1, p=0.001, evidence=(official(-5, 25),))]
    r1, rows = step(at(), s)
    assert row(rows).state == "impassable"
    r2, rows = step(at(25), s, rows)
    assert row(rows).state == "clear" and row(rows).override is None
    ch = [c for c in r2.changes if (c.vclass, c.horizon_min) == ("car", 0)]
    assert [(c.before["state"], c.after["state"], c.reason) for c in ch] == [
        ("impassable", "clear", "override_expired")
    ]
    assert [c.reason for c in r1.changes if (c.vclass, c.horizon_min) == ("car", 0)] == [
        "override_close"
    ]


def test_reopen_override_lowers_a_model_closure_to_at_most_watch_and_expires():
    s = [seg(1, p=0.8, overrides=(Override("reopen", at(), at(30)),))]
    _r1, rows = step(at(), s)
    r = row(rows)
    assert (r.state, r.override, r.reason) == ("watch", "reopen", "override_reopen")
    assert r.p == pytest.approx(CFG.overrides.reopen_cap_p)
    assert r.closed_since == at()  # the model's latch continues underneath
    _, rows = step(at(30), s, rows)  # expired, model still says 0.8
    r = row(rows)
    assert (r.state, r.override, r.reason) == ("impassable", None, "closed")


def test_reopen_only_acts_on_an_impassable_state():
    r = car(overrides=[Override("reopen", at(), at(30))], p=0.4)
    assert (r.state, r.override, r.p) == ("risky", None, pytest.approx(0.4))


def test_close_beats_reopen():
    both = [Override("reopen", at(), at(30)), Override("close", at(), at(30))]
    assert car(overrides=both, p=0.8).state == "impassable"


def test_force_watch_lifts_clear_and_unknown_but_not_higher_states():
    fw = [Override("force_watch", at(), at(30))]
    r = car(overrides=fw, p=0.001)
    assert (r.state, r.override) == ("watch", "force_watch")
    assert r.p == pytest.approx(CFG.states.watch_min)
    r = car(overrides=fw, p=0.001, obs=())  # no data: would be unknown
    assert (r.state, r.override) == ("watch", "force_watch")
    assert car(overrides=fw, p=0.4).state == "risky"
    assert car(overrides=fw, p=0.8).state == "impassable"
