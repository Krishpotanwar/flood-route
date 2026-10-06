"""Tests for FloodRoute background worker and data retention."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

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
        values (1, 1, 'SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))', '{}')
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
