"""Graph mapping checked against a genuine local Valhalla public-landmark recording.

fixtures/indiranagar_silk_board.json was recorded 2026-10-07 on Valhalla3.9.1-f28832966
with a Bengaluru OSM graph. It contains route costing/geometry, without flood observations.
"""

import json
import random
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import pytest
from route_testkit import T0, risk, risk_for

from floodroute.api.deps import db_segment_of, get_router
from floodroute.route.models import IST, RouteRequest
from floodroute.route.valhalla import (
    COSTING,
    TRACE_ATTRIBUTES,
    ValhallaRouter,
    decode_polyline6,
    encode_polyline6,
    request_body,
    route_from_response,
)
from floodroute.route.validate import plan

RECORDING = json.loads((Path(__file__).parent / "fixtures/indiranagar_silk_board.json").read_text())
SAMPLE, TRACE = RECORDING["route"], RECORDING["trace"]
SHAPE = SAMPLE["trip"]["legs"][0]["shape"]
POINTS = decode_polyline6(SHAPE)
LOCATIONS = RECORDING["route_request"]["locations"]
O, D = [(p["lat"], p["lon"]) for p in LOCATIONS]


def segment_of(way_id, geometry):
    return way_id


def _router(handler):
    client = httpx.Client(base_url="http://valhalla.test", transport=httpx.MockTransport(handler))
    return ValhallaRouter("http://valhalla.test", segment_of, client=client)


def _recorded_response(req):
    return httpx.Response(200, json=SAMPLE if req.url.path == "/route" else TRACE)


def test_decoder_matches_the_valhalla_docs_vector():
    # https://valhalla.github.io/valhalla/api/decoding/ (Rust example test, precision 1e6)
    assert decode_polyline6("e~epoA|jfpOiDaK") == [(42.225139, -8.670911), (42.225224, -8.670718)]


def test_encoder_reproduces_the_docs_vector_and_recorded_shape():
    assert encode_polyline6([(42.225139, -8.670911), (42.225224, -8.670718)]) == "e~epoA|jfpOiDaK"
    assert encode_polyline6(POINTS) == SHAPE


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
        "two_wheeler": "motor_scooter",
        "car": "auto",
        "ambulance": "auto",
        "heavy": "truck",
    }
    for vclass, costing in COSTING.items():
        assert request_body(O, D, vclass)["costing"] == costing
    with pytest.raises(KeyError):
        request_body(O, D, "hovercraft")


def test_request_body_swaps_polygon_rings_to_lon_lat():
    ring = ((12.0, 77.0), (12.0, 77.1), (12.1, 77.1), (12.0, 77.0))
    body = request_body(O, D, "car", [ring])
    assert body["exclude_polygons"] == [[[77.0, 12.0], [77.1, 12.0], [77.1, 12.1], [77.0, 12.0]]]
    assert body["locations"] == LOCATIONS
    assert "exclude_polygons" not in request_body(O, D, "car")


def test_recorded_graph_edges_preserve_every_way_geometry_and_cumulative_eta():
    route = route_from_response(SAMPLE, [TRACE], segment_of)
    assert len(route.edges) == 102
    assert [e.segment_id for e in route.edges] == [e["way_id"] for e in TRACE["edges"]]
    elapsed = 0
    for edge, traced in zip(route.edges, TRACE["edges"], strict=True):
        assert edge.geometry == tuple(
            POINTS[traced["begin_shape_index"] : traced["end_shape_index"] + 1]
        )
        assert edge.length_m == traced["length"] * 1000
        assert edge.travel_time_s == traced["end_node"]["elapsed_time"] - elapsed
        elapsed = traced["end_node"]["elapsed_time"]
    assert route.total_time_s == pytest.approx(SAMPLE["trip"]["summary"]["time"], abs=0.01)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r, t: r["trip"].pop("legs"),
        lambda r, t: r["trip"].update(legs=[]),
        lambda r, t: r["trip"].update(units="miles"),
        lambda r, t: r["trip"]["summary"].update(time=1),
        lambda r, t: r["trip"]["legs"][0]["summary"].update(time=float("nan")),
        lambda r, t: r["trip"]["legs"][0].pop("shape"),
        lambda r, t: t.pop("shape"),
        lambda r, t: t.update(shape=encode_polyline6([(0, 0), *POINTS[1:]])),
        lambda r, t: t.update(units="miles"),
        lambda r, t: t.pop("edges"),
        lambda r, t: t.update(edges=[]),
        lambda r, t: t["edges"][0].update(way_id=0),
        lambda r, t: t["edges"][0].update(way_id=-1),
        lambda r, t: t["edges"][0].update(way_id=True),
        lambda r, t: t["edges"][0].update(begin_shape_index=True),
        lambda r, t: t["edges"][0].update(end_shape_index=len(POINTS)),
        lambda r, t: t["edges"][0].update(end_shape_index=0),
        lambda r, t: t["edges"][1].update(begin_shape_index=3),
        lambda r, t: t["edges"][1].update(begin_shape_index=1),
        lambda r, t: t["edges"][0].update(length=-1),
        lambda r, t: t["edges"][0].update(length=float("inf")),
        lambda r, t: t["edges"][0].update(length=10**400),
        lambda r, t: t["edges"][0].update(length=True),
        lambda r, t: t["edges"][0]["end_node"].pop("elapsed_time"),
        lambda r, t: t["edges"][0]["end_node"].update(elapsed_time=float("nan")),
        lambda r, t: t["edges"][1]["end_node"].update(elapsed_time=0),
        lambda r, t: t["edges"][-1]["end_node"].update(elapsed_time=2000),
        lambda r, t: t["edges"].pop(),
    ],
)
def test_malformed_or_incomplete_graph_response_never_guesses(mutate):
    response, trace = deepcopy(SAMPLE), deepcopy(TRACE)
    mutate(response, trace)
    with pytest.raises(ValueError):
        route_from_response(response, [trace], segment_of)


def test_router_walks_the_exact_route_with_matching_costing_departure_and_units():
    seen = []

    def handler(req):
        seen.append(req)
        return _recorded_response(req)

    ring = ((12.0, 77.0), (12.1, 77.1), (12.0, 77.0))
    route = _router(handler)(O, D, "two_wheeler", T0.astimezone(IST), [ring])
    assert [(r.method, r.url.path) for r in seen] == [
        ("POST", "/route"),
        ("POST", "/trace_attributes"),
    ]
    requested, traced = [json.loads(r.content) for r in seen]
    assert requested["exclude_polygons"][0][0] == [77.0, 12.0]
    assert traced["costing"] == requested["costing"] == "motor_scooter"
    assert traced["date_time"] == requested["date_time"]
    assert requested["date_time"] == {"type": 1, "value": "2027-05-18T17:40"}
    assert traced["units"] == requested["units"] == "kilometers"
    assert traced["shape_match"] == "edge_walk" and traced["encoded_polyline"] == SHAPE
    assert traced["filters"] == {"action": "include", "attributes": list(TRACE_ATTRIBUTES)}
    assert len(route.edges) == 102


@pytest.mark.parametrize("code", [442, 170, 171, 441, 167, 176])
def test_route_no_path_and_exclusion_limits_return_none(code):
    body = {"error_code": code, "error": "No path could be found for input"}
    assert _router(lambda req: httpx.Response(400, json=body))(O, D, "car", T0) is None


def test_naive_depart_raises_instead_of_reading_as_utc():
    with pytest.raises(ValueError, match="timezone-aware"):
        request_body(O, D, "car", depart=datetime(2026, 10, 5, 12, 0))  # noqa: DTZ001


@pytest.mark.parametrize(
    "depart",
    [
        datetime(2026, 10, 7, 6, 30, tzinfo=UTC),
        datetime(2026, 10, 7, 12, 0, tzinfo=IST),
    ],
)
def test_equivalent_instants_encode_the_same_origin_local_clock(depart):
    assert request_body(O, D, "car", depart=depart)["date_time"] == {
        "type": 1,
        "value": "2026-10-07T12:00",
    }


def test_departure_conversion_preserves_the_origin_local_calendar_day():
    depart = datetime(2026, 10, 7, 23, 50, tzinfo=UTC)
    assert request_body(O, D, "car", depart=depart)["date_time"] == {
        "type": 1,
        "value": "2026-10-08T05:20",
    }


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"error_code": 130, "error": "Failed to parse location"}),
        httpx.Response(400, text="not json"),
        httpx.Response(500, json={"error_code": 200}),
        httpx.Response(503),
    ],
)
def test_route_failure_propagates(response):
    with pytest.raises(httpx.HTTPStatusError):
        _router(lambda req: response)(O, D, "car", T0)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"error_code": 442, "error": "No trace path"}),
        httpx.Response(400, json={"error_code": 443, "error": "Edge walk failed"}),
        httpx.Response(503),
    ],
)
def test_trace_failure_never_falls_back_or_reads_as_no_path(response):
    def handler(req):
        return httpx.Response(200, json=SAMPLE) if req.url.path == "/route" else response

    with pytest.raises(httpx.HTTPStatusError):
        _router(handler)(O, D, "car", T0)


@pytest.mark.parametrize("path", ["/route", "/trace_attributes"])
def test_success_status_with_invalid_json_is_an_upstream_failure(path):
    def handler(req):
        return (
            httpx.Response(200, text="not json")
            if req.url.path == path
            else _recorded_response(req)
        )

    with pytest.raises(RuntimeError, match="unexpected Valhalla response"):
        _router(handler)(O, D, "car", T0)


def test_malformed_trace_is_an_upstream_failure():
    def handler(req):
        trace = deepcopy(TRACE)
        trace["edges"] = []
        return httpx.Response(200, json=SAMPLE if req.url.path == "/route" else trace)

    with pytest.raises(RuntimeError, match="Valhalla graph edges"):
        _router(handler)(O, D, "car", T0)


@pytest.mark.parametrize("path", ["/route", "/trace_attributes"])
def test_timeout_propagates(path):
    def handler(req):
        if req.url.path == path:
            raise httpx.ReadTimeout("slow", request=req)
        return _recorded_response(req)

    with pytest.raises(httpx.ReadTimeout):
        _router(handler)(O, D, "car", T0)


def test_request_router_closes_its_http_client():
    dependency = get_router(None)
    router = next(dependency)
    assert not router.client.is_closed
    dependency.close()
    assert router.client.is_closed


def test_flooded_interior_graph_edge_is_checked_inside_one_long_maneuver():
    flooded = TRACE["edges"][41]
    geometry = tuple(POINTS[flooded["begin_shape_index"] : flooded["end_shape_index"] + 1])
    maneuver = SAMPLE["trip"]["legs"][0]["maneuvers"][0]
    assert maneuver["begin_shape_index"] < flooded["begin_shape_index"]
    assert flooded["end_shape_index"] < maneuver["end_shape_index"]
    seen = []

    def handler(req):
        body = json.loads(req.content)
        if req.url.path == "/route":
            seen.append(body)
            if "exclude_polygons" in body:
                return httpx.Response(400, json={"error_code": 442, "error": "No path"})
        return _recorded_response(req)

    client = httpx.Client(base_url="http://valhalla.test", transport=httpx.MockTransport(handler))
    router = ValhallaRouter(
        "http://valhalla.test", lambda way, g: 101 if g == geometry else None, client
    )
    req = RouteRequest(origin=LOCATIONS[0], destination=LOCATIONS[1], vclass="car", depart_at=T0)
    result = plan(
        req,
        router,
        risk_for({101: risk(0.9)}),
        now=T0,
        model_version="test",
        decision_id="interior",
    )
    assert result.response.no_safe_route
    assert all(not route.is_default for route in result.response.routes)
    assert any(
        s.segment_id == "101" and s.over_limit
        for route in result.response.routes
        for s in route.segments
    )
    ring = seen[1]["exclude_polygons"][0]
    assert all(
        min(p[0] for p in ring) < lon < max(p[0] for p in ring)
        and min(p[1] for p in ring) < lat < max(p[1] for p in ring)
        for lat, lon in geometry
    )
    assert not min(p[1] for p in ring) < POINTS[0][0] < max(p[1] for p in ring)


def test_inventory_match_requires_same_way_and_proximity(app_db):
    coords = ((12.97, 77.64), (12.971, 77.64))
    app_db.execute("""insert into segment
        (segment_id, osm_way_id, geom, road_class, city_id, assessed) values
        (9001, 12345, 'SRID=4326;LINESTRING(77.6401 12.97,77.6401 12.971)', 'primary',1,true),
        (9002, 67890, 'SRID=4326;LINESTRING(77.64 12.97,77.64 12.971)', 'primary',1,true),
        (9003, 12345, 'SRID=4326;LINESTRING(77.65 12.97,77.65 12.971)', 'primary',1,true),
        (9004, 12345, 'SRID=4326;LINESTRING(77.64 12.97,77.64 12.971)', 'primary',1,false)
    """)
    assert db_segment_of(app_db, 12345, coords) == 9001
    assert db_segment_of(app_db, 67890, coords) == 9002
    assert db_segment_of(app_db, 88888, coords) is None
    assert db_segment_of(app_db, 12345, ((13, 78), (13.001, 78))) is None


def test_same_way_adjacent_assessed_rows_fail_closed_instead_of_picking_one(app_db):
    app_db.execute("""insert into segment
        (segment_id, osm_way_id, geom, road_class, city_id, assessed) values
        (9001,12345,'SRID=4326;LINESTRING(77.64 12.97,77.64 12.971)','primary',1,true),
        (9002,12345,'SRID=4326;LINESTRING(77.64 12.971,77.64 12.972)','primary',1,true)
    """)
    with pytest.raises(RuntimeError, match="ambiguous assessed inventory"):
        db_segment_of(app_db, 12345, ((12.97, 77.64), (12.971, 77.64)))


def test_inventory_database_failure_propagates():
    class BrokenConnection:
        def execute(self, *args):
            raise psycopg.OperationalError("database unavailable")

    with pytest.raises(psycopg.OperationalError):
        db_segment_of(BrokenConnection(), 12345, ((12.97, 77.64), (12.971, 77.64)))
