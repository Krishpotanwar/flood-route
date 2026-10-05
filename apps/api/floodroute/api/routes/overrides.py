"""Human override control endpoint: POST /v1/overrides."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from floodroute.api.deps import get_db

router = APIRouter(prefix="/v1", tags=["overrides"])


class OverrideCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: int = 1
    segment_id: int
    action: Literal["close", "reopen", "force_watch"]
    reason: str = Field(min_length=3, max_length=500)
    operator_id: str = Field(min_length=1, max_length=128)
    second_operator_id: str | None = Field(default=None, max_length=128)
    starts_at: AwareDatetime | None = None
    expires_at: AwareDatetime


@router.post("/overrides", status_code=201)
def create_override(
    req: OverrideCreate,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Create a human operator override to close, reopen, or force-watch a road segment."""
    now = datetime.now(UTC)
    starts = req.starts_at or now

    if req.expires_at <= starts:
        raise HTTPException(status_code=400, detail="expires_at must be after starts_at")

    if req.second_operator_id is not None and req.second_operator_id == req.operator_id:
        raise HTTPException(
            status_code=400,
            detail="second_operator_id must be distinct from operator_id",
        )

    # Verify segment exists
    cur = db.execute("select 1 from segment where segment_id = %s", (req.segment_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail=f"segment {req.segment_id} not found")

    # Insert override
    cur = db.execute(
        """
        insert into override (
            tenant_id, segment_id, action, reason, operator_id,
            second_operator_id, starts_at, expires_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning override_id
        """,
        (
            req.tenant_id,
            req.segment_id,
            req.action,
            req.reason,
            req.operator_id,
            req.second_operator_id,
            starts,
            req.expires_at,
        ),
    )
    override_id = cur.fetchone()[0]

    # Append to audit log
    db.execute(
        """
        insert into audit_log (actor, action, segment_id, reason)
        values (%s, %s, %s, %s)
        """,
        (
            f"operator:{req.operator_id}",
            f"override_{req.action}",
            req.segment_id,
            req.reason,
        ),
    )

    return {
        "override_id": override_id,
        "segment_id": req.segment_id,
        "action": req.action,
        "operator_id": req.operator_id,
        "second_operator_id": req.second_operator_id,
        "starts_at": starts.isoformat(),
        "expires_at": req.expires_at.isoformat(),
        "reason": req.reason,
    }
