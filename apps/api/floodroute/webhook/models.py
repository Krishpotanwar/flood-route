"""Webhook Pydantic models for subscription management and delivery logs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

VALID_WEBHOOK_EVENTS = {
    "segment.state_changed",
    "route.invalidated",
    "override.created",
    "feed.degraded",
    "watch.material_change",
}


class WebhookSubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_url: HttpUrl
    secret: str | None = Field(
        default=None,
        min_length=16,
        description="Optional shared secret for HMAC-SHA256 signature verification. Generated if omitted.",
    )
    events: list[str] = Field(
        default_factory=lambda: [
            "segment.state_changed",
            "route.invalidated",
            "override.created",
            "feed.degraded",
        ],
        description="List of event types to subscribe to.",
    )


class WebhookSubscriptionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subscription_id: UUID
    tenant_id: int | None = None
    target_url: str
    events: list[str]
    is_active: bool
    created_at: datetime
    secret_preview: str


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    delivery_id: UUID
    subscription_id: UUID
    event_id: UUID
    event_type: str
    status: str
    status_code: int | None = None
    attempt: int = 1
    delivered_at: datetime | None = None
    error_message: str | None = None


class WebhookEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    timestamp: datetime
    payload: dict[str, Any]
