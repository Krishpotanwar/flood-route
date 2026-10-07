"""Bot and messaging routes: WhatsApp Business webhook and DLT SMS rendering."""

from __future__ import annotations

import json
import os
from threading import Lock
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from floodroute.api.deps import get_db
from floodroute.bot.sms import DLT_TEMPLATES, render_sms
from floodroute.bot.whatsapp import (
    handle_incoming_message,
    is_valid_inbound,
    parse_meta_payload,
    sender_allowed,
    verify_meta_webhook,
    verify_whatsapp_signature,
)

router = APIRouter(prefix="/v1", tags=["bot"])


def _require_verify_token() -> str:
    """Verify token comes from the environment only; there is no fallback.

    A hardcoded fallback would ship a publicly known token, so startup
    refuses to proceed until WHATSAPP_VERIFY_TOKEN is set and non-blank.
    """
    token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "WHATSAPP_VERIFY_TOKEN is not set: refusing to start the WhatsApp "
            "webhook without an explicit verify token"
        )
    return token


def _require_app_secret() -> str:
    """App Secret comes from the environment only; there is no fallback.

    The secret keys HMAC validation of webhook POSTs, so startup
    refuses to proceed until WHATSAPP_APP_SECRET is set and non-blank.
    """
    secret = os.environ.get("WHATSAPP_APP_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "WHATSAPP_APP_SECRET is not set: refusing to start the WhatsApp "
            "webhook without an explicit app secret"
        )
    return secret


DEFAULT_VERIFY_TOKEN = _require_verify_token()
DEFAULT_APP_SECRET = _require_app_secret()

# ponytail: preserve serial access to the in-memory sessions; per-sender
# locks/shared sessions are the upgrade if inbound bot throughput grows.
_INBOUND_LOCK = Lock()


def _handle_message(db: psycopg.Connection, parsed: dict[str, Any]) -> dict[str, Any]:
    with _INBOUND_LOCK:
        return handle_incoming_message(db, parsed)


class SMSRenderRequest(BaseModel):
    template_key: str
    variables: dict[str, str] = Field(default_factory=dict)
    auto_truncate: bool = True


@router.get("/whatsapp/webhook")
def whatsapp_verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    """Meta Cloud API webhook verification endpoint."""
    challenge = verify_meta_webhook(
        mode=hub_mode,
        token=hub_verify_token,
        challenge=hub_challenge,
        expected_token=DEFAULT_VERIFY_TOKEN,
    )
    if challenge:
        return PlainTextResponse(content=challenge)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_inbound_webhook(
    request: Request,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Meta Cloud API incoming message webhook handler.

    Meta signs every webhook POST with HMAC-SHA256 over the raw body keyed
    by the App Secret in X-Hub-Signature-256; see
    https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint/
    This handler rejects missing or invalid signatures with 403 before
    parsing. The GET verify-token handshake (constant-time, env-only),
    strict shape validation, and a per-sender rate limit remain as
    additional layers. Malformed events are ignored without touching the
    DB; over-limit senders get 429.
    """
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_whatsapp_signature(raw, signature, DEFAULT_APP_SECRET):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )
    try:
        decoded = raw.decode("utf-8")
        payload = json.loads(decoded)
        if not isinstance(payload, dict):
            return {"status": "ignored", "reason": "non_message_event"}
    except (ValueError, UnicodeDecodeError):
        return {"status": "ignored", "reason": "non_message_event"}
    parsed = parse_meta_payload(payload)
    if not is_valid_inbound(parsed):
        return {"status": "ignored", "reason": "non_message_event"}
    assert parsed is not None
    if not sender_allowed(parsed["sender"]):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this sender",
        )

    outbound = await run_in_threadpool(_handle_message, db, parsed)
    return {"status": "processed", "outbound": outbound}


@router.get("/sms/templates")
def list_sms_templates() -> list[dict[str, Any]]:
    """List pre-approved TRAI DLT SMS templates and character specifications."""
    return [
        {
            "template_key": key,
            "template_id": tmpl.template_id,
            "name": tmpl.name,
            "lang": tmpl.lang,
            "category": tmpl.category,
            "pattern": tmpl.pattern,
            "variable_names": list(tmpl.variable_names),
            "max_chars": tmpl.max_chars,
        }
        for key, tmpl in DLT_TEMPLATES.items()
    ]


@router.post("/sms/render")
def render_sms_endpoint(req: SMSRenderRequest) -> dict[str, Any]:
    """Render a DLT SMS template and validate character budget for single-part delivery."""
    try:
        return render_sms(req.template_key, req.variables, auto_truncate=req.auto_truncate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
