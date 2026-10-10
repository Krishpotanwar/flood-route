"""Tests for FloodRoute background worker and data retention."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from floodroute.worker import RetentionStats, Worker, WorkerConfig, prune_retention


def test_prune_retention_purges_old_route_decisions_and_reports(app_db):
    now = datetime.now(UTC)

    # 1. Insert a fresh route decision and an expired route decision (> 365 days old)
    old_ts = now - timedelta(days=400)
    app_db.execute(
        """
        insert into route_decision (
            decision_id, ts, vclass, depart_at, model_version, no_safe_route
        )
        values
            ('11111111-1111-1111-1111-111111111111', %s, 'car', %s, 'v0.0.1', false),
            ('22222222-2222-2222-2222-222222222222', %s, 'car', %s, 'v0.0.1', false)
        """,
        (now, now, old_ts, old_ts),
    )

    # 2. Insert resolved reports: one recent, one past 90 days retention
    app_db.execute(
        """
        insert into zone (zone_id, city_id, geom, params)
        values (
            1, 1,
            'SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))',
            '{}'
        )
        """
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (9801, 19801, 'SRID=4326;LINESTRING(77.58 12.97, 77.59 12.98)', 'primary', 1, true)
        """
    )
    old_report_time = now - timedelta(days=120)
    app_db.execute(
        """
        insert into report (report_id, ts, status, depth_class, segment_id)
        values
            ('33333333-3333-3333-3333-333333333333', %s, 'expired', 'knee', 9801),
            ('44444444-4444-4444-4444-444444444444', %s, 'expired', 'knee', 9801),
            ('55555555-5555-5555-5555-555555555555', %s, 'pending', 'knee', 9801)
        """,
        (now, old_report_time, old_report_time),
    )

    # 3. Run retention pruning
    stats = prune_retention(
        app_db,
        now=now,
        route_decision_retention_days=365,
        report_retention_days=90,
    )

    assert stats.route_decisions_purged == 1
    assert stats.purged_reports_count == 1  # Only the resolved old report is purged, active stays

    # Verify remaining rows
    remaining_decisions = app_db.execute("select count(*) from route_decision").fetchone()[0]
    assert remaining_decisions == 1

    remaining_reports = app_db.execute("select count(*) from report").fetchone()[0]
    assert remaining_reports == 2


def test_worker_is_due():
    worker = Worker()
    now = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)

    # None last run means always due
    assert worker.is_due(None, 300.0, now) is True

    # Run within interval is not due
    last_recent = now - timedelta(seconds=100)
    assert worker.is_due(last_recent, 300.0, now) is False

    # Run past interval is due
    last_old = now - timedelta(seconds=350)
    assert worker.is_due(last_old, 300.0, now) is True


def test_worker_step_with_mocked_tasks():
    cfg = WorkerConfig(
        sachet_interval_s=60.0,
        metno_interval_s=60.0,
        score_interval_s=60.0,
        retention_interval_s=60.0,
    )
    worker = Worker(db_url="postgresql://mock", config=cfg)
    now = datetime.now(UTC)

    with (
        patch("psycopg.connect") as mock_connect,
        patch("floodroute.worker.run_ingest", return_value=0) as mock_ingest,
        patch("floodroute.worker.execute_score_run") as mock_score,
        patch("floodroute.worker.prune_retention") as mock_retention,
    ):
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        score_result = MagicMock()
        score_result.changes = []
        mock_score.return_value = (42, score_result)

        mock_retention.return_value = RetentionStats(
            route_decisions_purged=5,
            expired_evidence_count=2,
            purged_reports_count=1,
        )

        summary = worker.step(now=now, force_all=True)

        assert summary["tasks"]["sachet"]["status_code"] == 0
        assert summary["tasks"]["metno"]["status_code"] == 0
        assert summary["tasks"]["score"]["run_id"] == 42
        assert summary["tasks"]["retention"]["route_decisions_purged"] == 5
        assert mock_ingest.call_count == 2

        # Check last run timestamps were recorded
        assert worker.last_sachet == now
        assert worker.last_metno == now
        assert worker.last_score == now
        assert worker.last_retention == now


def test_worker_run_loop_max_iterations():
    worker = Worker(db_url="postgresql://mock")
    with patch.object(worker, "step") as mock_step:
        worker.run_loop(poll_interval_s=0.01, max_iterations=2)
        assert mock_step.call_count == 2


def test_failed_ingest_retries_soon_instead_of_a_full_interval():
    cfg = WorkerConfig(sachet_interval_s=300.0, metno_interval_s=3600.0)
    worker = Worker(db_url="postgresql://mock", config=cfg)
    now = datetime.now(UTC)
    with (
        patch("psycopg.connect") as mock_connect,
        patch("floodroute.worker.run_ingest", return_value=1),
    ):
        mock_connect.return_value.__enter__.return_value = MagicMock()
        summary = worker.step(now=now, force_all=True)
        assert summary["tasks"]["sachet"]["status_code"] == 1
        assert summary["tasks"]["metno"]["status_code"] == 1
        # Failed runs wait only the short retry delay, not the full interval.
        assert worker.last_sachet == now - timedelta(seconds=300.0 - 60.0)
        assert worker.last_metno == now - timedelta(seconds=3600.0 - 300.0)
        assert worker.is_due(worker.last_sachet, 300.0, now + timedelta(seconds=61)) is True
        assert worker.is_due(worker.last_sachet, 300.0, now + timedelta(seconds=59)) is False


def test_snapshot_total_failure_is_reported_and_keeps_the_old_schedule():
    worker = Worker(db_url="postgresql://mock")
    now = datetime.now(UTC)
    with (
        patch("psycopg.connect") as mock_connect,
        patch("floodroute.worker.run_ingest", return_value=0),
        patch("floodroute.worker.execute_score_run") as mock_score,
        patch("floodroute.worker.prune_retention"),
        patch("floodroute.worker.evaluate_route_watches", return_value=[]),
        patch(
            "floodroute.worker.generate_city_closure_snapshot",
            side_effect=OSError("disk full"),
        ),
    ):
        mock_connect.return_value.__enter__.return_value = MagicMock()
        score_result = MagicMock()
        score_result.changes = []
        mock_score.return_value = (1, score_result)
        summary = worker.step(now=now, force_all=True)
        snap = summary["tasks"]["snapshot"]
        assert snap["cities"] == []
        assert len(snap["errors"]) == 4  # bengaluru, chennai, gurugram, mumbai
        assert worker.last_snapshot is None


def test_snapshot_covers_every_known_city():
    from floodroute.inventory import CITIES

    worker = Worker(db_url="postgresql://mock")
    now = datetime.now(UTC)
    seen = []
    with (
        patch("psycopg.connect") as mock_connect,
        patch("floodroute.worker.run_ingest", return_value=0),
        patch("floodroute.worker.execute_score_run") as mock_score,
        patch("floodroute.worker.prune_retention"),
        patch("floodroute.worker.evaluate_route_watches", return_value=[]),
        patch("floodroute.worker.generate_city_closure_snapshot") as mock_snap,
    ):
        mock_connect.return_value.__enter__.return_value = MagicMock()
        score_result = MagicMock()
        score_result.changes = []
        mock_score.return_value = (1, score_result)
        mock_snap.side_effect = lambda conn, city_name, vclass: seen.append(city_name) or {
            "feature_count": 0
        }
        worker.step(now=now, force_all=True)
        assert sorted(seen) == sorted(CITIES)


def test_worker_run_loop_survives_unexpected_step_errors():
    worker = Worker(db_url="postgresql://mock")
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("corrupt snapshot json")
        worker.stop()

    with patch.object(worker, "step", side_effect=flaky):
        worker.run_loop(poll_interval_s=0, max_iterations=2)
    assert len(calls) == 2


def test_worker_db_url_raises_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        _ = Worker().db_url


def test_prune_retention_deactivates_expired_watches(app_db):
    now = datetime.now(UTC)
    old_id, live_id = uuid4(), uuid4()
    app_db.execute(
        "insert into route_decision "
        "(decision_id, ts, vclass, depart_at, model_version, no_safe_route) "
        "values (%s, %s, 'car', %s, 'v0.0.1', false), (%s, %s, 'car', %s, 'v0.0.1', false)",
        (old_id, now, now, live_id, now, now),
    )
    app_db.execute(
        """
        insert into route_watch (
            watch_id, decision_id, vclass, segments, baseline_states,
            alert_channel, contact_target, expires_at, is_active, created_at
        )
        values (%s, %s, 'car', array[1], '{}', 'fcm', 't', %s, true, %s),
               (%s, %s, 'car', array[1], '{}', 'fcm', 't', %s, true, %s)
        """,
        (
            uuid4(), old_id, now - timedelta(minutes=1), now - timedelta(hours=2),
            uuid4(), live_id, now + timedelta(hours=1), now,
        ),
    )
    stats = prune_retention(app_db, now=now)
    assert stats.expired_watches_purged == 1
    active = app_db.execute("select count(*) from route_watch where is_active").fetchone()[0]
    assert active == 1


def _score_step(worker, now, freeze_record, changes, alerts):
    """Run one worker step with the score task isolated; returns (summary, mocks)."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch("floodroute.worker.run_ingest", return_value=0),
        patch("floodroute.worker.execute_score_run") as mock_score,
        patch("floodroute.worker.prune_retention"),
        patch(
            "floodroute.worker.generate_city_closure_snapshot",
            return_value={"feature_count": 0},
        ),
        patch("floodroute.worker.get_active_kill_switch", return_value=freeze_record),
        patch("floodroute.worker.evaluate_route_watches", return_value=alerts) as mock_evaluate,
        patch("floodroute.worker.dispatch_event") as mock_dispatch,
    ):
        mock_connect.return_value.__enter__.return_value = MagicMock()
        score_result = MagicMock()
        score_result.changes = changes
        mock_score.return_value = (7, score_result)
        summary = worker.step(now=now, force_all=True)
    return summary, mock_evaluate, mock_dispatch


def test_score_dispatch_held_while_global_freeze_engaged():
    worker = Worker(db_url="postgresql://mock")
    now = datetime.now(UTC)
    freeze = MagicMock()
    freeze.switch_id = "freeze-1"
    change = MagicMock()
    change.segment_id = 101
    summary, mock_evaluate, mock_dispatch = _score_step(
        worker, now, freeze_record=freeze, changes=[change], alerts=[]
    )
    score = summary["tasks"]["score"]
    assert score["run_id"] == 7
    assert score["changes_count"] == 1
    assert score["alerts_generated"] == 0
    assert score["dispatch_held"] is True
    # Advisory fanout skipped: no watch evaluation (counters untouched)
    # and no segment broadcast.
    mock_evaluate.assert_not_called()
    mock_dispatch.assert_not_called()
    assert worker.last_score == now


def test_score_dispatch_resumes_after_freeze_lifted():
    worker = Worker(db_url="postgresql://mock")
    now = datetime.now(UTC)
    change = MagicMock()
    change.segment_id = 101
    summary, mock_evaluate, mock_dispatch = _score_step(
        worker, now, freeze_record=None, changes=[change], alerts=[MagicMock()]
    )
    score = summary["tasks"]["score"]
    assert score["alerts_generated"] == 1
    assert "dispatch_held" not in score
    mock_evaluate.assert_called_once()
    mock_dispatch.assert_called_once()
    assert worker.last_score == now
