"""Human override controls and compliance audit log endpoints.

Implements PRD FR-C3 and FR-C4:
- Closure overrides with dual-operator requirement on arterial roads
- Real-time impact preview before committing closures
- Append-only audit trail queries and compliance CSV exports
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from floodroute.api.auth import (
    CoSignature,
    Operator,
    bind_actor,
    require_cosigner,
    require_operator,
)
from floodroute.api.deps import get_db

router = APIRouter(prefix="/v1", tags=["overrides"], dependencies=[Depends(require_operator)])

ARTERIAL_ROAD_CLASSES = {"motorway", "trunk", "primary"}


def _csv_cell(value: Any) -> str:
    """Prefix spreadsheet-formula triggers per OWASP CSV guidance."""
    text = "" if value is None else str(value)
    if text.lstrip()[:1] in ("=", "+", "-", "@") or text[:1] in ("\t", "\r", "\n"):
        return "'" + text
    return text


class OverrideCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # No default: every write names its tenant explicitly (there is no auth
    # context to fall back to, so a silent default would misattribute rows).
    tenant_id: int
    segment_id: int
    action: Literal["close", "reopen", "force_watch"]
    reason: str = Field(min_length=3, max_length=500)
    operator_id: str = Field(min_length=1, max_length=128)
    second_operator_id: str | None = Field(default=None, max_length=128)
    starts_at: AwareDatetime | None = None
    expires_at: AwareDatetime


class OverridePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: int
    action: Literal["close", "reopen", "force_watch"] = "close"


@router.post("/overrides", status_code=status.HTTP_201_CREATED)
def create_override(
    req: OverrideCreate,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    operator: Operator,
    co_signature: CoSignature = None,
) -> dict[str, Any]:
    """Create a human operator override to close, reopen, or force-watch a road segment."""
    now = datetime.now(UTC)
    starts = req.starts_at or now
    bind_actor(req.operator_id, operator)

    if req.expires_at <= starts:
        raise HTTPException(status_code=400, detail="expires_at must be after starts_at")

    if req.second_operator_id is not None and req.second_operator_id == req.operator_id:
        raise HTTPException(
            status_code=400,
            detail="second_operator_id must be distinct from operator_id",
        )

    # Verify segment exists and check arterial classification
    cur = db.execute("select road_class from segment where segment_id = %s", (req.segment_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"segment {req.segment_id} not found")

    road_class = row[0]
    if road_class in ARTERIAL_ROAD_CLASSES and not req.second_operator_id:
        raise HTTPException(
            status_code=400,
            detail=f"Arterial road '{road_class}' requires second operator confirmation",
        )

    if req.second_operator_id is not None:
        require_cosigner(req.second_operator_id, operator, co_signature)

    with db.transaction():
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

        # Append to audit log. The after payload keeps the replay context the
        # flat columns cannot: tenant, override id, expiry, and co-signer.
        db.execute(
            """
            insert into audit_log (actor, action, segment_id, reason, after)
            values (%s, %s, %s, %s, %s)
            """,
            (
                f"operator:{req.operator_id}",
                f"override_{req.action}",
                req.segment_id,
                req.reason,
                Jsonb(
                    {
                        "tenant_id": req.tenant_id,
                        "override_id": override_id,
                        "action": req.action,
                        "starts_at": starts.isoformat(),
                        "expires_at": req.expires_at.isoformat(),
                        "operator_id": req.operator_id,
                        "second_operator_id": req.second_operator_id,
                    }
                ),
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


@router.get("/overrides")
def list_active_overrides(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    tenant_id: Annotated[int | None, Query(description="Filter by owning tenant id")] = None,
) -> list[dict[str, Any]]:
    """List currently active human overrides, scoped to a tenant when given."""
    now = datetime.now(UTC)
    if tenant_id is None:
        sql = """
        select o.override_id, o.tenant_id, o.segment_id, s.road_class, o.action,
               o.reason, o.operator_id, o.second_operator_id, o.starts_at, o.expires_at
        from override o
        join segment s on o.segment_id = s.segment_id
        where o.expires_at > %s
        order by o.starts_at desc
        """
        rows = db.execute(sql, (now,)).fetchall()
    else:
        sql = """
        select o.override_id, o.tenant_id, o.segment_id, s.road_class, o.action,
               o.reason, o.operator_id, o.second_operator_id, o.starts_at, o.expires_at
        from override o
        join segment s on o.segment_id = s.segment_id
        where o.expires_at > %s and o.tenant_id = %s
        order by o.starts_at desc
        """
        rows = db.execute(sql, (now, tenant_id)).fetchall()
    return [
        {
            "override_id": r[0],
            "tenant_id": r[1],
            "segment_id": r[2],
            "road_class": r[3],
            "action": r[4],
            "reason": r[5],
            "operator_id": r[6],
            "second_operator_id": r[7],
            "starts_at": r[8].isoformat() if r[8] else None,
            "expires_at": r[9].isoformat() if r[9] else None,
        }
        for r in rows
    ]


@router.delete("/overrides/{override_id}")
def revert_override(
    override_id: int,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    operator: Operator,
    reason: str = Query(
        "Operator manual cancellation",
        description="Reason for reverting override",
        min_length=3,
        max_length=500,
    ),
    operator_id: str | None = Query(
        None,
        description="Identifier of reverting operator",
        min_length=1,
        max_length=128,
    ),
    second_operator_id: str | None = Query(None, min_length=1, max_length=128),
    co_signature: CoSignature = None,
) -> dict[str, Any]:
    """Revert an active override early and record the event in the audit log."""
    now = datetime.now(UTC)
    if operator_id is not None:
        bind_actor(operator_id, operator)
    operator_id = operator
    with db.transaction():
        cur = db.execute(
            """update override o set expires_at = clock_timestamp()
               from segment s
               where o.override_id = %s and o.expires_at > clock_timestamp()
                 and s.segment_id = o.segment_id
               returning o.segment_id, o.action, o.tenant_id, o.expires_at, s.road_class""",
            (override_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Active override {override_id} not found")

        seg_id, prev_action, tenant_id, now, road_class = row
        if road_class in ARTERIAL_ROAD_CLASSES or second_operator_id is not None:
            require_cosigner(second_operator_id, operator, co_signature)

        # Append cancellation to audit log
        db.execute(
            """
            insert into audit_log (actor, action, segment_id, reason, after)
            values (%s, %s, %s, %s, %s)
            """,
            (
                f"operator:{operator_id}",
                f"override_reverted_{prev_action}",
                seg_id,
                reason,
                Jsonb(
                    {
                        "tenant_id": tenant_id,
                        "override_id": override_id,
                        "prev_action": prev_action,
                        "reverted_at": now.isoformat(),
                        "operator_id": operator_id,
                        "second_operator_id": second_operator_id,
                    }
                ),
            ),
        )

    return {
        "override_id": override_id,
        "segment_id": seg_id,
        "reverted": True,
        "reverted_at": now.isoformat(),
        "reason": reason,
    }


@router.post("/overrides/preview")
def preview_override_impact(
    req: OverridePreviewRequest,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Calculate the operational impact of closing or overriding a segment before submission."""
    # 1. Inspect segment road class
    cur = db.execute("select road_class from segment where segment_id = %s", (req.segment_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"segment {req.segment_id} not found")

    road_class = row[0]
    is_arterial = road_class in ARTERIAL_ROAD_CLASSES
    requires_second_operator = is_arterial

    # 2. Count active route watches affected
    now = datetime.now(UTC)
    watch_cur = db.execute(
        """
        select count(*) from route_watch
        where %s = ANY(segments) and is_active and expires_at > %s
        """,
        (req.segment_id, now),
    )
    active_watches_affected = watch_cur.fetchone()[0]

    # 3. Determine impact tier
    if is_arterial or active_watches_affected >= 5:
        impact_level = "high"
    elif active_watches_affected > 0 or road_class == "secondary":
        impact_level = "moderate"
    else:
        impact_level = "low"

    return {
        "segment_id": req.segment_id,
        "road_class": road_class,
        "is_arterial": is_arterial,
        "requires_second_operator": requires_second_operator,
        "active_watches_affected": active_watches_affected,
        "impact_level": impact_level,
    }


@router.get("/audit")
def query_audit_log(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    actor: str | None = Query(None, description="Filter by actor pattern"),
    action: str | None = Query(None, description="Filter by action pattern"),
    limit: int = Query(50, ge=1, le=500),
    format: str = Query("json", description="Output format: json or csv"),
) -> Any:
    """Query append-only audit trail records for compliance and post-incident verification."""
    conditions = []
    params: list[Any] = []

    if actor:
        conditions.append("actor ilike %s")
        params.append(f"%{actor}%")
    if action:
        conditions.append("action ilike %s")
        params.append(f"%{action}%")

    where_clause = f"where {' and '.join(conditions)}" if conditions else ""
    sql = f"""
    select audit_id, ts, actor, action, segment_id, reason, after
    from audit_log
    {where_clause}
    order by ts desc
    limit %s
    """
    params.append(limit)
    rows = db.execute(sql, tuple(params)).fetchall()

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["audit_id", "timestamp", "actor", "action", "segment_id", "reason"])
        for r in rows:
            ts_str = r[1].isoformat() if r[1] else ""
            writer.writerow(
                [
                    r[0],
                    _csv_cell(ts_str),
                    _csv_cell(r[2]),
                    _csv_cell(r[3]),
                    r[4] or "",
                    _csv_cell(r[5] or ""),
                ]
            )
        return Response(content=output.getvalue(), media_type="text/csv")

    return [
        {
            "audit_id": r[0],
            "timestamp": r[1].isoformat() if r[1] else None,
            "actor": r[2],
            "action": r[3],
            "segment_id": r[4],
            "reason": r[5],
            "after": r[6],
        }
        for r in rows
    ]
