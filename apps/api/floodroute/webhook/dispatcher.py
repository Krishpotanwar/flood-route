"""Webhook event dispatcher with HMAC signing and delivery log persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import psycopg

from floodroute.webhook.models import WebhookEvent
from floodroute.webhook.signing import build_webhook_headers


def dispatch_event(
    db: psycopg.Connection,
    event: WebhookEvent,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Dispatch an event to all matching active webhook subscriptions."""
    sql = """
    select subscription_id, target_url, secret
    from webhook_subscription
    where is_active and %s = ANY(events)
    """
    rows = db.execute(sql, (event.event_type,)).fetchall()
    if not rows:
        return []

    data = {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat(),
        "payload": event.payload,
    }
    payload_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
    timestamp_str = event.timestamp.isoformat()

    close_client = False
    if client is None:
        client = httpx.Client(timeout=5.0)
        close_client = True

    results: list[dict[str, Any]] = []

    try:
        for sub_id, target_url, secret in rows:
            delivery_id = uuid4()
            headers = build_webhook_headers(secret, payload_bytes, str(event.event_id), timestamp_str)
            status = "failed"
            status_code = None
            error_msg = None
            now = datetime.now(UTC)

            try:
                resp = client.post(target_url, content=payload_bytes, headers=headers)
                status_code = resp.status_code
                if 200 <= resp.status_code < 300:
                    status = "success"
                else:
                    status = "failed"
                    error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except (httpx.HTTPError, OSError, RuntimeError) as exc:

                status = "failed"
                error_msg = str(exc)


            insert_sql = """
            insert into webhook_delivery (
                delivery_id, subscription_id, event_id, event_type, payload,
                status, status_code, attempt, delivered_at, error_message
            ) values (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
            """
            db.execute(
                insert_sql,
                (
                    delivery_id,
                    sub_id,
                    event.event_id,
                    event.event_type,
                    json.dumps(event.payload),
                    status,
                    status_code,
                    now,
                    error_msg,
                ),
            )
            db.commit()

            results.append(
                {
                    "delivery_id": str(delivery_id),
                    "subscription_id": str(sub_id),
                    "status": status,
                    "status_code": status_code,
                    "error": error_msg,
                }
            )
    finally:
        if close_client:
            client.close()

    return results
