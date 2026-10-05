"""Tests for GET /v1/feed/closures.geojson."""

from __future__ import annotations

from datetime import UTC, datetime

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE_1 = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"
SEG_LINE_2 = "SRID=4326;LINESTRING(77.60 12.97, 77.61 12.98)"


def test_feed_closures_geojson(client, app_db):
    now = datetime.now(UTC)

    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values
            (8001, 18001, %s, 'primary', 1, true),
            (8002, 18002, %s, 'secondary', 1, true),
            (8003, 18003, %s, 'residential', 1, true)
        """,
        (SEG_LINE_1, SEG_LINE_2, SEG_LINE_1),
    )
    # 8001: impassable, 8002: risky, 8003: watch
    app_db.execute(
        """
        insert into segment_risk (
            segment_id, vclass, horizon_min, p_unusable,
            depth_p50_cm, depth_p90_cm, state, confidence,
            evidence_age_s, model_version, updated_at
        )
        values
            (8001, 'car', 0, 0.95, 30.0, 45.0, 'impassable', 'high', 30, 'v0.0.1', %s),
            (8002, 'car', 0, 0.40, 15.0, 22.5, 'risky', 'medium', 60, 'v0.0.1', %s),
            (8003, 'car', 0, 0.15, 5.0, 7.5, 'watch', 'low', 90, 'v0.0.1', %s)
        """,
        (now, now, now),
    )

    r = client.get("/v1/feed/closures.geojson?vclass=car&horizon_min=0")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2

    feature_sids = {f["properties"]["segment_id"] for f in fc["features"]}
    assert feature_sids == {8001, 8002}

    f8001 = next(f for f in fc["features"] if f["properties"]["segment_id"] == 8001)
    assert f8001["geometry"]["type"] == "LineString"
    assert f8001["properties"]["state"] == "impassable"
    assert f8001["properties"]["road_class"] == "primary"
