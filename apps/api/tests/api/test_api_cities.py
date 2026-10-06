"""Tests for multi-city municipal catalog and hotspot API endpoints."""

from __future__ import annotations


def test_list_cities(client):
    r = client.get("/v1/cities")
    assert r.status_code == 200
    cities = r.json()
    assert len(cities) >= 4
    names = {c["name"] for c in cities}
    assert {"bengaluru", "chennai", "mumbai", "gurugram"}.issubset(names)

    # Check Mumbai and Gurugram payloads
    by_name = {c["name"]: c for c in cities}
    assert by_name["mumbai"]["state"] == "Maharashtra"
    assert by_name["mumbai"]["hydrology_type"] == "tidal_coastal"
    assert by_name["mumbai"]["city_id"] == 3

    assert by_name["gurugram"]["state"] == "Haryana"
    assert by_name["gurugram"]["hydrology_type"] == "arid_ridge_catchment"
    assert by_name["gurugram"]["city_id"] == 4


def test_get_city_details(client):
    r_mum = client.get("/v1/cities/mumbai")
    assert r_mum.status_code == 200
    data = r_mum.json()
    assert data["name"] == "mumbai"
    assert data["display_name"] == "Mumbai"
    assert len(data["bbox"]) == 4

    r_gur = client.get("/v1/cities/gurugram")
    assert r_gur.status_code == 200
    data_gur = r_gur.json()
    assert data_gur["name"] == "gurugram"
    assert data_gur["display_name"] == "Gurugram"

    r_404 = client.get("/v1/cities/atlantis")
    assert r_404.status_code == 404
    assert "not supported" in r_404.json()["detail"]


def test_get_city_hotspots(client):
    r = client.get("/v1/cities/mumbai/hotspots?limit=10&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["city"] == "mumbai"
    assert data["city_id"] == 3
    assert data["total_hotspots"] == 20
    assert len(data["hotspots"]) == 10

    # Test paging offset
    r2 = client.get("/v1/cities/mumbai/hotspots?limit=10&offset=10")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["hotspots"]) == 10
    assert data2["hotspots"][0]["hotspot_id"] != data["hotspots"][0]["hotspot_id"]

    r_404 = client.get("/v1/cities/unknown/hotspots")
    assert r_404.status_code == 404


def test_seed_city_endpoint(client, app_db):
    r = client.post("/v1/cities/gurugram/seed")
    assert r.status_code == 201
    data = r.json()
    assert data["city"] == "gurugram"
    assert data["seeded"] is True
    assert data["city_id"] == 4
    assert data["hotspots_count"] == 20
    assert data["inserted_segments"] == 20
    assert data["inserted_static"] == 20

    # Ensure records exist in database
    cur = app_db.execute("select count(*) from segment where city_id = 4 and assessed = true")
    assert cur.fetchone()[0] == 20

    r_404 = client.post("/v1/cities/valhalla/seed")
    assert r_404.status_code == 404
