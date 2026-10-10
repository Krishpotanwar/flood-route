"""Safety case controls and emergency kill switch API routes (TRD 16)."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from floodroute.api.auth import (
    CoSignature,
    Operator,
    bind_actor,
    require_cosigner,
    require_operator,
)
from floodroute.api.deps import get_db
from floodroute.safety.kill_switch import (
    disengage_kill_switch,
    engage_kill_switch,
    get_active_kill_switch,
    list_kill_switches,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/safety", tags=["safety"], dependencies=[Depends(require_operator)])


class EngageKillSwitchRequest(BaseModel):
    scope: Literal["global", "tenant", "city"] = "global"
    reason: str = Field(min_length=5, description="Reason for engaging emergency kill switch")
    operator_id: str = Field(min_length=1, description="Operator callsign or ID")
    tenant_id: int | None = None
    city_id: int | None = None
    notes: str | None = None


class DisengageKillSwitchRequest(BaseModel):
    reason: str = Field(min_length=5, description="Reason for safety disengagement")
    operator_id: str = Field(min_length=1, description="Primary releasing operator")
    second_operator_id: str = Field(min_length=1, description="Second co-verifying operator")
    notes: str | None = None


@router.get("/kill-switch")
def get_kill_switch_status(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    tenant_id: int | None = Query(None),
    city_id: int | None = Query(None),
) -> dict[str, Any]:
    """Inspect active emergency kill switch status and advisory freeze condition."""
    active = get_active_kill_switch(db, tenant_id=tenant_id, city_id=city_id)
    return {
        "is_active": active is not None,
        "advisory_status": "suspended" if active else "active",
        "active_switch": active.to_dict() if active else None,
    }


@router.post("/kill-switch")
def engage_emergency_kill_switch(
    req: EngageKillSwitchRequest,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    operator: Operator,
) -> dict[str, Any]:
    """Engage emergency kill switch, freezing routing outputs to advisory off."""
    bind_actor(req.operator_id, operator)
    try:
        with db.transaction():
            record = engage_kill_switch(
                conn=db,
                scope=req.scope,
                reason=req.reason,
                operator_id=req.operator_id,
                tenant_id=req.tenant_id,
                city_id=req.city_id,
                notes=req.notes,
            )
        return {
            "status": "engaged",
            "message": "Emergency kill switch engaged. Advisories frozen to off.",
            "record": record.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/kill-switch/{switch_id}/disengage")
@router.delete("/kill-switch/{switch_id}")
def disengage_emergency_kill_switch(
    switch_id: str,
    req: DisengageKillSwitchRequest,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    operator: Operator,
    co_signature: CoSignature = None,
) -> dict[str, Any]:
    """Disengage emergency kill switch. Enforces two-operator co-verification."""
    bind_actor(req.operator_id, operator)
    require_cosigner(req.second_operator_id, operator, co_signature)
    try:
        with db.transaction():
            record = disengage_kill_switch(
                conn=db,
                switch_id=switch_id,
                reason=req.reason,
                operator_id=req.operator_id,
                second_operator_id=req.second_operator_id,
                notes=req.notes,
            )
        return {
            "status": "disengaged",
            "message": "Emergency kill switch disengaged. Normal advisory routing restored.",
            "record": record.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/kill-switch/history")
def get_kill_switch_history(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    active_only: bool = Query(False),
) -> dict[str, Any]:
    """List recent kill switch engagement history."""
    records = list_kill_switches(db, active_only=active_only, limit=limit)
    return {
        "count": len(records),
        "records": [r.to_dict() for r in records],
    }
