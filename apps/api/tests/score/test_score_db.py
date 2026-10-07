"""Tests for floodroute.score.db (PostgreSQL bridge for the scoring engine).

Verifies loading input from DB, executing scoring run, and persisting
shadow_run, segment_risk, segment_risk_history, and audit_log.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from floodroute.score import score_run
from floodroute.score.config import DEFAULT_PATH, load_config, parse_config
from floodroute.score.db import (
    SUPPORTED_VCLASSES,
    config_digest,
    execute_score_run,
    load_run_input,
)

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
ALERT_GEOM = (
    "SRID=4326;MULTIPOLYGON(((77.55 12.95, 77.65 12.95, 77.65 13.05, 77.55 13.05, 77.55 12.95)))"
)
SEG_LINE = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"


def test_config_digest_stability_and_uniqueness():
    cfg1 = load_config()
    cfg2 = load_config()
    d1 = config_digest(cfg1)
    d2 = config_digest(cfg2)
    assert d1 == d2
    assert len(d1) == 16
    assert isinstance(d1, str)


def test_config_digest_moves_with_any_threshold():
    data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    edited = copy.deepcopy(data)
    edited["states"]["watch_min"] = 0.11
    assert config_digest(load_config()) != config_digest(parse_config(json.dumps(edited)))
    edited = copy.deepcopy(data)
    edited["confidence"]["spread_penalty_mm_h"] = 99.0
    assert config_digest(load_config()) != config_digest(parse_config(json.dumps(edited)))


def test_null_rain_rows_are_skipped_never_dry(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 12, 0, tzinfo=UTC)
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        "insert into rain_obs (source, zone_id, ts, mm_60m, mm_24h) values "
        "('gauge', 1, %s, NULL, NULL), "
        "('gauge', 1, %s, 12.0, 30.0)",
        (now - timedelta(minutes=5), now - timedelta(minutes=10)),
    )
    app_db.execute(
        "insert into rain_fcst (source, zone_id, issued, valid, mm_per_h, ensemble_spread) "
        "values ('metno', 1, %s, %s, NULL, NULL)",
        (now - timedelta(minutes=30), now + timedelta(hours=1)),
    )
    run_input, _ = load_run_input(app_db, now, cfg)
    zone = run_input.zones[0]
    assert [o.mm_60m for o in zone.obs] == [12.0]
    assert zone.fcst == ()


def test_verified_evidence_fields_load_from_db_and_fire_rules(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 12, 0, tzinfo=UTC)
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (1001, 555001, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into segment_static (segment_id, structure, base_logit, zone_id)
        values (1001, 'underpass', -5.0, 1)
        """
    )
    app_db.execute(
        """
        insert into evidence (segment_id, kind, ts, expires, source_id, trust,
                              depth_cm, verified, contributors)
        values (1001, 'sensor', %s, %s, 'sens-1', 0.9, 60.0, true, 9),
               (1001, 'report', %s, %s, 'u1', 0.5, 5.0, false, NULL)
        """,
        (
            now - timedelta(minutes=5),
            now + timedelta(minutes=30),
            now - timedelta(minutes=5),
            now + timedelta(minutes=30),
        ),
    )
    run_input, _ = load_run_input(app_db, now, cfg)
    by_source = {e.source_id: e for e in run_input.segments[0].evidence}
    assert (by_source["sens-1"].verified, by_source["sens-1"].contributors) == (True, 9)
    assert (by_source["u1"].verified, by_source["u1"].contributors) == (False, None)
    result = score_run(run_input, {}, cfg)
    car_h0 = next(r for r in result.rows if (r.vclass, r.horizon_min) == ("car", 0))
    assert "depth_unusable" in car_h0.evidence_rules  # 60 cm verified over car 30 cm


def test_future_starting_override_covers_later_horizons(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 12, 0, tzinfo=UTC)
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (1001, 555001, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into segment_static (segment_id, structure, base_logit, zone_id)
        values (1001, 'none', -5.0, 1)
        """
    )
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Test Admin', 'admin')")
    app_db.execute(
        """
        insert into override (tenant_id, segment_id, action, reason, operator_id, starts_at, expires_at)
        values (1, 1001, 'close', 'planned flooding closure', 'op-42', %s, %s)
        """,
        (now + timedelta(minutes=45), now + timedelta(hours=3)),
    )
    run_input, _ = load_run_input(app_db, now, cfg)
    assert len(run_input.segments[0].overrides) == 1
    result = score_run(run_input, {}, cfg)
    states = {
        r.horizon_min: r.state for r in result.rows if r.vclass == "car"
    }
    assert states == {0: "unknown", 30: "unknown", 60: "impassable", 120: "impassable"}


def test_loaded_segments_default_to_uncovered(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 12, 0, tzinfo=UTC)
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (1001, 555001, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into segment_static (segment_id, structure, base_logit, zone_id)
        values (1001, 'underpass', -1.5, 1)
        """
    )
    run_input, _ = load_run_input(app_db, now, cfg)
    assert run_input.segments[0].covered is False


def test_assessed_segment_without_static_row_fails_loud(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 12, 0, tzinfo=UTC)
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (9001, 555001, %s, 'primary', 1, false)
        """,
        (SEG_LINE,),
    )
    run_input, _ = load_run_input(app_db, now, cfg)
    assert run_input.segments[0].zone_id == -1  # unassessed rows never look up rain
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (1001, 555002, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )
    with pytest.raises(ValueError, match="no segment_static row"):
        load_run_input(app_db, now, cfg)


def test_execute_score_run_rejects_unstorable_horizons(app_db):
    data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    data["horizons_min"] = [0, 15]
    cfg = parse_config(json.dumps(data))
    with pytest.raises(ValueError, match="cannot be stored"):
        execute_score_run(app_db, cfg=cfg, now=datetime(2027, 5, 18, 14, 0, tzinfo=UTC))


def test_unknown_rows_persist_null_depth_and_null_age(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 14, 0, tzinfo=UTC)
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (2001, 666001, %s, 'secondary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into segment_static (segment_id, structure, base_logit, zone_id)
        values (2001, 'none', -5.0, 1)
        """
    )
    run_id, _ = execute_score_run(app_db, cfg=cfg, now=now, notes="null prose check")
    rows = app_db.execute(
        "select depth_p50_cm, depth_p90_cm, evidence_age_s, state from segment_risk"
        " where segment_id = 2001"
    ).fetchall()
    assert len(rows) == len(SUPPORTED_VCLASSES) * len(cfg.horizons_min)
    assert all(r[:3] == (None, None, None) for r in rows)
    assert {r[3] for r in rows} == {"unknown"}
    hist = app_db.execute(
        "select count(*) from segment_risk_history where run_id = %s"
        " and depth_p50_cm is null and evidence_age_s is null",
        (run_id,),
    ).fetchone()[0]
    assert hist == len(rows)


def test_load_run_input_empty_db(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 12, 0, tzinfo=UTC)
    run_input, prev = load_run_input(app_db, now, cfg)
    assert run_input.now == now
    assert len(run_input.zones) == 0
    assert len(run_input.segments) == 0
    assert len(prev) == 0


def test_load_run_input_with_populated_tables(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 12, 0, tzinfo=UTC)

    # 1. Insert zone
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )

    # 2. Insert official alert (active, intersects zone)
    app_db.execute(
        """
        insert into official_alert (cap_id, sender, event, severity, certainty, onset, expires, area, raw)
        values (%s, 'SNDMC', 'Flood', 'Severe', 'Observed', %s, %s, %s, '{}')
        """,
        ("ALT-001", now - timedelta(hours=1), now + timedelta(hours=3), ALERT_GEOM),
    )

    # 3. Insert rain observations (one recent, one expired > 24h ago)
    app_db.execute(
        """
        insert into rain_obs (source, zone_id, ts, mm_60m, mm_24h)
        values
            ('gauge', 1, %s, 15.0, 45.0),
            ('gauge', 1, %s, 5.0, 10.0)
        """,
        (now - timedelta(minutes=10), now - timedelta(hours=26)),
    )

    # 4. Insert rain forecast (one valid, one far future)
    app_db.execute(
        """
        insert into rain_fcst (source, zone_id, issued, valid, mm_per_h, ensemble_spread)
        values
            ('metno', 1, %s, %s, 22.0, 3.5),
            ('metno', 1, %s, %s, 30.0, 4.0)
        """,
        (
            now - timedelta(minutes=30),
            now + timedelta(hours=1),
            now - timedelta(minutes=30),
            now + timedelta(hours=12),
        ),
    )

    # 5. Insert segment and static attributes
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (1001, 555001, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into segment_static (segment_id, structure, base_logit, zone_id)
        values (1001, 'underpass', -1.5, 1)
        """
    )

    # 6. Insert evidence (one active, one expired)
    app_db.execute(
        """
        insert into evidence (segment_id, kind, ts, expires, source_id, trust, depth_cm, speed_ratio)
        values
            (1001, 'sensor', %s, %s, 'sens-1', 0.9, 18.0, 0.4),
            (1001, 'probe', %s, %s, 'probe-1', 0.5, 5.0, 0.9)
        """,
        (
            now - timedelta(minutes=15),
            now + timedelta(minutes=45),
            now - timedelta(hours=2),
            now - timedelta(minutes=10),
        ),
    )

    # 7. Insert override
    app_db.execute("insert into tenant (tenant_id, name, kind) values (1, 'Test Admin', 'admin')")
    app_db.execute(
        """
        insert into override (tenant_id, segment_id, action, reason, operator_id, starts_at, expires_at)
        values (1, 1001, 'close', 'Flooded water logging', 'op-42', %s, %s)
        """,
        (now - timedelta(minutes=5), now + timedelta(hours=2)),
    )

    # 8. Insert prior segment risk
    app_db.execute(
        """
        insert into segment_risk (
            segment_id, vclass, horizon_min, p_unusable,
            depth_p50_cm, depth_p90_cm, state, confidence,
            evidence_age_s, model_version, updated_at
        )
        values (1001, 'car', 0, 0.1, 0.0, 0.0, 'clear', 'low', 60, %s, %s)
        """,
        (cfg.model_version, now - timedelta(minutes=5)),
    )

    # Load and verify
    run_input, prev = load_run_input(app_db, now, cfg)

    assert (1001, "car", 0) in prev
    assert prev[(1001, "car", 0)].state == "clear"

    assert len(run_input.zones) == 1
    zone = run_input.zones[0]
    assert zone.zone_id == 1
    assert zone.alert_active is True
    assert len(zone.obs) == 1
    assert zone.obs[0].mm_60m == 15.0
    assert len(zone.fcst) == 1
    assert zone.fcst[0].mm_per_h == 22.0

    assert len(run_input.segments) == 1
    seg = run_input.segments[0]
    assert seg.segment_id == 1001
    assert seg.assessed is True
    assert seg.structure == "underpass"
    assert len(seg.evidence) == 1
    assert seg.evidence[0].source_id == "sens-1"
    assert len(seg.overrides) == 1
    assert seg.overrides[0].action == "close"


def test_execute_score_run_end_to_end(app_db):
    cfg = load_config()
    now = datetime(2027, 5, 18, 14, 0, tzinfo=UTC)

    # Setup zone and segment
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (2001, 666001, %s, 'secondary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into segment_static (segment_id, structure, base_logit, zone_id)
        values (2001, 'underpass', -2.0, 1)
        """
    )
    # Heavy rain observation
    app_db.execute(
        """
        insert into rain_obs (source, zone_id, ts, mm_60m, mm_24h)
        values ('gauge', 1, %s, 65.0, 110.0)
        """,
        (now - timedelta(minutes=5),),
    )

    # Run scoring
    run_id, result = execute_score_run(app_db, cfg=cfg, now=now, notes="initial scoring cycle")
    assert run_id > 0
    assert len(result.rows) > 0

    # 1. Verify shadow_run was created
    cur = app_db.execute(
        "select model_version, config_hash, notes from shadow_run where run_id = %s", (run_id,)
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == cfg.model_version
    assert row[2] == "initial scoring cycle"

    # 2. Verify segment_risk has rows
    cur = app_db.execute(
        "select segment_id, vclass, horizon_min, state, p_unusable, confidence from segment_risk where segment_id = 2001"
    )
    risk_rows = cur.fetchall()
    assert len(risk_rows) == len(SUPPORTED_VCLASSES) * len(cfg.horizons_min)
    for sid, vclass, h, state, p, conf in risk_rows:
        assert sid == 2001
        assert state in ("clear", "watch", "risky", "impassable")
        assert 0.0 <= p <= 1.0
        assert conf in ("low", "medium", "high")

    # 3. Verify segment_risk_history references run_id
    cur = app_db.execute("select count(*) from segment_risk_history where run_id = %s", (run_id,))
    assert cur.fetchone()[0] == len(risk_rows)

    # 4. Verify audit_log recorded changes
    cur = app_db.execute(
        "select actor, action, segment_id, after->>'state' from audit_log where segment_id = 2001"
    )
    audit_rows = cur.fetchall()
    assert len(audit_rows) > 0
    for actor, action, seg_id, new_state in audit_rows:
        assert actor == f"system:scoring:{cfg.model_version}"
        assert action == "state_change"
        assert seg_id == 2001


def test_persist_run_result_upsert_and_history(app_db):
    cfg = load_config()
    now1 = datetime(2027, 5, 18, 14, 0, tzinfo=UTC)
    now2 = datetime(2027, 5, 18, 14, 15, tzinfo=UTC)

    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (3001, 777001, %s, 'primary', 1, true)
        """,
        (SEG_LINE,),
    )
    app_db.execute(
        """
        insert into segment_static (segment_id, structure, base_logit, zone_id)
        values (3001, 'none', -5.0, 1)
        """
    )
    # Light rain initially
    app_db.execute(
        "insert into rain_obs (source, zone_id, ts, mm_60m, mm_24h) values ('gauge', 1, %s, 1.0, 2.0)",
        (now1,),
    )

    # First run
    run_id1, _ = execute_score_run(app_db, cfg=cfg, now=now1, notes="run 1")

    # Add torrential rain
    app_db.execute(
        "insert into rain_obs (source, zone_id, ts, mm_60m, mm_24h) values ('gauge', 1, %s, 90.0, 150.0)",
        (now2,),
    )

    # Second run
    run_id2, _ = execute_score_run(app_db, cfg=cfg, now=now2, notes="run 2")
    assert run_id2 > run_id1

    # segment_risk must have the same number of rows (upserted in place)
    cur = app_db.execute("select count(*) from segment_risk where segment_id = 3001")
    expected_rows = len(SUPPORTED_VCLASSES) * len(cfg.horizons_min)
    assert cur.fetchone()[0] == expected_rows

    # segment_risk_history must contain rows from both runs
    cur = app_db.execute(
        "select run_id, count(*) from segment_risk_history where segment_id = 3001 group by run_id order by run_id"
    )
    history_counts = cur.fetchall()
    assert len(history_counts) == 2
    assert history_counts[0] == (run_id1, expected_rows)
    assert history_counts[1] == (run_id2, expected_rows)


def test_audit_log_append_only_trigger(app_db, db):
    """Verify that 0002 locks audit_log: grants block app, trigger blocks superuser."""
    # 1. app role is blocked by table GRANTs
    app_db.execute(
        """
        insert into audit_log (actor, action, segment_id, reason)
        values ('test_user', 'manual_probe', 9999, 'testing append only')
        """
    )
    with pytest.raises(
        psycopg.errors.InsufficientPrivilege, match="permission denied for table audit_log"
    ):
        app_db.execute("update audit_log set reason = 'tampered' where segment_id = 9999")

    with pytest.raises(
        psycopg.errors.InsufficientPrivilege, match="permission denied for table audit_log"
    ):
        app_db.execute("delete from audit_log where segment_id = 9999")

    # 2. superuser / owner is blocked by the audit_log_append_only trigger
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="audit_log is append-only"):
        db.execute("update audit_log set reason = 'tampered' where segment_id = 9999")

    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="audit_log is append-only"):
        db.execute("delete from audit_log where segment_id = 9999")
