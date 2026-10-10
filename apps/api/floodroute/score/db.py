"""Database runner for scoring: load DB state, run score_run, and persist outputs.

Pure business logic remains in run.py; this module handles the PostgreSQL I/O:
- Loads zones, rain observations, rain forecasts, and active official alerts.
- Loads assessed segments, structures, active evidence, and overrides.
- Reads previous segment_risk state.
- Executes pure score_run.
- Persists shadow_run, upserts segment_risk, appends segment_risk_history, and records audit_log changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime

import psycopg
from psycopg.types.json import Jsonb

from floodroute.score.config import Config, load_config
from floodroute.score.records import (
    Evidence,
    Override,
    RainFcst,
    RainObs,
    RiskRow,
    RunInput,
    RunResult,
    SegmentInput,
    ZoneInput,
)
from floodroute.score.run import score_run

SUPPORTED_VCLASSES: frozenset[str] = frozenset({"two_wheeler", "car", "ambulance", "heavy"})
# The segment_risk table only stores these horizons (0001 CHECK). A config with
# anything else would die mid-run on the CHECK, so the bridge refuses up front.
SUPPORTED_HORIZONS: frozenset[int] = frozenset({0, 30, 60, 120})

logger = logging.getLogger(__name__)


def config_digest(cfg: Config) -> str:
    """Stable sha256 hash of the effective configuration (every threshold).

    The hash covers the whole config, so any threshold edit moves the
    shadow_run.config_hash and two runs with different closures never share it."""
    raw = json.dumps(asdict(cfg), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_run_input(
    conn: psycopg.Connection, now: datetime, cfg: Config
) -> tuple[RunInput, dict[tuple[int, str, int], RiskRow]]:
    """Load all inputs required for a scoring run from PostgreSQL."""
    # 1. Load zones
    with conn.cursor() as cur:
        cur.execute(
            """
            select z.zone_id,
                   exists(
                       select 1 from official_alert a
                       where a.onset <= %s
                         and (a.expires is null or a.expires > %s)
                         and a.severity in ('Moderate', 'Severe', 'Extreme')
                         and (a.area is null or ST_Intersects(a.area, z.geom))
                   ) as alert_active
            from zone z
            order by z.zone_id
            """,
            (now, now),
        )
        zone_rows = cur.fetchall()

        # Load rain observations for zones (past 24h)
        cur.execute(
            """
            select source, zone_id, ts, mm_60m, mm_24h
            from rain_obs
            where ts <= %s and ts >= %s - interval '24 hours'
            order by ts desc
            """,
            (now, now),
        )
        obs_by_zone: dict[int, list[RainObs]] = {}
        for src, zid, ts, mm60, mm24 in cur.fetchall():
            if mm60 is None:
                continue  # NULL means missing data, never confirmed dry
            obs_by_zone.setdefault(zid, []).append(
                RainObs(source=src, ts=ts, mm_60m=mm60, mm_24h=mm24)
            )

        # Load rain forecasts for zones (valid from now to next 6 hours)
        cur.execute(
            """
            select source, zone_id, valid, mm_per_h, ensemble_spread
            from rain_fcst
            where valid >= %s - interval '1 hour' and valid <= %s + interval '6 hours'
            order by valid asc
            """,
            (now, now),
        )
        fcst_by_zone: dict[int, list[RainFcst]] = {}
        for src, zid, valid, mm_h, spread in cur.fetchall():
            if mm_h is None:
                continue  # NULL means missing data, never confirmed dry
            fcst_by_zone.setdefault(zid, []).append(
                RainFcst(
                    source=src,
                    valid=valid,
                    mm_per_h=mm_h,
                    spread=spread,
                )
            )

    zones = tuple(
        ZoneInput(
            zone_id=zid,
            alert_active=bool(alert_act),
            obs=tuple(obs_by_zone.get(zid, ())),
            fcst=tuple(fcst_by_zone.get(zid, ())),
        )
        for zid, alert_act in zone_rows
    )

    # 2. Load segments, evidence, and overrides
    with conn.cursor() as cur:
        cur.execute(
            """
            select s.segment_id, s.assessed,
                    coalesce(ss.structure, 'none') as structure,
                    ss.base_logit,
                    ss.zone_id
            from segment s
            left join segment_static ss on s.segment_id = ss.segment_id
            order by s.segment_id
            """
        )
        seg_rows = cur.fetchall()
        for sid, assessed, _struct, _base, zid in seg_rows:
            if assessed and zid is None:
                raise ValueError(
                    f"segment {sid}: assessed but has no segment_static row, "
                    "so its rain zone is unknown (refusing to score it as zone 1)"
                )

        # Load active evidence
        cur.execute(
            """
            select segment_id, kind, ts, expires, source_id, trust,
                   depth_cm, speed_ratio, verified, contributors
            from evidence
            where ts <= %s and expires > %s
            order by ts desc
            """,
            (now, now),
        )
        evidence_by_seg: dict[int, list[Evidence]] = {}
        for sid, kind, ts, exp, src_id, trust, depth, spd, ver, contrib in cur.fetchall():
            evidence_by_seg.setdefault(sid, []).append(
                Evidence(
                    kind=kind,
                    ts=ts,
                    expires=exp,
                    source_id=src_id,
                    trust=trust if trust is not None else 1.0,
                    depth_cm=depth,
                    speed_ratio=spd,
                    verified=bool(ver),
                    contributors=contrib,
                )
            )

        # Load overrides live at any horizon of this run: active_actions tests
        # each row against the valid time now + h, so a close that starts in
        # 45 minutes must be loaded even though it has not started yet.
        cur.execute(
            """
            select segment_id, action, starts_at, expires_at
            from override
            where expires_at > %s
            order by starts_at desc
            """,
            (now,),
        )
        overrides_by_seg: dict[int, list[Override]] = {}
        for sid, action, starts, expires in cur.fetchall():
            overrides_by_seg.setdefault(sid, []).append(
                Override(action=action, starts_at=starts, expires_at=expires)
            )

    segments = tuple(
        SegmentInput(
            segment_id=sid,
            # Unassessed rows never look up rain (score_segment ignores their
            # zone), so a missing static row only needs a placeholder here.
            # Assessed rows with no zone raised above and never reach this.
            zone_id=zid if zid is not None else -1,
            assessed=bool(assessed),
            structure=struct,
            base_logit=base_l,
            # No DEM/drain coverage source exists yet: default to uncovered.
            covered=False,
            evidence=tuple(evidence_by_seg.get(sid, ())),
            overrides=tuple(overrides_by_seg.get(sid, ())),
        )
        for sid, assessed, struct, base_l, zid in seg_rows
    )

    # 3. Load previous risk state
    prev: dict[tuple[int, str, int], RiskRow] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            select segment_id, vclass, horizon_min, state, p_unusable,
                   confidence, evidence_age_s, model_version, updated_at,
                   closed_since, reopen_ok_since
            from segment_risk
            """
        )
        for (
            sid,
            vclass,
            h,
            state,
            p,
            conf,
            age_s,
            mv,
            up_at,
            closed_since,
            reopen_since,
        ) in cur.fetchall():
            prev[(sid, vclass, h)] = RiskRow(
                segment_id=sid,
                vclass=vclass,
                horizon_min=h,
                assessed=True,
                p=p,
                state=state,
                confidence=conf,
                evidence_age_s=age_s,
                model_version=mv,
                updated_at=up_at,
                closed_since=closed_since,
                reopen_ok_since=reopen_since,
            )

    return RunInput(now=now, zones=zones, segments=segments), prev


def persist_run_result(
    conn: psycopg.Connection,
    result: RunResult,
    cfg: Config,
    now: datetime | None = None,
    notes: str | None = None,
) -> int:
    """Persist a scoring run result transactionally into PostgreSQL."""
    chash = config_digest(cfg)
    run_time = now or (result.rows[0].updated_at if result.rows else datetime.now(UTC))
    with conn.transaction(), conn.cursor() as cur:
        # 1. Record shadow run
        cur.execute(
            """
            insert into shadow_run (started_at, model_version, config_hash, notes)
            values (%s, %s, %s, %s)
            returning run_id
            """,
            (run_time, cfg.model_version, chash, notes),
        )
        run_id = cur.fetchone()[0]

        # 2. Upsert segment_risk and append segment_risk_history
        upsert_risk_sql = """
            insert into segment_risk (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at,
                closed_since, reopen_ok_since
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (segment_id, vclass, horizon_min) do update
            set p_unusable = excluded.p_unusable,
                depth_p50_cm = excluded.depth_p50_cm,
                depth_p90_cm = excluded.depth_p90_cm,
                state = excluded.state,
                confidence = excluded.confidence,
                evidence_age_s = excluded.evidence_age_s,
                model_version = excluded.model_version,
                updated_at = excluded.updated_at,
                closed_since = excluded.closed_since,
                reopen_ok_since = excluded.reopen_ok_since
            """

        insert_history_sql = """
            insert into segment_risk_history (
                segment_id, vclass, horizon_min, p_unusable,
                depth_p50_cm, depth_p90_cm, state, confidence,
                evidence_age_s, model_version, updated_at,
                closed_since, reopen_ok_since, run_id
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

        skipped_vclasses: set[str] = set()
        for r in result.rows:
            if not r.assessed or r.p is None or r.state is None:
                continue  # Unassessed segments do not write risk state
            if r.vclass not in SUPPORTED_VCLASSES:
                skipped_vclasses.add(r.vclass)
                continue  # Research/experimental classes outside database schema are omitted
            # No depth model exists at v0: persisting invented constants made
            # depth MAE measure the placeholder, not model skill. NULL means
            # "no depth prediction"; the backtest skips NULLs.
            args = (
                r.segment_id,
                r.vclass,
                r.horizon_min,
                r.p,
                None,
                None,
                r.state,
                r.confidence or "low",
                r.evidence_age_s,  # None (no evidence) stays NULL, never 0
                r.model_version,
                r.updated_at,
                r.closed_since,
                r.reopen_ok_since,
            )
            cur.execute(upsert_risk_sql, args)
            cur.execute(insert_history_sql, (*args, run_id))
        if skipped_vclasses:
            logger.warning(
                "persist_run_result: omitted %d rows for vehicle classes outside "
                "the database schema: %s (no routing fallback persists them)",
                sum(
                    1
                    for r in result.rows
                    if r.vclass in skipped_vclasses and r.assessed
                ),
                sorted(skipped_vclasses),
            )

        # 3. Append state changes to audit_log
        audit_sql = """
            insert into audit_log (ts, actor, action, segment_id, before, after, reason)
            values (%s, %s, %s, %s, %s, %s, %s)
            """
        for c in result.changes:
            if c.vclass not in SUPPORTED_VCLASSES:
                continue
            cur.execute(
                audit_sql,
                (
                    c.ts,
                    f"system:scoring:{cfg.model_version}",
                    "state_change",
                    c.segment_id,
                    Jsonb(c.before) if c.before else None,
                    Jsonb(c.after),
                    c.reason,
                ),
            )

    return run_id


def execute_score_run(
    conn: psycopg.Connection,
    cfg: Config | None = None,
    now: datetime | None = None,
    notes: str | None = None,
) -> tuple[int, RunResult]:
    """Execute an end-to-end scoring run: load DB, score, persist."""
    effective_cfg = cfg or load_config()
    bad_horizons = [h for h in effective_cfg.horizons_min if h not in SUPPORTED_HORIZONS]
    if bad_horizons:
        raise ValueError(
            f"config horizons_min {bad_horizons} cannot be stored: "
            "segment_risk only accepts horizons (0, 30, 60, 120)"
        )
    current_time = now or datetime.now(UTC)
    inputs, prev = load_run_input(conn, current_time, effective_cfg)
    result = score_run(inputs, prev, effective_cfg)
    run_id = persist_run_result(conn, result, effective_cfg, now=current_time, notes=notes)
    return run_id, result
