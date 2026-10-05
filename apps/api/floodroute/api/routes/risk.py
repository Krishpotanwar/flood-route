"""Segment risk endpoint: GET /v1/risk."""

from __future__ import annotations

from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from floodroute.api.deps import get_db

router = APIRouter(prefix="/v1", tags=["risk"])

VALID_HORIZONS = frozenset({0, 30, 60, 120})
VALID_VCLASSES = frozenset({"two_wheeler", "car", "ambulance", "heavy"})


@router.get("/risk")
def get_risk(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    bbox: str | None = Query(None, description="Bounding box as min_lon,min_lat,max_lon,max_lat"),
    h: int = Query(0, description="Forecast horizon in minutes (0, 30, 60, 120)"),
    vclass: str = Query("car", description="Vehicle class: two_wheeler, car, ambulance, heavy"),
    segment_id: int | None = Query(None, description="Specific segment ID filter"),
) -> dict[str, Any]:
    """Query current risk state for segments within a bounding box or by segment ID."""
    if h not in VALID_HORIZONS:
        raise HTTPException(status_code=422, detail="h must be one of 0, 30, 60, 120")
    if vclass not in VALID_VCLASSES:
        raise HTTPException(
            status_code=422,
            detail="vclass must be one of two_wheeler, car, ambulance, heavy",
        )

    clauses = ["1=1"]
    params: list[Any] = [vclass, h]

    if segment_id is not None:
        clauses.append("s.segment_id = %s")
        params.append(segment_id)

    if bbox:
        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            min_lon, min_lat, max_lon, max_lat = parts
            if min_lon > max_lon or min_lat > max_lat:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="invalid bbox; expected min_lon,min_lat,max_lon,max_lat",
            )
        clauses.append("ST_Intersects(s.geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))")
        params.extend([min_lon, min_lat, max_lon, max_lat])

    where_sql = " and ".join(clauses)
    sql = f"""
    select s.segment_id, s.assessed,
           sr.state, sr.p_unusable, sr.confidence,
           sr.depth_p50_cm, sr.depth_p90_cm, sr.evidence_age_s, sr.updated_at
    from segment s
    left join segment_risk sr
      on s.segment_id = sr.segment_id and sr.vclass = %s and sr.horizon_min = %s
    where {where_sql}
    order by s.segment_id
    limit 1000
    """

    cur = db.execute(sql, tuple(params))
    items = []
    for sid, assessed, state, p, conf, d50, d90, age_s, up_at in cur.fetchall():
        items.append({
            "segment_id": sid,
            "assessed": assessed,
            "state": state if assessed else None,
            "p_unusable": float(p) if p is not None else None,
            "confidence": conf if assessed else None,
            "depth_p50_cm": float(d50) if d50 is not None else None,
            "depth_p90_cm": float(d90) if d90 is not None else None,
            "evidence_age_s": age_s,
            "updated_at": up_at.isoformat() if up_at else None,
        })

    return {
        "vclass": vclass,
        "horizon_min": h,
        "count": len(items),
        "segments": items,
    }
