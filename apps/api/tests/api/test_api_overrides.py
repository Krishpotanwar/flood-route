"""Tests for POST /v1/overrides."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"


def test_override_validation_errors(client, app_db):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
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
            "tenant_id": 1,
            "segment_id": 6001,
            "action": "close",
            "reason": "Road submerged",
            "operator_id": "op-primary",
            "starts_at": now.isoformat(),
            "expires_at": (now - timedelta(hours=1)).isoformat(),
        },
    )
    assert r1.status_code == 400

    # 2. Duplicate operators (two people means two people)
    r2 = client.post(
        "/v1/overrides",
        json={
            "tenant_id": 1,
            "segment_id": 6001,
            "action": "close",
            "reason": "Road submerged",
            "operator_id": "op-primary",
            "second_operator_id": "op-primary",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert r2.status_code == 400

    # 3. Nonexistent segment
    r3 = client.post(
        "/v1/overrides",
        json={
            "tenant_id": 1,
            "segment_id": 999999,
            "action": "close",
            "reason": "Road submerged",
            "operator_id": "op-primary",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert r3.status_code == 404


def test_override_success_and_audit_log(client, app_db):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
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
            "tenant_id": 1,
            "segment_id": 7001,
            "action": "close",
            "reason": "Underpass flooded with 40cm water",
            "operator_id": "op-primary",
            "second_operator_id": "op-secondary",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=3)).isoformat(),
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["override_id"] > 0
    assert data["action"] == "close"
    assert data["operator_id"] == "op-primary"
    assert data["second_operator_id"] == "op-secondary"

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


def test_override_arterial_requires_second_operator(client, app_db):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (7002, 17002, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )

    # Missing second_operator_id on arterial road
    r = client.post(
        "/v1/overrides",
        json={
            "tenant_id": 1,
            "segment_id": 7002,
            "action": "close",
            "reason": "Arterial flooding",
            "operator_id": "op-primary",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert r.status_code == 400
    assert "Arterial road 'primary' requires second operator confirmation" in r.json()["detail"]


def test_list_and_revert_overrides(client, app_db):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (7003, 17003, %s, 'residential', 1, true)
        """,
        (SEG_LINE,),
    )

    # 1. Create residential override (single operator allowed)
    r_create = client.post(
        "/v1/overrides",
        json={
            "tenant_id": 1,
            "segment_id": 7003,
            "action": "close",
            "reason": "Tree fell in flood water",
            "operator_id": "op-primary",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert r_create.status_code == 201
    ov_id = r_create.json()["override_id"]

    # 2. List active overrides
    r_list = client.get("/v1/overrides")
    assert r_list.status_code == 200
    items = r_list.json()
    assert any(item["override_id"] == ov_id for item in items)

    # 3. Revert override early
    r_rev = client.delete(
        f"/v1/overrides/{ov_id}?reason=Cleared+fallen+tree&operator_id=op-primary"
    )
    assert r_rev.status_code == 200
    assert r_rev.json()["reverted"] is True

    # 4. Check list again: should no longer appear as active
    r_list_after = client.get("/v1/overrides")
    assert r_list_after.status_code == 200
    assert not any(item["override_id"] == ov_id for item in r_list_after.json())

    # 5. Check audit log for revert event
    cur = app_db.execute(
        "select action, reason from audit_log where segment_id = 7003 and action = 'override_reverted_close'"
    )
    row = cur.fetchone()
    assert row is not None
    assert row[1] == "Cleared fallen tree"


def test_override_preview_impact(client, app_db):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (7004, 17004, %s, 'secondary', 1, true),
               (7005, 17005, %s, 'trunk', 1, true)
        """,
        (SEG_LINE, SEG_LINE),
    )

    # Insert an active route watch affecting segment 7004
    app_db.execute(
        """
        insert into route_watch (watch_id, tenant_id, vclass, segments, baseline_states, alert_channel, contact_target, is_active, created_at, expires_at)
        values ('c4e10118-2831-4122-b5e0-827d04845e69', 1, 'car', ARRAY[7004, 9999], '{"7004":"clear"}', 'webhook', 'https://example.com/hook', true, %s, %s)
        """,
        (now, now + timedelta(hours=1)),
    )

    # Preview impact on secondary road with 1 affected watch
    r_sec = client.post(
        "/v1/overrides/preview",
        json={"segment_id": 7004, "action": "close"},
    )
    assert r_sec.status_code == 200
    data_sec = r_sec.json()
    assert data_sec["road_class"] == "secondary"
    assert data_sec["is_arterial"] is False
    assert data_sec["requires_second_operator"] is False
    assert data_sec["active_watches_affected"] == 1
    assert data_sec["impact_level"] == "moderate"

    # Preview impact on trunk road (arterial)
    r_trunk = client.post(
        "/v1/overrides/preview",
        json={"segment_id": 7005, "action": "close"},
    )
    assert r_trunk.status_code == 200
    data_trunk = r_trunk.json()
    assert data_trunk["road_class"] == "trunk"
    assert data_trunk["is_arterial"] is True
    assert data_trunk["requires_second_operator"] is True
    assert data_trunk["impact_level"] == "high"


def test_query_audit_log_json_and_csv(client, app_db):
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    app_db.execute(
        """
        insert into audit_log (actor, action, segment_id, reason)
        values ('operator:test-lead', 'manual_inspection', 8888, 'Culvert overflow inspected')
        """
    )

    # Query JSON format
    r_json = client.get("/v1/audit?actor=test-lead")
    assert r_json.status_code == 200
    items = r_json.json()
    assert len(items) >= 1
    assert items[0]["actor"] == "operator:test-lead"
    assert items[0]["action"] == "manual_inspection"

    # Query CSV format
    r_csv = client.get("/v1/audit?action=manual_inspection&format=csv")
    assert r_csv.status_code == 200
    assert r_csv.headers["content-type"].startswith("text/csv")
    csv_text = r_csv.text
    assert "audit_id,timestamp,actor,action,segment_id,reason" in csv_text
    assert "operator:test-lead" in csv_text
    assert "Culvert overflow inspected" in csv_text

