"""Inbound enterprise-webhook receipt verification (receiver side).

Outbound delivery signs with HMAC-SHA256 (`signing`); this module is the
mirror for receivers: check the signature, enforce the replay window, and
drop already-seen event ids. No HTTP receipt endpoint exists in
`api/routes/` yet, so nothing wires this in; the helpers are covered by unit
tests and ready for that endpoint.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from floodroute.webhook.signing import verify_signature, verify_timestamp_fresh


def verify_receipt(
    secret: str,
    payload_bytes: bytes,
    signature_header: str,
    timestamp_iso: str,
    max_skew_s: float = 300.0,
) -> bool:
    """True only when the signature matches AND the timestamp is fresh.

    Either check alone is insufficient: the signature cannot stop a captured
    delivery from being replayed, and freshness without a signature proves
    nothing about the sender.
    """
    if not secret or not signature_header or not timestamp_iso:
        return False
    if not verify_signature(secret, payload_bytes, signature_header):
        return False
    try:
        envelope = json.loads(payload_bytes)
        signed_timestamp = envelope["timestamp"]
        if datetime.fromisoformat(signed_timestamp) != datetime.fromisoformat(timestamp_iso):
            return False
    except (KeyError, TypeError, ValueError, UnicodeDecodeError):
        return False
    return verify_timestamp_fresh(signed_timestamp, max_skew_s)


def is_duplicate_delivery(
    conn: psycopg.Connection,
    subscription_id: UUID,
    event_id: Any,
) -> bool:
    """True when this (subscription, event) pair already has a delivery row."""
    row = conn.execute(
        "select 1 from webhook_delivery where subscription_id = %s and event_id = %s limit 1",
        (subscription_id, event_id),
    ).fetchone()
    return row is not None
