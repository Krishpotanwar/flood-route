"""Tests for offline and CDN road closure snapshots (TRD 11)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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
    assert statuses[0]["is_stale"] is True  # No verified feed health behind the file.


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


def _seed_segment(app_db, segment_id=8001, city_id=1):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (%s, 18001, %s, 'primary', %s, true)
        """,
        (segment_id, SEG_LINE, city_id),
    )
    return now


def _seed_risk(app_db, segment_id, state, p, updated):
    for h in (0, 30, 60, 120):
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (%s, 'car', %s, %s, 0.0, 5.0, %s, 'high', 30, 'v0.0.1', %s)
            """,
            (segment_id, h, p, state, updated),
        )


def test_snapshot_unions_model_closures_with_override_source_tags(app_db, tmp_path: Path):
    _seed_segment(app_db)
    now = datetime.now(UTC)
    _seed_risk(app_db, 8001, "impassable", 0.9, now)
    app_db.execute(
        "insert into source_health (source, last_ok, last_error, lag_s)"
        " values ('sachet', %s, NULL, 10), ('metno', %s, NULL, 100)",
        (now, now),
    )

    snapshot = generate_city_closure_snapshot(
        app_db, city_name="bengaluru", vclass="car", snapshot_dir=tmp_path
    )
    assert snapshot["feature_count"] == 1
    props = snapshot["features"][0]["properties"]
    assert props["state"] == "impassable" and props["source"] == "model"
    assert props["as_of"] is not None
    assert snapshot["stale"] is False
    assert snapshot["conditions_as_of"] == now.isoformat()
    assert set(snapshot["sources"]) == {"sachet", "metno"}


def test_snapshot_marks_old_model_evidence_stale_not_fresh(app_db, tmp_path: Path):
    _seed_segment(app_db)
    old = datetime.now(UTC) - timedelta(hours=2)
    _seed_risk(app_db, 8001, "risky", 0.4, old)

    snapshot = generate_city_closure_snapshot(
        app_db, city_name="bengaluru", vclass="car", snapshot_dir=tmp_path
    )
    assert snapshot["stale"] is True
    assert snapshot["conditions_as_of"] == old.isoformat()


def test_fresh_model_row_cannot_hide_an_old_closure(app_db, tmp_path: Path):
    now = _seed_segment(app_db)
    old = now - timedelta(days=1)
    _seed_risk(app_db, 8001, "risky", 0.4, old)
    app_db.execute(
        "insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)"
        " values (8002, 18002, %s, 'primary', 1, true)", (SEG_LINE,),
    )
    _seed_risk(app_db, 8002, "impassable", 0.9, now)
    app_db.execute(
        "insert into source_health (source, last_ok, lag_s)"
        " values ('sachet', %s, 0), ('metno', %s, 0)", (now, now),
    )
    snapshot = generate_city_closure_snapshot(app_db, snapshot_dir=tmp_path)
    assert snapshot["feature_count"] == 2
    assert snapshot["stale"] is True
    assert snapshot["conditions_as_of"] == old.isoformat()


@pytest.mark.parametrize("lag,error", [(None, None), (9000, None), (0, "warning: forecast is in the future")])
def test_recent_feed_refresh_does_not_hide_unknown_or_old_source_data(
    app_db, tmp_path: Path, lag, error
):
    now = _seed_segment(app_db)
    _seed_risk(app_db, 8001, "risky", 0.4, now)
    app_db.execute(
        "insert into source_health (source, last_ok, lag_s, last_error)"
        " values ('sachet', %s, 0, NULL), ('metno', %s, %s, %s)",
        (now, now, lag, error),
    )
    assert generate_city_closure_snapshot(app_db, snapshot_dir=tmp_path)["stale"] is True


def test_future_override_is_not_a_current_snapshot_closure(app_db, tmp_path: Path):
    now = _seed_segment(app_db)
    app_db.execute(
        "insert into override (tenant_id, segment_id, action, reason, operator_id, starts_at, expires_at)"
        " values (1, 8001, 'close', 'Scheduled closure', 'op1', %s, %s)",
        (now + timedelta(minutes=45), now + timedelta(hours=2)),
    )
    assert generate_city_closure_snapshot(app_db, snapshot_dir=tmp_path)["feature_count"] == 0


def test_snapshot_rejects_an_unknown_city(app_db, tmp_path: Path):
    import pytest

    with pytest.raises(KeyError):
        generate_city_closure_snapshot(app_db, city_name="nowhere", snapshot_dir=tmp_path)


def test_snapshot_etag_is_stable_for_identical_content(app_db, tmp_path: Path):
    _seed_segment(app_db)
    _seed_risk(app_db, 8001, "impassable", 0.9, datetime.now(UTC))
    first = generate_city_closure_snapshot(
        app_db, city_name="bengaluru", vclass="car", snapshot_dir=tmp_path
    )
    second = generate_city_closure_snapshot(
        app_db, city_name="bengaluru", vclass="car", snapshot_dir=tmp_path
    )
    assert first["etag"] == second["etag"]
    assert load_city_closure_snapshot(
        city_name="bengaluru", vclass="car", snapshot_dir=tmp_path
    )["etag"] == first["etag"]


def test_snapshot_dir_env_override_is_absolute(tmp_path: Path, monkeypatch):
    from floodroute.feed.snapshot import get_snapshot_dir

    target = tmp_path / "snaps"
    monkeypatch.setenv("FLOODROUTE_SNAPSHOT_DIR", str(target))
    resolved = get_snapshot_dir()
    assert resolved.is_absolute() and resolved == target.resolve()


@pytest.mark.parametrize(
    "changes,expected_stale",
    [
        ({}, False),
        ({"stale": True}, True),
        ({"generated_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat()}, True),
        ({"generated_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}, True),
        ({"generated_at": None}, True),
        ({"generated_at": "2026-10-07T12:00:00"}, True),
        ({"stale": None}, True),
        ({"city": "mumbai"}, True),
        ({"vclass": "car"}, True),
    ],
)
def test_snapshot_status_uses_payload_freshness_and_full_vehicle_class(
    tmp_path: Path, changes, expected_stale
):
    doc = {
        "city": "bengaluru", "vclass": "two_wheeler", "stale": False,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    doc.update(changes)
    path = tmp_path / "closures_bengaluru_two_wheeler.json"
    path.write_text(json.dumps(doc))
    status = list_snapshot_status(tmp_path)[0]
    assert status["city"] == "bengaluru" and status["vclass"] == "two_wheeler"
    assert status["is_stale"] is expected_stale
    path.write_text("invalid JSON")
    status = list_snapshot_status(tmp_path)[0]
    assert status["is_stale"] is True and status["generated_at"] is None
    path.write_bytes(b"\xff")
    assert list_snapshot_status(tmp_path)[0]["is_stale"] is True


def test_api_rejects_unknown_vclass_and_flags_stale_files(client, app_db, tmp_path: Path):
    r = client.get("/v1/feed/snapshot/closures?city=bengaluru&vclass=pedestrian")
    assert r.status_code == 422
    r = client.post("/v1/feed/snapshot/generate?city=bengaluru&vclass=pedestrian")
    assert r.status_code == 422

    old = datetime.now(UTC) - timedelta(hours=2)
    _seed_segment(app_db, segment_id=8003)
    _seed_risk(app_db, 8003, "impassable", 0.9, old)
    r = client.get("/v1/feed/snapshot/closures?city=bengaluru&vclass=car")
    assert r.status_code == 200
    assert r.headers.get("x-snapshot-stale") == "true"
    assert r.json()["stale"] is True
    # Serve budget: max-age + stale-while-revalidate stays within 300 s.
    cc = r.headers["cache-control"]
    max_age = int(cc.split("max-age=")[1].split(",")[0])
    swr = int(cc.split("stale-while-revalidate=")[1].split(",")[0])
    assert max_age + swr <= 300
    # An aged file triggers an on-demand regen instead of serving old as fresh.
    import json as _json

    from floodroute.feed.snapshot import get_snapshot_dir

    path = get_snapshot_dir() / "closures_bengaluru_car.json"
    doc = _json.loads(path.read_text())
    doc["generated_at"] = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    path.write_text(_json.dumps(doc))
    r2 = client.get("/v1/feed/snapshot/closures?city=bengaluru&vclass=car")
    assert r2.status_code == 200
    assert r2.json()["stale"] is True
