import json
import math
from dataclasses import replace

import pytest
from pydantic import ValidationError
from route_testkit import T0, edge, risk

from floodroute.route.models import (
    DEFAULT,
    HORIZONS,
    Edge,
    EdgeIn,
    RouteRequest,
    RouteResponse,
    SegmentRisk,
)
from floodroute.route.models import Route as RouteModel

# TRD 8.2 request example
TRD_REQUEST = {
    "origin": {"lat": 12.9166, "lon": 77.6101},
    "destination": {"lat": 12.9352, "lon": 77.6245},
    "vclass": "two_wheeler",
    "depart_at": "2027-05-18T17:40:00+05:30",
    "profile": "citizen",
    "lang": "kn",
}


def with_(**changes):
    return {**TRD_REQUEST, **changes}


def test_the_trd_example_request_is_valid():
    req = RouteRequest.model_validate(TRD_REQUEST)
    assert req.depart_at.utcoffset().total_seconds() == 5.5 * 3600
    assert req.vclass == "two_wheeler" and req.lang == "kn"
    defaults = RouteRequest.model_validate(
        {k: v for k, v in TRD_REQUEST.items() if k not in ("profile", "lang")}
    )
    assert (defaults.profile, defaults.lang) == ("citizen", "en")


@pytest.mark.parametrize(
    "bad",
    [
        with_(origin={"lat": 77.6101, "lon": 12.9166}),  # lat and lon swapped
        with_(origin={"lat": 51.5, "lon": -0.12}),  # London
        with_(destination={"lat": float("nan"), "lon": 77.6}),
        with_(destination={"lat": 12.9, "lon": float("inf")}),
        with_(origin={"lat": 12.9}),
        with_(origin={"lat": 12.9, "lon": 77.6, "accuracy": 5}),  # unknown field
        with_(vclass="bicycle"),
        with_(vclass=None),
        with_(profile="fire"),
        with_(lang="EN"),
        with_(lang="english"),
        with_(lang="e1"),
        with_(depart_at="2027-05-18T17:40:00"),  # no offset: ambiguous, rejected
        with_(depart_at="soon"),
        {**TRD_REQUEST, "extra": 1},
    ],
)
def test_bad_requests_are_rejected_at_the_boundary(bad):
    with pytest.raises(ValidationError):
        RouteRequest.model_validate(bad)


def test_requests_in_india_at_the_edges_are_accepted():
    for lat, lon in [(8.08, 77.55), (34.1, 74.8), (23.0, 68.2), (27.5, 97.2), (11.6, 92.7)]:
        RouteRequest.model_validate(with_(origin={"lat": lat, "lon": lon}))


def test_config_rejects_unordered_bands_and_thresholds_past_impassable():
    with pytest.raises(ValueError):
        replace(DEFAULT, watch_p=0.4)  # watch above risky
    with pytest.raises(ValueError):
        replace(DEFAULT, max_iterations=-1)
    assert DEFAULT.thresholds == {"citizen": 0.25, "ambulance": 0.45}
    assert (DEFAULT.watch_p, DEFAULT.risky_p, DEFAULT.impassable_p) == (0.10, 0.30, 0.50)


@pytest.mark.parametrize(
    "field",
    ["exclude_buffer_m", "max_depart_lead_min", "dwell_s", "commit_zone_m", "closed_memory_s",
     "min_saving_s", "min_saving_frac"],
)  # fmt: skip
@pytest.mark.parametrize("bad", [-1.0, float("nan")])
def test_config_rejects_values_that_would_silently_disable_a_rule(field, bad):
    with pytest.raises(ValueError):
        replace(DEFAULT, **{field: bad})
    with pytest.raises(ValueError):
        replace(DEFAULT, min_saving_frac=1.5)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p, s: (p.pop(60), s.pop(60)),  # a missing horizon could hide a peak
        lambda p, s: (p.update({45: 0.1}), s.update({45: "watch"})),
        lambda p, s: s.pop(30),  # state keys must match p keys
        lambda p, s: p.update({30: float("nan")}),
        lambda p, s: p.update({30: 1.0001}),
        lambda p, s: p.update({30: -0.0001}),
        lambda p, s: s.update({30: "safe"}),
        lambda p, s: s.update({30: "Clear"}),
    ],
)
def test_malformed_segment_risk_fails_closed(mutate):
    p = dict.fromkeys(HORIZONS, 0.1)
    s = dict.fromkeys(HORIZONS, "watch")
    mutate(p, s)
    with pytest.raises(ValueError):
        SegmentRisk(T0, p, s)


def test_segment_risk_needs_an_aware_time_and_accepts_the_bounds():
    with pytest.raises(ValueError):
        SegmentRisk(
            T0.replace(tzinfo=None),
            dict.fromkeys(HORIZONS, 0.1),
            dict.fromkeys(HORIZONS, "watch"),
        )
    assert risk(0.0).p[0] == 0.0 and risk(1.0).p[120] == 1.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_edge_rejects_nonsense_times_and_lengths(bad):
    with pytest.raises(ValueError):
        Edge(1, (), bad)
    with pytest.raises(ValueError):
        Edge(1, (), 1.0, bad)


def test_unknown_junctions_hold_and_zero_length_with_geometry_is_rejected():
    assert Edge(1, ((12.9, 77.6), (12.91, 77.6)), 60.0).turn_off_after is False
    assert EdgeIn(segment_id=1, travel_time_s=60.0).turn_off_after is False
    with pytest.raises(ValidationError):
        EdgeIn(
            segment_id=1,
            travel_time_s=60.0,
            length_m=0.0,
            geometry=[{"lat": 12.9, "lon": 77.6}, {"lat": 12.91, "lon": 77.6}],
        )
    ok = EdgeIn(
        segment_id=1,
        travel_time_s=60.0,
        length_m=100.0,
        geometry=[{"lat": 12.9, "lon": 77.6}, {"lat": 12.91, "lon": 77.6}],
    )
    assert ok.length_m == 100.0


def test_a_route_needs_edges_and_sums_its_time():
    with pytest.raises(ValueError):
        RouteModel(())
    assert math.isclose(RouteModel((edge(1, 1.5), edge(2, 2))).total_time_s, 210.0)


def test_response_json_has_the_trd_shape():
    from route_testkit import FakeRouter, request, risk_for, route

    from floodroute.route.validate import plan

    out = plan(
        request(),
        FakeRouter(lambda n, p: route(edge(1, 31))),
        risk_for({1: risk(0.18, confidence="medium", age=140)}),
        now=T0,
        model_version="v0.3.1",
        decision_id="c1f2",
    )
    d = json.loads(out.response.model_dump_json())
    assert set(d) == {
        "decision_id", "model_version", "no_safe_route", "valid_until", "routes",
        "guidance_when_no_route", "lang",
    }  # fmt: skip
    r = d["routes"][0]
    assert set(r) == {
        "kind", "is_default", "eta_min", "delta_min", "worst_state", "data_age_s",
        "reasons", "segments", "geometry",
    }  # fmt: skip
    assert r["segments"] == [
        {"segment_id": "1", "assessed": True, "state": "watch", "p": 0.18,
         "confidence": "medium", "evidence_age_s": 140, "over_limit": False}
    ]  # fmt: skip
    assert (r["eta_min"], r["data_age_s"], r["worst_state"]) == (31, 140, "watch")
    assert d["no_safe_route"] is False and d["valid_until"] == "2027-05-18T19:40:00+05:30"


def test_json_schemas_build_for_the_openapi_contract():
    assert "no_safe_route" in RouteResponse.model_json_schema()["properties"]
    assert RouteRequest.model_json_schema()["additionalProperties"] is False
