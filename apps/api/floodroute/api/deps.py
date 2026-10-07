"""Dependencies for FastAPI endpoints."""

from __future__ import annotations

import os
from collections.abc import Callable, Generator, Sequence
from typing import Annotated

import psycopg
from fastapi import Depends
from psycopg_pool import ConnectionPool

from floodroute.db.conn import database_url
from floodroute.route.models import (
    DEFAULT as ROUTE_CONFIG,
)
from floodroute.route.models import (
    HORIZONS,
    LatLon,
    Polygon,
    Route,
    SegmentRisk,
)
from floodroute.route.models import (
    Config as RouteConfig,
)
from floodroute.route.valhalla import ValhallaRouter
from floodroute.score.config import Config as ScoreConfig
from floodroute.score.config import load_config

RouterCallable = Callable[[LatLon, LatLon, str, any, Sequence[Polygon]], Route | None]

# Forecast rows for one segment/vclass should come from a single scoring run.
# Past this updated_at spread the horizons mix runs and the row is unusable.
MAX_HORIZON_SKEW_S = 60.0

_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}

_POOL: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Get or create singleton connection pool."""
    global _POOL
    if _POOL is None or _POOL.closed:
        url = database_url()
        _POOL = ConnectionPool(
            conninfo=url,
            min_size=10,
            max_size=50,
            timeout=10.0,
            open=True,
            kwargs={"autocommit": True},
        )
    return _POOL


def close_pool() -> None:
    """Close the active connection pool if open."""
    global _POOL
    if _POOL is not None and not _POOL.closed:
        _POOL.close()
        _POOL = None


def get_db() -> Generator[psycopg.Connection, None, None]:
    """Provide a connection to PostgreSQL acting as floodroute_app (DML only)."""
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute("set role floodroute_app")
        yield conn


def get_score_config() -> ScoreConfig:
    return load_config()


def get_route_config() -> RouteConfig:
    return ROUTE_CONFIG


def db_segment_of(conn: psycopg.Connection, coords: Sequence[LatLon]) -> int | None:
    """Find the nearest assessed segment for a route maneuver geometry."""
    if len(coords) < 2:
        return None
    pts = ", ".join(f"{lon} {lat}" for lat, lon in coords)
    line_wkt = f"SRID=4326;LINESTRING({pts})"
    try:
        cur = conn.execute(
            """
            select segment_id
            from segment
            where assessed = true
              and ST_DWithin(geom::geography, ST_GeogFromText(%s), 50)
            order by ST_Distance(geom::geography, ST_GeogFromText(%s))
            limit 1
            """,
            (line_wkt, line_wkt),
        )
        row = cur.fetchone()
        return row[0] if row else None
    except (psycopg.Error, ValueError):
        return None


def db_risk_for(conn: psycopg.Connection, segment_id: int, vclass: str) -> SegmentRisk | None:
    """Load the current forecast for a segment and vehicle class.

    None means no forecast rows exist (segment outside inventory: legitimately
    unassessed). A partial horizon set raises instead of reading as neutral,
    since a missing horizon could hide a flood peak.
    """
    cur = conn.execute(
        """
        select sr.horizon_min, sr.p_unusable, sr.state, sr.confidence, sr.evidence_age_s, sr.updated_at
        from segment_risk sr
        join segment s on s.segment_id = sr.segment_id
        where sr.segment_id = %s and sr.vclass = %s and s.assessed
        order by sr.horizon_min
        """,
        (segment_id, vclass),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    p = {row[0]: float(row[1]) for row in rows}
    state = {row[0]: row[2] for row in rows}
    if set(p.keys()) != set(HORIZONS):
        raise RuntimeError(
            f"incomplete forecast for segment {segment_id}/{vclass}: "
            f"have horizons {sorted(p)} expected {sorted(HORIZONS)}"
        )
    stamps = [row[5] for row in rows]
    if any(t is None or t.tzinfo is None for t in stamps):
        raise RuntimeError(f"forecast for segment {segment_id}/{vclass} is missing timestamps")
    # A newer horizon cannot renew an older one. A scoring run normally
    # writes together; retain the oldest timestamp when small skew exists.
    issued_at = min(stamps)
    if (max(stamps) - issued_at).total_seconds() > MAX_HORIZON_SKEW_S:
        raise RuntimeError(
            f"forecast for segment {segment_id}/{vclass} mixes runs "
            f"(updated_at spread past {MAX_HORIZON_SKEW_S}s)"
        )
    known = [row[3] for row in rows if row[3] in _CONFIDENCE_RANK]
    confidence = min(known, key=_CONFIDENCE_RANK.get) if known else "low"
    ages = [row[4] for row in rows if row[4] is not None]
    evidence_age_s = max(ages) if ages else None
    return SegmentRisk(
        issued_at=issued_at,
        p=p,
        state=state,
        confidence=confidence,
        evidence_age_s=evidence_age_s,
    )


def get_router(
    conn: Annotated[psycopg.Connection, Depends(get_db)],
) -> RouterCallable:
    """Create Valhalla router connected to VALHALLA_URL."""
    base_url = os.environ.get("VALHALLA_URL", "http://127.0.0.1:8002").rstrip("/")
    return ValhallaRouter(
        base_url=base_url,
        segment_of=lambda coords: db_segment_of(conn, coords),
    )
