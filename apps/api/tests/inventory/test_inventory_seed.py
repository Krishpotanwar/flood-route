"""Tests for inventory seeding pipeline into PostGIS."""

from __future__ import annotations

import json
from pathlib import Path

from floodroute.inventory.seed import (
    candidate_id_to_segment_id,
    ensure_city_zone,
    load_hotspot_counts,
    seed_inventory,
)


def test_candidate_id_to_segment_id():
    # Determinism
    id1 = candidate_id_to_segment_id("8680571-x1")
    id2 = candidate_id_to_segment_id("8680571-x1")
    assert id1 == id2
    assert isinstance(id1, int)

    # Positive 63-bit range
    assert 0 < id1 < 2**63

    # Distinct IDs for distinct candidates
    id3 = candidate_id_to_segment_id("8680571-x2")
    id4 = candidate_id_to_segment_id("15802887")
    assert id1 != id3
    assert id1 != id4
    assert id3 != id4


def test_load_hotspot_counts(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist.csv"
    assert load_hotspot_counts(non_existent) == {}

    csv_file = tmp_path / "test_matched.csv"
    csv_file.write_text(
        "hotspot_row,name,list_kind,lat,lon,geocode_confidence,match_type,candidate_id,osm_way_id\n"
        "1,Spot A,swd,13.0,77.6,high,name+distance,cand-1,1001\n"
        "2,Spot B,swd,13.0,77.6,medium,distance,cand-1,1001\n"
        "3,Spot C,swd,13.0,77.6,high,name,cand-2,1002\n"
        "4,Spot D,swd,13.0,77.6,low,none,,1003\n"
    )

    counts = load_hotspot_counts(csv_file)
    assert counts == {"cand-1": 2, "cand-2": 1}


def test_ensure_city_zone(db):
    zid = ensure_city_zone(db, "bengaluru", zone_id=10)
    assert zid == 10

    cur = db.execute("select city_id, ST_GeometryType(geom) from zone where zone_id = 10")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] == "ST_MultiPolygon"

    # Idempotent
    zid_repeat = ensure_city_zone(db, "bengaluru", zone_id=10)
    assert zid_repeat == 10


def test_seed_inventory_synthetic(db, tmp_path: Path):
    geojson_path = tmp_path / "test_candidates.geojson"
    matched_path = tmp_path / "test_matched.csv"

    features = [
        {
            "type": "Feature",
            "id": "cand-underpass",
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.58, 12.97], [77.581, 12.971]],
            },
            "properties": {
                "candidate_id": "cand-underpass",
                "osm_way_id": 111,
                "name": "Underpass Way",
                "highway": "primary",
                "structure": "underpass",
                "reasons": ["tunnel=yes"],
            },
        },
        {
            "type": "Feature",
            "id": "cand-culvert",
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.60, 12.95], [77.601, 12.951]],
            },
            "properties": {
                "candidate_id": "cand-culvert",
                "osm_way_id": 222,
                "name": "Culvert Way",
                "highway": "secondary",
                "structure": "culvert",
                "reasons": ["waterway_crossing"],
            },
        },
        {
            "type": "Feature",
            "id": "cand-dip",
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.62, 12.93], [77.621, 12.931]],
            },
            "properties": {
                "candidate_id": "cand-dip",
                "osm_way_id": 333,
                "name": "Dip Way",
                "highway": "residential",
                "structure": "dip",
                "reasons": ["flood_prone=yes"],
            },
        },
    ]

    gj = {"type": "FeatureCollection", "features": features}
    geojson_path.write_text(json.dumps(gj))

    matched_path.write_text(
        "hotspot_row,name,list_kind,lat,lon,geocode_confidence,match_type,candidate_id,osm_way_id\n"
        "1,Spot 1,swd,12.97,77.58,high,name+distance,cand-underpass,111\n"
        "2,Spot 2,swd,12.97,77.58,high,name+distance,cand-underpass,111\n"
    )

    stats = seed_inventory(
        conn=db,
        city="bengaluru",
        candidates_path=geojson_path,
        matched_path=matched_path,
        zone_id=1,
    )

    assert stats.total_candidates == 3
    assert stats.inserted_segments == 3
    assert stats.inserted_static == 3
    assert stats.matched_hotspots == 2
    assert stats.by_structure == {"underpass": 1, "culvert": 1, "dip": 1}

    # Verify segment table
    cur = db.execute(
        "select segment_id, osm_way_id, road_class, assessed, ST_AsText(geom) from segment order by osm_way_id"
    )
    rows = cur.fetchall()
    assert len(rows) == 3
    assert rows[0][1] == 111
    assert rows[0][2] == "primary"
    assert rows[0][3] is True  # assessed is True

    # Verify segment_static table
    cur = db.execute(
        "select s.osm_way_id, ss.structure, ss.hotspot_count, ss.base_logit, ss.drain_dist_m "
        "from segment_static ss join segment s on ss.segment_id = s.segment_id "
        "order by s.osm_way_id"
    )
    s_rows = cur.fetchall()
    assert len(s_rows) == 3

    # underpass
    assert s_rows[0][0] == 111
    assert s_rows[0][1] == "underpass"
    assert s_rows[0][2] == 2  # 2 matched hotspots
    assert s_rows[0][3] == -3.5

    # culvert
    assert s_rows[1][0] == 222
    assert s_rows[1][1] == "culvert"
    assert s_rows[1][2] == 0
    assert s_rows[1][3] == -4.0
    assert s_rows[1][4] == 0.0  # waterway_crossing drain_dist_m == 0

    # dip
    assert s_rows[2][0] == 333
    assert s_rows[2][1] == "dip"
    assert s_rows[2][2] == 0
    assert s_rows[2][3] == -4.2

    # Idempotent re-run
    stats2 = seed_inventory(
        conn=db,
        city="bengaluru",
        candidates_path=geojson_path,
        matched_path=matched_path,
        zone_id=1,
    )
    assert stats2.inserted_segments == 3
    cur = db.execute("select count(*) from segment")
    assert cur.fetchone()[0] == 3


def test_seed_inventory_bengaluru_sample(db):
    stats = seed_inventory(
        conn=db,
        city="bengaluru",
        limit=20,
    )
    assert stats.total_candidates == 20
    assert stats.inserted_segments == 20
    assert stats.inserted_static == 20

    # Ensure all segments are within Bengaluru geographic area
    cur = db.execute(
        "select count(*) from segment where ST_Within(geom, ST_MakeEnvelope(77.4, 12.8, 77.85, 13.2, 4326))"
    )
    assert cur.fetchone()[0] == 20
