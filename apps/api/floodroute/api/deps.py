"""Dependencies for FastAPI endpoints."""

from __future__ import annotations

import os
from collections.abc import Callable, Generator, Sequence
from typing import Annotated

import psycopg
from fastapi import Depends

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


def get_db() -> Generator[psycopg.Connection, None, None]:
    """Provide a connection to PostgreSQL acting as floodroute_app (DML only)."""
    url = database_url()
    with psycopg.connect(url, autocommit=True) as conn:
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
    """Load the current forecast for a segment and vehicle class."""
    cur = conn.execute(
        """
        select horizon_min, p_unusable, state, confidence, evidence_age_s, updated_at
        from segment_risk
        where segment_id = %s and vclass = %s
        order by horizon_min
        """,
        (segment_id, vclass),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    p = {row[0]: float(row[1]) for row in rows}
    state = {row[0]: row[2] for row in rows}
    if set(p.keys()) != set(HORIZONS):
        return None
    return SegmentRisk(
        issued_at=rows[0][5],
        p=p,
        state=state,
        confidence=rows[0][3],
        evidence_age_s=rows[0][4],
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
