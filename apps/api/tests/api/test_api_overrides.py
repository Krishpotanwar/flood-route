"""Tests for POST /v1/overrides."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"


def test_override_validation_errors(client, app_db):
    now = datetime.now(UTC)
    app_db.execute(
        "insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')"
    )
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (6001, 16001, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )

    # 1. Expiry in the past
    r1 = client.post(
        "/v1/overrides",
        json={
            "segment_id": 6001,
            "action": "close",
            "reason": "Road submerged",
            "operator_id": "op-1",
            "starts_at": now.isoformat(),
            "expires_at": (now - timedelta(hours=1)).isoformat(),
        },
    )
    assert r1.status_code == 400

    # 2. Duplicate operators (two people means two people)
    r2 = client.post(
        "/v1/overrides",
        json={
            "segment_id": 6001,
            "action": "close",
            "reason": "Road submerged",
            "operator_id": "op-1",
            "second_operator_id": "op-1",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert r2.status_code == 400

    # 3. Nonexistent segment
    r3 = client.post(
        "/v1/overrides",
        json={
            "segment_id": 999999,
            "action": "close",
            "reason": "Road submerged",
            "operator_id": "op-1",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert r3.status_code == 404


def test_override_success_and_audit_log(client, app_db):
    now = datetime.now(UTC)
    app_db.execute(
        "insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')"
    )
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (7001, 17001, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )

    r = client.post(
        "/v1/overrides",
        json={
            "segment_id": 7001,
            "action": "close",
            "reason": "Underpass flooded with 40cm water",
            "operator_id": "op-primary",
            "second_operator_id": "op-supervisor",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=3)).isoformat(),
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["override_id"] > 0
    assert data["action"] == "close"
    assert data["operator_id"] == "op-primary"
    assert data["second_operator_id"] == "op-supervisor"

    # Verify audit_log entry
    cur = app_db.execute(
        "select actor, action, segment_id, reason from audit_log where segment_id = 7001"
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "operator:op-primary"
    assert row[1] == "override_close"
    assert row[2] == 7001
    assert row[3] == "Underpass flooded with 40cm water"
