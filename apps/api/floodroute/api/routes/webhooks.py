"""Webhook subscription endpoints: POST/GET/DELETE /v1/webhooks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from floodroute.api.auth import require_operator
from floodroute.api.deps import get_db
from floodroute.webhook.dispatcher import dispatch_event, resolve_webhook_target
from floodroute.webhook.models import (
    VALID_WEBHOOK_EVENTS,
    WebhookDeliveryOut,
    WebhookEvent,
    WebhookSubscriptionCreate,
    WebhookSubscriptionOut,
)
from floodroute.webhook.signing import generate_webhook_secret

router = APIRouter(
    prefix="/v1/webhooks", tags=["webhooks"], dependencies=[Depends(require_operator)]
)

# User-supplied secrets must carry real entropy for the HMAC to mean
# anything; the DB CHECK (>= 16) stays as the backstop, generated secrets are
# 64 hex chars.
MIN_USER_SECRET_LEN = 32


def _mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "****"
    return f"****{secret[-4:]}"


@router.post("", response_model=WebhookSubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_webhook_subscription(
    payload: WebhookSubscriptionCreate,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    tenant_id: Annotated[int | None, Query(description="Owning tenant id")] = None,
) -> WebhookSubscriptionOut:
    """Register a new webhook subscription for real-time flood events."""
    for ev in payload.events:
        if ev not in VALID_WEBHOOK_EVENTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid event type: {ev}. Allowed: {sorted(VALID_WEBHOOK_EVENTS)}",
            )

    if payload.secret is not None and len(payload.secret) < MIN_USER_SECRET_LEN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"User-supplied secret must be at least {MIN_USER_SECRET_LEN} characters; omit it to generate one",
        )

    secret = payload.secret if payload.secret else generate_webhook_secret()
    sub_id = uuid4()
    now = datetime.now(UTC)
    url_str = str(payload.target_url)
    try:
        resolve_webhook_target(url_str)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    sql = """
    insert into webhook_subscription (subscription_id, tenant_id, target_url, secret, events, is_active, created_at)
    values (%s, %s, %s, %s, %s, true, %s)
    """
    db.execute(sql, (sub_id, tenant_id, url_str, secret, payload.events, now))
    db.commit()

    return WebhookSubscriptionOut(
        subscription_id=sub_id,
        tenant_id=tenant_id,
        target_url=url_str,
        events=payload.events,
        is_active=True,
        created_at=now,
        secret_preview=_mask_secret(secret),
    )


@router.get("", response_model=list[WebhookSubscriptionOut])
def list_webhook_subscriptions(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    tenant_id: Annotated[int | None, Query(description="Filter by owning tenant id")] = None,
) -> list[WebhookSubscriptionOut]:
    """List active webhook subscriptions, scoped to a tenant when given.

    Full enforcement waits on caller-identity plumbing (no auth store exists
    yet); until then callers pass their tenant explicitly.
    """
    if tenant_id is None:
        sql = """
        select subscription_id, tenant_id, target_url, secret, events, is_active, created_at
        from webhook_subscription
        where is_active
        order by created_at desc
        """
        rows = db.execute(sql).fetchall()
    else:
        sql = """
        select subscription_id, tenant_id, target_url, secret, events, is_active, created_at
        from webhook_subscription
        where is_active and tenant_id = %s
        order by created_at desc
        """
        rows = db.execute(sql, (tenant_id,)).fetchall()
    return [
        WebhookSubscriptionOut(
            subscription_id=r[0],
            tenant_id=r[1],
            target_url=r[2],
            events=r[4],
            is_active=r[5],
            created_at=r[6],
            secret_preview=_mask_secret(r[3]),
        )
        for r in rows
    ]


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook_subscription(
    subscription_id: UUID,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    tenant_id: Annotated[int | None, Query(description="Must match the owning tenant id")] = None,
) -> None:
    """Deactivate a webhook subscription."""
    if tenant_id is None:
        sql = "update webhook_subscription set is_active = false where subscription_id = %s and is_active"
        cur = db.execute(sql, (subscription_id,))
    else:
        sql = "update webhook_subscription set is_active = false where subscription_id = %s and is_active and tenant_id = %s"
        cur = db.execute(sql, (subscription_id, tenant_id))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook subscription {subscription_id} not found or already deactivated",
        )


@router.post("/{subscription_id}/test", response_model=list[dict])
def test_webhook_subscription(
    subscription_id: UUID,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    tenant_id: Annotated[int | None, Query(description="Must match the owning tenant id")] = None,
) -> list[dict]:
    """Dispatch a test ping event to the named subscription only."""
    if tenant_id is None:
        row = db.execute(
            "select target_url, secret, events from webhook_subscription where subscription_id = %s and is_active",
            (subscription_id,),
        ).fetchone()
    else:
        row = db.execute(
            "select target_url, secret, events from webhook_subscription where subscription_id = %s and is_active and tenant_id = %s",
            (subscription_id, tenant_id),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook subscription {subscription_id} not found",
        )

    test_event = WebhookEvent(
        event_type=row[2][0] if row[2] else "segment.state_changed",
        timestamp=datetime.now(UTC),
        payload={
            "ping": True,
            "message": "FloodRoute test webhook ping",
            "subscription_id": str(subscription_id),
        },
    )
    return dispatch_event(db, test_event, only_subscription_id=subscription_id)


@router.get("/{subscription_id}/deliveries", response_model=list[WebhookDeliveryOut])
def list_subscription_deliveries(
    subscription_id: UUID,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    tenant_id: Annotated[int | None, Query(description="Must match the owning tenant id")] = None,
) -> list[WebhookDeliveryOut]:
    """List recent delivery logs for a specific webhook subscription."""
    if tenant_id is not None:
        owner = db.execute(
            "select 1 from webhook_subscription where subscription_id = %s and tenant_id = %s",
            (subscription_id, tenant_id),
        ).fetchone()
        if not owner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Webhook subscription {subscription_id} not found",
            )
    sql = """
    select delivery_id, subscription_id, event_id, event_type, status, status_code,
           attempt, delivered_at, error_message
    from webhook_delivery
    where subscription_id = %s
    order by delivered_at desc
    limit 50
    """
    rows = db.execute(sql, (subscription_id,)).fetchall()
    return [
        WebhookDeliveryOut(
            delivery_id=r[0],
            subscription_id=r[1],
            event_id=r[2],
            event_type=r[3],
            status=r[4],
            status_code=r[5],
            attempt=r[6],
            delivered_at=r[7],
            error_message=r[8],
        )
        for r in rows
    ]
