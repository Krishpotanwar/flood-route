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


def test_webhook_crud(client, app_db):
    # 1. Create subscription
    create_body = {
        "target_url": "https://example.com/flood-webhook",
        "secret": "my-secret-key-1234567890",
        "events": ["segment.state_changed", "route.invalidated"],
    }
    r_create = client.post("/v1/webhooks", json=create_body)
    assert r_create.status_code == 201
    data = r_create.json()
    sub_id = data["subscription_id"]
    assert data["target_url"] == "https://example.com/flood-webhook"
    assert data["secret_preview"] == "****7890"
    assert data["is_active"] is True
    assert set(data["events"]) == {"segment.state_changed", "route.invalidated"}

    # 2. List subscriptions
    r_list = client.get("/v1/webhooks")
    assert r_list.status_code == 200
    subs = r_list.json()
    assert len(subs) == 1
    assert subs[0]["subscription_id"] == sub_id

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
