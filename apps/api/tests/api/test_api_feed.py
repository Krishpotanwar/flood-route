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


def test_feed_closures_cap_xml(client, app_db):
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
            (8002, 18002, %s, 'secondary', 1, true)
        """,
        (SEG_LINE_1, SEG_LINE_2),
    )
    app_db.execute(
        """
        insert into segment_risk (
            segment_id, vclass, horizon_min, p_unusable,
            depth_p50_cm, depth_p90_cm, state, confidence,
            evidence_age_s, model_version, updated_at
        )
        values
            (8001, 'car', 0, 0.95, 30.0, 45.0, 'impassable', 'high', 30, 'v0.0.1', %s),
            (8002, 'car', 0, 0.40, 15.0, 22.5, 'risky', 'medium', 60, 'v0.0.1', %s)
        """,
        (now, now),
    )

    r = client.get("/v1/feed/cap.xml?vclass=car&horizon_min=0")
    assert r.status_code == 200
    assert "application/xml" in r.headers["content-type"]

    import xml.etree.ElementTree as ET

    root = ET.fromstring(r.text)
    # Check CAP namespace
    assert "urn:oasis:names:tc:emergency:cap:1.2" in root.tag

    # Verify standard elements
    ns = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}
    identifier = root.find("cap:identifier", ns)
    assert identifier is not None and "urn:floodroute:closure:" in identifier.text

    info = root.find("cap:info", ns)
    assert info is not None
    assert info.find("cap:event", ns).text == "Flash Flood Road Closures"
    assert info.find("cap:severity", ns).text == "Extreme"

    areas = info.findall("cap:area", ns)
    assert len(areas) == 2

    # Check circle coordinate and parameters
    circle = areas[0].find("cap:circle", ns)
    assert circle is not None and " " in circle.text

    # Safety invariant: segment state is never labeled "safe"
    assert "<value>safe</value>" not in r.text.lower()
    assert "state: safe" not in r.text.lower()


def test_feed_closures_cap_xml_empty(client, app_db):

    r = client.get("/v1/feed/cap.xml?vclass=two_wheeler&horizon_min=0")
    assert r.status_code == 200
    assert "application/xml" in r.headers["content-type"]

    import xml.etree.ElementTree as ET

    root = ET.fromstring(r.text)
    ns = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}
    info = root.find("cap:info", ns)
    assert info is None  # Empty alert when no active closures

