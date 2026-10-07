"""Route material-change watch subscriptions and evaluation engine.

Implements TRD 8.1, 10 and PRD FR-L1:
- Material change detection (new Impassable or risk increases by one band)
- Max 3 alerts per user/route per hour rate limit
- Multi-channel notification dispatch
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import psycopg
from pydantic import BaseModel, ConfigDict, Field

STATE_RANKS = {
    "unknown": 0,
    "clear": 0,
    "watch": 1,
    "risky": 2,
    "impassable": 3,
}

AlertChannel = Literal["fcm", "whatsapp", "sms", "webhook"]


class WatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_token: str | None = None
    alert_channel: AlertChannel = Field(
        default="fcm",
        description="Notification channel: fcm, whatsapp, sms, webhook",
    )
    contact_target: str = Field(
        description="Destination device token, phone number (+91...), or webhook target URL",
    )
    dwell_minutes: int = Field(
        default=60,
        ge=10,
        le=180,
        description="Duration in minutes to maintain active watch on this route",
    )


class WatchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    watch_id: UUID
    decision_id: UUID
    vclass: str
    segments_count: int
    alert_channel: str
    contact_target: str
    alerts_sent_count: int
    expires_at: datetime
    status: str = "active"


class WatchAlert(BaseModel):
    model_config = ConfigDict(extra="ignore")

    watch_id: UUID
    decision_id: UUID
    alert_channel: str
    contact_target: str
    timestamp: datetime
    reason: str
    changed_segments: list[dict[str, Any]]


def create_route_watch(
    db: psycopg.Connection,
    decision_id: UUID,
    req: WatchRequest,
    tenant_id: int | None = None,
) -> WatchResponse:
    """Subscribe to material change alerts for a planned route decision."""
    # Serialise creation per audited decision: one watch shares one alert counter.
    with db.transaction():
        sql = "select vclass, chosen from route_decision where decision_id = %s for update"
        row = db.execute(sql, (decision_id,)).fetchone()
        if not row:
            raise ValueError(f"Route decision {decision_id} not found")

        vclass, chosen_data = row[0], row[1]
        segment_ids: list[int] = []

        if isinstance(chosen_data, dict):
            raw_segs = chosen_data.get("segments", [])
            for s in raw_segs:
                if isinstance(s, dict) and "segment_id" in s:
                    segment_ids.append(int(s["segment_id"]))
                elif isinstance(s, int):
                    segment_ids.append(s)
        elif isinstance(chosen_data, list):
            for s in chosen_data:
                if isinstance(s, dict) and "segment_id" in s:
                    segment_ids.append(int(s["segment_id"]))

        if not segment_ids:
            raise ValueError(f"No routable segments found in route decision {decision_id}")

        # Deduplicate while preserving order
        unique_segments = list(dict.fromkeys(segment_ids))

        # Fetch initial baseline states
        cur = db.execute(
            """
            select sr.segment_id, sr.state
            from segment_risk sr
            join segment s on s.segment_id = sr.segment_id
            where sr.segment_id = ANY(%s) and sr.vclass = %s and sr.horizon_min = 0 and s.assessed
            """,
            (unique_segments, vclass),
        )
        baseline_states: dict[str, str] = {str(sid): state for sid, state in cur.fetchall()}
        for sid in unique_segments:
            if str(sid) not in baseline_states:
                # Missing row means unknown, never clear: an unassessed segment
                # must not read as free of water.
                baseline_states[str(sid)] = "unknown"

        # One active watch per decision: duplicates would each carry their own
        # 3/hr counter and multiply alerts to the same target.
        existing = db.execute(
            """
            select watch_id, decision_id, vclass, cardinality(segments),
                   alert_channel, contact_target, alerts_sent_count, expires_at, is_active
            from route_watch
            where decision_id = %s and is_active and expires_at > now()
            order by created_at desc
            limit 1
            """,
            (decision_id,),
        ).fetchone()
        if existing:
            return WatchResponse(
                watch_id=existing[0],
                decision_id=existing[1],
                vclass=existing[2],
                segments_count=existing[3],
                alert_channel=existing[4],
                contact_target=existing[5],
                alerts_sent_count=existing[6],
                expires_at=existing[7],
                status="active" if existing[8] else "inactive",
            )

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=req.dwell_minutes)
        watch_id = uuid4()

        insert_sql = """
        insert into route_watch (
            watch_id, decision_id, device_token, tenant_id, vclass,
            segments, baseline_states, alert_channel, contact_target,
            alerts_sent_count, expires_at, is_active, created_at
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, true, %s)
        """
        db.execute(
            insert_sql,
            (
                watch_id,
                decision_id,
                req.device_token,
                tenant_id,
                vclass,
                unique_segments,
                json.dumps(baseline_states),
                req.alert_channel,
                req.contact_target,
                expires_at,
                now,
            ),
        )

        return WatchResponse(
            watch_id=watch_id,
            decision_id=decision_id,
            vclass=vclass,
            segments_count=len(unique_segments),
            alert_channel=req.alert_channel,
            contact_target=req.contact_target,
            alerts_sent_count=0,
            expires_at=expires_at,
            status="active",
        )


def get_route_watch(db: psycopg.Connection, decision_id: UUID) -> WatchResponse | None:
    """Retrieve active watch subscription for a route decision."""
    sql = """
    select watch_id, decision_id, vclass, cardinality(segments),
           alert_channel, contact_target, alerts_sent_count, expires_at, is_active
    from route_watch
    where decision_id = %s and is_active and expires_at > now()
    order by created_at desc
    limit 1
    """
    row = db.execute(sql, (decision_id,)).fetchone()
    if not row:
        return None

    return WatchResponse(
        watch_id=row[0],
        decision_id=row[1],
        vclass=row[2],
        segments_count=row[3],
        alert_channel=row[4],
        contact_target=row[5],
        alerts_sent_count=row[6],
        expires_at=row[7],
        status="active" if row[8] else "inactive",
    )


def cancel_route_watch(db: psycopg.Connection, decision_id: UUID) -> bool:
    """Cancel and deactivate active watch subscriptions for a route decision."""
    sql = """
    update route_watch
    set is_active = false
    where decision_id = %s and is_active
    """
    cur = db.execute(sql, (decision_id,))
    db.commit()
    return cur.rowcount > 0


def evaluate_route_watches(db: psycopg.Connection) -> list[WatchAlert]:
    """Scan all active route watches and generate alerts on material risk changes.

    Enforces rate-limiting: maximum 3 alerts per hour per watch subscription.
    """
    now = datetime.now(UTC)
    sql = """
    select watch_id, decision_id, vclass, segments, baseline_states,
           alert_channel, contact_target, alerts_sent_count, last_alert_at
    from route_watch
    where is_active and expires_at > %s
    """
    watches = db.execute(sql, (now,)).fetchall()
    alerts: list[WatchAlert] = []

    for (
        watch_id,
        decision_id,
        vclass,
        segments,
        baseline_raw,
        channel,
        target,
        alert_count,
        last_alert,
    ) in watches:
        # Check 1-hour rate limit (max 3 alerts / hr)
        current_hour_count = alert_count
        if last_alert is not None:
            elapsed_sec = (now - last_alert).total_seconds()
            if elapsed_sec >= 3600:
                current_hour_count = 0
            elif current_hour_count >= 3:
                # Capped: skip further notifications this hour
                continue

        baseline: dict[str, str] = (
            baseline_raw if isinstance(baseline_raw, dict) else json.loads(baseline_raw)
        )

        # Query latest segment risk
        seg_sql = """
        select sr.segment_id, sr.state, sr.p_unusable, sr.depth_p50_cm, s.road_class
        from segment_risk sr
        join segment s on sr.segment_id = s.segment_id
        where sr.segment_id = ANY(%s) and sr.vclass = %s and sr.horizon_min = 0 and s.assessed
        """
        cur = db.execute(seg_sql, (segments, vclass))
        rows = cur.fetchall()

        changed_segments: list[dict[str, Any]] = []
        updated_baseline = {str(sid): "unknown" for sid in segments}

        for sid, state, p, d50, rclass in rows:
            sid_str = str(sid)
            old_state = baseline.get(sid_str, "unknown")
            old_rank = STATE_RANKS.get(old_state, 0)
            new_rank = STATE_RANKS.get(state, 0)

            # Material change condition:
            # 1. Road turned Impassable (and wasn't previously)
            # 2. Risk band increased (e.g. clear -> watch/risky/impassable)
            is_material = (state == "impassable" and old_state != "impassable") or (
                new_rank > old_rank
            )

            # The baseline always advances to the current state, even on a
            # recovery (fall). Otherwise a baseline stuck at impassable would
            # never alert on a later re-flood (a fall is logged, not alerted).
            updated_baseline[sid_str] = state
            if is_material:
                changed_segments.append(
                    {
                        "segment_id": sid,
                        "road_class": rclass,
                        "previous_state": old_state,
                        "current_state": state,
                        "p_unusable": float(p) if p is not None else None,
                        "depth_p50_cm": float(d50) if d50 is not None else None,
                    }
                )

        if changed_segments:
            reason = (
                f"Flood risk increased on {len(changed_segments)} segment(s) along your route. "
                "Detour navigation is recommended."
            )
            alert = WatchAlert(
                watch_id=watch_id,
                decision_id=decision_id,
                alert_channel=channel,
                contact_target=target,
                timestamp=now,
                reason=reason,
                changed_segments=changed_segments,
            )
            alerts.append(alert)

            # Update database state
            new_count = current_hour_count + 1
            up_sql = """
            update route_watch
            set alerts_sent_count = %s,
                last_alert_at = %s,
                baseline_states = %s
            where watch_id = %s
            """
            db.execute(up_sql, (new_count, now, json.dumps(updated_baseline), watch_id))
            db.commit()
        elif updated_baseline != baseline:
            # Recovery (or any fall) moves the baseline without alerting, so
            # a later rise counts as news again. Counters are untouched.
            db.execute(
                "update route_watch set baseline_states = %s where watch_id = %s",
                (json.dumps(updated_baseline), watch_id),
            )
            db.commit()

    return alerts
