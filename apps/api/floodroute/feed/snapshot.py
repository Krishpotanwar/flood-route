"""Offline and CDN resilience snapshot generator for road closures and risk layers (TRD 11).

The snapshot unions human overrides with model-assessed closures, and every
file carries its own provenance: per-feature `source` + `as_of`, plus a
top-level `sources` map (feed health) and a `stale` flag. Unknown or old
inputs read as stale, never as fresh.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from floodroute.inventory import CITIES, CITY_IDS
from floodroute.score.db import SUPPORTED_VCLASSES

# A feed older than this makes any snapshot built on it stale.
SACHET_STALE_S = 600.0  # 2x the 5-min worker cadence
METNO_STALE_S = 7200.0  # 2x the hourly cadence
SNAPSHOT_STALE_S = 300.0  # matches list_snapshot_status / serving budget
MAX_FUTURE_SKEW_S = 300.0


def get_snapshot_dir() -> Path:
    """Resolve destination directory for static CDN and offline snapshots.

    `FLOODROUTE_SNAPSHOT_DIR` wins when set (absolute path); otherwise the
    first existing candidate is used, always returned as an absolute path so
    the worker and the API cannot disagree by cwd.
    """
    env = os.environ.get("FLOODROUTE_SNAPSHOT_DIR", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    candidates = [
        Path("data/snapshots"),
        Path("../data/snapshots"),
        Path("../../data/snapshots"),
        Path(__file__).resolve().parents[4] / "data" / "snapshots",
    ]
    for c in candidates:
        if c.parent.exists():
            c.mkdir(parents=True, exist_ok=True)
            return c.resolve()
    p = Path("data/snapshots")
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def generate_city_closure_snapshot(
    conn: psycopg.Connection,
    city_name: str = "bengaluru",
    vclass: str = "car",
    snapshot_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate and persist an offline CDN GeoJSON snapshot for a city and vehicle profile.

    Features union active human `close` overrides with model-assessed
    `impassable`/`risky` segments at horizon 0; overrides win on conflict.
    Raises KeyError on an unknown city instead of serving another city's
    geometry under the wrong name.
    """
    norm = city_name.strip().lower()
    if norm not in CITY_IDS:
        raise KeyError(f"Unknown city {city_name!r}. Supported: {sorted(CITY_IDS)}")
    if vclass not in SUPPORTED_VCLASSES:
        raise ValueError(
            f"Unknown vclass {vclass!r}. Supported: {sorted(SUPPORTED_VCLASSES)}"
        )
    city_id = CITY_IDS[norm]
    bbox = CITIES[norm]
    now = datetime.now(UTC)

    # Active human overrides (starts_at is the newest evidence time the row carries).
    override_sql = """
    select s.segment_id, s.osm_way_id, s.road_class, ST_AsGeoJSON(s.geom),
           'impassable' as state, 1.0 as p_unusable, coalesce(ss.structure, 'none') as structure,
           o.starts_at
    from override o
    join segment s on o.segment_id = s.segment_id
    left join segment_static ss on s.segment_id = ss.segment_id
    where o.action = 'close'
      and o.starts_at <= %s
      and o.expires_at > %s
      and s.city_id = %s
    """
    override_rows = conn.execute(override_sql, (now, now, city_id)).fetchall()

    # Model-assessed closures at the current horizon: without these the file
    # would publish model-flagged water as open whenever the backend is down.
    model_sql = """
    select s.segment_id, s.osm_way_id, s.road_class, ST_AsGeoJSON(s.geom),
           sr.state, sr.p_unusable, coalesce(ss.structure, 'none') as structure, sr.updated_at
    from segment_risk sr
    join segment s on sr.segment_id = s.segment_id
    left join segment_static ss on s.segment_id = ss.segment_id
    where sr.vclass = %s and sr.horizon_min = 0
      and sr.state in ('impassable', 'risky')
      and s.city_id = %s
      and s.assessed = true
    """
    model_rows = conn.execute(model_sql, (vclass, city_id)).fetchall()

    by_segment: dict[Any, dict[str, Any]] = {}
    model_stale = False
    evidence_times: list[datetime] = []
    for r in model_rows:
        seg_id, osm_id, rclass, geom_json, state, p_u, struct, updated = r
        geom = json.loads(geom_json) if isinstance(geom_json, str) else geom_json
        if updated is None:
            model_stale = True
        else:
            age_s = (now - updated).total_seconds()
            model_stale |= not -MAX_FUTURE_SKEW_S <= age_s <= SNAPSHOT_STALE_S
            evidence_times.append(updated)
        by_segment[seg_id] = {
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "segment_id": seg_id,
                "osm_way_id": osm_id,
                "road_class": rclass,
                "state": state,
                "p_unusable": float(p_u) if p_u is not None else 0.0,
                "structure": struct,
                "source": "model",
                "as_of": updated.isoformat() if updated is not None else None,
            },
        }
    for r in override_rows:
        seg_id, osm_id, rclass, geom_json, state, p_u, struct, starts_at = r
        geom = json.loads(geom_json) if isinstance(geom_json, str) else geom_json
        by_segment[seg_id] = {
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "segment_id": seg_id,
                "osm_way_id": osm_id,
                "road_class": rclass,
                "state": state,
                "p_unusable": float(p_u) if p_u is not None else 0.0,
                "structure": struct,
                "source": "override",
                "as_of": starts_at.isoformat() if starts_at is not None else None,
            },
        }
        if starts_at is not None:
            evidence_times.append(starts_at)
    features = list(by_segment.values())

    # Provenance: feed health plus the newest model evidence behind this file.
    sources: dict[str, Any] = {}
    try:
        for name, last_ok, last_error, lag_s in conn.execute(
            "select source, last_ok, last_error, lag_s from source_health"
        ).fetchall():
            age_s = (now - last_ok).total_seconds() if last_ok is not None else None
            sources[name] = {
                "last_ok": last_ok.isoformat() if last_ok is not None else None,
                "last_error": last_error,
                "lag_s": lag_s,
                "age_s": age_s,
            }
    except psycopg.Error:
        sources = {}
    # The oldest retained condition bounds freshness: one newer row cannot
    # make an old closure fresh. A refresh timestamp is not a source-data age.
    evidence_as_of = min(evidence_times, default=now)
    conditions_as_of = evidence_as_of.isoformat()
    stale = model_stale or (now - evidence_as_of).total_seconds() > SNAPSHOT_STALE_S
    if not stale:
        limits = {"sachet": SACHET_STALE_S, "metno": METNO_STALE_S}
        for name, limit in limits.items():
            source = sources.get(name, {})
            age, lag = source.get("age_s"), source.get("lag_s")
            if (
                age is None or lag is None
                or age < -MAX_FUTURE_SKEW_S or age > limit or lag < 0
                or age + lag > limit or source.get("last_error")
            ):
                stale = True
                break

    now_iso = now.isoformat()
    snapshot_data: dict[str, Any] = {
        "type": "FeatureCollection",
        "snapshot_version": "v1.0",
        "city": norm,
        "city_id": city_id,
        "vclass": vclass,
        "bbox": list(bbox),
        "generated_at": now_iso,
        "conditions_as_of": conditions_as_of,
        "stale": stale,
        "sources": sources,
        "feature_count": len(features),
        "features": features,
    }

    # Canonical serialisation for both the digest and the file, so the ETag is
    # stable for identical content (the served JSONResponse re-serialises
    # anyway; the ETag identifies content, not wire bytes). generated_at is
    # excluded: it moves on every regen while the closures do not.
    def canonical(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    content = {k: v for k, v in snapshot_data.items() if k != "generated_at"}
    digest = hashlib.sha256(canonical(content)).hexdigest()
    snapshot_data["etag"] = f'"{digest[:16]}"'
    payload = canonical(snapshot_data)

    target_dir = snapshot_dir or get_snapshot_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    # Sweep orphaned tmp files from crashed writers (older than 1 h only, so a
    # concurrent writer's file is never touched).
    for old in target_dir.glob("closures_*.tmp.*"):
        try:
            if now.timestamp() - old.stat().st_mtime > 3600:
                old.unlink()
        except OSError:
            pass
    out_file = target_dir / f"closures_{norm}_{vclass}.json"
    temp_file = target_dir / f"closures_{norm}_{vclass}.tmp.{os.getpid()}.{now.timestamp()}"
    with open(temp_file, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def list_snapshot_status(snapshot_dir: Path | None = None) -> list[dict[str, Any]]:
    """Inspect status, age and freshness of all cached snapshot artifacts."""
    target_dir = snapshot_dir or get_snapshot_dir()
    results: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    if not target_dir.exists():
        return []

    for p in target_dir.glob("closures_*.json"):
        # Extract city and vclass from filename: closures_{city}_{vclass}.json
        parts = p.stem.split("_", 2)
        city = parts[1] if len(parts) >= 2 else "unknown"
        vclass = parts[2] if len(parts) >= 3 else "unknown"
        try:
            stat = p.stat()
        except OSError:
            continue  # A concurrent cleanup may remove the file.
        snapshot = load_city_closure_snapshot(city, vclass, target_dir)
        if not isinstance(snapshot, dict):
            snapshot = {}
        generated_at = None
        age_seconds = None
        try:
            generated = datetime.fromisoformat(snapshot["generated_at"])
            age_seconds = (now - generated).total_seconds()
            generated_at = generated.isoformat()
        except (KeyError, ValueError, TypeError):
            pass  # Missing, malformed or naive timestamps are unknown, hence stale.
        is_stale = (
            snapshot.get("stale") is not False
            or age_seconds is None
            or not -MAX_FUTURE_SKEW_S <= age_seconds <= SNAPSHOT_STALE_S
            or city not in CITIES or vclass not in SUPPORTED_VCLASSES
            or snapshot.get("city") != city or snapshot.get("vclass") != vclass
        )

        results.append(
            {
                "filename": p.name,
                "city": city,
                "vclass": vclass,
                "size_bytes": stat.st_size,
                "generated_at": generated_at,
                "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
                "is_stale": is_stale,
            }
        )

    results.sort(key=lambda x: x["filename"])
    return results
