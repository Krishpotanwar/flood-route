"""Tests for GET /v1/risk."""

from __future__ import annotations

from datetime import UTC, datetime

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE_INSIDE = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"
SEG_LINE_OUTSIDE = "SRID=4326;LINESTRING(80.20 13.05, 80.21 13.06)"


def test_risk_validation_errors(client):
    r1 = client.get("/v1/risk?h=45")
    assert r1.status_code == 422

    r2 = client.get("/v1/risk?vclass=rocket")
    assert r2.status_code == 422

    r3 = client.get("/v1/risk?bbox=invalid")
    assert r3.status_code == 400

    r4 = client.get("/v1/risk?bbox=77.8,13.1,77.5,12.9")
    assert r4.status_code == 400


def test_risk_query_with_bbox_and_segment_filter(client, app_db):
    now = datetime.now(UTC)

    # Setup zone and segments
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values
            (1001, 10001, %s, 'primary', 1, true),
            (1002, 10002, %s, 'residential', 1, false),
            (1003, 10003, %s, 'primary', 1, true)
        """,
        (SEG_LINE_INSIDE, SEG_LINE_INSIDE, SEG_LINE_OUTSIDE),
    )
    app_db.execute(
        """
        insert into segment_risk (
            segment_id, vclass, horizon_min, p_unusable,
            depth_p50_cm, depth_p90_cm, state, confidence,
            evidence_age_s, model_version, updated_at
        )
        values (1001, 'car', 0, 0.18, 5.0, 7.5, 'watch', 'medium', 60, 'v0.0.1', %s)
        """,
        (now,),
    )

    # 1. Query with bbox
    r = client.get("/v1/risk?bbox=77.5,12.9,77.7,13.1&vclass=car&h=0")
    assert r.status_code == 200
    data = r.json()
    assert data["vclass"] == "car"
    assert data["horizon_min"] == 0
    seg_ids = [s["segment_id"] for s in data["segments"]]
    assert 1001 in seg_ids
    assert 1002 in seg_ids
    assert 1003 not in seg_ids  # Outside bbox

    # Check 1001 details
    s1001 = next(s for s in data["segments"] if s["segment_id"] == 1001)
    assert s1001["assessed"] is True
    assert s1001["state"] == "watch"
    assert s1001["p_unusable"] == 0.18
    assert s1001["confidence"] == "medium"

    # Check 1002 details (unassessed)
    s1002 = next(s for s in data["segments"] if s["segment_id"] == 1002)
    assert s1002["assessed"] is False
    assert s1002["state"] is None
    assert s1002["p_unusable"] is None

    # Safety rule: API never returns a "safe" label
    for s in data["segments"]:
        assert s["state"] != "safe"

    # 2. Query with segment_id filter
    r_single = client.get("/v1/risk?segment_id=1001&vclass=car&h=0")
    assert r_single.status_code == 200
    single_data = r_single.json()
    assert single_data["count"] == 1
    assert single_data["segments"][0]["segment_id"] == 1001
