"""Seed pipeline for flood-vulnerable road segment inventory and hotspots into PostGIS.

Loads candidate segments (from osm_extract GeoJSON) and matched hotspots
into `segment` and `segment_static` tables.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from floodroute.inventory import CITIES, get_city_id

logger = logging.getLogger(__name__)


DEFAULT_STRUCTURE_LOGITS: dict[str, float] = {
    "underpass": -3.5,
    "low_bridge": -3.8,
    "culvert": -4.0,
    "dip": -4.2,
    "none": -5.0,
}

VALID_STRUCTURES = frozenset({"underpass", "low_bridge", "culvert", "dip", "none"})


def candidate_id_to_segment_id(candidate_id: str) -> int:
    """Deterministically map candidate_id (e.g. '15802887' or '8680571-x1') to positive 63-bit int."""
    digest = hashlib.sha256(candidate_id.encode("utf-8")).digest()
    return (int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF) or 1


@dataclass(frozen=True)
class SeedStats:
    """Summary of an inventory seeding run."""

    city: str
    city_id: int
    total_candidates: int
    inserted_segments: int
    inserted_static: int
    matched_hotspots: int
    by_structure: dict[str, int]


def load_hotspot_counts(matched_path: Path | str) -> dict[str, int]:
    """Count matches per candidate_id from a matched CSV file."""
    counts: Counter[str] = Counter()
    p = Path(matched_path)
    if not p.exists():
        logger.warning("matched hotspots file not found: %s; seeding hotspot_count=0", p)
        return {}
    with p.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = (row.get("candidate_id") or "").strip()
            mtype = (row.get("match_type") or "").strip()
            if cid and mtype != "none":
                counts[cid] += 1
    return dict(counts)


def ensure_city_zone(
    conn: psycopg.Connection,
    city: str,
    zone_id: int | None = None,
) -> int:
    """Ensure a base zone exists for the given city. Returns zone_id."""
    city_norm = city.lower().strip()
    city_id = get_city_id(city_norm)
    zid = zone_id if zone_id is not None else city_id
    west, south, east, north = CITIES[city_norm]
    poly_wkt = f"MULTIPOLYGON((({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south})))"
    conn.execute(
        """
        insert into zone (zone_id, city_id, geom, params)
        values (%s, %s, ST_Multi(ST_GeomFromText(%s, 4326)), '{"r_low": 10.0, "r_high": 30.0}')
        on conflict (zone_id) do nothing
        """,
        (zid, city_id, poly_wkt),
    )
    return zid


def seed_inventory(
    conn: psycopg.Connection,
    city: str = "bengaluru",
    candidates_path: Path | str | None = None,
    matched_path: Path | str | None = None,
    zone_id: int | None = None,
    limit: int | None = None,
    batch_size: int = 500,
    if_empty: bool = False,
) -> SeedStats:
    """Seed candidate segments and matched hotspots into segment and segment_static."""
    city_norm = city.lower().strip()
    city_id = get_city_id(city_norm)

    if if_empty:
        cur = conn.execute(
            "select count(*) from segment where city_id = %s and assessed = true",
            (city_id,),
        )
        existing_row = cur.fetchone()
        existing_count = existing_row[0] if existing_row else 0
        if existing_count > 0:
            logger.info(
                "City %s (city_id=%d) already has %d assessed segments; skipping seeding (if_empty=True).",
                city_norm,
                city_id,
                existing_count,
            )
            return SeedStats(
                city=city_norm,
                city_id=city_id,
                total_candidates=existing_count,
                inserted_segments=0,
                inserted_static=0,
                matched_hotspots=0,
                by_structure={},
            )

    # Resolve paths if not specified
    repo_root = Path(__file__).resolve().parents[4]
    inv_dir = repo_root / "data" / "inventory"

    if candidates_path is None:
        cand_p = inv_dir / f"{city_norm}_candidates.geojson"
        if not cand_p.exists():
            for alt in [
                Path(os.environ.get("FLOODROUTE_INVENTORY_DIR", "")),
                Path("data/inventory"),
                Path("../data/inventory"),
                Path("../../data/inventory"),
                Path("/app/data/inventory"),
            ]:
                if alt and alt.exists() and (alt / f"{city_norm}_candidates.geojson").exists():
                    inv_dir = alt
                    cand_p = inv_dir / f"{city_norm}_candidates.geojson"
                    break
    else:
        cand_p = Path(candidates_path)

    match_p = inv_dir / f"{city_norm}_matched.csv" if matched_path is None else Path(matched_path)

    if not cand_p.exists():
        raise FileNotFoundError(f"Candidates file not found: {cand_p}")

    # Ensure zone exists
    effective_zone_id = ensure_city_zone(conn, city_norm, zone_id=zone_id)

    # Load hotspot match counts
    hotspot_counts = load_hotspot_counts(match_p)
    total_matched = sum(hotspot_counts.values())

    # Read candidates GeoJSON
    with cand_p.open(encoding="utf-8") as f:
        data = json.load(f)
    features = data.get("features", [])
    if limit is not None and limit > 0:
        features = features[:limit]

    total_candidates = len(features)
    by_structure: Counter[str] = Counter()

    segment_rows: list[tuple[Any, ...]] = []
    static_rows: list[tuple[Any, ...]] = []

    for n, feat in enumerate(features):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        cid_raw = props.get("candidate_id") or feat.get("id")
        if cid_raw is None or str(cid_raw).strip() == "":
            raise ValueError(f"candidate feature {n} has no candidate_id")
        cid = str(cid_raw)
        seg_id = candidate_id_to_segment_id(cid)

        try:
            osm_way_id = int(props.get("osm_way_id", 0))
        except (TypeError, ValueError):
            logger.warning("candidate %s has non-numeric osm_way_id %r; using 0", cid, props.get("osm_way_id"))
            osm_way_id = 0
        road_class = props.get("highway") or "unclassified"
        struct = props.get("structure") or "none"
        if struct not in VALID_STRUCTURES:
            struct = "none"

        by_structure[struct] += 1
        hcount = min(32767, hotspot_counts.get(cid, 0))
        base_logit = DEFAULT_STRUCTURE_LOGITS.get(struct, -5.0)

        # Estimate drain_dist_m: 0.0 if waterway_crossing, else None
        reasons = props.get("reasons", [])
        drain_dist_m = 0.0 if "waterway_crossing" in reasons else None

        geom_json = json.dumps(geom)
        segment_rows.append((seg_id, osm_way_id, geom_json, road_class, city_id, True))
        static_rows.append((seg_id, struct, hcount, base_logit, drain_dist_m, effective_zone_id))

    sql_segment = """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s)
        on conflict (segment_id) do update set
          osm_way_id = excluded.osm_way_id,
          geom = excluded.geom,
          road_class = excluded.road_class,
          city_id = excluded.city_id,
          assessed = excluded.assessed
    """

    sql_static = """
        insert into segment_static (segment_id, structure, hotspot_count, base_logit, drain_dist_m, zone_id)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (segment_id) do update set
          structure = excluded.structure,
          hotspot_count = excluded.hotspot_count,
          base_logit = excluded.base_logit,
          drain_dist_m = excluded.drain_dist_m,
          zone_id = excluded.zone_id
    """

    with conn.cursor() as cur:
        try:
            for i in range(0, len(segment_rows), batch_size):
                cur.executemany(sql_segment, segment_rows[i : i + batch_size])
                cur.executemany(sql_static, static_rows[i : i + batch_size])
        except Exception:
            conn.rollback()
            raise

    conn.commit()

    return SeedStats(
        city=city_norm,
        city_id=city_id,
        total_candidates=total_candidates,
        inserted_segments=len(segment_rows),
        inserted_static=len(static_rows),
        matched_hotspots=total_matched,
        by_structure=dict(by_structure),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed candidate segments and hotspots into PostGIS."
    )
    parser.add_argument("--city", default="bengaluru", help="City name (e.g. bengaluru, chennai)")
    parser.add_argument("--candidates", help="Path to candidates GeoJSON file")
    parser.add_argument("--matched", help="Path to matched hotspots CSV file")
    parser.add_argument("--zone-id", type=int, help="Zone ID to associate segments with")
    parser.add_argument("--limit", type=int, help="Max candidates to load")
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="Skip seeding if segments already exist for the city in the database",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL (defaults to DATABASE_URL environment variable)",
    )
    args = parser.parse_args()

    url = (args.db_url or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        url = "postgresql://postgres:postgres@localhost:54329/floodroute"

    with psycopg.connect(url) as conn:
        stats = seed_inventory(
            conn,
            city=args.city,
            candidates_path=args.candidates,
            matched_path=args.matched,
            zone_id=args.zone_id,
            limit=args.limit,
            if_empty=args.if_empty,
        )
        if stats.inserted_segments > 0:
            print(f"Seeded {stats.city} (city_id={stats.city_id}):")
            print(f"  Segments: {stats.inserted_segments}")
            print(f"  Static entries: {stats.inserted_static}")
            print(f"  Matched hotspots: {stats.matched_hotspots}")
            print(f"  By structure: {stats.by_structure}")
        else:
            print(f"City {stats.city} (city_id={stats.city_id}) already has {stats.total_candidates} segments; skipped.")


if __name__ == "__main__":
    main()
