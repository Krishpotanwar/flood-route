"""Fix-3 regression tests: HTTP API + bot + freeze + metrics + console + webhooks.

One minimal test per audit fix. All tests run against throwaway databases;
no live network calls (webhook delivery is monkeypatched at the boundary).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import floodroute.api.routes.bot as bot_routes
import floodroute.api.routes.webhooks as webhooks_routes
import floodroute.bot.whatsapp as wa
from floodroute.api.deps import get_db, get_route_config, get_router, get_score_config
from floodroute.api.main import create_app
from floodroute.api.photo import ALLOWED_FORMATS
from floodroute.bot.sms import render_sms
from floodroute.feed.snapshot import generate_city_closure_snapshot
from floodroute.metrics.collector import _format_labels
from floodroute.metrics.middleware import sanitize_path
from floodroute.route.models import Edge, Route, RouteRequest

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE_1 = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"
SEG_LINE_2 = "SRID=4326;LINESTRING(77.60 12.97, 77.61 12.98)"


def _seed_segments(app_db, *ids):
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    for i, sid in enumerate(ids):
        line = SEG_LINE_1 if i % 2 == 0 else SEG_LINE_2
        app_db.execute(
            """
            insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
            values (%s, %s, %s, 'residential', 1, true)
            """,
            (sid, 30000 + sid, line),
        )


def _seed_risk(app_db, sid, state, p, updated, horizons=(0, 30, 60, 120), conf="high", age=30):
    for h in horizons:
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (%s, 'car', %s, %s, 0.0, 5.0, %s, %s, %s, 'v0.0.1', %s)
            """,
            (sid, h, p, state, conf, age, updated),
        )


def _wa_text_payload(sender="919988776655", body="status"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.fix3.1",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def _signed_wa_post(client, payload):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    secret = os.environ["WHATSAPP_APP_SECRET"]
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/v1/whatsapp/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig}",
        },
    )


# ---- C4: verify token has no fallback ----------------------------------------


def test_verify_token_required_at_startup(monkeypatch):
    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="WHATSAPP_VERIFY_TOKEN"):
        bot_routes._require_verify_token()


def test_no_hardcoded_verify_token_in_source():
    src = pathlib.Path(bot_routes.__file__).read_text()
    assert "floodroute_wa_token_2026" not in src


# ---- C2: inbound shape + rate limit ------------------------------------------


def test_whatsapp_missing_coords_falls_back_without_500(client):
    payload = _wa_text_payload()
    payload["entry"][0]["changes"][0]["value"]["messages"][0] = {
        "from": "919988776655",
        "id": "wamid.fix3.loc",
        "type": "location",
        "location": {"latitude": None, "longitude": None},
    }
    r = _signed_wa_post(client, payload)
    assert r.status_code == 200
    assert r.json()["status"] == "processed"
    assert r.json()["outbound"]["type"] == "interactive"


def test_whatsapp_missing_sender_is_ignored(client):
    payload = _wa_text_payload()
    del payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"]
    r = _signed_wa_post(client, payload)
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_sender_rate_limit_window(monkeypatch):
    monkeypatch.setattr(wa, "_RATE", {})
    t0 = 1_000_000.0
    for _ in range(wa.RATE_LIMIT_N):
        assert wa.sender_allowed("919000000001", now_ts=t0) is True
    assert wa.sender_allowed("919000000001", now_ts=t0) is False
    assert wa.sender_allowed("919000000001", now_ts=t0 + wa.RATE_LIMIT_WINDOW_S) is True


def test_app_secret_required_at_startup(monkeypatch):
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="WHATSAPP_APP_SECRET"):
        bot_routes._require_app_secret()


def test_whatsapp_unsigned_post_is_403(client):
    r = client.post("/v1/whatsapp/webhook", json=_wa_text_payload())
    assert r.status_code == 403


def test_whatsapp_wrong_signature_is_403(client):
    payload = _wa_text_payload()
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    r = client.post(
        "/v1/whatsapp/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    assert r.status_code == 403


def test_whatsapp_signed_post_processes(client):
    r = _signed_wa_post(client, _wa_text_payload(body="status"))
    assert r.status_code == 200
    assert r.json()["status"] == "processed"
    assert "outbound" in r.json()


def test_verify_whatsapp_signature_rejects_malformed():
    secret = os.environ["WHATSAPP_APP_SECRET"]
    body = b'{"entry":[]}'
    good = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert wa.verify_whatsapp_signature(body, good, secret) is True
    assert wa.verify_whatsapp_signature(body, None, secret) is False
    assert wa.verify_whatsapp_signature(body, "sha256=deadbeef", secret) is False
    assert wa.verify_whatsapp_signature(body, "badprefix", secret) is False
    assert wa.verify_whatsapp_signature(body, good, "") is False


# ---- WhatsApp I14/I15/I16 ----------------------------------------------------


def test_whatsapp_unknown_vehicle_class_asks_retry(app_db):
    wa.get_user_session("919000000002").lang = "en"
    parsed = {
        "sender": "919000000002",
        "message_id": "wamid.fix3.veh",
        "type": "interactive",
        "text": None,
        "location": None,
        "button_id": "VEHICLE_ROCKET",
    }
    resp = wa.handle_incoming_message(app_db, parsed)
    assert "not recognized" in resp["text"]["body"]
    assert wa.get_user_session("919000000002").vclass == "car"


def test_whatsapp_sessions_evict_expired_and_capped(monkeypatch):
    monkeypatch.setattr(wa, "_SESSIONS", {})
    monkeypatch.setattr(wa, "_RATE", {})
    monkeypatch.setattr(wa, "SESSION_CAP", 2)
    old = wa.get_user_session("919000000003")
    old.updated_at = datetime.now(UTC) - timedelta(seconds=wa.SESSION_TTL_S + 10)
    wa.get_user_session("919000000004")
    wa.get_user_session("919000000005")
    wa.get_user_session("919000000006")
    assert "919000000003" not in wa._SESSIONS
    assert len(wa._SESSIONS) <= 2


# ---- SMS I12/I13 --------------------------------------------------------------


def test_sms_word_boundary_blocks_punctuation_variants():
    for variant in ["(safe)", "safe.", "SAFE!", "all clear, stay safe"]:
        with pytest.raises(ValueError, match="safety invariant"):
            render_sms("EN_ROAD_CLOSED", {"landmark": variant, "detour": "Main Rd"})


def test_sms_allows_unsafe_substring():
    out = render_sms(
        "EN_ROAD_CLOSED",
        {"landmark": "Riverside", "detour": "Lakeview (unsafe at night)"},
    )
    assert out["is_single_segment"] is True


def test_sms_missing_variable_lists_names():
    with pytest.raises(ValueError, match="detour"):
        render_sms("EN_ROAD_CLOSED", {"landmark": "Silk Board"})


# ---- H-a: deps fail closed ----------------------------------------------------


def test_db_risk_for_partial_horizons_raises(app_db):
    now = datetime.now(UTC)
    _seed_segments(app_db, 9501)
    _seed_risk(app_db, 9501, "risky", 0.4, now, horizons=(0,))
    from floodroute.api.deps import db_risk_for

    with pytest.raises(RuntimeError, match="incomplete forecast"):
        db_risk_for(app_db, 9501, "car")


def test_db_risk_for_zero_rows_is_none(app_db):
    from floodroute.api.deps import db_risk_for

    assert db_risk_for(app_db, 9599, "car") is None


def test_db_risk_for_skewed_runs_raise(app_db):
    now = datetime.now(UTC)
    _seed_segments(app_db, 9502)
    for i, h in enumerate((0, 30, 60, 120)):
        skew = now + timedelta(hours=2) if i == 3 else now
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9502, 'car', %s, 0.4, 0.0, 5.0, 'risky', 'high', 30, 'v0.0.1', %s)
            """,
            (h, skew),
        )
    from floodroute.api.deps import db_risk_for

    with pytest.raises(RuntimeError, match="mixes runs"):
        db_risk_for(app_db, 9502, "car")


def test_db_risk_for_uses_oldest_stamp_weakest_confidence_oldest_age(app_db):
    now = datetime.now(UTC)
    _seed_segments(app_db, 9503)
    for i, h in enumerate((0, 30, 60, 120)):
        conf = "low" if h == 30 else "high"
        app_db.execute(
            """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at
            )
            values (9503, 'car', %s, 0.4, 0.0, 5.0, 'risky', %s, %s, 'v0.0.1', %s)
            """,
            (h, conf, 30 * (i + 1), now + timedelta(seconds=i)),
        )
    from floodroute.api.deps import db_risk_for

    risk = db_risk_for(app_db, 9503, "car")
    assert risk is not None
    assert risk.issued_at == now
    assert risk.confidence == "low"
    assert risk.evidence_age_s == 120


# ---- H-d + I4: risk allow-list source + bbox -----------------------------------


def test_risk_allow_lists_come_from_score_db():
    from floodroute.api.routes.risk import VALID_HORIZONS, VALID_VCLASSES
    from floodroute.score.db import SUPPORTED_HORIZONS, SUPPORTED_VCLASSES

    assert VALID_HORIZONS is SUPPORTED_HORIZONS
    assert VALID_VCLASSES is SUPPORTED_VCLASSES


def test_risk_bbox_rejects_out_of_range_and_oversize(client):
    r1 = client.get("/v1/risk?bbox=-200,0,10,10")
    assert r1.status_code == 400
    r2 = client.get("/v1/risk?bbox=70,8,85,20")
    assert r2.status_code == 422


# ---- I2 + I9: feed validation + freeze -----------------------------------------


def test_feed_rejects_unknown_params(client):
    assert client.get("/v1/feed/closures.geojson?vclass=rocket").status_code == 422
    assert client.get("/v1/feed/closures.geojson?horizon_min=45").status_code == 422
    assert client.get("/v1/feed/cap.xml?vclass=rocket").status_code == 422


def test_feed_frozen_returns_503(client, app_db):
    from floodroute.safety.kill_switch import engage_kill_switch

    engage_kill_switch(
        conn=app_db, scope="global", reason="Fix3 feed freeze", operator_id="op_fix3"
    )
    assert client.get("/v1/feed/closures.geojson").status_code == 503
    r = client.get("/v1/feed/cap.xml")
    assert r.status_code == 503
    assert "advisory_off" in r.text or "freeze" in r.text


# ---- H-e: snapshot freeze + library vclass ------------------------------------


def test_snapshot_city_freeze_suspends_serving(client, app_db):
    from floodroute.safety.kill_switch import engage_kill_switch

    engage_kill_switch(
        conn=app_db,
        scope="city",
        reason="Fix3 snapshot freeze",
        operator_id="op_fix3",
        city_id=1,
    )
    assert client.get("/v1/feed/snapshot/closures?city=bengaluru").status_code == 503
    assert client.post("/v1/feed/snapshot/generate?city=bengaluru").status_code == 503
    assert client.get("/v1/feed/snapshot/status").status_code == 200


def test_snapshot_library_rejects_unknown_vclass(app_db, tmp_path):
    with pytest.raises(ValueError, match="Unknown vclass"):
        generate_city_closure_snapshot(
            app_db, city_name="bengaluru", vclass="rocket", snapshot_dir=tmp_path
        )


# ---- H-c + I8 + H-f: route decision audit --------------------------------------


def _route_payload(now):
    return {
        "origin": {"lat": 12.97, "lon": 77.58},
        "destination": {"lat": 12.99, "lon": 77.60},
        "vclass": "car",
        "depart_at": now.isoformat(),
        "profile": "citizen",
        "lang": "en",
    }


def test_route_records_every_violating_segment(app_db):
    now = datetime.now(UTC)
    _seed_segments(app_db, 9201, 9202)
    _seed_risk(app_db, 9201, "impassable", 0.95, now)
    _seed_risk(app_db, 9202, "impassable", 0.95, now)

    def stubborn_router(origin, dest, vclass, date_time, exclude_polys=()):
        return Route(
            (
                Edge(9201, ((12.97, 77.58), (12.98, 77.59)), 120.0, 800.0),
                Edge(9202, ((12.98, 77.59), (12.99, 77.60)), 180.0, 1000.0),
            )
        )

    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    app.dependency_overrides[get_router] = lambda: stubborn_router
    with TestClient(app) as c:
        r = c.post("/v1/route", json=_route_payload(now))
    assert r.status_code == 200
    row = app_db.execute(
        "select rejected from route_decision where decision_id = %s",
        (r.json()["decision_id"],),
    ).fetchone()
    raw = row[0]
    rejected = json.loads(raw) if isinstance(raw, str) else list(raw)
    assert sorted(rejected) == [9201, 9202]


def test_reroute_persists_decision(app_db):
    payload = {
        "origin": {"lat": 12.97, "lon": 77.59},
        "destination": {"lat": 12.92, "lon": 77.62},
        "vclass": "car",
        "current_edges": [
            {
                "segment_id": 901,
                "travel_time_s": 120,
                "length_m": 500,
                "turn_off_after": True,
                "geometry": [{"lat": 12.97, "lon": 77.59}, {"lat": 12.95, "lon": 77.60}],
            }
        ],
        "profile": "citizen",
        "lang": "en",
    }
    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db

    def clear_router(origin, dest, vclass, date_time, exclude_polys=()):
        return Route(
            (Edge(901, ((12.97, 77.59), (12.95, 77.60)), 120.0, 500.0),)
        )

    app.dependency_overrides[get_router] = lambda: clear_router
    with TestClient(app) as c:
        r = c.post("/v1/route/reroute", json=payload)
    assert r.status_code == 200
    row = app_db.execute(
        "select vclass from route_decision where decision_id = %s",
        (r.json()["decision_id"],),
    ).fetchone()
    assert row is not None and row[0] == "car"


def test_route_502_hides_internals(app_db):
    from fastapi import HTTPException

    from floodroute.api.routes.route import compute_route

    def boom(*args, **kwargs):
        raise RuntimeError("valhalla boom")

    req = RouteRequest(**_route_payload(datetime.now(UTC)))
    with pytest.raises(HTTPException) as exc:
        compute_route(
            req,
            db=app_db,
            route_cfg=get_route_config(),
            score_cfg=get_score_config(),
            router_fn=boom,
        )
    assert exc.value.status_code == 502
    assert exc.value.detail == "routing temporarily unavailable"


def test_watch_create_frozen_returns_503(client, app_db):
    from uuid import uuid4

    from floodroute.safety.kill_switch import engage_kill_switch

    now = datetime.now(UTC)
    decision_id = uuid4()
    app_db.execute(
        "insert into route_decision (decision_id, ts, vclass, model_version) values (%s, %s, 'car', 'v0.0.1')",
        (decision_id, now),
    )
    engage_kill_switch(
        conn=app_db, scope="global", reason="Fix3 watch freeze", operator_id="op_fix3"
    )
    r = client.post(
        f"/v1/routes/{decision_id}/watch",
        json={
            "device_token": "dev-frozen",
            "alert_channel": "fcm",
            "contact_target": "target-frozen",
            "dwell_minutes": 45,
        },
    )
    assert r.status_code == 503


# ---- H-b + I23: webhooks --------------------------------------------------------


def test_webhook_short_secret_rejected(client):
    r = client.post(
        "/v1/webhooks",
        json={"target_url": "https://example.com/hook", "secret": "short"},
    )
    assert r.status_code == 422


def test_webhook_test_ping_targets_named_subscription_only(client, app_db, monkeypatch):
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    now = _dt.now(_UTC)
    id1, id2 = uuid4(), uuid4()
    app_db.execute(
        """
        insert into webhook_subscription (subscription_id, target_url, secret, events, is_active, created_at)
        values (%s, 'https://one.example.com/hook', 'one-secret-12345678901234567890', array['segment.state_changed'], true, %s),
               (%s, 'https://two.example.com/hook', 'two-secret-12345678901234567890', array['segment.state_changed'], true, %s)
        """,
        (id1, now, id2, now),
    )
    seen = {}

    def fake_dispatch(db, event, **kwargs):
        seen.update(kwargs)
        seen["event"] = event
        return [{"status": "success", "subscription_id": str(kwargs.get("only_subscription_id"))}]

    monkeypatch.setattr(webhooks_routes, "dispatch_event", fake_dispatch)
    r = client.post(f"/v1/webhooks/{id1}/test")
    assert r.status_code == 200
    assert seen.get("only_subscription_id") == id1
    assert r.json()[0]["subscription_id"] == str(id1)


def test_webhook_delete_rejects_other_tenant(client, app_db):
    app_db.execute("insert into tenant (tenant_id, name, kind) values (9, 'T9', 'fleet')")
    r = client.post(
        "/v1/webhooks?tenant_id=9",
        json={"target_url": "https://example.com/hook", "events": ["segment.state_changed"]},
    )
    assert r.status_code == 201
    sub_id = r.json()["subscription_id"]
    assert client.delete(f"/v1/webhooks/{sub_id}?tenant_id=10").status_code == 404
    assert client.get(f"/v1/webhooks/{sub_id}/deliveries?tenant_id=10").status_code == 404


def test_receipt_verify_and_dedup(app_db):
    from floodroute.webhook.receipt import is_duplicate_delivery, verify_receipt
    from floodroute.webhook.signing import compute_signature

    secret = "receipt-secret-12345678901234567890"
    fresh = datetime.now(UTC).isoformat()
    payload = json.dumps({"event_id": "evt-1", "timestamp": fresh}).encode()
    sig = "sha256=" + compute_signature(secret, payload)
    assert verify_receipt(secret, payload, sig, fresh) is True
    assert verify_receipt(secret, b'{"tampered":true}', sig, fresh) is False
    assert verify_receipt(secret, payload, sig, "2020-01-01T00:00:00+00:00") is False
    assert verify_receipt("", payload, sig, fresh) is False

    sub_id = uuid4()
    event_id = uuid4()
    now = datetime.now(UTC)
    app_db.execute(
        """
        insert into webhook_subscription (subscription_id, target_url, secret, events, is_active, created_at)
        values (%s, 'https://dup.example.com/hook', 'dup-secret-12345678901234567890', array['segment.state_changed'], true, %s)
        """,
        (sub_id, now),
    )
    assert is_duplicate_delivery(app_db, sub_id, event_id) is False
    app_db.execute(
        """
        insert into webhook_delivery (delivery_id, subscription_id, event_id, event_type, payload, status, attempt)
        values (%s, %s, %s, 'segment.state_changed', '{}', 'success', 1)
        """,
        (uuid4(), sub_id, event_id),
    )
    assert is_duplicate_delivery(app_db, sub_id, event_id) is True


# ---- I5 + I6 + I22 + M2: overrides ----------------------------------------------


def test_override_tenant_required(client, app_db):
    now = datetime.now(UTC)
    _seed_segments(app_db, 9601)
    r = client.post(
        "/v1/overrides",
        json={
            "segment_id": 9601,
            "action": "close",
            "reason": "Water over road surface",
            "operator_id": "op-primary",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert r.status_code == 422


def test_override_audit_carries_replay_context(client, app_db):
    now = datetime.now(UTC)
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Admin', 'admin')")
    _seed_segments(app_db, 9602)
    r = client.post(
        "/v1/overrides",
        json={
            "tenant_id": 1,
            "segment_id": 9602,
            "action": "close",
            "reason": "Water over road surface",
            "operator_id": "op-primary",
            "second_operator_id": "op-secondary",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert r.status_code == 201
    ov_id = r.json()["override_id"]
    items = client.get("/v1/audit?action=override_close").json()
    match = next(i for i in items if i["segment_id"] == 9602)
    assert match["after"]["override_id"] == ov_id
    assert match["after"]["tenant_id"] == 1
    assert match["after"]["second_operator_id"] == "op-secondary"
    assert "expires_at" in match["after"]

    # Tenant-scoped list
    assert any(i["override_id"] == ov_id for i in client.get("/v1/overrides?tenant_id=1").json())
    assert client.get("/v1/overrides?tenant_id=999").json() == []

    # Revert rejects a too-short reason
    assert client.delete(f"/v1/overrides/{ov_id}?reason=no").status_code == 422


def test_audit_csv_neutralizes_formulas(client, app_db):
    app_db.execute(
        """
        insert into audit_log (actor, action, segment_id, reason)
        values ('=cmd|''/c calc''!A0', '+evil-action', 9603, '@malicious reason')
        """
    )
    r = client.get("/v1/audit?format=csv")
    assert r.status_code == 200
    assert "'=cmd" in r.text
    assert "'+evil-action" in r.text
    assert "'@malicious reason" in r.text


# ---- I10 + I11: photo ------------------------------------------------------------


def test_photo_upload_rejects_wrong_type_and_oversize(client):
    r_type = client.post(
        "/v1/reports/photo",
        content=b"not-an-image",
        headers={"Content-Type": "text/plain"},
    )
    assert r_type.status_code == 415
    r_big = client.post(
        "/v1/reports/photo",
        content=b"tiny",
        headers={"Content-Type": "image/jpeg", "Content-Length": str(99 * 1024 * 1024)},
    )
    assert r_big.status_code == 413


def test_photo_allowlist_drops_mpo():
    assert "MPO" not in ALLOWED_FORMATS
    assert ALLOWED_FORMATS == {"JPEG", "PNG", "WEBP"}


# ---- I18 + I19: metrics ----------------------------------------------------------


def test_metrics_label_escaping():
    rendered = _format_labels({"endpoint": 'a"b\\c\nd', "method": "GET"})
    assert rendered == '{endpoint="a\\"b\\\\c\\nd",method="GET"}'


def test_metrics_path_cardinality():
    assert sanitize_path("/v1/cities/bengaluru") == "/v1/cities/{city}"
    assert sanitize_path("/v1/cities/bengaluru/hotspots") == "/v1/cities/{city}/{op}"
    assert sanitize_path("/v1/reports/photo/ph_abc123.jpg") == "/v1/reports/photo/{id}"
    assert sanitize_path("/v1/health") == "/v1/health"


# ---- I1 + I20 + C3 -----------------------------------------------------------------


def test_cors_has_no_credentialed_wildcard(client):
    r = client.get("/v1/health", headers={"Origin": "https://floodroute.in"})
    assert r.headers.get("access-control-allow-origin") == "https://floodroute.in"
    assert "access-control-allow-credentials" not in r.headers
    r_evil = client.get("/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r_evil.headers


def test_health_db_error_is_generic():
    import psycopg

    from floodroute.api.routes.health import health_check

    class BoomDb:
        def execute(self, *args, **kwargs):
            raise psycopg.OperationalError("conn refused at 10.0.0.9:5432")

    data = health_check(db=BoomDb(), cfg=SimpleNamespace(model_version="v0.0.1"))
    assert data["status"] == "degraded"
    assert data["database"] == "error"
    assert "10.0.0.9" not in json.dumps(data)


def test_console_escapes_dynamic_strings():
    app = create_app()
    with TestClient(app) as c:
        text = c.get("/console").text
    assert "escapeHtml(" in text
    assert "${item.actor}" not in text
    assert "${item.reason}" not in text
    assert "${p.segment_id}" not in text
    assert "escapeHtml(p.segment_id)" in text


def test_verify_token_env_name():
    assert os.environ["WHATSAPP_VERIFY_TOKEN"] == "test-only-verify-token-not-a-secret"
