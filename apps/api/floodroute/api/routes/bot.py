"""Bot and messaging routes: WhatsApp Business webhook and DLT SMS rendering."""

from __future__ import annotations

import os
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from floodroute.api.deps import get_db
from floodroute.bot.sms import DLT_TEMPLATES, render_sms
from floodroute.bot.whatsapp import (
    handle_incoming_message,
    parse_meta_payload,
    verify_meta_webhook,
)

router = APIRouter(prefix="/v1", tags=["bot"])

DEFAULT_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "floodroute_wa_token_2026")


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
def whatsapp_inbound_webhook(
    payload: dict[str, Any],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Meta Cloud API incoming message webhook handler."""
    parsed = parse_meta_payload(payload)
    if not parsed:
        return {"status": "ignored", "reason": "non_message_event"}

    outbound = handle_incoming_message(db, parsed)
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
