"""Tests for enterprise webhook subscriptions and HMAC delivery logging."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx

from floodroute.webhook.dispatcher import dispatch_event
from floodroute.webhook.models import WebhookEvent
from floodroute.webhook.signing import (
    build_webhook_headers,
    compute_signature,
    generate_webhook_secret,
    verify_signature,
    verify_timestamp_fresh,
)


def test_webhook_signing_utilities():
    secret = generate_webhook_secret()
    assert len(secret) == 64

    payload = b'{"event":"segment.state_changed","segment_id":1001}'
    sig = compute_signature(secret, payload)
    assert len(sig) == 64

    headers = build_webhook_headers(secret, payload, "evt-123", "2026-10-06T12:00:00+00:00")
    assert headers["X-FloodRoute-Signature-256"] == f"sha256={sig}"
    assert headers["X-FloodRoute-Event-Id"] == "evt-123"
    assert headers["X-FloodRoute-Timestamp"] == "2026-10-06T12:00:00+00:00"

    # Verification
    assert verify_signature(secret, payload, headers["X-FloodRoute-Signature-256"]) is True
    assert verify_signature(secret, b'{"tampered":true}', headers["X-FloodRoute-Signature-256"]) is False
    assert verify_signature("wrong-secret-12345678", payload, headers["X-FloodRoute-Signature-256"]) is False


def test_delivery_timestamp_freshness_window():
    now = datetime.now(UTC)
    assert verify_timestamp_fresh(now.isoformat()) is True
    assert verify_timestamp_fresh("2020-01-01T00:00:00+00:00") is False
    assert verify_timestamp_fresh("not-a-time") is False
    assert verify_timestamp_fresh("2020-01-01T00:00:00") is False  # naive never counts


def test_failed_delivery_logs_null_delivered_at_and_the_loop_continues(app_db):
    good_id, bad_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    app_db.execute(
        """
        insert into webhook_subscription (subscription_id, target_url, secret, events, is_active, created_at)
        values (%s, 'https://good.example.com/hook', 'good-secret-12345678', array['segment.state_changed'], true, %s),
               (%s, 'https://bad.example.com/hook', 'bad-secret-12345678', array['segment.state_changed'], true, %s)
        """,
        (good_id, now, bad_id, now),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "bad" in request.headers["host"]:
            raise httpx.ConnectError("unreachable", request=request)
        return httpx.Response(200, json={"received": True})

    event = WebhookEvent(
        event_type="segment.state_changed", timestamp=now, payload={"ping": True}
    )
    results = dispatch_event(
        app_db, event, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert len(results) == 2  # the bad subscription never aborts the loop
    assert {r["status"] for r in results} == {"success", "failed"}
    rows = app_db.execute(
        "select status, delivered_at from webhook_delivery order by status"
    ).fetchall()
    by_status = {r[0]: r[1] for r in rows}
    assert by_status["success"] is not None
    assert by_status["failed"] is None


def test_webhook_crud(client, app_db):
    app_db.execute("insert into tenant (tenant_id, name, kind) values (7, 'Acme', 'fleet')")
    # 1. Create subscription
    create_body = {
        "target_url": "https://example.com/flood-webhook",
        "secret": "my-secret-key-1234567890abcdef12",
        "events": ["segment.state_changed", "route.invalidated"],
    }
    r_create = client.post("/v1/webhooks?tenant_id=7", json=create_body)
    assert r_create.status_code == 201
    data = r_create.json()
    sub_id = data["subscription_id"]
    assert data["target_url"] == "https://example.com/flood-webhook"
    assert data["secret_preview"] == "****ef12"
    assert data["is_active"] is True
    assert data["tenant_id"] == 7
    assert set(data["events"]) == {"segment.state_changed", "route.invalidated"}

    # 2. List subscriptions
    r_list = client.get("/v1/webhooks")
    assert r_list.status_code == 200
    subs = r_list.json()
    assert len(subs) == 1
    assert subs[0]["subscription_id"] == sub_id

    # 2b. Tenant-scoped list filters out other tenants
    r_tenant = client.get("/v1/webhooks?tenant_id=8")
    assert r_tenant.status_code == 200
    assert r_tenant.json() == []
    r_tenant7 = client.get("/v1/webhooks?tenant_id=7")
    assert len(r_tenant7.json()) == 1

    # 3. Deactivate subscription
    r_del = client.delete(f"/v1/webhooks/{sub_id}")
    assert r_del.status_code == 204

    # 4. Confirm no active subscriptions
    r_list2 = client.get("/v1/webhooks")
    assert r_list2.status_code == 200
    assert len(r_list2.json()) == 0

    # 5. Delete again should return 404
    r_del2 = client.delete(f"/v1/webhooks/{sub_id}")
    assert r_del2.status_code == 404


def test_webhook_validation(client):
    # Invalid event
    r = client.post(
        "/v1/webhooks",
        json={
            "target_url": "https://example.com/hook",
            "events": ["invalid.event_name"],
        },
    )
    assert r.status_code == 422

    # Invalid URL scheme
    r2 = client.post(
        "/v1/webhooks",
        json={
            "target_url": "ftp://example.com/hook",
        },
    )
    assert r2.status_code == 422


def test_webhook_dispatcher_and_deliveries(client, app_db):
    target_url = "https://dispatcher-test.example.com/webhook"
    sub_id = uuid4()
    secret = "dispatcher-test-secret-12345"
    now = datetime.now(UTC)

    app_db.execute(
        """
        insert into webhook_subscription (subscription_id, target_url, secret, events, is_active, created_at)
        values (%s, %s, %s, array['segment.state_changed'], true, %s)
        """,
        (sub_id, target_url, secret, now),
    )

    # Test custom mock transport
    def mock_handler(request: httpx.Request) -> httpx.Response:
        sig_header = request.headers.get("X-FloodRoute-Signature-256", "")
        if verify_signature(secret, request.content, sig_header):
            return httpx.Response(200, json={"received": True})
        return httpx.Response(401, json={"error": "invalid signature"})

    transport = httpx.MockTransport(mock_handler)
    mock_client = httpx.Client(transport=transport)

    event = WebhookEvent(
        event_type="segment.state_changed",
        timestamp=now,
        payload={"segment_id": 9999, "new_state": "impassable"},
    )

    results = dispatch_event(app_db, event, client=mock_client)
    assert len(results) == 1
    res = results[0]
    assert res["status"] == "success"
    assert res["status_code"] == 200

    # Check deliveries endpoint
    r_deliv = client.get(f"/v1/webhooks/{sub_id}/deliveries")
    assert r_deliv.status_code == 200
    deliveries = r_deliv.json()
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "success"
    assert deliveries[0]["event_type"] == "segment.state_changed"
