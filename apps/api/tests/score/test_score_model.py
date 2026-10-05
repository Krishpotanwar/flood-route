"""Effective rainfall, g(R), logit assembly and the properties the model must keep."""

from __future__ import annotations

import copy
import json
import random
from datetime import timedelta

import pytest
from score_helpers import CFG, T0, at, fcst, row, seg, step

from floodroute.score import RainObs, ZoneInput
from floodroute.score.config import DEFAULT_PATH, parse_config
from floodroute.score.model import effective_rain, g, sigmoid, zone_rain

RAW = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))


def test_sigmoid_is_stable_at_extremes():
    assert sigmoid(0) == 0.5
    assert sigmoid(-1000) == 0.0
    assert sigmoid(1000) == 1.0
    assert 0 < sigmoid(-30) < 1e-12


def test_g_clamps_to_zero_and_one():
    assert g(5, 10, 40) == 0.0
    assert g(10, 10, 40) == 0.0
    assert g(25, 10, 40) == 0.5
    assert g(40, 10, 40) == 1.0
    assert g(90, 10, 40) == 1.0


def _zone(obs, forecasts=()):
    return zone_rain(ZoneInput(1, obs=tuple(obs), fcst=tuple(forecasts)), T0, CFG)


def test_effective_rain_blends_observed_into_forecast_over_the_window():
    zr = _zone([RainObs("gauge", T0, 20.0)], [fcst(at(30), 50.0), fcst(at(60), 50.0)])
    assert effective_rain(zr, 0, CFG).value == 20.0  # h = 0 is the observed rate
    assert effective_rain(zr, 30, CFG).value == pytest.approx(35.0)  # half the window ahead
    assert effective_rain(zr, 60, CFG).value == pytest.approx(50.0)  # forecast alone from 60 min


def test_missing_forecast_falls_back_to_persistence_and_says_so():
    zr = _zone([RainObs("gauge", T0, 20.0)])
    r = effective_rain(zr, 60, CFG)
    assert (r.value, r.fcst_missing) == (20.0, True)
    assert effective_rain(zr, 0, CFG).fcst_missing is False


def test_forecast_match_uses_tolerance_and_best_source():
    obs = [RainObs("gauge", T0, 0.0)]
    near = fcst(at(60, 1799), 30.0, source="nwp")  # 29 min 59 s from the target
    far = fcst(at(60, 1801), 99.0, source="nwp")  # just beyond the 30 min tolerance
    assert effective_rain(_zone(obs, [near]), 60, CFG).value == 30.0
    assert effective_rain(_zone(obs, [far]), 60, CFG).fcst_missing is True
    both = _zone(obs, [fcst(at(60), 10.0, "nwp"), fcst(at(60), 40.0, "imd_nowcast")])
    assert effective_rain(both, 60, CFG).value == 40.0  # nowcast outranks nwp (TRD 5)


def test_rain_source_hierarchy_and_freshness():
    old_gauge = RainObs("gauge", T0 - timedelta(minutes=25), 5.0)
    new_nowcast = RainObs("imd_nowcast", T0 - timedelta(minutes=1), 40.0)
    zr = _zone([new_nowcast, old_gauge])
    assert (zr.obs_source, zr.obs_rate) == ("gauge", 5.0)  # best rank wins while under 30 min
    stale_gauge = RainObs("gauge", T0 - timedelta(minutes=30), 5.0)  # exactly 30 min: not newer
    zr = _zone([new_nowcast, stale_gauge])
    assert (zr.obs_source, zr.obs_rate) == ("imd_nowcast", 40.0)
    zr = _zone([stale_gauge])
    assert zr.obs_source is None and zr.obs_age_s is None and not zr.has_obs


def test_no_fresh_observation_falls_back_to_forecast_now_else_zero():
    stale = RainObs("gauge", T0 - timedelta(hours=2), 70.0)
    assert _zone([stale], [fcst(T0, 12.0)]).obs_rate == 12.0
    assert _zone([stale]).obs_rate == 0.0


def test_antecedent_uses_best_ranked_source_with_a_24h_total():
    obs = [
        RainObs("gauge", T0, 1.0, None),
        RainObs("imerg", T0 - timedelta(hours=4), 0.0, 80.0),
    ]
    assert _zone(obs).mm_24h == 80.0  # imerg is old but within the antecedent age limit
    old = [RainObs("imerg", T0 - timedelta(hours=7), 0.0, 80.0)]
    assert _zone(old).mm_24h is None


def test_delta_is_derived_from_the_profile_and_zero_for_the_reference():
    assert CFG.delta("car") == 0.0
    assert CFG.delta("two_wheeler") > CFG.delta("auto_rickshaw") > CFG.delta("car")
    assert CFG.delta("car") > CFG.delta("suv") > CFG.delta("heavy")


def test_editing_a_profile_changes_the_score_on_the_next_run():  # FR-R7
    data = copy.deepcopy(RAW)
    data["vehicle_profiles"]["ambulance"].update(caution_cm=30.0, unusable_cm=45.0)
    high_clearance = parse_config(json.dumps(data))
    s = [seg(1)]
    _, base = step(at(), s, rate=25.0, cfg=CFG)
    _, edit = step(at(), s, rate=25.0, cfg=high_clearance)
    assert row(edit, vclass="ambulance").p < row(base, vclass="ambulance").p
    assert row(edit, vclass="car").p == row(base, vclass="car").p


@pytest.mark.parametrize("structure", sorted(CFG.structures))
def test_more_rain_never_lowers_p(structure):
    """Monotonic in observed rain, forecast rain and 24 h wetness, for every class and horizon,
    with and without evidence whose rules switch on or off with rain."""
    from floodroute.score import Evidence

    rng = random.Random(f"mono-{structure}")
    exp = at(0) + timedelta(hours=1)
    evidence_sets = {
        "none": (),
        "sensor_shallow": (Evidence("sensor", at(), exp, "s1", depth_cm=2.0, verified=True),),
        "probe_slow": (Evidence("probe", at(), exp, "p1", speed_ratio=0.2, contributors=9),),
        "deep_photo": (Evidence("report", at(), exp, "u1", depth_cm=60.0, verified=True),),
    }
    for name, evidence in evidence_sets.items():
        s = [seg(1, structure=structure, evidence=evidence)]
        for _ in range(2):
            fc_rate, wet = rng.uniform(0, 100), rng.uniform(0, 150)  # fixed while rain rises
            last = {}
            for rate in [float(x) for x in range(121)]:
                fc = [fcst(at(h), fc_rate + rate) for h in (30, 60, 120)]
                _, rows = step(at(), s, rate=rate, mm_24h=wet, fcst=fc)
                for key, r in rows.items():
                    assert r.p >= last.get(key, 0.0) - 1e-12, (name, key, rate)
                    last[key] = r.p
        # 24 h wetness
        last = {}
        for mm in range(0, 300, 5):
            _, rows = step(at(), s, rate=3.0, mm_24h=float(mm))
            for key, r in rows.items():
                assert r.p >= last.get(key, 0.0) - 1e-12, (name, key, mm)
                last[key] = r.p
