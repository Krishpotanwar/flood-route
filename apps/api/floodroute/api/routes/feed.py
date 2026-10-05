"""Closure feed endpoint: GET /v1/feed/closures.geojson."""

from __future__ import annotations

import json
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Query

from floodroute.api.deps import get_db

router = APIRouter(prefix="/v1/feed", tags=["feed"])


@router.get("/closures.geojson")
def get_closures_geojson(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    vclass: str = Query("car", description="Vehicle class: two_wheeler, car, ambulance, heavy"),
    horizon_min: int = Query(0, description="Horizon in minutes: 0, 30, 60, 120"),
) -> dict[str, Any]:
    """GeoJSON feed of currently impassable and risky road segments."""
    sql = """
    select s.segment_id, s.road_class, sr.state, sr.p_unusable, sr.confidence,
           sr.depth_p50_cm, sr.depth_p90_cm, sr.updated_at, ST_AsGeoJSON(s.geom)
    from segment_risk sr
    join segment s on sr.segment_id = s.segment_id
    where sr.vclass = %s
      and sr.horizon_min = %s
      and sr.state in ('impassable', 'risky')
    order by s.segment_id
    """
    cur = db.execute(sql, (vclass, horizon_min))
    features = []
    for sid, rclass, state, p, conf, d50, d90, up_at, geom_str in cur.fetchall():
        features.append({
            "type": "Feature",
            "geometry": json.loads(geom_str),
            "properties": {
                "segment_id": sid,
                "road_class": rclass,
                "vclass": vclass,
                "horizon_min": horizon_min,
                "state": state,
                "p_unusable": float(p) if p is not None else None,
                "confidence": conf,
                "depth_p50_cm": float(d50) if d50 is not None else None,
                "depth_p90_cm": float(d90) if d90 is not None else None,
                "updated_at": up_at.isoformat() if up_at else None,
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }
