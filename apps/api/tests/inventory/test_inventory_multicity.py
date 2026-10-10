"""Tests for multi-city municipal onboarding and configuration registry."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from floodroute.inventory.multicity import (
    CITY_REGISTRY,
    get_city_metadata,
    infer_structure,
    list_supported_cities,
    load_city_hotspots,
    seed_city_hotspots_into_db,
)
from floodroute.inventory.seed import candidate_id_to_segment_id


def test_list_supported_cities():
    cities = list_supported_cities()
    names = {c.name for c in cities}
    assert {"bengaluru", "chennai", "mumbai", "gurugram"}.issubset(names)

    # Validate city IDs
    id_map = {c.name: c.city_id for c in cities}
    assert id_map["bengaluru"] == 1
    assert id_map["chennai"] == 2
    assert id_map["mumbai"] == 3
    assert id_map["gurugram"] == 4


def test_get_city_metadata():
    mum = get_city_metadata("mumbai")
    assert mum.name == "mumbai"
    assert mum.display_name == "Mumbai"
    assert mum.state == "Maharashtra"
    assert mum.hydrology_type == "tidal_coastal"
    assert mum.rainfall_trigger_mm_h == 35.0

    gur = get_city_metadata("gurugram")
    assert gur.name == "gurugram"
    assert gur.display_name == "Gurugram"
    assert gur.state == "Haryana"
    assert gur.hydrology_type == "arid_ridge_catchment"

    with pytest.raises(KeyError):
        get_city_metadata("non_existent_city")


def test_load_mumbai_and_gurugram_hotspots():
    mum_spots = load_city_hotspots("mumbai")
    assert len(mum_spots) == 20
    mum_box = CITY_REGISTRY["mumbai"].bbox

    for spot in mum_spots:
        assert spot["city"] == "mumbai"
        assert spot["city_id"] == 3
        assert mum_box[0] <= spot["lon"] <= mum_box[2]
        assert mum_box[1] <= spot["lat"] <= mum_box[3]
        assert spot["structure"] in {"underpass", "culvert", "dip", "low_bridge"}

    gur_spots = load_city_hotspots("gurugram")
    assert len(gur_spots) == 20
    gur_box = CITY_REGISTRY["gurugram"].bbox

    for spot in gur_spots:
        assert spot["city"] == "gurugram"
        assert spot["city_id"] == 4
        assert gur_box[0] <= spot["lon"] <= gur_box[2]
        assert gur_box[1] <= spot["lat"] <= gur_box[3]
        assert spot["structure"] in {"underpass", "culvert", "dip", "low_bridge"}


def test_load_chennai_hotspots():
    che_spots = load_city_hotspots("chennai")
    assert len(che_spots) == 20
    assert CITY_REGISTRY["chennai"].hotspot_count == len(che_spots)
    che_box = CITY_REGISTRY["chennai"].bbox

    for spot in che_spots:
        assert spot["city"] == "chennai"
        assert spot["city_id"] == 2
        assert che_box[0] <= spot["lon"] <= che_box[2]
        assert che_box[1] <= spot["lat"] <= che_box[3]
        assert spot["structure"] in {"underpass", "culvert", "dip", "low_bridge"}


def test_bengaluru_registry_count_matches_csv_rows():
    assert CITY_REGISTRY["bengaluru"].hotspot_count == 711


def test_load_bengaluru_keeps_only_review_passed_points():
    spots = load_city_hotspots("bengaluru")
    assert len(spots) == 619  # 711 rows minus 72 low minus 20 none
    box = CITY_REGISTRY["bengaluru"].bbox
    for spot in spots:
        assert spot["confidence"] in ("high", "medium")
        assert box[0] <= spot["lon"] <= box[2]
        assert box[1] <= spot["lat"] <= box[3]
        assert spot["structure"] in {"underpass", "culvert", "dip", "low_bridge"}


def test_infer_structure_word_boundaries_and_low_bridge():
    assert infer_structure("Windsor Manor Underbridge") == "underpass"
    assert infer_structure("Kengeri RUB subway") == "underpass"
    assert infer_structure("Old Madras Road low bridge") == "low_bridge"
    assert infer_structure("Bellandur Nala inlet") == "culvert"
    assert infer_structure("Silk Board dip") == "dip"
    # "rub" inside an unrelated word must not fire
    assert infer_structure("Rubbish Lane pooling") == "dip"


def test_load_city_hotspots_applies_confidence_and_box_gates(tmp_path: Path):
    csv_path = tmp_path / "bengaluru.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            ["name", "lat", "lon", "raw_text", "geocode_confidence", "needs_review"],
        )
        w.writeheader()
        w.writerow(
            {
                "name": "Good Underpass",
                "lat": "12.97",
                "lon": "77.60",
                "raw_text": "railway underpass",
                "geocode_confidence": "high",
                "needs_review": "false",
            }
        )
        w.writerow(
            {
                "name": "Low Point",
                "lat": "12.97",
                "lon": "77.60",
                "raw_text": "dip",
                "geocode_confidence": "low",
                "needs_review": "true",
            }
        )
        w.writerow(
            {
                "name": "Outside Box",
                "lat": "14.00",
                "lon": "78.00",
                "raw_text": "dip",
                "geocode_confidence": "high",
                "needs_review": "false",
            }
        )
        w.writerow(
            {
                "name": "No Coords",
                "lat": "",
                "lon": "",
                "raw_text": "dip",
                "geocode_confidence": "high",
                "needs_review": "false",
            }
        )
    spots = load_city_hotspots("bengaluru", data_dir=tmp_path)
    assert [(s["name"], s["structure"]) for s in spots] == [("Good Underpass", "underpass")]


def test_seed_city_hotspots_into_db(db):
    stats = seed_city_hotspots_into_db(db, "mumbai")
    assert stats["city_id"] == 3
    assert stats["hotspots_count"] == 20
    assert stats["inserted_segments"] == 20
    assert stats["inserted_static"] == 20

    # Verify zone was created
    cur = db.execute("select count(*) from zone where city_id = 3")
    assert cur.fetchone()[0] == 1

    # Verify segments created
    cur = db.execute("select count(*) from segment where city_id = 3 and assessed = true")
    assert cur.fetchone()[0] == 20

    # Verify segment_static records
    cur = db.execute(
        """
        select count(*) from segment_static ss
        join segment s on ss.segment_id = s.segment_id
        where s.city_id = 3
        """
    )
    assert cur.fetchone()[0] == 20


def test_reseeding_synthetic_hotspots_preserves_identity_and_retires_rejected_rows(db, tmp_path):
    path = tmp_path / "bengaluru.csv"
    fields = ["name", "lat", "lon", "raw_text", "source_url", "geocode_confidence", "needs_review"]
    points = [
        dict(zip(fields, ["Point A", "12.97", "77.60", "underpass", "https://example.org/a", "high", "false"], strict=True)),
        dict(zip(fields, ["Point B", "12.98", "77.61", "dip", "https://example.org/b", "medium", "false"], strict=True)),
    ]

    def write_rows(rows):
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    write_rows(points)
    seed_city_hotspots_into_db(db, "bengaluru", data_dir=tmp_path)
    before = db.execute(
        "select segment_id, ST_AsText(geom) from segment where assessed order by segment_id"
    ).fetchall()
    write_rows(list(reversed(points)))
    seed_city_hotspots_into_db(db, "bengaluru", data_dir=tmp_path)
    assert db.execute(
        "select segment_id, ST_AsText(geom) from segment where assessed order by segment_id"
    ).fetchall() == before

    # The old positional scheme may already have assessed the rejected point.
    legacy_id = candidate_id_to_segment_id("bengaluru-spot-1")
    db.execute(
        "insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)"
        " values (%s, 9010000, 'SRID=4326;LINESTRING(77.59 12.96,77.60 12.97)', 'primary', 1, true),"
        " (42, 99, 'SRID=4326;LINESTRING(77.59 12.96,77.60 12.97)', 'primary', 1, true)",
        (legacy_id,),
    )
    points[0].update(geocode_confidence="low", needs_review="true")
    write_rows(points)
    seed_city_hotspots_into_db(db, "bengaluru", data_dir=tmp_path)
    active = db.execute("select segment_id from segment where assessed").fetchall()
    assert len(active) == 2  # Point B plus the real OSM segment.
    assert (42,) in active and (legacy_id,) not in active
    assert db.execute("select count(*) from segment where not assessed").fetchone()[0] == 2
    path.unlink()
    with pytest.raises(FileNotFoundError):
        seed_city_hotspots_into_db(db, "bengaluru", data_dir=tmp_path)
    assert db.execute("select count(*) from segment where assessed").fetchone()[0] == 2
