"""HMAC-SHA256 signing and verification for enterprise webhook delivery."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime


def generate_webhook_secret() -> str:
    """Generate a cryptographically secure 32-byte hexadecimal secret."""
    return secrets.token_hex(32)


def compute_signature(secret: str, payload_bytes: bytes) -> str:
    """Compute HMAC-SHA256 digest string for payload bytes."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def build_webhook_headers(
    secret: str,
    payload_bytes: bytes,
    event_id: str,
    timestamp_iso: str,
) -> dict[str, str]:
    """Build standard webhook headers including HMAC signature."""
    sig = compute_signature(secret, payload_bytes)
    return {
        "Content-Type": "application/json",
        "X-FloodRoute-Signature-256": f"sha256={sig}",
        "X-FloodRoute-Event-Id": event_id,
        "X-FloodRoute-Timestamp": timestamp_iso,
    }


def verify_signature(secret: str, payload_bytes: bytes, signature_header: str) -> bool:
    """Verify incoming signature against expected HMAC-SHA256 digest."""
    try:
        expected = compute_signature(secret, payload_bytes)
        candidate = signature_header.removeprefix("sha256=").strip()
        return hmac.compare_digest(expected, candidate)
    except (AttributeError, TypeError, ValueError):
        return False


def verify_timestamp_fresh(timestamp_iso: str, max_skew_s: float = 300.0) -> bool:
    """True when a signed delivery timestamp is within the replay window.

    Receivers must call this alongside `verify_signature`: the signature alone
    cannot stop a captured delivery from being replayed forever.
    """
    try:
        ts = datetime.fromisoformat(timestamp_iso)
    except (TypeError, ValueError):
        return False
    if ts.tzinfo is None:
        return False
    return abs((datetime.now(UTC) - ts).total_seconds()) <= max_skew_s
