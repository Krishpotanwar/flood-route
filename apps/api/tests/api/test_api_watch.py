"""Tests for route watch subscription endpoints: POST/GET/DELETE /v1/routes/{id}/watch."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE_1 = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"
SEG_LINE_2 = "SRID=4326;LINESTRING(77.60 12.97, 77.61 12.98)"


def _seed_route_data(db, decision_id):
    now = datetime.now(UTC)
    db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values
            (3001, 13001, %s, 'primary', 1, true),
            (3002, 13002, %s, 'secondary', 1, true)
        """,
        (SEG_LINE_1, SEG_LINE_2),
    )
    db.execute(
        """
        insert into segment_risk (
            segment_id, vclass, horizon_min, p_unusable,
            depth_p50_cm, depth_p90_cm, state, confidence,
            evidence_age_s, model_version, updated_at
        )
        values
            (3001, 'car', 0, 0.05, 0.0, 5.0, 'clear', 'high', 30, 'v0.0.1', %s),
            (3002, 'car', 0, 0.15, 5.0, 10.0, 'watch', 'medium', 60, 'v0.0.1', %s)
        """,
        (now, now),
    )
    chosen_payload = {
        "segments": [{"segment_id": 3001}, {"segment_id": 3002}],
        "eta_min": 20,
    }
    db.execute(
        """
        insert into route_decision (
            decision_id, ts, vclass, model_version, chosen
        ) values (%s, %s, 'car', 'v0.0.1', %s)
        """,
        (decision_id, now, json.dumps(chosen_payload)),
    )


def test_route_watch_crud_endpoints(client, app_db):
    decision_id = uuid4()
    _seed_route_data(app_db, decision_id)

    # 1. Subscribe to watch
    watch_req = {
        "device_token": "dev-token-abc",
        "alert_channel": "fcm",
        "contact_target": "fcm-push-target-xyz",
        "dwell_minutes": 45,
    }
    r = client.post(f"/v1/routes/{decision_id}/watch", json=watch_req)
    assert r.status_code == 200
    data = r.json()
    assert data["decision_id"] == str(decision_id)
    assert data["status"] == "active"
    assert data["segments_count"] == 2
    assert data["alerts_sent_count"] == 0

    # 2. Query status
    r_get = client.get(f"/v1/routes/{decision_id}/watch")
    assert r_get.status_code == 200
    assert r_get.json()["status"] == "active"

    # 3. Cancel watch
    r_del = client.delete(f"/v1/routes/{decision_id}/watch")
    assert r_del.status_code == 200
    assert r_del.json()["cancelled"] is True

    # 4. Query after cancel returns 404
    r_get2 = client.get(f"/v1/routes/{decision_id}/watch")
    assert r_get2.status_code == 404


def test_route_watch_not_found(client, app_db):
    random_id = uuid4()
    r = client.post(
        f"/v1/routes/{random_id}/watch",
        json={"contact_target": "target-123"},
    )
    assert r.status_code == 404
