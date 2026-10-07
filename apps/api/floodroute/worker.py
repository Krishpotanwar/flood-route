"""Worker daemon and scheduling loop (TRD sections 3, 5, 13, 19).

Coordinates periodic background tasks:
1. Ingestion: SACHET alerts and MET Norway rainfall forecasts.
2. Scoring: Periodic evaluation of monitored segments and risk state updates.
3. Retention: Age-based purging of route decisions and DPDP compliance cleanup.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from floodroute.db.conn import database_url
from floodroute.feed.snapshot import generate_city_closure_snapshot
from floodroute.ingest import metno, sachet
from floodroute.ingest.common import Http
from floodroute.ingest.common import run as run_ingest
from floodroute.inventory import CITIES
from floodroute.metrics.collector import METRICS
from floodroute.route.watch import evaluate_route_watches
from floodroute.safety.kill_switch import get_active_kill_switch
from floodroute.score.config import Config as ScoreConfig
from floodroute.score.config import load_config
from floodroute.score.db import execute_score_run
from floodroute.webhook import WebhookEvent, dispatch_event

logger = logging.getLogger(__name__)

# Retry delay after a failed ingest run (instead of a full interval).
SACHET_RETRY_S = 60.0
METNO_RETRY_S = 300.0


@dataclass
class RetentionStats:
    """Statistics from age-based retention and data cleanup."""

    route_decisions_purged: int = 0
    expired_evidence_count: int = 0
    purged_reports_count: int = 0
    expired_watches_purged: int = 0


@dataclass
class WorkerConfig:
    """Intervals and retention periods for background tasks."""

    sachet_interval_s: float = 300.0  # 5 min
    metno_interval_s: float = 3600.0  # 1 hour
    score_interval_s: float = 300.0  # 5 min
    snapshot_interval_s: float = 120.0  # 2 min (TRD 11)
    retention_interval_s: float = 86400.0  # 24 hours
    route_decision_retention_days: int = 365  # TRD 13: 1 year retention
    report_retention_days: int = 90  # DPDP Act 2023: 90 days retention


def prune_retention(
    conn: psycopg.Connection,
    now: datetime | None = None,
    route_decision_retention_days: int = 365,
    report_retention_days: int = 90,
) -> RetentionStats:
    """Purge old route decisions and concluded crowd reports past retention limits."""
    current_time = now or datetime.now(UTC)
    stats = RetentionStats()

    # 1. Purge route decisions older than retention policy (TRD 13)
    cutoff_decisions = current_time - timedelta(days=route_decision_retention_days)
    with conn.cursor() as cur:
        cur.execute(
            "delete from route_decision where ts < %s",
            (cutoff_decisions,),
        )
        stats.route_decisions_purged = cur.rowcount

        # 2. Delete expired evidence past expiration
        cur.execute(
            "delete from evidence where expires < %s",
            (current_time,),
        )
        stats.expired_evidence_count = cur.rowcount

        # 3. Purge concluded crowd reports older than DPDP retention limit
        cutoff_reports = current_time - timedelta(days=report_retention_days)
        cur.execute(
            "delete from report where ts < %s and status in ('rejected', 'expired')",
            (cutoff_reports,),
        )
        stats.purged_reports_count = cur.rowcount

        # 4. Deactivate expired route watches
        cur.execute(
            "update route_watch set is_active = false where expires_at <= %s and is_active",
            (current_time,),
        )
        stats.expired_watches_purged = cur.rowcount

    return stats


class Worker:
    """Scheduled task runner for FloodRoute ingestion, scoring, and data retention."""

    def __init__(
        self,
        db_url: str | None = None,
        config: WorkerConfig | None = None,
        score_config: ScoreConfig | None = None,
    ):
        self._explicit_db_url = db_url
        self.config = config or WorkerConfig()
        self.score_config = score_config or load_config()
        self.running = False
        self.last_sachet: datetime | None = None
        self.last_metno: datetime | None = None
        self.last_score: datetime | None = None
        self.last_retention: datetime | None = None
        self.last_snapshot: datetime | None = None

    @property
    def db_url(self) -> str:
        if self._explicit_db_url:
            return self._explicit_db_url
        return database_url()

    def stop(self) -> None:
        """Signal the worker to terminate gracefully."""
        self.running = False

    def is_due(self, last_run: datetime | None, interval_s: float, now: datetime) -> bool:
        """Check if a scheduled task is due for execution."""
        if last_run is None:
            return True
        return (now - last_run).total_seconds() >= interval_s

    def step(
        self,
        now: datetime | None = None,
        force_all: bool = False,
    ) -> dict[str, Any]:
        """Execute one evaluation tick across all scheduled tasks. Returns execution summary."""
        current_time = now or datetime.now(UTC)
        summary: dict[str, Any] = {"timestamp": current_time, "tasks": {}}

        with psycopg.connect(self.db_url, autocommit=True) as conn:
            # Task 1: SACHET alert feed ingestion
            if force_all or self.is_due(
                self.last_sachet, self.config.sachet_interval_s, current_time
            ):
                http_sachet = Http(sachet.HOSTS)
                try:
                    code = run_ingest(conn, sachet.SOURCE, lambda c: sachet.ingest(c, http_sachet))
                    summary["tasks"]["sachet"] = {"status_code": code}
                    if code == 0:
                        self.last_sachet = current_time
                    else:
                        # Failed run: retry soon instead of waiting a full interval.
                        self.last_sachet = current_time - timedelta(
                            seconds=self.config.sachet_interval_s - SACHET_RETRY_S
                        )
                except Exception as e:
                    logger.exception("Worker error running SACHET ingest")
                    summary["tasks"]["sachet"] = {"error": str(e)}
                    self.last_sachet = current_time - timedelta(
                        seconds=self.config.sachet_interval_s - SACHET_RETRY_S
                    )
                finally:
                    http_sachet.close()

            # Task 2: MET Norway rainfall forecast ingestion
            if force_all or self.is_due(
                self.last_metno, self.config.metno_interval_s, current_time
            ):
                http_metno = Http(metno.HOSTS)
                try:
                    code = run_ingest(conn, metno.SOURCE, lambda c: metno.ingest(c, http_metno))
                    summary["tasks"]["metno"] = {"status_code": code}
                    if code == 0:
                        self.last_metno = current_time
                    else:
                        self.last_metno = current_time - timedelta(
                            seconds=self.config.metno_interval_s - METNO_RETRY_S
                        )
                except Exception as e:
                    logger.exception("Worker error running MET Norway ingest")
                    summary["tasks"]["metno"] = {"error": str(e)}
                    self.last_metno = current_time - timedelta(
                        seconds=self.config.metno_interval_s - METNO_RETRY_S
                    )
                finally:
                    http_metno.close()

            # Task 3: Scoring cycle evaluation
            if force_all or self.is_due(
                self.last_score, self.config.score_interval_s, current_time
            ):
                score_start = time.perf_counter()
                try:
                    run_id, result = execute_score_run(
                        conn,
                        cfg=self.score_config,
                        now=current_time,
                        notes="worker:scheduled",
                    )
                    METRICS.score_runs_total.inc(labels={"status": "success"})
                    METRICS.score_duration_seconds.observe(time.perf_counter() - score_start)
                    # Advisory freeze (TRD 16): while a global freeze is
                    # engaged, worker dispatch of advisories is held. Feeds
                    # and snapshots keep serving ground truth during a
                    # freeze (withholding real closures would itself cause
                    # harm; the freeze governs advisories only, enforced at
                    # route/reroute/snapshot-request and now worker-dispatch
                    # time). City-scoped freezes stay request-time only:
                    # the worker has no identity/city plumbing, so only the
                    # global switch is checked here.
                    freeze = get_active_kill_switch(conn)
                    if freeze is not None:
                        logger.info(
                            "Advisory freeze active (%s): holding watch alerts "
                            "and segment broadcasts for run %s",
                            freeze.switch_id,
                            run_id,
                        )
                        summary["tasks"]["score"] = {
                            "run_id": run_id,
                            "changes_count": len(result.changes),
                            "alerts_generated": 0,
                            "dispatch_held": True,
                        }
                    else:
                        # Evaluate route watch alerts on risk changes
                        alerts = evaluate_route_watches(conn)
                        if result.changes:
                            ev = WebhookEvent(
                                event_type="segment.state_changed",
                                timestamp=current_time,
                                payload={
                                    "run_id": run_id,
                                    "changes_count": len(result.changes),
                                    "segments": [c.segment_id for c in result.changes[:50]],
                                },
                            )
                            dispatch_event(conn, ev)

                        summary["tasks"]["score"] = {
                            "run_id": run_id,
                            "changes_count": len(result.changes),
                            "alerts_generated": len(alerts),
                        }
                    self.last_score = current_time
                except Exception as e:
                    METRICS.score_runs_total.inc(labels={"status": "failed"})
                    logger.exception("Worker error running scoring cycle")
                    summary["tasks"]["score"] = {"error": str(e)}

            # Task 4: Data retention and cleanup
            if force_all or self.is_due(
                self.last_retention, self.config.retention_interval_s, current_time
            ):
                try:
                    stats = prune_retention(
                        conn,
                        now=current_time,
                        route_decision_retention_days=self.config.route_decision_retention_days,
                        report_retention_days=self.config.report_retention_days,
                    )
                    summary["tasks"]["retention"] = {
                        "route_decisions_purged": stats.route_decisions_purged,
                        "expired_evidence_count": stats.expired_evidence_count,
                        "purged_reports_count": stats.purged_reports_count,
                        "expired_watches_purged": stats.expired_watches_purged,
                    }
                    self.last_retention = current_time
                except Exception as e:
                    logger.exception("Worker error running retention prune")
                    summary["tasks"]["retention"] = {"error": str(e)}

            # Task 5: Pre-generate CDN offline closure snapshots (TRD 11)
            if force_all or self.is_due(
                self.last_snapshot, self.config.snapshot_interval_s, current_time
            ):
                snapshots_done = []
                snapshot_errors = []
                for c_name in sorted(CITIES):
                    try:
                        res = generate_city_closure_snapshot(conn, city_name=c_name, vclass="car")
                        snapshots_done.append({"city": c_name, "features": res["feature_count"]})
                    except Exception as e:  # noqa: BLE001 - one city never blocks the others
                        logger.warning("Failed to generate closure snapshot for %s: %s", c_name, e)
                        snapshot_errors.append({"city": c_name, "error": str(e)})
                summary["tasks"]["snapshot"] = {"cities": snapshots_done}
                if snapshot_errors:
                    summary["tasks"]["snapshot"]["errors"] = snapshot_errors
                if snapshots_done:
                    self.last_snapshot = current_time

        return summary


    def run_loop(
        self,
        poll_interval_s: float = 1.0,
        max_iterations: int | None = None,
    ) -> None:
        """Run worker loop until stopped or max_iterations reached."""
        self.running = True
        iterations = 0

        while self.running:
            try:
                self.step()
                iterations += 1
                if max_iterations is not None and iterations >= max_iterations:
                    break
            except Exception as e:  # noqa: BLE001 - the daemon never exits on one bad tick
                logger.error("Unhandled exception in worker step: %s", e)

            if self.running:
                time.sleep(poll_interval_s)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for running the background worker daemon."""
    ap = argparse.ArgumentParser(
        prog="python -m floodroute.worker", description="FloodRoute background daemon"
    )
    ap.add_argument("--once", action="store_true", help="Run one pass across all tasks and exit")
    ap.add_argument("--db-url", default=None, help="PostgreSQL connection string")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    worker = Worker(db_url=args.db_url)

    def handle_signal(sig, frame):
        worker.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if args.once:
        logger.info("Running single worker step...")
        summary = worker.step(force_all=True)
        logger.info("Worker completed step: %s", summary["tasks"])
        return 0

    logger.info("Starting FloodRoute worker daemon...")
    worker.run_loop()
    logger.info("Worker stopped cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
