"""Multi-city municipal onboarding and configuration registry."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from floodroute.inventory import CITIES, CITY_IDS
from floodroute.inventory.seed import (
    DEFAULT_STRUCTURE_LOGITS,
    candidate_id_to_segment_id,
    ensure_city_zone,
)


@dataclass(frozen=True)
class CityMetadata:
    name: str
    city_id: int
    display_name: str
    state: str
    bbox: tuple[float, float, float, float]  # west, south, east, north
    center: tuple[float, float]  # lat, lon
    hydrology_type: str
    rainfall_trigger_mm_h: float
    primary_drainage: str
    hotspot_count: int


CITY_REGISTRY: dict[str, CityMetadata] = {
    "bengaluru": CityMetadata(
        name="bengaluru",
        city_id=CITY_IDS["bengaluru"],
        display_name="Bengaluru",
        state="Karnataka",
        bbox=CITIES["bengaluru"],
        center=(12.9716, 77.5946),
        hydrology_type="tank_cascade",
        rainfall_trigger_mm_h=25.0,
        primary_drainage="Koramangala-Challaghatta & Vrishabhavathi Valleys",
        hotspot_count=713,
    ),
    "chennai": CityMetadata(
        name="chennai",
        city_id=CITY_IDS["chennai"],
        display_name="Chennai",
        state="Tamil Nadu",
        bbox=CITIES["chennai"],
        center=(13.0827, 80.2707),
        hydrology_type="coastal_estuarine",
        rainfall_trigger_mm_h=30.0,
        primary_drainage="Cooum, Adyar Rivers & Buckingham Canal",
        hotspot_count=20,
    ),
    "mumbai": CityMetadata(
        name="mumbai",
        city_id=CITY_IDS["mumbai"],
        display_name="Mumbai",
        state="Maharashtra",
        bbox=CITIES["mumbai"],
        center=(19.0760, 72.8777),
        hydrology_type="tidal_coastal",
        rainfall_trigger_mm_h=35.0,
        primary_drainage="Mithi River, Vakola Nala & Arabian Sea",
        hotspot_count=20,
    ),
    "gurugram": CityMetadata(
        name="gurugram",
        city_id=CITY_IDS["gurugram"],
        display_name="Gurugram",
        state="Haryana",
        bbox=CITIES["gurugram"],
        center=(28.4595, 77.0266),
        hydrology_type="arid_ridge_catchment",
        rainfall_trigger_mm_h=20.0,
        primary_drainage="Badshahpur Drain & Najafgarh Basin",
        hotspot_count=20,
    ),
}


def list_supported_cities() -> list[CityMetadata]:
    """Return catalog of all configured municipal deployment regions."""
    return list(CITY_REGISTRY.values())


def get_city_metadata(city_name: str) -> CityMetadata:
    """Retrieve municipal metadata for a given city identifier."""
    norm = city_name.strip().lower()
    if norm not in CITY_REGISTRY:
        raise KeyError(
            f"Unsupported city '{city_name}'. Available: {list(CITY_REGISTRY.keys())}"
        )
    return CITY_REGISTRY[norm]


def find_data_dir() -> Path:
    """Resolve data directory location across project working directories."""
    candidates = [
        Path("data/hotspots"),
        Path("../data/hotspots"),
        Path("../../data/hotspots"),
        Path(__file__).resolve().parents[4] / "data" / "hotspots",
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("data/hotspots")


def load_city_hotspots(
    city_name: str, data_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Load curated municipal hotspot records from CSV."""
    norm = city_name.strip().lower()
    meta = get_city_metadata(norm)
    folder = data_dir or find_data_dir()
    csv_path = folder / f"{norm}.csv"
    if not csv_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            lat = float(r["lat"]) if r.get("lat") else None
            lon = float(r["lon"]) if r.get("lon") else None
            if lat is None or lon is None:
                continue

            # Parse structure from raw_text or note
            raw = r.get("raw_text", "").lower()
            if "underpass" in raw or "subway" in raw or "rub" in raw:
                struct = "underpass"
            elif "culvert" in raw or "bridge" in raw:
                struct = "culvert"
            elif "dip" in raw or "low" in raw:
                struct = "dip"
            else:
                struct = "dip"

            rows.append(
                {
                    "hotspot_id": f"{norm}-{i + 1}",
                    "city": norm,
                    "city_id": meta.city_id,
                    "name": r.get("name", f"Hotspot {i + 1}"),
                    "ward_or_area": r.get("ward_or_area", ""),
                    "lat": lat,
                    "lon": lon,
                    "structure": struct,
                    "source_name": r.get("source_name", ""),
                    "source_url": r.get("source_url", ""),
                    "source_date": r.get("source_date", ""),
                    "list_kind": r.get("list_kind", ""),
                    "confidence": r.get("geocode_confidence", "high"),
                }
            )
    return rows


def seed_city_hotspots_into_db(
    conn: psycopg.Connection, city_name: str, data_dir: Path | None = None
) -> dict[str, int]:
    """Seed municipal zone and synthetic road segments for city hotspots into PostGIS."""
    norm = city_name.strip().lower()
    meta = get_city_metadata(norm)
    zone_id = ensure_city_zone(conn, norm)
    hotspots = load_city_hotspots(norm, data_dir=data_dir)

    inserted_segments = 0
    inserted_static = 0

    for idx, spot in enumerate(hotspots):
        cand_key = f"{norm}-spot-{idx + 1}"
        seg_id = candidate_id_to_segment_id(cand_key)
        lat, lon = spot["lat"], spot["lon"]

        # Synthetic 80m segment oriented along coordinates
        p1 = (lon - 0.0004, lat - 0.0002)
        p2 = (lon + 0.0004, lat + 0.0002)
        geom_wkt = f"SRID=4326;LINESTRING({p1[0]} {p1[1]}, {p2[0]} {p2[1]})"

        road_class = "primary" if spot["structure"] == "underpass" else "secondary"
        struct = spot["structure"]
        base_logit = DEFAULT_STRUCTURE_LOGITS.get(struct, -4.0)

        conn.execute(
            """
            insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
            values (%s, %s, ST_GeomFromEWKT(%s), %s, %s, true)
            on conflict (segment_id) do update set
              road_class = excluded.road_class,
              assessed = true
            """,
            (seg_id, 9000000 + idx + (meta.city_id * 10000), geom_wkt, road_class, meta.city_id),
        )
        inserted_segments += 1

        conn.execute(
            """
            insert into segment_static (segment_id, structure, hotspot_count, base_logit, drain_dist_m, zone_id)
            values (%s, %s, %s, %s, 10.0, %s)
            on conflict (segment_id) do update set
              structure = excluded.structure,
              hotspot_count = excluded.hotspot_count,
              base_logit = excluded.base_logit,
              zone_id = excluded.zone_id
            """,
            (seg_id, struct, 1, base_logit, zone_id),
        )
        inserted_static += 1

    conn.commit()
    return {
        "city_id": meta.city_id,
        "zone_id": zone_id,
        "hotspots_count": len(hotspots),
        "inserted_segments": inserted_segments,
        "inserted_static": inserted_static,
    }
