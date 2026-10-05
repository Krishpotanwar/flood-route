"""Tests for POST /v1/route."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from floodroute.api.deps import get_db, get_router
from floodroute.api.main import create_app
from floodroute.route.models import (
    Edge,
    LatLon,
    Polygon,
    Route,
)

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE_1 = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"
SEG_LINE_2 = "SRID=4326;LINESTRING(77.59 12.98, 77.60 12.99)"


def test_route_outside_india_rejected(client):
    r = client.post(
        "/v1/route",
        json={
            "origin": {"lat": 0.0, "lon": 0.0},
            "destination": {"lat": 12.9352, "lon": 77.6245},
            "vclass": "car",
            "depart_at": datetime.now(UTC).isoformat(),
        },
    )
    assert r.status_code == 422


def test_route_arrival_time_validation_and_decision_log(app_db):
    now = datetime.now(UTC)

    # 1. Setup zone and segments in DB
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values
            (9001, 19001, %s, 'primary', 1, true),
            (9002, 19002, %s, 'primary', 1, true),
            (9003, 19003, %s, 'secondary', 1, true)
        """,
        (SEG_LINE_1, SEG_LINE_2, SEG_LINE_1),
    )

    # Segment 9001 is clear across all horizons
    for h in (0, 30, 60, 120):
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9001, 'car', %s, 0.05, 0.0, 0.0, 'clear', 'high', 30, 'v0.0.1', %s)
            """,
            (h, now),
        )

    # Segment 9002 is IMPASSABLE
    for h in (0, 30, 60, 120):
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9002, 'car', %s, 0.85, 30.0, 45.0, 'impassable', 'high', 30, 'v0.0.1', %s)
            """,
            (h, now),
        )

    # Segment 9003 is CLEAR (the safe detour)
    for h in (0, 30, 60, 120):
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9003, 'car', %s, 0.02, 0.0, 0.0, 'clear', 'high', 30, 'v0.0.1', %s)
            """,
            (h, now),
        )

    # 2. Mock router: first query returns edges [9001, 9002].
    # When 9002 is excluded, returns detour edges [9001, 9003].
    def fake_router(
        origin: LatLon,
        dest: LatLon,
        vclass: str,
        depart: datetime,
        exclude_polygons: Sequence[Polygon] = (),
    ) -> Route | None:
        if not exclude_polygons:
            # Direct route via 9002 (flooded)
            return Route((
                Edge(segment_id=9001, geometry=((12.97, 77.58), (12.98, 77.59)), travel_time_s=60.0),
                Edge(segment_id=9002, geometry=((12.98, 77.59), (12.99, 77.60)), travel_time_s=120.0),
            ))
        else:
            # Safe detour via 9003
            return Route((
                Edge(segment_id=9001, geometry=((12.97, 77.58), (12.98, 77.59)), travel_time_s=60.0),
                Edge(segment_id=9003, geometry=((12.98, 77.59), (12.99, 77.60)), travel_time_s=180.0),
            ))

    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_router] = lambda: fake_router

    with TestClient(app) as test_client:
        r = test_client.post(
            "/v1/route",
            json={
                "origin": {"lat": 12.970, "lon": 77.580},
                "destination": {"lat": 12.990, "lon": 77.600},
                "vclass": "car",
                "depart_at": now.isoformat(),
                "profile": "citizen",
                "lang": "en",
            },
        )
        assert r.status_code == 200
        data = r.json()

        # Arrival-time validation loop found the safe detour!
        assert data["no_safe_route"] is False
        assert len(data["routes"]) == 2  # safest and fastest
        safest = next(rt for rt in data["routes"] if rt["kind"] == "safest")
        assert safest["is_default"] is True
        assert safest["worst_state"] == "clear"
        seg_ids = [s["segment_id"] for s in safest["segments"]]
        assert "9003" in seg_ids
        assert "9002" not in seg_ids

        # Verify route_decision was recorded in PostgreSQL
        decision_id = data["decision_id"]
        cur = app_db.execute(
            "select vclass, no_safe_route from route_decision where decision_id = %s",
            (decision_id,),
        )
        dec_row = cur.fetchone()
        assert dec_row is not None
        assert dec_row[0] == "car"
        assert dec_row[1] is False
