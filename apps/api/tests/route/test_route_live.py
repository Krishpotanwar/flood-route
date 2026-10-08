"""Opt-in local Valhalla/PostGIS integration, with synthetic risk in a disposable database.

Run with FLOODROUTE_LIVE_ROUTER_URL=http://127.0.0.1:8002 and FLOODROUTE_REQUIRE_DB=1.
This checks genuine graph-edge avoidance with synthetic risk, not field accuracy.
"""

import os
from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from floodroute.api.deps import db_segment_of, get_db
from floodroute.api.main import create_app
from floodroute.route.models import DEFAULT, HORIZONS
from floodroute.route.valhalla import ValhallaRouter, decode_polyline6
from floodroute.route.validate import exclusion_polygon

LIVE_URL = os.environ.get("FLOODROUTE_LIVE_ROUTER_URL")


def point(coords):
    return {"lat": coords[0], "lon": coords[1]}


def line_wkt(coords):
    return "SRID=4326;LINESTRING(" + ",".join(f"{lon} {lat}" for lat, lon in coords) + ")"


@pytest.mark.skipif(
    not LIVE_URL, reason="set FLOODROUTE_LIVE_ROUTER_URL for a local Bengaluru graph"
)
def test_live_closure_avoidance_and_reroute(app_db, monkeypatch):
    assert app_db.execute("select current_database()").fetchone()[0].startswith("fr_test_")
    monkeypatch.setenv("VALHALLA_URL", LIVE_URL)
    now = datetime.now(UTC)
    # Existing smoke-helper public landmarks: Indiranagar and Silk Board.
    origin, destination = (12.9719, 77.6412), (12.9172, 77.6228)
    sid = 95101
    with httpx.Client(base_url=LIVE_URL, timeout=5.0) as transport:
        way_ids = []

        def segment_of(way_id, coords):
            way_ids.append(way_id)
            return db_segment_of(app_db, way_id, coords)

        router = ValhallaRouter(LIVE_URL, segment_of, transport)
        baseline = router(origin, destination, "car", now)
        assert baseline is not None and len(baseline.edges) == len(way_ids)
        baseline_ways = tuple(way_ids)
        counts = Counter(baseline_ways)
        total_m = sum(edge.length_m for edge in baseline.edges)
        distance_m, candidates = 0.0, []
        for i, (way_id, edge) in enumerate(zip(baseline_ways, baseline.edges)):
            if (
                counts[way_id] == 1
                and 50 <= edge.length_m <= 300
                and DEFAULT.commit_zone_m < distance_m < total_m - DEFAULT.commit_zone_m
            ):
                candidates.append((i, abs(distance_m - total_m / 2)))
            distance_m += edge.length_m
        assert candidates, "local graph needs an interior short edge on a unique OSM way"
        closed_index = min(candidates, key=lambda candidate: candidate[1])[0]
        interior = baseline.edges[closed_index]
        app_db.execute(
            """insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
               values (%s, %s, %s, 'primary', 1, true)""",
            (sid, baseline_ways[closed_index], line_wkt(interior.geometry)),
        )
        for horizon in HORIZONS:
            app_db.execute(
                """insert into segment_risk
                   (segment_id, vclass, horizon_min, p_unusable, state, confidence,
                    evidence_age_s, model_version, updated_at)
                   values (%s, 'car', %s, 0.02, 'clear', 'high', 0, 'live-test', %s)""",
                (sid, horizon, now),
            )
        current = router(origin, destination, "car", now)
        assert current is not None
        closed_indexes = [i for i, edge in enumerate(current.edges) if edge.segment_id == sid]
        assert closed_indexes == [closed_index]
        closed_edge = current.edges[closed_indexes[0]]

    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    request = {
        "origin": point(origin),
        "destination": point(destination),
        "vclass": "car",
        "depart_at": now.isoformat(),
        "profile": "citizen",
    }
    with TestClient(app) as client:
        clear = client.post("/v1/route", json=request)
        assert clear.status_code == 200, clear.text
        assert clear.json()["routes"][0]["is_default"] is True
        assert clear.json()["routes"][0]["segments"][0]["state"] == "clear"
        app_db.execute(
            "update segment_risk set p_unusable = 0.95, state = 'impassable' where segment_id = %s",
            (sid,),
        )
        blocked = client.post("/v1/route", json=request)
        assert blocked.status_code == 200, blocked.text
        response = blocked.json()
        assert response["no_safe_route"] is False
        chosen = next(route for route in response["routes"] if route["is_default"])
        rejected = next(route for route in response["routes"] if not route["is_default"])
        assert rejected["kind"] == "fastest"
        assert any(s["segment_id"] == str(sid) and s["over_limit"] for s in rejected["segments"])
        assert chosen["geometry"] != rejected["geometry"]
        assert all(not segment["over_limit"] for segment in chosen["segments"])
        ring = exclusion_polygon(closed_edge, DEFAULT.exclude_buffer_m)
        polygon = "SRID=4326;POLYGON((" + ",".join(f"{lon} {lat}" for lat, lon in ring) + "))"
        assert not app_db.execute(
            "select ST_Intersects(ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s))",
            (line_wkt(decode_polyline6(chosen["geometry"])), polygon),
        ).fetchone()[0]

        edges = [
            {
                "segment_id": edge.segment_id,
                "travel_time_s": edge.travel_time_s,
                "length_m": edge.length_m,
                "turn_off_after": edge.turn_off_after,
                "geometry": [point(coords) for coords in edge.geometry],
            }
            for edge in current.edges
        ]
        tick = {**request, "current_edges": edges}
        suggested = client.post("/v1/route/reroute", json=tick)
        assert suggested.status_code == 200, suggested.text
        suggestion = suggested.json()
        assert (suggestion["action"], suggestion["code"], suggestion["warn"]) == (
            "suggest",
            "suggest",
            True,
        )
        assert suggestion["reason_keys"] == ["reroute.road_flooded"]
        assert all(s["segment_id"] != str(sid) for s in suggestion["suggested_route"]["segments"])
        tick["trip_state"] = suggestion["trip_state"]
        tick["depart_at"] = (now + timedelta(seconds=30)).isoformat()
        dwell = client.post("/v1/route/reroute", json=tick)
        assert dwell.status_code == 200, dwell.text
        assert (dwell.json()["action"], dwell.json()["code"], dwell.json()["warn"]) == (
            "keep",
            "dwell",
            True,
        )
        tick["origin"] = point(closed_edge.geometry[0])
        tick["current_edges"] = edges[closed_indexes[0] :]
        held = client.post("/v1/route/reroute", json=tick)
        assert held.status_code == 200, held.text
        assert (held.json()["action"], held.json()["code"], held.json()["warn"]) == (
            "hold",
            "commit_zone",
            True,
        )
        assert held.json()["suggested_route"] is None

        # A closure enclosing the origin has no usable alternate: never recommend its baseline.
        app_db.execute(
            "update segment set osm_way_id = %s, geom = ST_GeomFromEWKT(%s) where segment_id = %s",
            (baseline_ways[0], line_wkt(baseline.edges[0].geometry), sid),
        )
        reference_blocked = client.post("/v1/route", json=request)
        assert reference_blocked.status_code == 200, reference_blocked.text
        closed = reference_blocked.json()
        assert closed["no_safe_route"] is True
        assert closed["routes"] and all(not route["is_default"] for route in closed["routes"])
        assert any(
            segment["segment_id"] == str(sid) and segment["over_limit"]
            for route in closed["routes"]
            for segment in route["segments"]
        )
