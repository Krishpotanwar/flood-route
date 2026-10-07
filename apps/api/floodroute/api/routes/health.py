"""Health check endpoint: /v1/health."""

from __future__ import annotations

import logging
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends

from floodroute.api.deps import get_db, get_score_config
from floodroute.score.config import Config as ScoreConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health")
def health_check(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    cfg: Annotated[ScoreConfig, Depends(get_score_config)],
) -> dict[str, Any]:
    """Liveness, readiness, model version, and source health tracking."""
    db_status = "connected"
    sources: dict[str, dict[str, Any]] = {}
    is_healthy = True

    try:
        cur = db.execute("select source, last_ok, last_error, lag_s from source_health")
        for src, ok_ts, err, lag in cur.fetchall():
            sources[src] = {
                "last_ok": ok_ts.isoformat() if ok_ts else None,
                "last_error": err,
                "lag_s": lag,
            }
            if lag is not None and lag > 3600:
                is_healthy = False
    except psycopg.Error as e:
        logger.warning("Health check database error: %s", e)
        db_status = "error"
        is_healthy = False

    return {
        "status": "ok" if is_healthy else "degraded",
        "model_version": cfg.model_version,
        "database": db_status,
        "sources": sources,
    }
