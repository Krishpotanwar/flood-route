"""Domain unit tests for route watch material-change evaluation and rate limits."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg

from floodroute.route.watch import (
    WatchRequest,
    create_route_watch,
    evaluate_route_watches,
)

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE_1 = "SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)"
SEG_LINE_2 = "SRID=4326;LINESTRING(77.60 12.97, 77.61 12.98)"


def _seed_base_data(db):
    now = datetime.now(UTC)
    db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values
            (2001, 12001, %s, 'primary', 1, true),
            (2002, 12002, %s, 'secondary', 1, true)
        """,
        (SEG_LINE_1, SEG_LINE_2),
    )
    db.execute(
        """
        insert into segment_risk (
            segment_id, vclass, horizon_min, p_unusable,
            depth_p50_cm, depth_p90_cm, state, confidence,
            evidence_age_s, model_version, updated_at
        )
        values
            (2001, 'car', 0, 0.05, 0.0, 5.0, 'clear', 'high', 30, 'v0.0.1', %s),
            (2002, 'car', 0, 0.15, 5.0, 10.0, 'watch', 'medium', 60, 'v0.0.1', %s)
        """,
        (now, now),
    )
    return now


def _seed_route_decision(db, decision_id, segments=None):
    if segments is None:
        segments = [2001, 2002]
    now = datetime.now(UTC)
    chosen_payload = {
        "segments": [{"segment_id": sid} for sid in segments],
        "eta_min": 25,
    }
    db.execute(
        """
        insert into route_decision (
            decision_id, ts, vclass, model_version, chosen
        ) values (%s, %s, 'car', 'v0.0.1', %s)
        """,
        (decision_id, now, json.dumps(chosen_payload)),
    )


def test_evaluate_route_watches_material_change(app_db):
    _seed_base_data(app_db)
    decision_id = uuid4()
    _seed_route_decision(app_db, decision_id, segments=[2001, 2002])

    req = WatchRequest(
        contact_target="fcm-token-123",
        alert_channel="fcm",
        dwell_minutes=60,
    )
    resp = create_route_watch(app_db, decision_id, req)
    assert resp.status == "active"

    # Initial check: no change
    alerts_0 = evaluate_route_watches(app_db)
    assert len(alerts_0) == 0

    # Elevate segment 2001 to impassable (with depth_p90 >= depth_p50)
    now = datetime.now(UTC)
    app_db.execute(
        """
        update segment_risk
        set state = 'impassable', p_unusable = 0.90, depth_p50_cm = 40.0, depth_p90_cm = 60.0, updated_at = %s
        where segment_id = 2001 and vclass = 'car' and horizon_min = 0
        """,
        (now,),
    )

    alerts_1 = evaluate_route_watches(app_db)
    assert len(alerts_1) == 1
    a = alerts_1[0]
    assert a.decision_id == decision_id
    assert len(a.changed_segments) == 1
    assert a.changed_segments[0]["segment_id"] == 2001
    assert a.changed_segments[0]["current_state"] == "impassable"
    assert a.changed_segments[0]["previous_state"] == "clear"

    # Invariant: no safe label
    assert "safe" not in a.reason.lower()


def test_route_watch_rate_limit_3_per_hour(app_db):
    _seed_base_data(app_db)
    decision_id = uuid4()
    _seed_route_decision(app_db, decision_id, segments=[2001])

    req = WatchRequest(contact_target="phone-+919876543210", alert_channel="sms", dwell_minutes=60)
    create_route_watch(app_db, decision_id, req)

    # Trigger 3 successive alerts by setting counts manually
    now = datetime.now(UTC)
    app_db.execute(
        """
        update route_watch
        set alerts_sent_count = 3, last_alert_at = %s
        where decision_id = %s
        """,
        (now, decision_id),
    )

    # Change state to trigger alert
    app_db.execute(
        """
        update segment_risk
        set state = 'impassable', p_unusable = 0.85, depth_p50_cm = 35.0, depth_p90_cm = 50.0
        where segment_id = 2001
        """
    )

    # 4th alert in the same hour must be capped
    alerts = evaluate_route_watches(app_db)
    assert len(alerts) == 0

    # After 1 hour, alerts can be sent again
    past_1hr = now - timedelta(hours=1, minutes=5)
    app_db.execute(
        """
        update route_watch set last_alert_at = %s where decision_id = %s
        """,
        (past_1hr, decision_id),
    )
    alerts_after_1hr = evaluate_route_watches(app_db)
    assert len(alerts_after_1hr) == 1


def test_baseline_advances_on_recovery_so_a_reflood_alerts(app_db):
    _seed_base_data(app_db)
    decision_id = uuid4()
    _seed_route_decision(app_db, decision_id, segments=[2001])

    req = WatchRequest(contact_target="t", alert_channel="fcm", dwell_minutes=60)
    create_route_watch(app_db, decision_id, req)

    def set_state(state, p):
        app_db.execute(
            "update segment_risk set state = %s, p_unusable = %s, updated_at = %s"
            " where segment_id = 2001 and vclass = 'car' and horizon_min = 0",
            (state, p, datetime.now(UTC)),
        )

    set_state("impassable", 0.9)
    assert len(evaluate_route_watches(app_db)) == 1
    # Recovery: no alert, but the baseline must follow the fall.
    set_state("clear", 0.05)
    assert evaluate_route_watches(app_db) == []
    row = app_db.execute(
        "select baseline_states from route_watch where decision_id = %s", (decision_id,)
    ).fetchone()[0]
    states = row if isinstance(row, dict) else json.loads(row)
    assert states["2001"] == "clear"
    # Re-flood from the lower baseline alerts again.
    set_state("risky", 0.4)
    alerts = evaluate_route_watches(app_db)
    assert len(alerts) == 1
    assert alerts[0].changed_segments[0]["previous_state"] == "clear"


def test_missing_risk_row_baselines_unknown_and_duplicates_return_existing(app_db):
    _seed_base_data(app_db)
    decision_id = uuid4()
    _seed_route_decision(app_db, decision_id, segments=[2001, 9999])

    req = WatchRequest(contact_target="t", alert_channel="sms", dwell_minutes=60)
    first = create_route_watch(app_db, decision_id, req)
    row = app_db.execute(
        "select baseline_states from route_watch where decision_id = %s", (decision_id,)
    ).fetchone()[0]
    states = row if isinstance(row, dict) else json.loads(row)
    assert states["9999"] == "unknown"

    second = create_route_watch(
        app_db, decision_id, WatchRequest(contact_target="other", dwell_minutes=60)
    )
    assert second.watch_id == first.watch_id
    count = app_db.execute(
        "select count(*) from route_watch where decision_id = %s", (decision_id,)
    ).fetchone()[0]
    assert count == 1


def test_watch_request_rejects_an_unknown_alert_channel():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WatchRequest(contact_target="t", alert_channel="smoke-signal")


def test_concurrent_creators_share_one_watch_and_alert_counter(app_db, db_url):
    _seed_base_data(app_db)
    decision_id = uuid4()
    _seed_route_decision(app_db, decision_id)
    ready = Barrier(2)

    def create():
        with psycopg.connect(db_url, autocommit=True, connect_timeout=3) as conn:
            conn.execute("set role floodroute_app")
            ready.wait(timeout=5)
            return create_route_watch(conn, decision_id, WatchRequest(contact_target="t"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [
            future.result(timeout=10) for future in [pool.submit(create), pool.submit(create)]
        ]
    assert first.watch_id == second.watch_id
    assert (
        app_db.execute(
            "select count(*) from route_watch where decision_id=%s", (decision_id,)
        ).fetchone()[0]
        == 1
    )


def test_retired_segment_risk_is_unknown_and_does_not_alert(app_db):
    _seed_base_data(app_db)
    decision_id = uuid4()
    _seed_route_decision(app_db, decision_id, segments=[2001])
    watch = create_route_watch(app_db, decision_id, WatchRequest(contact_target="t"))
    app_db.execute("update segment set assessed=false where segment_id=2001")
    app_db.execute(
        "update segment_risk set state='impassable', p_unusable=0.9 where segment_id=2001"
    )
    assert evaluate_route_watches(app_db) == []
    baseline = app_db.execute(
        "select baseline_states from route_watch where watch_id=%s", (watch.watch_id,)
    ).fetchone()[0]
    assert baseline["2001"] == "unknown"
