"""Release boundary regressions; all databases and outbound transports are disposable."""

import json
import socket
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import psycopg
import pytest

from floodroute.api.deps import db_risk_for, get_router
from floodroute.route.models import Edge, Route
from floodroute.webhook.dispatcher import dispatch_event
from floodroute.webhook.models import WebhookEvent
from floodroute.webhook.receipt import verify_receipt
from floodroute.webhook.signing import compute_signature

PRIMARY_TOKEN = "test-only-primary-operator-token-1234567890"
SECONDARY_TOKEN = "test-only-secondary-operator-token-1234567890"
AUTH = {"Authorization": f"Bearer {PRIMARY_TOKEN}"}


def test_administration_fails_closed_and_public_reads_remain(anonymous_client, monkeypatch):
    for url in ("/v1/audit", "/v1/overrides", "/v1/webhooks", "/v1/safety/kill-switch"):
        assert anonymous_client.get(url).status_code == 401
    assert anonymous_client.post("/v1/cities/bengaluru/seed").status_code == 401
    assert anonymous_client.post("/v1/feed/snapshot/generate").status_code == 401
    for registry in ("", "invalid", "{}", "[]", '{"op":"short"}'):
        monkeypatch.setenv("FLOODROUTE_OPERATOR_TOKENS", registry)
        assert anonymous_client.get("/v1/audit", headers=AUTH).status_code == 503
        assert anonymous_client.get("/v1/cities").status_code == 200


def test_actor_and_cosigner_require_distinct_real_credentials(anonymous_client, app_db):
    payload = {"reason": "Telemetry failed checks", "operator_id": "forged"}
    assert (
        anonymous_client.post("/v1/safety/kill-switch", headers=AUTH, json=payload).status_code
        == 403
    )
    payload["operator_id"] = "op-primary"
    r = anonymous_client.post("/v1/safety/kill-switch", headers=AUTH, json=payload)
    assert r.status_code == 200
    switch_id = r.json()["record"]["switch_id"]
    release = {
        "reason": "Telemetry independently verified",
        "operator_id": "op-primary",
        "second_operator_id": "op-secondary",
    }
    url = f"/v1/safety/kill-switch/{switch_id}/disengage"
    assert anonymous_client.post(url, headers=AUTH, json=release).status_code == 401
    assert (
        anonymous_client.post(
            url,
            headers={**AUTH, "X-FloodRoute-Co-Signature": PRIMARY_TOKEN},
            json=release,
        ).status_code
        == 403
    )
    assert app_db.execute(
        "select is_active from kill_switch where switch_id=%s", (switch_id,)
    ).fetchone()[0]
    assert (
        anonymous_client.post(
            url,
            headers={**AUTH, "X-FloodRoute-Co-Signature": SECONDARY_TOKEN},
            json=release,
        ).status_code
        == 200
    )


def test_webhook_private_targets_rebinding_and_redirects_are_blocked(client, app_db, monkeypatch):
    for url in (
        "https://127.0.0.1/hook",
        "https://[::1]/hook",
        "https://169.254.169.254/hook",
        "https://100.64.0.1/hook",
    ):
        assert client.post("/v1/webhooks", json={"target_url": url}).status_code == 422
    created = client.post("/v1/webhooks", json={"target_url": "https://hooks.example.com/event"})
    assert created.status_code == 201
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://127.0.0.1/private"})

    event = WebhookEvent(
        event_type="segment.state_changed", timestamp=datetime.now(UTC), payload={}
    )
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as transport:
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))]
        )
        results = dispatch_event(app_db, event, client=transport)
        assert results[0]["status"] == "failed" and seen == []
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 443))]
        )
        results = dispatch_event(app_db, event, client=transport)
    assert results[0]["status_code"] == 302 and len(seen) == 1
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["Host"] == "hooks.example.com"
    assert seen[0].extensions["sni_hostname"] == "hooks.example.com"


def test_receipt_rejects_a_fresh_header_on_an_old_signed_body():
    timestamp = "2020-01-01T00:00:00+00:00"
    payload = json.dumps({"event_id": "old-event", "timestamp": timestamp}).encode()
    signature = "sha256=" + compute_signature(PRIMARY_TOKEN, payload)
    assert not verify_receipt(PRIMARY_TOKEN, payload, signature, datetime.now(UTC).isoformat())
    assert not verify_receipt(PRIMARY_TOKEN, payload, signature, timestamp)
    fresh = datetime.now(UTC).isoformat()
    payload = json.dumps({"event_id": "fresh-event", "timestamp": fresh}).encode()
    signature = "sha256=" + compute_signature(PRIMARY_TOKEN, payload)
    assert verify_receipt(PRIMARY_TOKEN, payload, signature, fresh)
    assert not verify_receipt(PRIMARY_TOKEN, payload, "sha256=非ASCII", fresh)


def test_freeze_during_route_and_reroute_removes_recommendations(client, app_db):
    now = datetime.now(UTC)
    client.app.dependency_overrides[get_router] = lambda: (
        lambda *a: Route((Edge(None, ((12.97, 77.58), (12.98, 77.59)), 60, 500),))
    )
    payload = {
        "origin": {"lat": 12.97, "lon": 77.58},
        "destination": {"lat": 12.98, "lon": 77.59},
        "vclass": "car",
        "depart_at": now.isoformat(),
    }
    with patch("floodroute.api.routes.route._active_freeze", side_effect=[None, object()]):
        response = client.post("/v1/route", json=payload).json()
    assert (
        response["no_safe_route"] and response["routes"] == [] and response["valid_until"] is None
    )
    payload["current_edges"] = [{"travel_time_s": 120, "length_m": 600}]
    with patch("floodroute.api.routes.route._active_freeze", side_effect=[None, object()]):
        response = client.post("/v1/route/reroute", json=payload).json()
    assert response["code"] == "advisory_off" and response["suggested_route"] is None
    audits = app_db.execute("select chosen, no_safe_route from route_decision").fetchall()
    assert len(audits) == 2 and all(chosen is None and frozen for chosen, frozen in audits)
    payload.pop("current_edges")
    response = client.post("/v1/route", json=payload)
    assert response.status_code == 200 and response.json()["routes"][0]["geometry"]
    chosen = app_db.execute(
        "select chosen from route_decision where decision_id=%s",
        (response.json()["decision_id"],),
    ).fetchone()[0]
    assert "geometry" not in chosen


def test_mixed_forecast_horizons_cannot_renew_an_old_clear_row():
    now = datetime.now(UTC)
    rows = [
        (h, 0.0, "clear", "high", 0, now - timedelta(minutes=30) if h == 0 else now)
        for h in (0, 30, 60, 120)
    ]
    db = SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchall=lambda: rows))
    with pytest.raises(RuntimeError, match="mixes runs"):
        db_risk_for(db, 1, "car")


def test_snapshot_fallback_staleness_changes_etag_and_conditional_headers(client, monkeypatch):
    import floodroute.api.routes.snapshot as snapshots

    cached = {
        "generated_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "conditions_as_of": "2020-01-01T00:00:00+00:00",
        "etag": '"old-etag"',
        "stale": False,
    }
    monkeypatch.setattr(snapshots, "_reject_when_frozen", lambda *a: None)
    monkeypatch.setattr(snapshots, "load_city_closure_snapshot", lambda *a, **kw: cached)

    def unavailable(*a, **kw):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(snapshots, "generate_city_closure_snapshot", unavailable)
    response = client.get("/v1/feed/snapshot/closures", headers={"If-None-Match": cached["etag"]})
    assert response.status_code == 200 and response.json()["stale"] is True
    assert response.headers["etag"] != cached["etag"]
    conditional = client.get(
        "/v1/feed/snapshot/closures", headers={"If-None-Match": response.headers["etag"]}
    )
    assert conditional.status_code == 304 and conditional.headers["X-Snapshot-Stale"] == "true"


def test_ambulance_profile_requires_authorization(anonymous_client):
    payload = {
        "origin": {"lat": 12.97, "lon": 77.58},
        "destination": {"lat": 12.98, "lon": 77.59},
        "vclass": "ambulance",
        "profile": "ambulance",
        "depart_at": datetime.now(UTC).isoformat(),
    }
    assert anonymous_client.post("/v1/route", json=payload).status_code == 401
    payload["current_edges"] = [{"travel_time_s": 60}]
    assert anonymous_client.post("/v1/route/reroute", json=payload).status_code == 401


def test_override_changes_roll_back_when_auditing_fails(client, app_db, db):
    from floodroute.inventory.multicity import seed_city_hotspots_into_db

    seed_city_hotspots_into_db(app_db, "bengaluru")
    segment_id = app_db.execute("select segment_id from segment where assessed limit 1").fetchone()[
        0
    ]
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    expires = datetime.now(UTC) + timedelta(hours=1)
    existing_id = app_db.execute(
        """insert into override (tenant_id, segment_id, action, reason, operator_id, starts_at, expires_at)
           values (1,%s,'close','Road flooded','op-primary',now(),%s) returning override_id""",
        (segment_id, expires),
    ).fetchone()[0]
    db.execute("""create function reject_review_audit() returns trigger language plpgsql as $$
                   begin raise exception 'test audit failure' using errcode='23514'; end $$""")
    db.execute(
        "create trigger reject_review_audit before insert on audit_log for each row execute function reject_review_audit()"
    )
    payload = {
        "tenant_id": 1,
        "segment_id": segment_id,
        "action": "close",
        "reason": "Road flooded",
        "operator_id": "op-primary",
        "second_operator_id": "op-secondary",
        "expires_at": expires.isoformat(),
    }
    with pytest.raises(psycopg.errors.CheckViolation):
        client.post("/v1/overrides", json=payload)
    assert app_db.execute("select count(*) from override").fetchone()[0] == 1
    with pytest.raises(psycopg.errors.CheckViolation):
        client.delete(f"/v1/overrides/{existing_id}?second_operator_id=op-secondary")
    assert (
        app_db.execute(
            "select expires_at from override where override_id=%s", (existing_id,)
        ).fetchone()[0]
        == expires
    )


def test_retired_model_risk_is_not_published_or_used_for_routes(client, app_db):
    from floodroute.inventory.multicity import seed_city_hotspots_into_db

    seed_city_hotspots_into_db(app_db, "bengaluru")
    sid = app_db.execute("select segment_id from segment where assessed limit 1").fetchone()[0]
    for horizon in (0, 30, 60, 120):
        app_db.execute(
            """insert into segment_risk (segment_id,vclass,horizon_min,p_unusable,
               depth_p50_cm,depth_p90_cm,state,confidence,evidence_age_s,model_version,updated_at)
               values (%s,'car',%s,0.9,40,50,'impassable','high',0,'v0.0.1',now())""",
            (sid, horizon),
        )
    assert db_risk_for(app_db, sid, "car") is not None
    app_db.execute("update segment set assessed=false where segment_id=%s", (sid,))
    assert db_risk_for(app_db, sid, "car") is None
    assert client.get("/v1/feed/closures.geojson").json()["features"] == []
    assert "<info>" not in client.get("/v1/feed/cap.xml").text


def test_arterial_closure_cancellation_requires_a_real_cosigner(client, anonymous_client, app_db):
    from floodroute.inventory.multicity import seed_city_hotspots_into_db

    seed_city_hotspots_into_db(app_db, "bengaluru")
    sid = app_db.execute("select segment_id from segment where assessed limit 1").fetchone()[0]
    app_db.execute("update segment set road_class='primary' where segment_id=%s", (sid,))
    app_db.execute("insert into tenant (tenant_id,name,kind) values (1,'Admin','admin')")
    expires = datetime.now(UTC) + timedelta(hours=1)
    response = client.post(
        "/v1/overrides",
        json={
            "tenant_id": 1,
            "segment_id": sid,
            "action": "close",
            "reason": "Road flooded",
            "operator_id": "op-primary",
            "second_operator_id": "op-secondary",
            "expires_at": expires.isoformat(),
        },
    )
    assert response.status_code == 201
    oid = response.json()["override_id"]
    url = f"/v1/overrides/{oid}?second_operator_id=op-secondary"
    assert anonymous_client.delete(url, headers=AUTH).status_code == 401
    assert (
        anonymous_client.delete(
            url, headers={**AUTH, "X-FloodRoute-Co-Signature": PRIMARY_TOKEN}
        ).status_code
        == 403
    )
    assert (
        app_db.execute("select expires_at from override where override_id=%s", (oid,)).fetchone()[0]
        == expires
    )
    assert (
        anonymous_client.delete(
            url, headers={**AUTH, "X-FloodRoute-Co-Signature": SECONDARY_TOKEN}
        ).status_code
        == 200
    )


def test_reroute_partial_current_forecast_returns_generic_502_before_router(client, app_db):
    app_db.execute(
        """insert into segment (segment_id,osm_way_id,geom,road_class,city_id,assessed)
           values (9001,19001,'SRID=4326;LINESTRING(77.58 12.97,77.59 12.98)','secondary',1,true)"""
    )
    app_db.execute(
        """insert into segment_risk (segment_id,vclass,horizon_min,p_unusable,
           depth_p50_cm,depth_p90_cm,state,confidence,evidence_age_s,model_version,updated_at)
           values (9001,'car',0,0,0,0,'clear','high',0,'v0.0.1',now())"""
    )

    def router_must_not_run(*args):
        pytest.fail("Candidate router called with an invalid current forecast")

    client.app.dependency_overrides[get_router] = lambda: router_must_not_run
    response = client.post(
        "/v1/route/reroute",
        json={
            "origin": {"lat": 12.97, "lon": 77.58},
            "destination": {"lat": 12.98, "lon": 77.59},
            "vclass": "car",
            "current_edges": [{"segment_id": 9001, "travel_time_s": 60, "length_m": 600}],
        },
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "routing temporarily unavailable"}
