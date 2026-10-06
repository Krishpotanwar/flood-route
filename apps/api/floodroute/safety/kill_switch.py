"""Safety case emergency kill switch and advisory freeze subsystem (TRD 16).

Implements the fail-safe emergency kill switch to immediately freeze routing
outputs to "advisory off" during telemetry faults, sensor spoofing, or model issues.
Enforces two-operator verification on safety disengagement.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import psycopg

logger = logging.getLogger(__name__)

KillSwitchScope = Literal["global", "tenant", "city"]


@dataclass
class KillSwitchRecord:
    """Represents an emergency freeze / kill switch engagement record."""

    switch_id: str
    scope: str
    tenant_id: int | None
    city_id: int | None
    is_active: bool
    reason: str
    operator_id: str
    second_operator_id: str | None
    engaged_at: str
    disengaged_at: str | None
    notes: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_active_kill_switch(
    conn: psycopg.Connection,
    tenant_id: int | None = None,
    city_id: int | None = None,
) -> KillSwitchRecord | None:
    """Query currently active kill switch applying to scope (global, tenant, or city)."""
    sql = """
    select switch_id, scope, tenant_id, city_id, is_active, reason,
           operator_id, second_operator_id, engaged_at, disengaged_at, notes
    from kill_switch
    where is_active = true
      and (
        scope = 'global'
        or (scope = 'tenant' and tenant_id = %s)
        or (scope = 'city' and city_id = %s)
      )
    order by (case when scope = 'global' then 1 when scope = 'city' then 2 else 3 end)
    limit 1
    """
    row = conn.execute(sql, (tenant_id, city_id)).fetchone()
    if not row:
        return None

    return KillSwitchRecord(
        switch_id=str(row[0]),
        scope=row[1],
        tenant_id=row[2],
        city_id=row[3],
        is_active=row[4],
        reason=row[5],
        operator_id=row[6],
        second_operator_id=row[7],
        engaged_at=row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8]),
        disengaged_at=row[9].isoformat() if row[9] and hasattr(row[9], "isoformat") else None,
        notes=row[10],
    )


def engage_kill_switch(
    conn: psycopg.Connection,
    scope: KillSwitchScope,
    reason: str,
    operator_id: str,
    tenant_id: int | None = None,
    city_id: int | None = None,
    notes: str | None = None,
) -> KillSwitchRecord:
    """Engage emergency kill switch, freezing routing outputs to advisory off."""
    cleaned_reason = reason.strip()
    if len(cleaned_reason) < 5:
        raise ValueError("Emergency kill switch engagement reason must be at least 5 characters")

    cleaned_op = operator_id.strip()
    if not cleaned_op:
        raise ValueError("Operator ID is required to engage kill switch")

    if scope == "tenant" and tenant_id is None:
        raise ValueError("Tenant ID is required for tenant-scoped kill switch")

    if scope == "city" and city_id is None:
        raise ValueError("City ID is required for city-scoped kill switch")

    switch_id = uuid.uuid4()
    now = datetime.now(UTC)

    sql = """
    insert into kill_switch (
      switch_id, tenant_id, scope, city_id, is_active,
      reason, operator_id, engaged_at, notes
    )
    values (%s, %s, %s, %s, true, %s, %s, %s, %s)
    returning switch_id, scope, tenant_id, city_id, is_active, reason,
              operator_id, second_operator_id, engaged_at, disengaged_at, notes
    """
    row = conn.execute(
        sql,
        (switch_id, tenant_id, scope, city_id, cleaned_reason, cleaned_op, now, notes),
    ).fetchone()

    # Append-only compliance audit logging (TRD 12 & 16)
    audit_sql = """
    insert into audit_log (actor, action, after, reason)
    values (%s, 'kill_switch_engaged', %s, %s)
    """
    audit_payload = json.dumps(
        {
            "switch_id": str(switch_id),
            "scope": scope,
            "tenant_id": tenant_id,
            "city_id": city_id,
        }
    )
    conn.execute(audit_sql, (cleaned_op, audit_payload, cleaned_reason))

    logger.warning(
        "EMERGENCY KILL SWITCH ENGAGED: id=%s scope=%s op=%s reason=%s",
        switch_id,
        scope,
        cleaned_op,
        cleaned_reason,
    )

    return KillSwitchRecord(
        switch_id=str(row[0]),
        scope=row[1],
        tenant_id=row[2],
        city_id=row[3],
        is_active=row[4],
        reason=row[5],
        operator_id=row[6],
        second_operator_id=row[7],
        engaged_at=row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8]),
        disengaged_at=None,
        notes=row[10],
    )


def disengage_kill_switch(
    conn: psycopg.Connection,
    switch_id: str,
    reason: str,
    operator_id: str,
    second_operator_id: str,
    notes: str | None = None,
) -> KillSwitchRecord:
    """Disengage emergency kill switch. Enforces two-operator safety co-verification."""
    cleaned_reason = reason.strip()
    if len(cleaned_reason) < 5:
        raise ValueError("Disengagement reason must be at least 5 characters")

    op1 = operator_id.strip()
    op2 = second_operator_id.strip()
    if not op1 or not op2:
        raise ValueError("Both operator and second operator IDs are required for disengagement")

    if op1.lower() == op2.lower():
        raise ValueError(
            "Two distinct operators required for safety kill switch disengagement (co-verification)"
        )

    now = datetime.now(UTC)
    sql = """
    update kill_switch
    set is_active = false,
        disengaged_at = %s,
        second_operator_id = %s,
        notes = coalesce(%s, notes)
    where switch_id = %s
      and is_active = true
    returning switch_id, scope, tenant_id, city_id, is_active, reason,
              operator_id, second_operator_id, engaged_at, disengaged_at, notes
    """
    row = conn.execute(sql, (now, op2, notes, switch_id)).fetchone()
    if not row:
        raise ValueError(f"Active kill switch not found for id {switch_id}")

    audit_sql = """
    insert into audit_log (actor, action, after, reason)
    values (%s, 'kill_switch_disengaged', %s, %s)
    """
    audit_payload = json.dumps(
        {
            "switch_id": switch_id,
            "operator_id": op1,
            "second_operator_id": op2,
        }
    )
    conn.execute(audit_sql, (f"{op1}+{op2}", audit_payload, cleaned_reason))

    logger.info(
        "Emergency kill switch disengaged: id=%s by ops %s and %s",
        switch_id,
        op1,
        op2,
    )

    return KillSwitchRecord(
        switch_id=str(row[0]),
        scope=row[1],
        tenant_id=row[2],
        city_id=row[3],
        is_active=row[4],
        reason=row[5],
        operator_id=row[6],
        second_operator_id=row[7],
        engaged_at=row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8]),
        disengaged_at=row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9]),
        notes=row[10],
    )


def list_kill_switches(
    conn: psycopg.Connection,
    active_only: bool = False,
    limit: int = 50,
) -> list[KillSwitchRecord]:
    """List recent kill switch engagement history."""
    clauses = []
    if active_only:
        clauses.append("is_active = true")

    where = f"where {' and '.join(clauses)}" if clauses else ""
    sql = f"""
    select switch_id, scope, tenant_id, city_id, is_active, reason,
           operator_id, second_operator_id, engaged_at, disengaged_at, notes
    from kill_switch
    {where}
    order by engaged_at desc
    limit %s
    """
    rows = conn.execute(sql, (limit,)).fetchall()
    return [
        KillSwitchRecord(
            switch_id=str(r[0]),
            scope=r[1],
            tenant_id=r[2],
            city_id=r[3],
            is_active=r[4],
            reason=r[5],
            operator_id=r[6],
            second_operator_id=r[7],
            engaged_at=r[8].isoformat() if hasattr(r[8], "isoformat") else str(r[8]),
            disengaged_at=r[9].isoformat() if r[9] and hasattr(r[9], "isoformat") else None,
            notes=r[10],
        )
        for r in rows
    ]
