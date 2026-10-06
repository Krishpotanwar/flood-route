"""Tests for offline and CDN road closure snapshots (TRD 11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from floodroute.feed.snapshot import (
    generate_city_closure_snapshot,
    list_snapshot_status,
    load_city_closure_snapshot,
)

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"


def test_generate_and_load_closure_snapshot(app_db, tmp_path: Path):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (8001, 18001, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into override (tenant_id, segment_id, action, reason, operator_id, second_operator_id, starts_at, expires_at)
        values (1, 8001, 'close', 'Waterlogged underpass', 'op1', 'op2', %s, %s)
        """,
        (now, now + timedelta(hours=2)),
    )

    snapshot = generate_city_closure_snapshot(
        app_db, city_name="bengaluru", vclass="car", snapshot_dir=tmp_path
    )
    assert snapshot["city"] == "bengaluru"
    assert snapshot["feature_count"] == 1
    assert "etag" in snapshot
    assert (tmp_path / "closures_bengaluru_car.json").exists()

    loaded = load_city_closure_snapshot(
        city_name="bengaluru", vclass="car", snapshot_dir=tmp_path
    )
    assert loaded is not None
    assert loaded["etag"] == snapshot["etag"]

    statuses = list_snapshot_status(snapshot_dir=tmp_path)
    assert len(statuses) == 1
    assert statuses[0]["city"] == "bengaluru"
    assert statuses[0]["is_stale"] is False


def test_api_get_closure_snapshot(client, app_db):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (8002, 18002, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into override (tenant_id, segment_id, action, reason, operator_id, second_operator_id, starts_at, expires_at)
        values (1, 8002, 'close', 'Waterlogged bridge', 'op1', 'op2', %s, %s)
        """,
        (now, now + timedelta(hours=2)),
    )

    # 1. Fetch snapshot via API
    r = client.get("/v1/feed/snapshot/closures?city=bengaluru&vclass=car")
    assert r.status_code == 200
    assert r.headers["cache-control"].startswith("public, max-age=120")
    etag = r.headers.get("etag")
    assert etag is not None

    data = r.json()
    assert data["city"] == "bengaluru"
    assert data["type"] == "FeatureCollection"

    # 2. Conditional GET with If-None-Match matching etag
    r_304 = client.get(
        "/v1/feed/snapshot/closures?city=bengaluru&vclass=car",
        headers={"if-none-match": etag},
    )
    assert r_304.status_code == 304

    # 3. Unknown city
    r_404 = client.get("/v1/feed/snapshot/closures?city=nonexistent")
    assert r_404.status_code == 404


def test_api_trigger_snapshot_generation(client, app_db):
    r = client.post("/v1/feed/snapshot/generate?city=bengaluru&vclass=ambulance")
    assert r.status_code == 201
    data = r.json()
    assert data["city"] == "bengaluru"
    assert data["vclass"] == "ambulance"
    assert data["generated"] is True
    assert "etag" in data

    # Check status endpoint
    r_status = client.get("/v1/feed/snapshot/status")
    assert r_status.status_code == 200
    items = r_status.json()
    assert any(it["city"] == "bengaluru" for it in items)
