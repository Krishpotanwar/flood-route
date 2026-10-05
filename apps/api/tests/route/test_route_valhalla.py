import json
import random

import httpx
import pytest
from route_testkit import T0, request, risk, risk_for

from floodroute.route.models import IST
from floodroute.route.valhalla import (
    COSTING,
    ValhallaRouter,
    decode_polyline6,
    encode_polyline6,
    request_body,
    route_from_response,
)
from floodroute.route.validate import plan

# HAND-WRITTEN AND UNVERIFIED. This sample is shaped from the Valhalla route API reference
# (https://valhalla.github.io/valhalla/api/route/api-reference/, read 2026-10-05). It is not a
# recording of a live Valhalla. Spike S1 must replace it with a real recording and re-run these
# tests; until then the mapping is only known to match the docs, not the server.
SHAPE = "ovjsWgf}_sC_uCwuBwyEg{CwvIgxG_aMwvI"
POINTS = [
    (12.9166, 77.6101),
    (12.919, 77.612),
    (12.9225, 77.6145),
    (12.928, 77.619),
    (12.9352, 77.6245),
]
SAMPLE = {
    "trip": {
        "locations": [
            {"type": "break", "lat": 12.9166, "lon": 77.6101, "original_index": 0},
            {"type": "break", "lat": 12.9352, "lon": 77.6245, "original_index": 1},
        ],
        "legs": [
            {
                "maneuvers": [
                    {"type": 2, "time": 90.0, "length": 0.45, "begin_shape_index": 0,
                     "end_shape_index": 2, "travel_mode": "drive", "travel_type": "motorcycle"},
                    {"type": 10, "time": 240.0, "length": 1.2, "begin_shape_index": 2,
                     "end_shape_index": 4, "travel_mode": "drive", "travel_type": "motorcycle"},
                    {"type": 4, "time": 0.0, "length": 0.0, "begin_shape_index": 4,
                     "end_shape_index": 4, "travel_mode": "drive", "travel_type": "motorcycle"},
                ],
                "summary": {"time": 330.0, "length": 1.65},
                "shape": SHAPE,
            }
        ],
        "summary": {"time": 330.0, "length": 1.65},
        "status_message": "Found route between points",
        "status": 0,
        "units": "kilometers",
        "language": "en-US",
    }
}  # fmt: skip
O, D = POINTS[0], POINTS[-1]


def segment_of(geometry):
    return {12.9166: 101, 12.9225: 102}.get(geometry[0][0])


def test_decoder_matches_the_valhalla_docs_vector():
    # https://valhalla.github.io/valhalla/api/decoding/ (Rust example test, precision 1e6)
    got = decode_polyline6("e~epoA|jfpOiDaK")
    assert got == [(42.225139, -8.670911), (42.225224, -8.670718)]


def test_encoder_reproduces_the_docs_vector_and_the_sample_shape():
    assert encode_polyline6([(42.225139, -8.670911), (42.225224, -8.670718)]) == "e~epoA|jfpOiDaK"
    assert decode_polyline6(SHAPE) == POINTS


def test_round_trip_random_india_points():
    rng = random.Random(3)
    pts = [(round(rng.uniform(8, 35), 6), round(rng.uniform(69, 97), 6)) for _ in range(200)]
    assert decode_polyline6(encode_polyline6(pts)) == pts
    assert decode_polyline6("") == []


@pytest.mark.parametrize("bad", ["_", "e~epoA|", "e~ep o", "\x7f\x7f"])
def test_malformed_polyline_raises(bad):
    with pytest.raises(ValueError):
        decode_polyline6(bad)


def test_costing_per_class():
    assert COSTING == {
        "two_wheeler": "motor_scooter", "car": "auto", "ambulance": "auto", "heavy": "truck",
    }  # fmt: skip
    for vclass, costing in COSTING.items():
        assert request_body(O, D, vclass)["costing"] == costing
    with pytest.raises(KeyError):
        request_body(O, D, "hovercraft")


def test_request_body_swaps_polygon_rings_to_lon_lat():
    ring = ((12.0, 77.0), (12.0, 77.1), (12.1, 77.1), (12.0, 77.0))
    body = request_body(O, D, "car", [ring])
    assert body["exclude_polygons"] == [[[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.0]]]
    assert body["locations"] == [{"lat": 12.9166, "lon": 77.6101}, {"lat": 12.9352, "lon": 77.6245}]
    assert "exclude_polygons" not in request_body(O, D, "car")


def test_maps_maneuvers_to_edges_and_skips_the_arrive_marker():
    r = route_from_response(SAMPLE, segment_of)
    assert [e.segment_id for e in r.edges] == [101, 102]
    assert [e.travel_time_s for e in r.edges] == [90.0, 240.0]
    assert [e.length_m for e in r.edges] == [450.0, 1200.0]
    assert r.edges[0].geometry == tuple(POINTS[0:3]) and r.edges[1].geometry == tuple(POINTS[2:5])
    assert r.total_time_s == SAMPLE["trip"]["summary"]["time"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.pop("legs"),
        lambda t: t["legs"][0].pop("shape"),
        lambda t: t["legs"][0]["maneuvers"][0].pop("time"),
        lambda t: t["legs"][0]["maneuvers"][0].update(end_shape_index=99),
        lambda t: t["legs"][0]["maneuvers"][0].update(begin_shape_index=3, end_shape_index=1),
        lambda t: t["legs"][0]["maneuvers"][0].update(time=float("nan")),
        lambda t: t["legs"][0].update(maneuvers=[]),
    ],
)
def test_malformed_response_raises_never_guesses(mutate):
    resp = json.loads(json.dumps(SAMPLE))
    mutate(resp["trip"])
    with pytest.raises(ValueError):
        route_from_response(resp, segment_of)


def _router(handler):
    client = httpx.Client(base_url="http://valhalla.test", transport=httpx.MockTransport(handler))
    return ValhallaRouter("http://valhalla.test", segment_of, client=client)


def test_router_posts_to_route_and_maps_the_response():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=SAMPLE)

    ring = ((12.0, 77.0), (12.1, 77.1), (12.0, 77.0))
    r = _router(handler)(O, D, "two_wheeler", T0.astimezone(IST), [ring])
    assert (seen[0].method, seen[0].url.path) == ("POST", "/route")
    body = json.loads(seen[0].content)
    assert body["costing"] == "motor_scooter" and body["exclude_polygons"][0][0] == [77.0, 12.0]
    assert [e.segment_id for e in r.edges] == [101, 102]


@pytest.mark.parametrize("code", [442, 170, 171, 441])
def test_no_path_errors_return_none(code):
    # error_code values from the docs error table; the JSON body shape is [U] until S1 records one
    body = {"error_code": code, "error": "No path could be found for input"}
    response = httpx.Response(400, json=body)
    assert _router(lambda req: response)(O, D, "car", T0) is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"error_code": 130, "error": "Failed to parse location"}),
        httpx.Response(400, text="not json"),
        httpx.Response(500, json={"error_code": 200}),
        httpx.Response(503),
    ],
)
def test_other_failures_raise_so_no_route_goes_out_unchecked(response):
    with pytest.raises(httpx.HTTPStatusError):
        _router(lambda req: response)(O, D, "car", T0)


def test_timeout_propagates():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(httpx.ReadTimeout):
        _router(handler)(O, D, "car", T0)


# ---- plan() over ValhallaRouter, no live server -----------------------------------------

ALT_POINTS = [(12.9166, 77.6101), (12.915, 77.619), (12.92, 77.626), (12.9352, 77.6245)]
ALT = json.loads(json.dumps(SAMPLE))  # hand-written like SAMPLE: same shape, a different road
ALT["trip"]["legs"][0].update(shape=encode_polyline6(ALT_POINTS))
ALT["trip"]["legs"][0]["maneuvers"] = [
    {"type": 2, "time": 150.0, "length": 0.8, "begin_shape_index": 0, "end_shape_index": 1},
    {"type": 10, "time": 270.0, "length": 1.5, "begin_shape_index": 1, "end_shape_index": 3},
    {"type": 4, "time": 0.0, "length": 0.0, "begin_shape_index": 3, "end_shape_index": 3},
]
SEGMENTS = {POINTS[1]: 101, POINTS[3]: 102, ALT_POINTS[1]: 201, ALT_POINTS[2]: 202}


def test_plan_over_the_valhalla_router_reroutes_around_a_flooded_maneuver():
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append(body)
        return httpx.Response(200, json=ALT if "exclude_polygons" in body else SAMPLE)

    client = httpx.Client(base_url="http://valhalla.test", transport=httpx.MockTransport(handler))
    router = ValhallaRouter("http://valhalla.test", lambda g: SEGMENTS.get(g[1]), client=client)
    table = {101: risk(0.01), 102: risk(0.9), 201: risk(0.01), 202: risk(0.02)}
    out = plan(
        request("two_wheeler"), router, risk_for(table),
        now=T0, model_version="v0", decision_id="d1",
    )  # fmt: skip

    assert ["exclude_polygons" in b for b in seen] == [False, True]
    (ring,) = seen[1]["exclude_polygons"]  # [lon, lat] pairs around the flooded maneuver
    for lat, lon in POINTS[2:5]:
        assert min(p[0] for p in ring) < lon < max(p[0] for p in ring)
        assert min(p[1] for p in ring) < lat < max(p[1] for p in ring)
    assert seen[0]["costing"] == "motor_scooter"

    safest, fastest = out.response.routes
    assert (safest.kind, safest.is_default, safest.eta_min) == ("safest", True, 7)
    assert [s.segment_id for s in safest.segments] == ["201", "202"]
    assert (fastest.kind, fastest.is_default, fastest.eta_min) == ("fastest", False, 6)
    assert [(s.segment_id, s.over_limit) for s in fastest.segments] == [
        ("101", False),
        ("102", True),
    ]
    assert safest.reasons[:2] == ["Avoiding a road where water is likely now.", "1 min longer."]
    expected = [pt for i, j in ((0, 1), (1, 3)) for pt in ALT_POINTS[i : j + 1]]
    assert decode_polyline6(safest.geometry) == expected
