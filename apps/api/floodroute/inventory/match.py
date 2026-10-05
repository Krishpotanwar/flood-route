"""Match hotspot rows to OSM structure candidates by name and by distance.

Rule, applied per hotspot, first hit wins:
  name+distance  a candidate whose name overlaps the hotspot name (score >= NAME_MIN) lies within
                 NAME_R metres. Best = highest score, then nearest.
  distance       no name hit, but some candidate lies within DIST_R[confidence] metres (high 100 m,
                 medium 200 m). Low or no geocode confidence never gets a distance-only match.
  name           the name overlaps strongly (>= NAME_ONLY) but the candidate is farther than NAME_R,
                 or the hotspot has no coordinates. Always needs review.
  none           nothing qualifies.
Failure modes: see docs/spikes/S5-hotspot-inventory.md.
"""

import math
import re
from itertools import pairwise

NAME_MIN, NAME_ONLY, NAME_R = 0.5, 0.67, 300.0
DIST_R = {"high": 100.0, "medium": 200.0}
GENERIC = {
    "road", "rd", "main", "cross", "junction", "jn", "circle", "cir", "underpass", "underbridge",
    "flyover", "bridge", "railway", "rail", "vehicle", "layout", "near", "the", "of", "in", "at",
    "on", "to", "and", "ward", "no", "opp", "behind", "beside", "back", "side", "area", "front",
    "stretch", "between", "from", "below", "signal", "bengaluru", "bangalore", "chennai",
}
SPELL = {"mehkri": "mekhri", "mekri": "mekhri", "nagara": "nagar", "lyt": "layout", "lout": "layout"}


def tokens(name):
    """Distinctive lower-case tokens of a place name; single letters merge ('K R' -> 'kr')."""
    s = re.sub(r"\bward\.?\s*(?:no\.?)?\s*[-.]?\s*\d+(?:/\d+)?", " ", name.lower())
    s = re.sub("[\u2019'`]", "", s).replace("&", " and ")
    out, run = [], []
    for t in re.findall(r"[a-z0-9]+", s) + [""]:
        if len(t) == 1 and t.isalpha():
            run.append(t)
            continue
        if run:
            out.append("".join(run))
            run = []
        if t:
            out.append(SPELL.get(t, t))
    return {t for t in out if t not in GENERIC}


def overlap(a, b):
    """|A and B| / min(|A|, |B|); 0 when either side has no distinctive tokens."""
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def dist_m(lat, lon, pts):
    """Metres from a point to a polyline of (lon, lat) vertices (local equirectangular)."""
    kx, ky = 111320.0 * math.cos(math.radians(lat)), 110540.0
    p = [((x - lon) * kx, (y - lat) * ky) for x, y in pts]
    if len(p) == 1:
        return math.hypot(*p[0])
    best = math.inf
    for (ax, ay), (bx, by) in pairwise(p):
        dx, dy = bx - ax, by - ay
        n = dx * dx + dy * dy
        t = 0.0 if n == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / n))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def match(h, cands):
    """h: {name, lat, lon, geocode_confidence}; cands: [{candidate_id, osm_way_id, name, structure, pts}].

    ponytail: O(candidates) per hotspot with a bbox prefilter; add a grid index above ~100k candidates.
    """
    ht = tokens(h["name"])
    conf = h.get("geocode_confidence", "none")
    has_xy = h.get("lat") not in (None, "") and h.get("lon") not in (None, "")
    lat, lon = (float(h["lat"]), float(h["lon"])) if has_xy else (0.0, 0.0)
    pad = 0.004  # degrees, about 440 m: covers NAME_R, the largest distance radius
    scored = []
    for c in cands:
        d = None
        if has_xy:
            xs, ys = [p[0] for p in c["pts"]], [p[1] for p in c["pts"]]
            if min(xs) - pad <= lon <= max(xs) + pad and min(ys) - pad <= lat <= max(ys) + pad:
                d = dist_m(lat, lon, c["pts"])
        scored.append((overlap(ht, tokens(c.get("name", ""))), d, c))
    best = None
    near = [(s, d, c) for s, d, c in scored if d is not None]
    hit = [x for x in near if x[0] >= NAME_MIN and x[1] <= NAME_R]
    if hit:
        best, mtype = max(hit, key=lambda x: (x[0], -x[1])), "name+distance"
    elif conf in DIST_R and (cl := [x for x in near if x[1] <= DIST_R[conf]]):
        best, mtype = min(cl, key=lambda x: x[1]), "distance"
    elif (nm := [x for x in scored if x[0] >= NAME_ONLY]):
        best = max(nm, key=lambda x: (x[0], -(x[1] if x[1] is not None else 1e9)))
        mtype = "name"
    else:
        return {"match_type": "none", "needs_review": True, "n_in_radius": len(near)}
    s, d, c = best
    in_r = [x for x in near if x[1] <= (NAME_R if mtype != "distance" else DIST_R[conf])]
    clean = mtype == "name+distance" and s >= 0.8 and d <= 150 and conf in DIST_R and len(in_r) <= 2
    return {
        "match_type": mtype, "candidate_id": c["candidate_id"], "osm_way_id": c["osm_way_id"],
        "way_name": c.get("name", ""), "structure": c["structure"], "dist_m": None if d is None else round(d),
        "name_score": round(s, 2), "n_in_radius": len(in_r), "needs_review": not clean,
    }


OUT_COLS = [
    "hotspot_row", "name", "list_kind", "lat", "lon", "geocode_confidence", "match_type", "candidate_id",
    "osm_way_id", "way_name", "structure", "dist_m", "name_score", "n_in_radius", "needs_review",
]


def main(hotspots_csv, candidates_geojson, out_csv):
    """python -m floodroute.inventory.match HOTSPOTS.csv CANDIDATES.geojson OUT.csv"""
    import csv
    import json

    with open(candidates_geojson, encoding="utf-8") as fh:
        cands = [
            {**f["properties"], "pts": f["geometry"]["coordinates"]}
            for f in json.load(fh)["features"]
        ]
    with open(hotspots_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, OUT_COLS, restval="")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            m = match(r, cands)
            m.update(hotspot_row=i, name=r["name"], list_kind=r["list_kind"], lat=r["lat"], lon=r["lon"],
                     geocode_confidence=r["geocode_confidence"])
            w.writerow(m)


if __name__ == "__main__":
    import sys

    main(*sys.argv[1:4])
