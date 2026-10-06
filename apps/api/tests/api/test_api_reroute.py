"""Tests for POST /v1/route/reroute (TRD 7.4, FR-RT5 to FR-RT7)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

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


def setup_segments(app_db, now: datetime):
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values
            (9101, 19101, %s, 'primary', 1, true),
            (9102, 19102, %s, 'primary', 1, true),
            (9103, 19103, %s, 'secondary', 1, true)
        """,
        (SEG_LINE_1, SEG_LINE_2, SEG_LINE_1),
    )

    # 9101 is Clear
    for h in (0, 30, 60, 120):
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9101, 'car', %s, 0.02, 0.0, 0.0, 'clear', 'high', 30, 'v0.0.1', %s)
            """,
            (h, now),
        )

    # 9102 is Impassable
    for h in (0, 30, 60, 120):
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9102, 'car', %s, 0.95, 45.0, 60.0, 'impassable', 'high', 30, 'v0.0.1', %s)
            """,
            (h, now),
        )

    # 9103 is Clear (detour)
    for h in (0, 30, 60, 120):
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9103, 'car', %s, 0.01, 0.0, 0.0, 'clear', 'high', 30, 'v0.0.1', %s)
            """,
            (h, now),
        )


def make_router():
    def fake_router(
        origin: LatLon,
        dest: LatLon,
        vclass: str,
        depart: datetime,
        exclude_polygons: Sequence[Polygon] = (),
    ) -> Route | None:
        if not exclude_polygons:
            # Baseline route contains impassable 9102
            return Route(
                (
                    Edge(9101, ((12.97, 77.58), (12.98, 77.59)), 120.0, 800.0, turn_off_after=True),
                    Edge(9102, ((12.98, 77.59), (12.99, 77.60)), 180.0, 1000.0, turn_off_after=True),
                )
            )
        # Detour route avoids 9102 using 9103
        return Route(
            (
                Edge(9101, ((12.97, 77.58), (12.98, 77.59)), 120.0, 800.0, turn_off_after=True),
                Edge(9103, ((12.98, 77.59), (12.99, 77.58)), 150.0, 900.0, turn_off_after=True),
            )
        )

    return fake_router


def test_reroute_requires_current_edges(client):
    r = client.post(
        "/v1/route/reroute",
        json={
            "origin": {"lat": 12.97, "lon": 77.58},
            "destination": {"lat": 12.99, "lon": 77.60},
            "vclass": "car",
            "current_edges": [],
        },
    )
    assert r.status_code == 400
    assert "current_edges" in r.json()["detail"]


def test_reroute_suggests_detour_when_current_route_is_flooded(app_db):
    now = datetime.now(UTC)
    setup_segments(app_db, now)

    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_router] = make_router

    tc = TestClient(app)
    resp = tc.post(
        "/v1/route/reroute",
        json={
            "origin": {"lat": 12.97, "lon": 77.58},
            "destination": {"lat": 12.99, "lon": 77.60},
            "vclass": "car",
            "current_edges": [
                {
                    "segment_id": 9101,
                    "travel_time_s": 120.0,
                    "length_m": 800.0,
                    "turn_off_after": True,
                    "geometry": [{"lat": 12.97, "lon": 77.58}, {"lat": 12.98, "lon": 77.59}],
                },
                {
                    "segment_id": 9102,
                    "travel_time_s": 180.0,
                    "length_m": 1000.0,
                    "turn_off_after": True,
                    "geometry": [{"lat": 12.98, "lon": 77.59}, {"lat": 12.99, "lon": 77.60}],
                },
            ],
            "trip_state": {
                "last_suggestion_at": None,
                "baseline_band": 0,
                "closed_at": {},
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "suggest"
    assert body["code"] == "suggest"
    assert body["warn"] is True
    assert "reroute.road_flooded" in body["reason_keys"]
    assert any("flooded" in r.lower() for r in body["reasons"])
    assert body["suggested_route"] is not None
    assert body["current_violations_count"] == 1
    assert body["current_worst_state"] == "impassable"
    # State updated with suggestion timestamp
    assert body["trip_state"]["last_suggestion_at"] is not None
    assert "9102" in body["trip_state"]["closed_at"]


def test_reroute_holds_in_commit_zone_without_turn_off(app_db):
    now = datetime.now(UTC)
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (9104, 19104, %s, 'primary', 1, true)
        """,
        (SEG_LINE_1,),
    )
    for h in (0, 30, 60, 120):
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9104, 'car', %s, 0.95, 45.0, 60.0, 'impassable', 'high', 30, 'v0.0.1', %s)
            """,
            (h, now),
        )

    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_router] = make_router

    tc = TestClient(app)
    resp = tc.post(
        "/v1/route/reroute",
        json={
            "origin": {"lat": 12.97, "lon": 77.58},
            "destination": {"lat": 12.99, "lon": 77.60},
            "vclass": "car",
            "current_edges": [
                {
                    "segment_id": 9104,
                    "travel_time_s": 30.0,
                    "length_m": 150.0,  # inside 300m commit zone
                    "turn_off_after": False,  # no turn off before flooded edge
                    "geometry": [{"lat": 12.97, "lon": 77.58}, {"lat": 12.98, "lon": 77.59}],
                }
            ],
            "trip_state": {
                "last_suggestion_at": None,
                "baseline_band": 0,
                "closed_at": {},
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "hold"
    assert body["code"] == "commit_zone"
    assert body["warn"] is True
    assert "reroute.commit_zone" in body["reason_keys"]
    assert body["suggested_route"] is None


def test_reroute_respects_dwell_time(app_db):
    now = datetime.now(UTC)
    setup_segments(app_db, now)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_router] = make_router

    tc = TestClient(app)
    # last_suggestion was only 30 seconds ago (dwell limit is 150s)
    recent_suggestion = (now - timedelta(seconds=30)).isoformat()

    resp = tc.post(
        "/v1/route/reroute",
        json={
            "origin": {"lat": 12.97, "lon": 77.58},
            "destination": {"lat": 12.99, "lon": 77.60},
            "vclass": "car",
            "depart_at": now.isoformat(),
            "current_edges": [
                {
                    "segment_id": 9101,  # clear, 800m long, with turn off
                    "travel_time_s": 120.0,
                    "length_m": 800.0,
                    "turn_off_after": True,
                },
                {
                    "segment_id": 9102,  # impassable ahead
                    "travel_time_s": 120.0,
                    "length_m": 800.0,
                    "turn_off_after": True,
                },
            ],
            "trip_state": {
                "last_suggestion_at": recent_suggestion,
                "baseline_band": 0,
                "closed_at": {},
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "keep"
    assert body["code"] == "dwell"
    assert body["warn"] is True  # still warns of flood ahead!
    assert "reroute.flood_ahead" in body["reason_keys"]


def test_reroute_all_clear_no_trigger(app_db):
    now = datetime.now(UTC)
    setup_segments(app_db, now)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_router] = make_router

    tc = TestClient(app)
    resp = tc.post(
        "/v1/route/reroute",
        json={
            "origin": {"lat": 12.97, "lon": 77.58},
            "destination": {"lat": 12.99, "lon": 77.58},
            "vclass": "car",
            "current_edges": [
                {
                    "segment_id": 9101,  # clear
                    "travel_time_s": 120.0,
                    "length_m": 800.0,
                    "turn_off_after": True,
                },
                {
                    "segment_id": 9103,  # clear
                    "travel_time_s": 150.0,
                    "length_m": 900.0,
                    "turn_off_after": True,
                },
            ],
            "trip_state": {
                "last_suggestion_at": None,
                "baseline_band": 0,
                "closed_at": {},
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "keep"
    assert body["code"] == "no_trigger"
    assert body["warn"] is False
    assert body["current_violations_count"] == 0
    assert body["current_worst_state"] == "clear"


def test_reroute_rejects_recently_closed_candidate(app_db):
    now = datetime.now(UTC)
    setup_segments(app_db, now)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_router] = make_router

    tc = TestClient(app)
    # The detour candidate uses segment 9103, but 9103 was closed 5 minutes ago (< 15 min memory)
    closed_recently = (now - timedelta(minutes=5)).isoformat()

    resp = tc.post(
        "/v1/route/reroute",
        json={
            "origin": {"lat": 12.97, "lon": 77.58},
            "destination": {"lat": 12.99, "lon": 77.60},
            "vclass": "car",
            "depart_at": now.isoformat(),
            "current_edges": [
                {
                    "segment_id": 9101,
                    "travel_time_s": 120.0,
                    "length_m": 800.0,
                    "turn_off_after": True,
                },
                {
                    "segment_id": 9102,  # flooded ahead
                    "travel_time_s": 180.0,
                    "length_m": 1000.0,
                    "turn_off_after": True,
                },
            ],
            "trip_state": {
                "last_suggestion_at": None,
                "baseline_band": 0,
                "closed_at": {"9103": closed_recently},
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "keep"
    assert body["code"] == "recently_closed"
    assert body["warn"] is True
    assert "reroute.no_alternative" in body["reason_keys"]


def test_reroute_safety_invariant_no_safe_label(app_db):
    now = datetime.now(UTC)
    setup_segments(app_db, now)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_router] = make_router

    tc = TestClient(app)
    resp = tc.post(
        "/v1/route/reroute",
        json={
            "origin": {"lat": 12.97, "lon": 77.58},
            "destination": {"lat": 12.99, "lon": 77.60},
            "vclass": "car",
            "current_edges": [
                {
                    "segment_id": 9101,
                    "travel_time_s": 120.0,
                    "length_m": 800.0,
                    "turn_off_after": True,
                }
            ],
        },
    )

    assert resp.status_code == 200
    body = resp.json()

    def check_no_safe(obj):
        if isinstance(obj, str):
            # The word "safe" as a standalone word must never appear
            words = [w.strip(".,;:!?()[]\"'") for w in obj.lower().split()]
            assert "safe" not in words, f"Found forbidden 'safe' in: {obj}"
        elif isinstance(obj, list):
            for item in obj:
                check_no_safe(item)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if k != "no_safe_route":  # machine-readable boolean key
                    check_no_safe(v)

    check_no_safe(body)
