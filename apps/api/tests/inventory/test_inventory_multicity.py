"""Tests for multi-city municipal onboarding and configuration registry."""

from __future__ import annotations

import pytest

from floodroute.inventory.multicity import (
    CITY_REGISTRY,
    get_city_metadata,
    list_supported_cities,
    load_city_hotspots,
    seed_city_hotspots_into_db,
)


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
