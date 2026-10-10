"""Multi-city municipal onboarding and configuration registry."""

from __future__ import annotations

import csv
import json
import re
import warnings
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "city_id": self.city_id,
            "display_name": self.display_name,
            "state": self.state,
            "bbox": list(self.bbox),
            "center": list(self.center),
            "hydrology_type": self.hydrology_type,
            "rainfall_trigger_mm_h": self.rainfall_trigger_mm_h,
            "primary_drainage": self.primary_drainage,
            "hotspot_count": self.hotspot_count,
        }


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
        hotspot_count=711,  # logical CSV rows; 20 lack coords (loadable 691)
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


# Structure words in hotspot prose. Word-boundary regexes so "rub" does not
# fire inside unrelated words; aligned with match.py HINTS (which maps the
# bridge family to {low_bridge, culvert}: the loader emits low_bridge).
STRUCT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"under\s?pass|under\s?bridge|subway|\brub\b"), "underpass"),
    (re.compile(r"\bbridge\b|\bflyover\b"), "low_bridge"),
    (re.compile(r"\bculvert\b|\bvents?\b|\bnala\b|\bdrain\b|\btunnel\b"), "culvert"),
    (re.compile(r"\bdip\b|\blow\b"), "dip"),
]


def infer_structure(raw_text: str) -> str:
    """Map hotspot prose to one loader structure label (default dip)."""
    raw = (raw_text or "").lower()
    for rx, struct in STRUCT_PATTERNS:
        if rx.search(raw):
            return struct
    return "dip"


def load_city_hotspots(
    city_name: str, data_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Load curated municipal hotspot records from CSV.

    Only review-passed points (geocode_confidence high/medium,
    needs_review false) with coordinates inside the city box are kept.
    Low/none-confidence rows never become segments.
    """
    norm = city_name.strip().lower()
    meta = get_city_metadata(norm)
    folder = data_dir or find_data_dir()
    csv_path = folder / f"{norm}.csv"
    if not csv_path.exists():
        warnings.warn(f"hotspot CSV not found: {csv_path}; no hotspots loaded", stacklevel=2)
        return []

    rows: list[dict[str, Any]] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            try:
                lat = float(r["lat"]) if r.get("lat") else None
                lon = float(r["lon"]) if r.get("lon") else None
            except (TypeError, ValueError):
                continue
            if lat is None or lon is None:
                continue

            conf = (r.get("geocode_confidence") or "").strip().lower() or "low"
            if conf not in ("high", "medium"):
                continue
            if (r.get("needs_review") or "").strip().lower() != "false":
                continue

            west, south, east, north = meta.bbox
            if not (west <= lon <= east and south <= lat <= north):
                continue

            struct = infer_structure(r.get("raw_text", ""))

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
                    "confidence": conf,
                }
            )
    if not rows:
        warnings.warn(f"no loadable hotspots for {norm} in {csv_path}", stacklevel=2)
    return rows


def seed_city_hotspots_into_db(
    conn: psycopg.Connection, city_name: str, data_dir: Path | None = None
) -> dict[str, int]:
    """Seed municipal zone and synthetic road segments for city hotspots into PostGIS."""
    norm = city_name.strip().lower()
    meta = get_city_metadata(norm)
    folder = data_dir or find_data_dir()
    if not (folder / f"{norm}.csv").exists():
        raise FileNotFoundError(f"hotspot CSV not found: {folder / f'{norm}.csv'}")
    hotspots = load_city_hotspots(norm, data_dir=folder)
    active_ids: list[int] = []
    with conn.transaction():
        zone_id = ensure_city_zone(conn, norm)
        # Retire the old positional IDs without deleting their audit/evidence.
        # Both ID schemes must match so a real OSM way in this numeric range
        # cannot be mistaken for one of our former synthetic segments.
        legacy_base = 9000000 + meta.city_id * 10000
        legacy_ids = [
            sid
            for sid, osm_id in conn.execute(
                "select segment_id, osm_way_id from segment where city_id = %s"
                " and osm_way_id >= %s and osm_way_id < %s",
                (meta.city_id, legacy_base, legacy_base + 10000),
            ).fetchall()
            if sid == candidate_id_to_segment_id(f"{norm}-spot-{osm_id - legacy_base + 1}")
        ]
        if legacy_ids:
            conn.execute(
                "update segment set assessed = false where segment_id = any(%s)", (legacy_ids,)
            )

        for spot in hotspots:
            lat, lon = spot["lat"], spot["lon"]
            # Location and provenance identify this synthetic point, not the
            # current CSV/filter ordering. Negative OSM IDs mark our own rows.
            key = json.dumps([norm, spot["source_url"], spot["name"], lat, lon])
            seg_id = candidate_id_to_segment_id(f"hotspot:{key}")
            active_ids.append(seg_id)
            p1, p2 = (lon - 0.0004, lat - 0.0002), (lon + 0.0004, lat + 0.0002)
            geom_wkt = f"SRID=4326;LINESTRING({p1[0]} {p1[1]}, {p2[0]} {p2[1]})"
            struct = spot["structure"]
            road_class = "primary" if struct == "underpass" else "secondary"
            conn.execute(
                """
                insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
                values (%s, %s, ST_GeomFromEWKT(%s), %s, %s, true)
                on conflict (segment_id) do update set
                  geom = excluded.geom,
                  road_class = excluded.road_class,
                  assessed = true
                """,
                (seg_id, -seg_id, geom_wkt, road_class, meta.city_id),
            )
            conn.execute(
                """
                insert into segment_static (segment_id, structure, hotspot_count, base_logit, drain_dist_m, zone_id)
                values (%s, %s, 1, %s, NULL, %s)
                on conflict (segment_id) do update set
                  structure = excluded.structure,
                  hotspot_count = excluded.hotspot_count,
                  base_logit = excluded.base_logit,
                  drain_dist_m = NULL,
                  zone_id = excluded.zone_id
                """,
                (seg_id, struct, DEFAULT_STRUCTURE_LOGITS.get(struct, -4.0), zone_id),
            )
        conn.execute(
            "update segment set assessed = false where city_id = %s"
            " and osm_way_id = -segment_id and osm_way_id < 0"
            " and not (segment_id = any(%s))",
            (meta.city_id, active_ids),
        )

    return {
        "city_id": meta.city_id,
        "zone_id": zone_id,
        "hotspots_count": len(hotspots),
        "inserted_segments": len(active_ids),
        "inserted_static": len(active_ids),
    }
