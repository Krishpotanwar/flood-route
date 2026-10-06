"""Offline and CDN resilience snapshot generator for road closures and risk layers (TRD 11)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from floodroute.inventory import CITIES, CITY_IDS


def get_snapshot_dir() -> Path:
    """Resolve destination directory for static CDN and offline snapshots."""
    candidates = [
        Path("data/snapshots"),
        Path("../data/snapshots"),
        Path("../../data/snapshots"),
        Path(__file__).resolve().parents[4] / "data" / "snapshots",
    ]
    for c in candidates:
        if c.parent.exists():
            c.mkdir(parents=True, exist_ok=True)
            return c
    p = Path("data/snapshots")
    p.mkdir(parents=True, exist_ok=True)
    return p


def generate_city_closure_snapshot(
    conn: psycopg.Connection,
    city_name: str = "bengaluru",
    vclass: str = "car",
    snapshot_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate and persist an offline CDN GeoJSON snapshot for a city and vehicle profile."""
    norm = city_name.strip().lower()
    city_id = CITY_IDS.get(norm, 1)
    bbox = CITIES.get(norm, (77.40, 12.80, 77.85, 13.20))
    now = datetime.now(UTC)

    # Query active human overrides and impassable segments
    sql = """
    select s.segment_id, s.osm_way_id, s.road_class, ST_AsGeoJSON(s.geom),
           'impassable' as state, 1.0 as p_unusable, coalesce(ss.structure, 'none') as structure
    from override o
    join segment s on o.segment_id = s.segment_id
    left join segment_static ss on s.segment_id = ss.segment_id
    where o.action = 'close'
      and o.expires_at > %s
      and s.city_id = %s
    """
    rows = conn.execute(sql, (now, city_id)).fetchall()

    features = []
    for r in rows:
        seg_id, osm_id, rclass, geom_json, state, p_u, struct = r
        geom = json.loads(geom_json) if isinstance(geom_json, str) else geom_json
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "segment_id": seg_id,
                    "osm_way_id": osm_id,
                    "road_class": rclass,
                    "state": state,
                    "p_unusable": float(p_u) if p_u is not None else 0.0,
                    "structure": struct,
                },
            }
        )

    now_iso = now.isoformat()
    snapshot_data: dict[str, Any] = {
        "type": "FeatureCollection",
        "snapshot_version": "v1.0",
        "city": norm,
        "city_id": city_id,
        "vclass": vclass,
        "bbox": list(bbox),
        "generated_at": now_iso,
        "conditions_as_of": now_iso,
        "feature_count": len(features),
        "features": features,
    }

    serialized = json.dumps(snapshot_data, indent=2)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    snapshot_data["etag"] = f'"{digest[:16]}"'

    target_dir = snapshot_dir or get_snapshot_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_dir / f"closures_{norm}_{vclass}.json"
    temp_file = target_dir / f"closures_{norm}_{vclass}.tmp.{now.timestamp()}"

    temp_file.write_text(json.dumps(snapshot_data), encoding="utf-8")
    temp_file.replace(out_file)

    return snapshot_data


def load_city_closure_snapshot(
    city_name: str = "bengaluru",
    vclass: str = "car",
    snapshot_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Read cached pre-generated snapshot file from disk."""
    norm = city_name.strip().lower()
    target_dir = snapshot_dir or get_snapshot_dir()
    path = target_dir / f"closures_{norm}_{vclass}.json"
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        return json.loads(content)
    except (OSError, json.JSONDecodeError):
        return None


def list_snapshot_status(snapshot_dir: Path | None = None) -> list[dict[str, Any]]:
    """Inspect status, age and freshness of all cached snapshot artifacts."""
    target_dir = snapshot_dir or get_snapshot_dir()
    results: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    if not target_dir.exists():
        return []

    for p in target_dir.glob("closures_*.json"):
        stat = p.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        age_seconds = (now - mtime).total_seconds()
        is_stale = age_seconds > 300.0  # Older than 5 minutes

        # Extract city and vclass from filename: closures_{city}_{vclass}.json
        parts = p.stem.split("_")
        city = parts[1] if len(parts) >= 2 else "unknown"
        vclass = parts[2] if len(parts) >= 3 else "car"

        results.append(
            {
                "filename": p.name,
                "city": city,
                "vclass": vclass,
                "size_bytes": stat.st_size,
                "generated_at": mtime.isoformat(),
                "age_seconds": round(age_seconds, 1),
                "is_stale": is_stale,
            }
        )

    results.sort(key=lambda x: x["filename"])
    return results
