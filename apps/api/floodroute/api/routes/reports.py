"""Crowd report submission endpoint: POST /v1/reports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from floodroute.api.deps import get_db
from floodroute.route.models import IN_LAT, IN_LON

router = APIRouter(prefix="/v1", tags=["reports"])

DEPTH_CM_MAP = {
    "wet": 2.0,
    "ankle": 10.0,
    "knee": 35.0,
    "vehicle_deep": 60.0,
}


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=IN_LAT[0], le=IN_LAT[1])
    lon: float = Field(ge=IN_LON[0], le=IN_LON[1])
    depth_class: Literal["wet", "ankle", "knee", "vehicle_deep"]
    photo_ref: str | None = Field(default=None, max_length=255)
    reporter_id: str = Field(min_length=1, max_length=128)


@router.post("/reports", status_code=201)
def submit_report(
    req: ReportCreate,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Submit a citizen flood depth report with automatic map-matching to road segment."""
    now = datetime.now(UTC)
    report_id = str(uuid.uuid4())

    # Map match to nearest segment within 100m
    cur = db.execute(
        """
        select segment_id,
               ST_Distance(geom::geography, ST_SetSRID(ST_Point(%s, %s), 4326)::geography) as dist_m
        from segment
        where ST_DWithin(geom::geography, ST_SetSRID(ST_Point(%s, %s), 4326)::geography, 100)
        order by dist_m
        limit 1
        """,
        (req.lon, req.lat, req.lon, req.lat),
    )
    row = cur.fetchone()
    segment_id = row[0] if row else None

    # Insert into report table
    db.execute(
        """
        insert into report (report_id, segment_id, ts, depth_class, trust, photo_ref, status)
        values (%s, %s, %s, %s, %s, %s, 'pending')
        """,
        (report_id, segment_id, now, req.depth_class, 0.5, req.photo_ref),
    )

    # If matched to a segment, inject as evidence so scoring immediately reacts
    if segment_id is not None:
        depth_cm = DEPTH_CM_MAP[req.depth_class]
        expires = now + timedelta(minutes=15)
        db.execute(
            """
            insert into evidence (segment_id, kind, ts, expires, depth_cm, source_id, trust)
            values (%s, 'report', %s, %s, %s, %s, %s)
            """,
            (segment_id, now, expires, depth_cm, req.reporter_id, 0.5),
        )

    return {
        "report_id": report_id,
        "segment_id": segment_id,
        "depth_class": req.depth_class,
        "status": "received",
    }
