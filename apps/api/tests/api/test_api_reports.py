"""Tests for POST /v1/reports."""

from __future__ import annotations

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE = "SRID=4326;LINESTRING(77.580 12.970, 77.581 12.971)"


def test_submit_report_validation(client):
    # Outside India coordinate check
    r = client.post(
        "/v1/reports",
        json={
            "lat": 51.5074,  # London
            "lon": -0.1278,
            "depth_class": "knee",
            "reporter_id": "rep-001",
        },
    )
    assert r.status_code == 422


def test_submit_report_near_segment(client, app_db):
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (5001, 15001, %s, 'secondary', 1, true)
        """,
        (SEG_LINE,),
    )

    # Submit report right on the segment (77.5805, 12.9705)
    r = client.post(
        "/v1/reports",
        json={
            "lat": 12.9705,
            "lon": 77.5805,
            "depth_class": "ankle",
            "reporter_id": "user-abc-123",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "received"
    assert data["segment_id"] == 5001
    assert data["depth_class"] == "ankle"

    # Verify report row in DB
    cur = app_db.execute(
        "select segment_id, depth_class, status from report where report_id = %s",
        (data["report_id"],),
    )
    assert cur.fetchone() == (5001, "ankle", "pending")

    # Verify evidence row in DB
    cur = app_db.execute(
        "select segment_id, kind, depth_cm, source_id from evidence where segment_id = 5001"
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == 5001
    assert row[1] == "report"
    assert row[2] == 10.0  # Ankle depth = 10.0 cm
    assert row[3] == "user-abc-123"


def test_submit_report_isolated_location(client, app_db):
    # Location with no segments within 100m
    r = client.post(
        "/v1/reports",
        json={
            "lat": 15.0000,
            "lon": 75.0000,
            "depth_class": "vehicle_deep",
            "reporter_id": "isolated-user",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "received"
    assert data["segment_id"] is None
