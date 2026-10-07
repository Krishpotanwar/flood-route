"""Underpass, culvert and low-bridge candidates from an OSM PBF (needs pyosmium).

    python -m floodroute.inventory.osm_extract PBF OUT_DIR CITY [CITY ...]

Writes OUT_DIR/<city>_candidates.geojson and <city>_candidates.csv. One pass over the PBF serves
every requested city. Candidates are a superset: they flag where a road meets water or goes below
grade, not whether it floods. Output is derived from OSM, so ODbL attribution and share-alike apply.
"""

import csv
import json
import math
import sys
from itertools import pairwise
from pathlib import Path

import osmium

from floodroute.inventory import CITIES

MOTOR = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "service",
    "living_street",
    "road",
    "track",
} | {f"{k}_link" for k in ("motorway", "trunk", "primary", "secondary", "tertiary")}
WATER = {"river", "stream", "canal", "drain", "ditch"}
TUNNEL = {"yes", "culvert", "building_passage"}
KEEP = (
    "name",
    "ref",
    "highway",
    "tunnel",
    "bridge",
    "layer",
    "maxheight",
    "flood_prone",
    "oneway",
    "surface",
    "lanes",
    "waterway",
    "ford",
    "covered",
)
CELL = 200.0  # grid cell for the waterway index, metres


def layer(tags):
    """First integer of a layer tag ('-1', '-1;0'), else 0."""
    try:
        return int(str(tags.get("layer", "0")).replace(",", ";").split(";")[0].strip())
    except ValueError:
        return 0


def has(tags, key):
    return tags.get(key, "no") not in ("no", "")


def structure(tags, culvert_cross=False):
    """Structure guess for one candidate. Order matters: below grade beats bridge beats crossing."""
    if tags.get("tunnel") == "culvert":
        return "culvert"
    if tags.get("tunnel") == "yes" or layer(tags) < 0:
        return "underpass"
    if tags.get("tunnel") == "building_passage":
        return "none"
    if has(tags, "bridge"):
        return "low_bridge"
    if culvert_cross:
        return "culvert"
    return "dip"  # at-grade water crossing or flood_prone stretch; building_passage maps to none


class Proj:
    """Equirectangular metres around a city centre. Good to well under 1% over 50 km."""

    def __init__(self, lat0):
        self.kx = 111320.0 * math.cos(math.radians(lat0))
        self.ky = 110540.0

    def xy(self, lon, lat):
        return lon * self.kx, lat * self.ky


def seg_hit(p1, p2, p3, p4):
    """Intersection point of segments p1p2 and p3p4 (projected), or None. Touching counts."""
    d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
    if abs(d) < 1e-9:
        return None
    t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
    u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d
    if 0 <= t <= 1 and 0 <= u <= 1:
        return p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])
    return None


def length_m(pts):
    return sum(math.dist(a, b) for a, b in pairwise(pts))


def read_pbf(pbf, cities):
    """One pass. Returns {city: {"hw": [...], "ww": [...], "rail": [...]}} of in-bbox ways."""
    out = {c: {"hw": [], "ww": [], "rail": []} for c in cities}
    fp = (
        osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY)
        .with_locations()
        .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
        .with_filter(osmium.filter.KeyFilter("highway", "waterway", "railway", "flood_prone"))
    )
    for w in fp:
        if len(w.nodes) < 2:
            continue
        try:
            pts = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            continue  # edge of the extract
        for c in cities:
            west, south, east, north = CITIES[c]
            if any(west <= lon <= east and south <= lat <= north for lon, lat in pts):
                break
        else:
            continue
        t = {k: w.tags[k] for k in KEEP if k in w.tags}
        hw, ww, rl = t.get("highway"), t.get("waterway"), w.tags.get("railway")
        if hw is not None and hw not in MOTOR and t.get("flood_prone") != "yes":
            continue  # footways, steps, cycleways: not vehicle passability
        # ponytail: the three kinds are exclusive; a way tagged highway and waterway counts as highway
        # railway=rail only: Namma Metro viaducts are railway=subway, roads pass under them at grade
        if (
            hw is None
            and t.get("flood_prone") != "yes"
            and ww not in WATER
            and not (rl == "rail" and has(w.tags, "bridge"))
        ):
            continue
        rec = {"id": w.id, "tags": t, "pts": pts}
        if hw is not None or (t.get("flood_prone") == "yes" and ww not in WATER):
            out[c]["hw"].append(rec)
        elif ww in WATER:
            out[c]["ww"].append(rec)
        else:
            rec["tags"] = {"railway": rl, "bridge": w.tags.get("bridge", "")}
            out[c]["rail"].append(rec)
    return out


class SegIndex:
    """Grid index over projected segments of a way list."""

    def __init__(self, ways, proj):
        self.proj, self.cells = proj, {}
        for wy in ways:
            xy = [proj.xy(*p) for p in wy["pts"]]
            for a, b in pairwise(xy):
                for key in self._keys(a, b):
                    self.cells.setdefault(key, []).append((a, b, wy))

    @staticmethod
    def _keys(a, b):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for i in range(int(x0 // CELL), int(x1 // CELL) + 1):
            for j in range(int(y0 // CELL), int(y1 // CELL) + 1):
                yield i, j

    def hits(self, a, b):
        seen = set()
        for key in self._keys(a, b):
            for c, d, wy in self.cells.get(key, ()):
                if (id(c), id(d)) in seen:
                    continue
                seen.add((id(c), id(d)))
                p = seg_hit(a, b, c, d)
                if p:
                    yield p, wy


def clip(a, b, p, half=60.0):
    """Sub-segment of ab within `half` metres of p (whole segment when it is short)."""
    n = math.dist(a, b)
    if n <= 2 * half:
        return a, b
    ux, uy = (b[0] - a[0]) / n, (b[1] - a[1]) / n
    return (p[0] - ux * half, p[1] - uy * half), (p[0] + ux * half, p[1] + uy * half)


def candidates(data, proj):
    """Yield feature dicts (without geometry projection back; coordinates are lon/lat)."""
    ww_idx = SegIndex(data["ww"], proj)
    rail_idx = SegIndex(data["rail"], proj)
    for hw in data["hw"]:
        t = hw["tags"]
        h = t.get("highway")
        motor = h in MOTOR
        reasons = []
        if motor and t.get("tunnel") in TUNNEL:
            reasons.append(f"tunnel={t['tunnel']}")
        if motor and layer(t) < 0:
            reasons.append("layer<0")
        if t.get("flood_prone") == "yes":
            reasons.append("flood_prone=yes")
        xy = [proj.xy(*p) for p in hw["pts"]]
        bridged, tunneled = has(t, "bridge"), has(t, "tunnel") or layer(t) < 0
        crossings = []  # (point, kind, other way)
        if motor:
            for a, b in pairwise(xy):
                for p, ww in ww_idx.hits(a, b):
                    crossings.append((a, b, p, "water", ww))
                if not bridged and not tunneled:
                    for p, rl in rail_idx.hits(a, b):
                        crossings.append((a, b, p, "rail", rl))
        if bridged and any(k == "water" for *_, k, _ in crossings):
            reasons.append("bridge_over_water")
        props = {
            "osm_way_id": hw["id"],
            "name": t.get("name", ""),
            "highway": h or "",
            "tags": t,
            "length_m": round(length_m(xy)),
        }
        if reasons:
            yield {
                **props,
                "candidate_id": str(hw["id"]),
                "reasons": reasons,
                "structure": structure(t),
                "pts": hw["pts"],
            }
        if bridged or tunneled:
            continue  # their water crossings are the structure itself
        done = set()
        for a, b, p, kind, other in crossings:
            if (kind, other["id"]) in done:
                continue  # one candidate per way pair, not per vertex
            done.add((kind, other["id"]))
            sa, sb = clip(a, b, p)
            ot = other["tags"]
            culvert = kind == "water" and ot.get("tunnel") == "culvert"
            yield {
                **props,
                "candidate_id": f"{hw['id']}-x{len(done)}",
                "reasons": ["under_rail_bridge" if kind == "rail" else "waterway_crossing"],
                "structure": "underpass" if kind == "rail" else structure(t, culvert),
                "crossing": (ot.get("waterway") or "railway")
                + (":" + ot["name"] if "name" in ot else "")
                + f"#{other['id']}",
                "pts": [(sa[0] / proj.kx, sa[1] / proj.ky), (sb[0] / proj.kx, sb[1] / proj.ky)],
            }


def write(city, feats, out_dir, meta):
    out = Path(out_dir)
    gj = {
        "type": "FeatureCollection",
        "name": f"{city}_candidates",
        "attribution": "Contains data (c) OpenStreetMap contributors, ODbL 1.0, openstreetmap.org/copyright",
        "extract": meta,
        "features": [
            {
                "type": "Feature",
                "id": f["candidate_id"],
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(x, 6), round(y, 6)] for x, y in f["pts"]],
                },
                "properties": {
                    k: f[k]
                    for k in (
                        "candidate_id",
                        "osm_way_id",
                        "name",
                        "highway",
                        "structure",
                        "reasons",
                        "length_m",
                        "tags",
                        "crossing",
                    )
                    if k in f
                },
            }
            for f in feats
        ],
    }
    (out / f"{city}_candidates.geojson").write_text(json.dumps(gj, separators=(",", ":")) + "\n")
    cols = [
        "candidate_id",
        "osm_way_id",
        "name",
        "highway",
        "structure",
        "reasons",
        "length_m",
        "lat",
        "lon",
        "tunnel",
        "bridge",
        "layer",
        "flood_prone",
        "crossing",
    ]
    with open(out / f"{city}_candidates.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(cols)
        for f in feats:
            xs = [p[0] for p in f["pts"]]
            ys = [p[1] for p in f["pts"]]
            mid = (sum(xs) / len(xs), sum(ys) / len(ys))  # vertex mean: exact centre of 2-pt clips
            t = f["tags"]
            wr.writerow(
                [
                    f["candidate_id"],
                    f["osm_way_id"],
                    f["name"],
                    f["highway"],
                    f["structure"],
                    ";".join(f["reasons"]),
                    f["length_m"],
                    round(mid[1], 6),
                    round(mid[0], 6),
                    t.get("tunnel", ""),
                    t.get("bridge", ""),
                    t.get("layer", ""),
                    t.get("flood_prone", ""),
                    f.get("crossing", ""),
                ]
            )


def main(pbf, out_dir, cities):
    hdr = osmium.io.Reader(pbf, osmium.osm.osm_entity_bits.NOTHING)
    meta = {
        "pbf": Path(pbf).name,
        "pbf_timestamp": hdr.header().get("osmosis_replication_timestamp"),
        "source": "https://download.bbbike.org/osm/pbf/region/asia/india/southern-zone.osm.pbf",
    }
    hdr.close()
    data = read_pbf(pbf, cities)
    for c in cities:
        _, south, _, north = CITIES[c]
        proj = Proj((south + north) / 2)
        feats = list(candidates(data[c], proj))
        write(c, feats, out_dir, {**meta, "bbox_w_s_e_n": CITIES[c]})
        by = {}
        for f in feats:
            for r in f["reasons"]:
                by[r.split("=")[0]] = by.get(r.split("=")[0], 0) + 1
        print(
            c,
            {
                "highways": len(data[c]["hw"]),
                "waterways": len(data[c]["ww"]),
                "rail_bridges": len(data[c]["rail"]),
                "candidates": len(feats),
                "by_reason": by,
            },
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
