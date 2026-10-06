"""Small runnable checks for the S5 inventory logic, on hand-made toy data (no network, no PBF)."""

import csv

import pytest

from floodroute.inventory import CITIES
from floodroute.inventory.geocode import Geocoder, confidence, simplify
from floodroute.inventory.hotspots import build, validate
from floodroute.inventory.match import dist_m, match, prepare, tokens

BLR = CITIES["bengaluru"]


def cand(cid, name, pts, structure="underpass"):
    return {
        "candidate_id": cid,
        "osm_way_id": int(cid.split("-")[0]),
        "name": name,
        "structure": structure,
        "pts": pts,
    }


def test_tokens_merge_initials_and_spelling():
    assert tokens("K.R. Circle underpass") == tokens("KR Circle") == {"kr"}
    assert tokens("Mehkri Circle") == tokens("Mekhri Circle Underpass") == {"mekhri"}
    assert tokens("Rayapuram near Govt Maternity Hospital, Ward 137") == {
        "rayapuram",
        "govt",
        "maternity",
        "hospital",
    }


def test_dist_m_point_to_segment():
    seg = [(77.5900, 12.9700), (77.5910, 12.9700)]
    assert dist_m(12.9709, 77.5905, seg) == pytest.approx(
        0.0009 * 110540, rel=0.01
    )  # beside the middle
    assert dist_m(12.9700, 77.5920, seg) == pytest.approx(
        0.0010 * 111320 * 0.9744, rel=0.01
    )  # past the end


def test_match_name_distance_and_failure_modes():
    kr = cand("1", "K R Circle Underpass", [(77.5864, 12.9761), (77.5866, 12.9761)])
    anon = cand("2", "", [(77.6000, 12.9500), (77.6002, 12.9500)])
    anand = cand("3", "Anand Rao Circle Underpass", [(77.5800, 12.9800), (77.5802, 12.9800)])
    passage = cand(
        "4", "Hebbal Passage", [(77.5900, 13.0500), (77.5902, 13.0500)], structure="none"
    )
    cands, common = prepare([kr, anon, anand, passage])
    assert len(cands) == 3  # building passages are never matched

    def run(name, lat, lon, conf):
        return match(
            {"name": name, "lat": lat, "lon": lon, "geocode_confidence": conf}, cands, common
        )

    # name and distance agree: clean match
    m = run("KR Circle underpass", 12.9763, 77.5865, "high")
    assert (m["match_type"], m["osm_way_id"], m["needs_review"]) == ("name+distance", 1, False)
    # no name, unnamed candidate 55 m away: distance only if the point is trusted enough, and always reviewed
    m = run("Some Layout", 12.9505, 77.6001, "medium")
    assert (m["match_type"], m["osm_way_id"], m["needs_review"]) == ("distance", 2, True)
    assert (
        run("Some Layout", 12.9505, 77.6001, "high")["match_type"] == "none"
    )  # high allows 50 m only
    assert (
        run("Some Layout", 12.9505, 77.6001, "low")["match_type"] == "none"
    )  # low never earns distance
    # name matches but the point is 553 m away: name only, reviewed; 1.1 km away: too far to trust
    far = run("Anand Rao Circle", 12.9850, 77.5800, "high")
    assert (far["match_type"], far["osm_way_id"], far["dist_m"], far["needs_review"]) == (
        "name",
        3,
        553,
        True,
    )
    assert run("Anand Rao Circle", 12.9900, 77.5800, "high")["match_type"] == "none"
    nocoord = run("Anand Rao Circle", "", "", "none")
    assert (nocoord["match_type"], nocoord["osm_way_id"], nocoord["dist_m"]) == ("name", 3, None)
    # nothing near, nothing named alike
    assert run("Hebbal", 13.05, 77.60, "high")["match_type"] == "none"


def test_match_name_only_respects_the_structure_named():
    bridge = cand(
        "5", "Kodigehalli Road Bridge", [(77.59, 13.06), (77.5902, 13.06)], structure="low_bridge"
    )
    under = cand("6", "Kodigehalli Underpass", [(77.60, 13.07), (77.6002, 13.07)])
    cands, common = prepare([bridge, under])
    h = {
        "name": "Kodigehalli railway underpass",
        "lat": "",
        "lon": "",
        "geocode_confidence": "none",
    }
    assert (
        match(h, cands, common)["osm_way_id"] == 6
    )  # says underpass: the bridge on the same-named road is ignored
    assert match({**h, "name": "Kodigehalli bridge"}, cands, common)["osm_way_id"] == 5
    assert (
        match(
            {**h, "name": "Kodigehalli railway underpass"},
            [c for c in cands if c["osm_way_id"] == 5],
            common,
        )["match_type"]
        == "none"
    )
    road = cand(
        "7", "Kodigehalli Main Road", [(77.59, 13.06), (77.5902, 13.06)], structure="low_bridge"
    )
    only_road, common = prepare([road])  # shares the locality name but does not name a structure
    assert match({**h, "name": "Kodigehalli"}, only_road, common)["match_type"] == "none"


def test_match_ignores_names_common_to_many_candidates():
    ring = [
        cand(
            f"{i}",
            "Outer Ring Road Underpass",
            [(77.60 + i * 1e-3, 12.95), (77.6005 + i * 1e-3, 12.95)],
        )
        for i in range(31)
    ]
    cands, common = prepare(ring)
    assert {"outer", "ring"} <= common
    far = {
        "name": "Outer Ring Road and Gangamma Gudi Circle underpass",
        "lat": "",
        "lon": "",
        "geocode_confidence": "none",
    }
    assert (
        match(far, cands, common)["match_type"] == "none"
    )  # only 'outer ring' overlaps, which names every ring-road way


def res(name, rank, bbox, lat=12.97, lon=77.59):
    return {"name": name, "place_rank": rank, "boundingbox": bbox, "lat": str(lat), "lon": str(lon)}


def test_geocode_confidence_levels():
    tiny = ["12.9160", "12.9161", "77.6239", "77.6240"]
    area = ["12.9200", "12.9500", "77.6100", "77.6400"]  # about 4.5 km diagonal
    city = ["12.60", "13.30", "77.20", "78.00"]
    assert confidence([res("Silk Board Junction", 30, tiny)], "Silk Board Junction", BLR) == (
        "high",
        "",
    )
    assert (
        confidence([res("Koramangala", 20, tiny)], "Koramangala", BLR)[0] == "medium"
    )  # below street level
    assert (
        confidence([res("Koramangala", 20, area)], "Koramangala", BLR)[0] == "low"
    )  # too wide to be a spot
    assert (
        confidence([res("Bengaluru", 16, city)], "Hebbal", BLR)[0] == "low"
    )  # fell back to the city
    assert (
        confidence([res("Hebbal", 30, tiny, lat=28.6, lon=77.2)], "Hebbal", BLR)[0] == "none"
    )  # outside box
    assert confidence([], "Hebbal", BLR)[0] == "none"
    # two Kuvempu Circles 11 km apart: the first hit may be the wrong one, so never better than low
    pair = [res("Kuvempu Circle", 30, tiny, lat=13.03), res("Kuvempu Circle", 30, tiny, lat=12.93)]
    assert confidence(pair, "Kuvempu Circle", BLR) == ("low", "ambiguous_namesakes")
    assert (
        confidence(
            pair[:1] + [res("Kuvempu Circle", 30, tiny, lat=13.0301)], "Kuvempu Circle", BLR
        )[0]
        == "high"
    )


def test_simplify_drops_structure_words_once():
    assert simplify("Anand Rao Circle Underpass, Bengaluru") == "Anand Rao Circle, Bengaluru"
    assert simplify("Kodigehalli Railway Underpass, Bengaluru") == "Kodigehalli, Bengaluru"
    assert simplify("Queens Circle, Bengaluru") is None  # nothing to drop
    assert simplify("Underpass, Bengaluru") is None  # would leave nothing


def test_geocoder_caches_and_waits(tmp_path):
    calls, naps, now = [], [], [0.0]

    def fetch(url):
        calls.append(url)
        return [res("X", 30, ["12.9", "12.9", "77.5", "77.5"])]

    def sleep(s):
        naps.append(s)
        now[0] += s

    g = Geocoder(tmp_path, BLR, fetch=fetch, sleep=sleep, clock=lambda: now[0])
    g.search("a, Bengaluru")
    g.search("b, Bengaluru")  # second real request must wait out the minimum gap
    g.search("a, Bengaluru")  # cached: no request, no wait
    assert len(calls) == 2 and g.requests == 2 and len(naps) == 1 and naps[0] >= 1.0
    assert "bounded=1" in calls[0] and "countrycodes=in" in calls[0]
    # a fresh instance reads the same disk cache: zero requests
    g2 = Geocoder(
        tmp_path, BLR, fetch=lambda u: pytest.fail("cached"), sleep=sleep, clock=lambda: now[0]
    )
    assert g2.search("b, Bengaluru")[0]["name"] == "X"


class FakeGeo:
    """Answers only the queries in `known`; everything else is a miss."""

    def __init__(self, known):
        self.known, self.asked = known, []

    def search(self, q):
        self.asked.append(q)
        return self.known.get(q, [])


def seed(name, url, lat="", lon="", kind="swd_vulnerable_severe", query="", extent="point"):
    return {
        "name": name,
        "ward_or_area": "",
        "source_name": "s",
        "source_url": url,
        "source_date": "2020-05-18",
        "list_kind": kind,
        "raw_text": name,
        "src_lat": lat,
        "src_lon": lon,
        "geocode_query": query,
        "extent": extent,
    }


def test_hotspot_build_cross_checks_and_falls_back():
    rows = [
        seed("Madiwala Lake Outlet", "https://a", "12.9200", "77.6200"),
        seed("Madiwala lake outlet", "https://b", "12.9201", "77.6201"),  # agrees: both high
        seed("Hoodi Signal", "https://a", "12.9920", "77.7180"),
        seed("Hoodi Signal", "https://b", "12.9700", "77.7180"),  # 2.2 km apart: both low
        seed("Lavakusha Nagar", "https://a", "13.2543", "77.5173"),  # outside the city box: typo
        seed("Silk Board", "https://a"),  # no coordinates: asks Nominatim
        seed("Whitefield", "https://a", query="Whitefield, Bengaluru", extent="area"),
        seed(
            "Kodigehalli railway underpass",
            "https://a",
            query="Kodigehalli Railway Underpass, Bengaluru",
        ),
    ]
    tiny = ["12.9", "12.9", "77.7", "77.7"]
    geo = FakeGeo(
        {
            "Whitefield, Bengaluru": [res("Whitefield", 30, tiny, lat=12.97, lon=77.75)],
            "Kodigehalli, Bengaluru": [res("Kodigehalli", 30, tiny, lat=13.06, lon=77.59)],
        }
    )
    out, stats = build(rows, "bengaluru", geo)
    got = [(o["geocode_confidence"], o["needs_review"]) for o in out]
    assert got[:2] == [("high", "false")] * 2
    assert got[2:4] == [("low", "true")] * 2 and "conflicts" in out[2]["geocode_method"]
    assert (out[4]["lat"], out[4]["geocode_confidence"]) == ("", "none") and "rejected" in out[4][
        "geocode_method"
    ]
    assert geo.asked == [
        "Lavakusha Nagar, Bengaluru",
        "Silk Board, Bengaluru",
        "Whitefield, Bengaluru",
        "Kodigehalli Railway Underpass, Bengaluru",
        "Kodigehalli, Bengaluru",
    ]
    assert (
        out[7]["geocode_confidence"] == "high"
        and "retry_q='Kodigehalli, Bengaluru'" in out[7]["geocode_method"]
    )
    assert stats[("retry", "hit")] == 1
    assert out[5]["geocode_confidence"] == "none" and out[5]["needs_review"] == "true"
    assert out[6]["geocode_confidence"] == "low"  # an area centroid is not a segment: capped at low


def test_hotspot_seed_needs_provenance(tmp_path):
    bad = seed("No source", "")
    with pytest.raises(ValueError, match="line 2"):
        validate([bad])
    validate([seed("Fine", "https://example.org/list.pdf")])


def test_osm_candidates_toy_network():
    pytest.importorskip("osmium")
    from floodroute.inventory.osm_extract import Proj, candidates, layer, structure

    assert (layer({"layer": "-1;0"}), layer({"layer": "x"}), layer({})) == (-1, 0, 0)
    assert (
        structure({"tunnel": "building_passage"}) == "none"
        and structure({"layer": "-1"}) == "underpass"
    )

    def way(i, tags, *pts):
        return {"id": i, "tags": tags, "pts": list(pts)}

    def cross(i, tags):
        return way(i, tags, (77.5900, 12.9700), (77.5910, 12.9700))

    stream = way(900, {"waterway": "stream"}, (77.5905, 12.9695), (77.5905, 12.9705))
    rail = way(901, {"railway": "rail", "bridge": "yes"}, (77.5905, 12.9695), (77.5905, 12.9705))
    data = {
        "ww": [stream],
        "rail": [rail],
        "hw": [
            cross(1, {"highway": "residential"}),  # at-grade crossing of the stream
            cross(
                2, {"highway": "primary", "bridge": "yes", "layer": "1"}
            ),  # bridge over the stream
            cross(3, {"highway": "secondary", "tunnel": "yes", "layer": "-1"}),
            cross(4, {"highway": "residential", "tunnel": "building_passage"}),
            cross(5, {"highway": "footway", "tunnel": "yes"}),  # not a vehicle road
            way(
                6, {"highway": "residential", "flood_prone": "yes"}, (77.60, 12.98), (77.601, 12.98)
            ),
            way(7, {"highway": "residential"}, (77.61, 12.99), (77.611, 12.99)),  # nothing here
        ],
    }
    # the rail bridge sits on the same line as the stream, so way 1 also passes under it
    got = {}
    for f in candidates(data, Proj(12.97)):
        got.setdefault(f["osm_way_id"], []).append((f["structure"], tuple(f["reasons"])))
    assert ("dip", ("waterway_crossing",)) in got[1] and (
        "underpass",
        ("under_rail_bridge",),
    ) in got[1]
    assert got[2] == [("low_bridge", ("bridge_over_water",))]
    assert got[3] == [("underpass", ("tunnel=yes", "layer<0"))]
    assert got[4] == [("none", ("tunnel=building_passage",))]
    assert got[6] == [("dip", ("flood_prone=yes",))]
    assert 5 not in got and 7 not in got


def test_seed_csv_if_present_has_provenance():
    """The committed Bengaluru seed must pass the same provenance gate the pipeline applies."""
    from pathlib import Path

    p = Path(__file__).resolve().parents[4] / "data" / "hotspots" / "bengaluru_seed.csv"
    if not p.exists():
        pytest.skip("seed not present")
    with open(p, newline="", encoding="utf-8") as fh:
        validate(list(csv.DictReader(fh)))
