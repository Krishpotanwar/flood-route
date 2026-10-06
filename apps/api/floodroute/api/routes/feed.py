"""Closure feed endpoints: GeoJSON and OASIS CAP 1.2 XML feeds."""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Query, Response

from floodroute.api.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/feed", tags=["feed"])

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"



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
        features.append(
            {
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
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.get("/cap.xml")
def get_closures_cap_xml(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    vclass: str = Query("car", description="Vehicle class: two_wheeler, car, ambulance, heavy"),
    horizon_min: int = Query(0, description="Horizon in minutes: 0, 30, 60, 120"),
) -> Response:
    """OASIS CAP 1.2 XML feed of currently impassable and risky road closures."""
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
    rows = cur.fetchall()

    now = datetime.now(UTC)
    expires = now + timedelta(hours=2)
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    expires_str = expires.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    alert_id = f"urn:floodroute:closure:{int(now.timestamp())}:{len(rows)}"

    root = ET.Element("alert", xmlns=CAP_NS)
    ET.SubElement(root, "identifier").text = alert_id
    ET.SubElement(root, "sender").text = "ops@floodroute.in"
    ET.SubElement(root, "sent").text = now_str
    ET.SubElement(root, "status").text = "Actual"
    ET.SubElement(root, "msgType").text = "Alert"
    ET.SubElement(root, "scope").text = "Public"

    if rows:
        info = ET.SubElement(root, "info")
        ET.SubElement(info, "language").text = "en-IN"
        ET.SubElement(info, "category").text = "Safety"
        ET.SubElement(info, "event").text = "Flash Flood Road Closures"
        ET.SubElement(info, "urgency").text = "Immediate"

        has_impassable = any(r[2] == "impassable" for r in rows)
        severity = "Extreme" if has_impassable else "Severe"
        ET.SubElement(info, "severity").text = severity
        ET.SubElement(info, "certainty").text = "Observed"

        event_code = ET.SubElement(info, "eventCode")
        ET.SubElement(event_code, "valueName").text = "SAME"
        ET.SubElement(event_code, "value").text = "FLW"

        ET.SubElement(info, "expires").text = expires_str
        ET.SubElement(info, "senderName").text = "FloodRoute Flood Risk Monitor"
        ET.SubElement(info, "headline").text = f"Road Inundation Closures for {vclass.replace('_', ' ').title()}"
        ET.SubElement(info, "description").text = (
            f"Active flood closures on {len(rows)} road segment(s). "
            f"Water levels exceed vehicle clearance thresholds."
        )
        ET.SubElement(info, "instruction").text = (
            "Avoid submerged roads and underpasses. "
            "Use alternate detour navigation before travelling."
        )
        ET.SubElement(info, "web").text = "https://floodroute.in"

        param_vclass = ET.SubElement(info, "parameter")
        ET.SubElement(param_vclass, "valueName").text = "vehicleClass"
        ET.SubElement(param_vclass, "value").text = vclass

        param_hz = ET.SubElement(info, "parameter")
        ET.SubElement(param_hz, "valueName").text = "horizonMin"
        ET.SubElement(param_hz, "value").text = str(horizon_min)

        for sid, rclass, state, p, _conf, d50, _d90, _up_at, geom_str in rows:
            area = ET.SubElement(info, "area")
            desc = f"Segment {sid} ({rclass}) - State: {state.upper()}"
            if d50 is not None:
                desc += f" (Est depth: {d50:.0f}cm)"
            ET.SubElement(area, "areaDesc").text = desc

            try:
                geom = json.loads(geom_str)
                coords = geom.get("coordinates", [])
                if geom.get("type") == "LineString" and coords:
                    mid_idx = len(coords) // 2
                    lon, lat = coords[mid_idx][0], coords[mid_idx][1]
                    ET.SubElement(area, "circle").text = f"{lat:.6f},{lon:.6f} 0.15"
                elif geom.get("type") == "Point" and coords:
                    lon, lat = coords[0], coords[1]
                    ET.SubElement(area, "circle").text = f"{lat:.6f},{lon:.6f} 0.15"
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                logger.debug("Failed parsing geometry for segment %s into CAP circle", sid)


            p_sid = ET.SubElement(area, "parameter")
            ET.SubElement(p_sid, "valueName").text = "segmentId"
            ET.SubElement(p_sid, "value").text = str(sid)

            p_state = ET.SubElement(area, "parameter")
            ET.SubElement(p_state, "valueName").text = "state"
            ET.SubElement(p_state, "value").text = state

            if p is not None:
                p_val = ET.SubElement(area, "parameter")
                ET.SubElement(p_val, "valueName").text = "pUnusable"
                ET.SubElement(p_val, "value").text = f"{p:.4f}"

            if d50 is not None:
                p_d50 = ET.SubElement(area, "parameter")
                ET.SubElement(p_d50, "valueName").text = "depthP50Cm"
                ET.SubElement(p_d50, "value").text = f"{d50:.1f}"

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Response(content=xml_bytes, media_type="application/xml")
