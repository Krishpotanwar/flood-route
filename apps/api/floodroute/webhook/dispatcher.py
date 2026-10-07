"""Webhook event dispatcher with HMAC signing and delivery log persistence."""

from __future__ import annotations

import ipaddress
import json
import socket
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import psycopg

from floodroute.webhook.models import WebhookEvent
from floodroute.webhook.signing import build_webhook_headers


def resolve_webhook_target(target: str) -> tuple[httpx.URL, str]:
    """Validate every resolved address and pin the connection to a public IP.

    Keep the original Host/SNI for HTTP routing and certificate verification;
    connecting to the validated IP avoids a second, potentially rebound lookup.
    """
    url = httpx.URL(target)
    if url.scheme != "https" or not url.host or url.username or url.password or url.fragment:
        raise ValueError(
            "Webhook targets must be public HTTPS URLs without credentials or fragments"
        )
    try:
        addresses = [ipaddress.ip_address(url.host)]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(row[4][0])
                for row in socket.getaddrinfo(url.host, url.port or 443, type=socket.SOCK_STREAM)
            ]
        except (OSError, ValueError):
            raise ValueError("Webhook destination is unavailable") from None
    if not addresses or any(
        not address.is_global
        or address.is_reserved
        or (getattr(address, "ipv4_mapped", None) is not None and not address.ipv4_mapped.is_global)
        for address in addresses
    ):
        raise ValueError("Webhook destination must resolve exclusively to public addresses")
    return url.copy_with(host=str(addresses[0])), url.host


def dispatch_event(
    db: psycopg.Connection,
    event: WebhookEvent,
    client: httpx.Client | None = None,
    only_subscription_id: Any | None = None,
) -> list[dict[str, Any]]:
    """Dispatch an event to all matching active webhook subscriptions.

    `only_subscription_id` restricts delivery to one subscription (used by the
    test-ping endpoint so one ping never fans out to every subscriber).
    """
    if only_subscription_id is None:
        sql = """
        select subscription_id, target_url, secret
        from webhook_subscription
        where is_active and %s = ANY(events)
        """
        rows = db.execute(sql, (event.event_type,)).fetchall()
    else:
        sql = """
        select subscription_id, target_url, secret
        from webhook_subscription
        where is_active and %s = ANY(events) and subscription_id = %s
        """
        rows = db.execute(sql, (event.event_type, only_subscription_id)).fetchall()
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
        # Each TLS connection verifies its own original hostname, even when
        # two subscribers share an IP. No proxy or redirect can re-resolve it.
        client = httpx.Client(
            timeout=5.0,
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        close_client = True

    results: list[dict[str, Any]] = []

    try:
        for sub_id, target_url, secret in rows:
            delivery_id = uuid4()
            try:
                headers = build_webhook_headers(
                    secret, payload_bytes, str(event.event_id), timestamp_str
                )
            except Exception as exc:  # noqa: BLE001 - one bad row never stops the loop
                db.execute(
                    """
                    insert into webhook_delivery (
                        delivery_id, subscription_id, event_id, event_type, payload,
                        status, status_code, attempt, delivered_at, error_message
                    ) values (%s, %s, %s, %s, %s, 'failed', %s, 1, %s, %s)
                    """,
                    (
                        delivery_id,
                        sub_id,
                        event.event_id,
                        event.event_type,
                        json.dumps(event.payload),
                        None,
                        None,
                        f"header build failed: {exc}",
                    ),
                )
                db.commit()
                results.append(
                    {
                        "delivery_id": str(delivery_id),
                        "subscription_id": str(sub_id),
                        "status": "failed",
                        "status_code": None,
                        "error": str(exc),
                    }
                )
                continue
            status = "failed"
            status_code = None
            error_msg = None
            delivered_at = None

            try:
                pinned_url, hostname = resolve_webhook_target(target_url)
                original_url = httpx.URL(target_url)
                headers["Host"] = original_url.netloc.decode("ascii")
                resp = client.post(
                    pinned_url,
                    content=payload_bytes,
                    headers=headers,
                    follow_redirects=False,
                    timeout=5.0,
                    extensions={"sni_hostname": hostname},
                )
                status_code = resp.status_code
                if 200 <= resp.status_code < 300:
                    status = "success"
                    delivered_at = datetime.now(UTC)
                else:
                    status = "failed"
                    error_msg = f"HTTP {resp.status_code}"
            except Exception:  # noqa: BLE001 - per-subscription isolation, keep going
                status = "failed"
                error_msg = "Webhook delivery failed"

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
                    delivered_at,
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
